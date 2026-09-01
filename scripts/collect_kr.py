#!/usr/bin/env python3
"""Collect adjusted KRX prices and produce the static KR screener payload."""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from pykrx import stock

from rs_engine import average, market_cap_size, percentile_scores, range_signals, trend_template_score, weighted_return


SEOUL = ZoneInfo("Asia/Seoul")
BENCHMARKS = {"KOSPI": "069500", "KOSDAQ": "229200"}
MIN_CLOSE = 5_000
MAX_WORKERS = 4
LOGGER = logging.getLogger("collect_kr")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/kr.json")
    parser.add_argument("--cache", default=".cache/kr_history.pkl")
    parser.add_argument("--lookback-days", type=int, default=520)
    return parser.parse_args()


def first_column(frame: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    raise KeyError(f"missing columns {names}; received {list(frame.columns)}")


def latest_market_snapshot(now: datetime) -> tuple[str, pd.DataFrame]:
    for offset in range(0, 12):
        date = (now - timedelta(days=offset)).strftime("%Y%m%d")
        frame = stock.get_market_cap_by_ticker(date, market="ALL")
        if frame is not None and not frame.empty:
            return date, frame
    raise RuntimeError("최근 KRX 거래일을 찾지 못했습니다.")


def load_cache(path: Path) -> dict[str, pd.DataFrame]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            cached = pickle.load(handle)  # trusted workflow-owned cache only
        return cached if isinstance(cached, dict) else {}
    except Exception as error:
        LOGGER.warning("캐시를 읽지 못해 전체 수집을 다시 시작합니다: %s", error)
        return {}


def save_cache(path: Path, histories: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(histories, handle, protocol=pickle.HIGHEST_PROTOCOL)


def fetch_history(ticker: str, start: str, end: str, cached: pd.DataFrame | None) -> tuple[str, pd.DataFrame]:
    try:
        fetch_start = start
        if cached is not None and not cached.empty:
            last = pd.Timestamp(cached.index.max())
            if last.strftime("%Y%m%d") >= end:
                return ticker, cached
            fetch_start = (last + pd.Timedelta(days=1)).strftime("%Y%m%d")
        for attempt in range(3):
            try:
                fresh = stock.get_market_ohlcv_by_date(fetch_start, end, ticker, adjusted=True)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        if fresh is None or fresh.empty:
            return ticker, cached if cached is not None else pd.DataFrame()
        combined = pd.concat([cached, fresh]) if cached is not None and not cached.empty else fresh
        combined = combined[~combined.index.duplicated(keep="last")].sort_index().tail(320)
        return ticker, combined
    except Exception as error:
        LOGGER.warning("%s 수집 실패: %s", ticker, error)
        return ticker, cached if cached is not None else pd.DataFrame()


def ticker_names(date: str, tickers: list[str]) -> dict[str, str]:
    try:
        series = stock.get_market_ticker_and_name(date, market="ALL")
        if series is not None and len(series):
            return {str(key): str(value) for key, value in series.items()}
    except Exception:
        pass
    return {ticker: stock.get_market_ticker_name(ticker) or ticker for ticker in tickers}


def price_columns(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    close = first_column(frame, "종가", "Close").astype(float)
    high = first_column(frame, "고가", "High").astype(float)
    low = first_column(frame, "저가", "Low").astype(float)
    volume = first_column(frame, "거래량", "Volume").astype(float)
    return close, high, low, volume


def build_metrics(ticker: str, frame: pd.DataFrame, market: str, benchmark: pd.Series) -> dict[str, Any] | None:
    if frame is None or len(frame) < 253:
        return None
    close, high, low, volume = price_columns(frame)
    closes = close.tolist()
    raw = weighted_return(closes)
    raw_previous = weighted_return(closes[:-1])
    if raw is None or raw_previous is None:
        return None

    ma50 = average(closes, 50)
    ma150 = average(closes, 150)
    ma200 = average(closes, 200)
    ma200_prior = average(closes[:-20], 200)
    if None in (ma50, ma150, ma200, ma200_prior):
        return None

    current = closes[-1]
    low52 = min(closes[-252:])
    high52 = max(high.tolist()[-252:])
    ma_aligned = current > ma50 > ma150 > ma200
    trend_template = bool(
        ma_aligned
        and ma200 > ma200_prior
        and current >= low52 * 1.30
        and current >= high52 * 0.75
    )

    recent_range = (max(closes[-10:]) / min(closes[-10:]) - 1) if min(closes[-10:]) > 0 else 99
    prior_slice = closes[-40:-10]
    prior_range = (max(prior_slice) / min(prior_slice) - 1) if min(prior_slice) > 0 else 0
    vcp = bool(trend_template and prior_range > 0 and recent_range <= prior_range * 0.70 and average(volume.tolist(), 10) < average(volume.tolist(), 50) * 0.80)

    aligned = pd.concat([close.rename("stock"), benchmark.rename("benchmark")], axis=1).dropna().tail(252)
    if aligned.empty:
        rs_line_value = 0.0
        rs_line_new = False
    else:
        ratios = aligned["stock"] / aligned["benchmark"]
        normalized = ratios / ratios.iloc[0] * 100
        rs_line_value = float(normalized.iloc[-1])
        rs_line_new = bool(ratios.iloc[-1] >= ratios.max() * 0.97)

    return {
        "ticker": ticker,
        "market": market,
        "close": int(round(current)),
        "changePct": round((current / closes[-2] - 1) * 100, 2),
        "ma50": int(round(ma50)),
        "ma150": int(round(ma150)),
        "ma200": int(round(ma200)),
        "_ma200Prior": ma200_prior,
        "_low52": low52,
        "_high52": high52,
        "rsRaw": raw,
        "rsRawPrevious": raw_previous,
        "rsLineValue": round(rs_line_value, 2),
        "rsLineNew": rs_line_new,
        "newHigh52": bool(current >= high52 * 0.97),
        "trendTemplate": trend_template,
        "vcp": vcp,
        "signals": range_signals(closes, high.tolist(), low.tolist(), volume.tolist()),
        "maAligned": ma_aligned,
    }


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    now = datetime.now(SEOUL)
    date, cap_frame = latest_market_snapshot(now)
    close_snapshot = first_column(cap_frame, "종가", "Close").astype(float)
    cap_snapshot = first_column(cap_frame, "시가총액", "Market Cap").astype(float)
    eligible = [str(ticker) for ticker in cap_frame.index if close_snapshot.loc[ticker] >= MIN_CLOSE]
    names = ticker_names(date, eligible)
    kospi = set(stock.get_market_ticker_list(date, market="KOSPI"))
    kosdaq = set(stock.get_market_ticker_list(date, market="KOSDAQ"))
    markets = {ticker: "KOSPI" if ticker in kospi else "KOSDAQ" for ticker in eligible if ticker in kospi or ticker in kosdaq}
    eligible = [ticker for ticker in eligible if ticker in markets]

    cache_path = Path(args.cache)
    histories = load_cache(cache_path)
    start = (datetime.strptime(date, "%Y%m%d") - timedelta(days=args.lookback_days)).strftime("%Y%m%d")
    LOGGER.info("%s개 종목 수집 시작 (%s~%s)", len(eligible), start, date)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_history, ticker, start, date, histories.get(ticker)): ticker for ticker in eligible}
        for index, future in enumerate(as_completed(futures), start=1):
            ticker, frame = future.result()
            if frame is not None and not frame.empty:
                histories[ticker] = frame
            if index % 100 == 0:
                LOGGER.info("%s/%s 완료", index, len(futures))
    histories = {ticker: frame for ticker, frame in histories.items() if ticker in markets}
    save_cache(cache_path, histories)

    benchmark_series: dict[str, pd.Series] = {}
    for market, ticker in BENCHMARKS.items():
        _, frame = fetch_history(ticker, start, date, histories.get(ticker))
        if frame is None or frame.empty:
            raise RuntimeError(f"{market} 벤치마크 데이터를 수집하지 못했습니다.")
        benchmark_series[market] = price_columns(frame)[0]
        histories[ticker] = frame
    save_cache(cache_path, histories)

    metrics = {}
    for ticker in eligible:
        metric = build_metrics(ticker, histories.get(ticker, pd.DataFrame()), markets[ticker], benchmark_series[markets[ticker]])
        if metric:
            metrics[ticker] = metric

    current_scores = percentile_scores({ticker: item["rsRaw"] for ticker, item in metrics.items()})
    previous_scores = percentile_scores({ticker: item["rsRawPrevious"] for ticker, item in metrics.items()})
    items = []
    for ticker, item in metrics.items():
        rs = current_scores[ticker]
        market_cap = int(cap_snapshot.get(ticker, 0))
        item.update({
            "name": names.get(ticker, ticker),
            "theme": "",
            "marketCap": market_cap,
            "size": market_cap_size(market_cap),
            "rs": rs,
            "newEntry": rs >= 70 and previous_scores.get(ticker, 0) < 70,
            "trendScore": trend_template_score(
                item["close"], item["ma50"], item["ma150"], item["ma200"],
                item["_ma200Prior"], item["_low52"], item["_high52"], rs,
            ),
            "pocketPivot": "pocketPivot" in item["signals"],
        })
        item.pop("rsRaw", None)
        item.pop("rsRawPrevious", None)
        item.pop("_ma200Prior", None)
        item.pop("_low52", None)
        item.pop("_high52", None)
        items.append(item)

    items.sort(key=lambda row: (-row["rs"], -row["marketCap"], row["ticker"]))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "region": "kr",
        "updatedAt": f"{datetime.strptime(date, '%Y%m%d').strftime('%Y-%m-%d')} {now.strftime('%H:%M')} KST",
        "source": "KRX·Naver adjusted OHLCV via pykrx",
        "universeCount": len(metrics),
        "publishedCount": len(items),
        "items": items,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    LOGGER.info("%s개 결과를 %s에 저장했습니다.", len(items), output)


if __name__ == "__main__":
    main()

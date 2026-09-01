"""OpenDART financial collection and SEPA/CANSLIM scoring."""

from __future__ import annotations

import io
import logging
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any
from xml.etree import ElementTree


DART_BASE = "https://opendart.fss.or.kr/api"
REPORT_Q1 = "11013"
REPORT_HALF = "11012"
REPORT_Q3 = "11014"
REPORT_ANNUAL = "11011"
LOGGER = logging.getLogger("dart_engine")


def parse_amount(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "null"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        number = float(text)
        return -number if negative else number
    except ValueError:
        return None


def growth_percent(current: float | None, previous: float | None) -> float | None:
    """Return comparable YoY growth; loss-base comparisons stay unavailable."""
    if current is None or previous is None or previous <= 0:
        return None
    return round((current / previous - 1) * 100, 2)


def latest_period(now: datetime) -> tuple[int, str]:
    """Choose the latest report normally filed by the current date."""
    marker = (now.month, now.day)
    if marker >= (11, 15):
        return now.year, REPORT_Q3
    if marker >= (8, 15):
        return now.year, REPORT_HALF
    if marker >= (5, 16):
        return now.year, REPORT_Q1
    return now.year - 1, REPORT_ANNUAL


def download_corp_codes(api_key: str, timeout: int = 40) -> tuple[dict[str, str], dict[str, str]]:
    import requests

    response = requests.get(f"{DART_BASE}/corpCode.xml", params={"crtfc_key": api_key}, timeout=timeout)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        xml = archive.read(archive.namelist()[0])
    root = ElementTree.fromstring(xml)
    stock_map: dict[str, str] = {}
    name_map: dict[str, str] = {}
    for node in root.findall("list"):
        corp_code = (node.findtext("corp_code") or "").strip()
        stock_code = (node.findtext("stock_code") or "").strip()
        corp_name = normalize_company_name(node.findtext("corp_name") or "")
        if corp_code and stock_code:
            stock_map[stock_code] = corp_code
        if corp_code and corp_name:
            name_map[corp_name] = corp_code
    return stock_map, name_map


def normalize_company_name(name: str) -> str:
    text = re.sub(r"\s|\(주\)|주식회사", "", str(name))
    text = re.sub(r"(\d*우B?|우)$", "", text)
    return text.upper()


def request_statement(api_key: str, corp_code: str, year: int, report_code: str, timeout: int = 30) -> list[dict[str, Any]]:
    import requests

    params = {"crtfc_key": api_key, "corp_code": corp_code, "bsns_year": str(year), "reprt_code": report_code}
    for fs_div in ("CFS", "OFS"):
        params["fs_div"] = fs_div
        for attempt in range(2):
            try:
                response = requests.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=params, timeout=timeout)
                response.raise_for_status()
                payload = response.json()
                status = payload.get("status")
                if status == "000":
                    return payload.get("list") or []
                if status == "013":
                    break
                if status == "020":
                    raise RuntimeError("OpenDART 일일 요청 한도를 초과했습니다.")
                raise RuntimeError(f"OpenDART 오류 {status}: {payload.get('message', '')}")
            except (requests.RequestException, ValueError):
                if attempt:
                    raise
                time.sleep(1.0)
    return []


def _account_score(row: dict[str, Any], ids: tuple[str, ...], names: tuple[str, ...]) -> int:
    account_id = str(row.get("account_id", "")).lower()
    account_nm = re.sub(r"\s", "", str(row.get("account_nm", ""))).lower()
    for index, candidate in enumerate(ids):
        if candidate.lower() in account_id:
            return 100 - index
    for index, candidate in enumerate(names):
        if candidate.lower() in account_nm:
            return 50 - index
    return -1


def find_account(rows: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    definitions = {
        "eps": (
            ("BasicEarningsLossPerShare", "EarningsPerShare"),
            ("기본주당이익", "기본주당순이익", "주당이익"),
            {"IS", "CIS"},
        ),
        "revenue": (
            ("Revenue", "OperatingRevenue"),
            ("수익(매출액)", "매출액", "영업수익"),
            {"IS", "CIS"},
        ),
        "profit": (
            ("ProfitLossAttributableToOwnersOfParent", "ProfitLoss"),
            ("지배기업소유주지분순이익", "당기순이익", "반기순이익", "분기순이익"),
            {"IS", "CIS"},
        ),
        "equity": (
            ("EquityAttributableToOwnersOfParent", "Equity"),
            ("지배기업소유주지분", "자본총계"),
            {"BS"},
        ),
    }
    ids, names, statements = definitions[kind]
    candidates = [row for row in rows if row.get("sj_div") in statements]
    ranked = sorted(candidates, key=lambda row: _account_score(row, ids, names), reverse=True)
    return ranked[0] if ranked and _account_score(ranked[0], ids, names) >= 0 else None


def calculate_financial_metrics(current_rows: list[dict[str, Any]], annual_rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_eps = find_account(current_rows, "eps")
    current_sales = find_account(current_rows, "revenue")
    annual_eps = find_account(annual_rows, "eps")
    annual_profit = find_account(annual_rows, "profit")
    annual_equity = find_account(annual_rows, "equity")

    if current_eps:
        result["quarterEpsGrowth"] = growth_percent(parse_amount(current_eps.get("thstrm_amount")), parse_amount(current_eps.get("frmtrm_q_amount")))
    if current_sales:
        result["quarterSalesGrowth"] = growth_percent(parse_amount(current_sales.get("thstrm_amount")), parse_amount(current_sales.get("frmtrm_q_amount")))
    if annual_eps:
        series = [parse_amount(annual_eps.get(key)) for key in ("thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount")]
        result["annualEpsSeries"] = series
        if all(value is not None and value > 0 for value in series):
            growth_latest = growth_percent(series[0], series[1])
            growth_prior = growth_percent(series[1], series[2])
            result["annualEpsGrowth"] = round((growth_latest + growth_prior) / 2, 2)
            result["annualEpsLatestGrowth"] = growth_latest
    if annual_profit and annual_equity:
        profit = parse_amount(annual_profit.get("thstrm_amount"))
        equity_now = parse_amount(annual_equity.get("thstrm_amount"))
        equity_prior = parse_amount(annual_equity.get("frmtrm_amount"))
        average_equity = (equity_now + equity_prior) / 2 if equity_now and equity_prior else None
        if profit is not None and average_equity and average_equity > 0:
            result["roe"] = round(profit / average_equity * 100, 2)
    return {key: value for key, value in result.items() if value is not None}


def collect_financials(api_key: str, items: list[dict[str, Any]], now: datetime, workers: int = 4) -> dict[str, dict[str, Any]]:
    stock_map, name_map = download_corp_codes(api_key)
    ticker_to_corp = {
        item["ticker"]: stock_map.get(item["ticker"]) or name_map.get(normalize_company_name(item.get("name", "")))
        for item in items
    }
    corp_codes = sorted({code for code in ticker_to_corp.values() if code})
    current_year, current_report = latest_period(now)
    annual_year = now.year - 1

    def collect_one(corp_code: str) -> tuple[str, dict[str, Any]]:
        current = request_statement(api_key, corp_code, current_year, current_report)
        annual = current if current_report == REPORT_ANNUAL and current_year == annual_year else request_statement(api_key, corp_code, annual_year, REPORT_ANNUAL)
        return corp_code, calculate_financial_metrics(current, annual)

    by_corp: dict[str, dict[str, Any]] = {}
    failures: list[tuple[str, Exception]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(collect_one, code): code for code in corp_codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                corp_code, metrics = future.result()
                if metrics:
                    by_corp[corp_code] = metrics
            except Exception as error:
                failures.append((code, error))
                LOGGER.warning("OpenDART %s 수집 실패: %s", code, error)

    fatal = next(
        (error for _, error in failures if isinstance(error, RuntimeError) and "OpenDART 오류 013" not in str(error)),
        None,
    )
    if fatal:
        raise RuntimeError(f"OpenDART 재무 수집을 완료하지 못했습니다: {fatal}") from fatal
    if corp_codes and not by_corp:
        raise RuntimeError("OpenDART에서 유효한 재무 데이터를 한 종목도 받지 못했습니다.")
    return {ticker: by_corp[corp] for ticker, corp in ticker_to_corp.items() if corp in by_corp}


def score_item(item: dict[str, Any], financial: dict[str, Any] | None, market_uptrend: bool) -> None:
    financial = financial or {}
    item.update({key: value for key, value in financial.items() if key != "annualEpsSeries"})
    q_eps = financial.get("quarterEpsGrowth")
    q_sales = financial.get("quarterSalesGrowth")
    annual_growth = financial.get("annualEpsGrowth")
    annual_latest = financial.get("annualEpsLatestGrowth")
    annual_series = financial.get("annualEpsSeries") or []

    c_score = 2 if q_eps is not None and q_eps >= 25 and q_sales is not None and q_sales >= 25 else 1 if q_eps is not None and q_eps >= 25 else 0
    annual_increasing = len(annual_series) == 3 and all(value is not None and value > 0 for value in annual_series) and annual_series[0] > annual_series[1] > annual_series[2]
    if annual_increasing and annual_growth is not None and annual_growth >= 25 and annual_latest is not None and annual_latest >= 25:
        a_score = 2
    elif len(annual_series) == 3 and all(value is not None and value > 0 for value in annual_series) and annual_growth is not None and annual_growth >= 15:
        a_score = 1
    else:
        a_score = 0
    high_pct = float(item.get("high52Pct") or 0)
    n_score = 2 if high_pct >= 97 else 1 if high_pct >= 85 else 0
    s_score = 1 if item.get("changePct", 0) > 0 and item.get("volumeRatio50", 0) >= 1.5 else 0
    l_score = 2 if item.get("rs", 0) >= 80 else 1 if item.get("rs", 0) >= 60 else 0
    i_score = 1 if item.get("institutionalAccumulation") else 0
    m_score = 1 if market_uptrend else 0
    scores = {"C": c_score, "A": a_score, "N": n_score, "S": s_score, "L": l_score, "I": i_score, "M": m_score}
    item["canSlim"] = scores
    item["canSlimScore"] = sum(scores.values())
    item["financialDataAvailable"] = bool(financial)

    if q_eps is None or q_sales is None or annual_growth is None:
        item["sepaGrade"] = "-"
    elif item.get("trendScore") == 8 and q_eps >= 25 and q_sales >= 10 and annual_growth >= 25:
        item["sepaGrade"] = "S"
    elif item.get("trendScore", 0) >= 7 and q_eps >= 25 and q_sales >= 10:
        item["sepaGrade"] = "A"
    elif item.get("trendScore", 0) >= 6 and q_eps >= 25:
        item["sepaGrade"] = "B"
    else:
        item["sepaGrade"] = "C"
    item["epsExplosion"] = q_eps is not None and q_eps >= 100

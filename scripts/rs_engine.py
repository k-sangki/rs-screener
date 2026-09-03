"""Dependency-light calculation helpers used by the KRX collector."""

from __future__ import annotations

from bisect import bisect_left
from math import floor
from statistics import fmean
from typing import Iterable, Mapping, Sequence


RETURN_WINDOWS = ((63, 0.40), (126, 0.20), (189, 0.20), (252, 0.20))


def weighted_return(closes: Sequence[float]) -> float | None:
    """Return the 63/126/189/252-day weighted price performance."""
    if len(closes) < 253 or closes[-1] <= 0:
        return None
    current = float(closes[-1])
    score = 0.0
    for window, weight in RETURN_WINDOWS:
        base = float(closes[-(window + 1)])
        if base <= 0:
            return None
        score += ((current / base) - 1.0) * weight
    return score


def percentile_scores(raw_scores: Mapping[str, float]) -> dict[str, int]:
    """Map raw values to a 1–99 rank scale; ties receive the same score."""
    if not raw_scores:
        return {}
    ordered = sorted(raw_scores.values())
    count = len(ordered)
    if count == 1:
        return {ticker: 99 for ticker in raw_scores}
    return {
        ticker: min(99, max(1, 1 + floor(98 * bisect_left(ordered, value) / (count - 1))))
        for ticker, value in raw_scores.items()
    }


def grouped_percentile_scores(
    raw_scores: Mapping[str, float], groups: Mapping[str, str]
) -> dict[str, int]:
    """Rank each ticker only against other tickers in the same market group."""
    grouped: dict[str, dict[str, float]] = {}
    for ticker, value in raw_scores.items():
        grouped.setdefault(groups[ticker], {})[ticker] = value
    result: dict[str, int] = {}
    for scores in grouped.values():
        result.update(percentile_scores(scores))
    return result


def average(values: Iterable[float], window: int) -> float | None:
    data = list(values)
    if len(data) < window:
        return None
    return fmean(float(value) for value in data[-window:])


def market_cap_size(value: int | float) -> str:
    value = float(value)
    if value >= 10_000_000_000_000:
        return "대형"
    if value >= 1_000_000_000_000:
        return "중대형"
    if value >= 300_000_000_000:
        return "중형"
    return "소형"


def has_recent_pocket_pivot(closes: Sequence[float], volumes: Sequence[float], days: int = 7) -> bool:
    """Heuristic: an up day whose volume exceeds every prior down-volume day in 10 sessions."""
    if len(closes) < 18 or len(volumes) != len(closes):
        return False
    start = max(1, len(closes) - days)
    for index in range(start, len(closes)):
        if closes[index] <= closes[index - 1]:
            continue
        prior_down_volumes = [
            volumes[j]
            for j in range(max(1, index - 10), index)
            if closes[j] < closes[j - 1]
        ]
        if prior_down_volumes and volumes[index] > max(prior_down_volumes):
            return True
    return False


def trend_template_score(
    current: float,
    ma50: float,
    ma150: float,
    ma200: float,
    ma200_prior: float,
    low52: float,
    high52: float,
    rs: int,
) -> int:
    """Return an auditable 0–8 Minervini-style trend score."""
    checks = (
        current > ma150,
        current > ma200,
        ma150 > ma200,
        ma200 > ma200_prior,
        ma50 > ma150 and ma50 > ma200,
        current > ma50,
        current >= low52 * 1.30 and current >= high52 * 0.75,
        rs >= 70,
    )
    return sum(checks)


def range_signals(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
) -> list[str]:
    """Detect price/volume signals that can be calculated from daily OHLCV alone."""
    if len(closes) < 53 or not (len(closes) == len(highs) == len(lows) == len(volumes)):
        return []
    signals: list[str] = []
    current = float(closes[-1])
    if has_recent_pocket_pivot(closes, volumes):
        signals.append("pocketPivot")
    if current >= max(highs[-252:-1] or highs[:-1]):
        signals.append("high52Breakout")
    if current >= max(highs[-51:-1]):
        signals.append("high50Breakout")
    if current >= max(highs[-21:-1]):
        signals.append("high20Breakout")
    avg50_volume = average(volumes[:-1], 50)
    if avg50_volume and volumes[-1] <= avg50_volume * 0.50:
        signals.append("dryUp")
    ranges = [float(high) - float(low) for high, low in zip(highs, lows)]
    inside_day = highs[-1] < highs[-2] and lows[-1] > lows[-2]
    nr4 = ranges[-1] <= min(ranges[-4:])
    nr7 = ranges[-1] <= min(ranges[-7:])
    if nr7:
        signals.append("nr7")
    if inside_day and nr4:
        signals.append("idNr4")
    if inside_day and nr7:
        signals.append("idNr7")
    return signals

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
    """Map raw values to 0–99 percentile scores; ties receive the same score."""
    if not raw_scores:
        return {}
    ordered = sorted(raw_scores.values())
    count = len(ordered)
    return {
        ticker: min(99, max(0, floor(100 * bisect_left(ordered, value) / count)))
        for ticker, value in raw_scores.items()
    }


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

"""Personal reference ranges over the preceding 28 local days (target day excluded).

These are product heuristics, not clinical norms. Thresholds are versioned here and
documented in docs/analysis-rules.md; change BASELINE_VERSION when any value changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

BASELINE_VERSION = "baseline-1.1"  # 1.1: baselines never span a device change
WINDOW_DAYS = 28
MIN_VALID = 14

# concern: direction that may deserve attention. abs/pct: meaningful-change threshold vs the median.
THRESHOLDS: dict[str, dict] = {
    "resting_hr": {"concern": "up", "abs": 5.0, "unit": "bpm"},
    "hrv_overnight_avg": {"concern": "down", "pct": 15.0, "unit": "ms"},
    "sleep_duration": {"concern": "down", "abs": 3600.0, "unit": "s"},
}
SUSTAINED_DAYS = 3


def quantile(sorted_vals: list[float], q: float) -> float:
    """Linear interpolation between closest ranks (same as numpy's default)."""
    if not sorted_vals:
        raise ValueError("empty")
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


@dataclass
class Baseline:
    n: int
    window_start: str
    window_end: str
    median: float | None
    q1: float | None
    q3: float | None
    sufficient: bool
    dates: list[str]


def compute_baseline(series: dict[str, float], target: date, window: int = WINDOW_DAYS, min_valid: int = MIN_VALID,
                     era_start: date | None = None) -> Baseline:
    """series: local_date -> measured value (only valid, comparable measurements).
    era_start: first day recorded by the current device; earlier days are not comparable and are excluded."""
    start, end = target - timedelta(days=window), target - timedelta(days=1)
    if era_start is not None and era_start > start:
        start = era_start
    pts = sorted((d, v) for d, v in series.items() if start.isoformat() <= d <= end.isoformat())
    vals = sorted(v for _, v in pts)
    ok = len(vals) >= min_valid
    return Baseline(
        n=len(vals), window_start=start.isoformat(), window_end=end.isoformat(),
        median=median(vals) if ok else None, q1=quantile(vals, 0.25) if ok else None,
        q3=quantile(vals, 0.75) if ok else None, sufficient=ok, dates=[d for d, _ in pts],
    )


@dataclass
class Deviation:
    delta_abs: float
    delta_pct: float | None
    beyond_threshold: bool      # in the direction of concern
    direction: str              # up | down | none


def deviation(metric: str, value: float, b: Baseline) -> Deviation:
    assert b.sufficient and b.median is not None
    delta = value - b.median
    pct = (100.0 * delta / b.median) if b.median not in (0, 0.0) else None
    th = THRESHOLDS[metric]
    size = abs(pct) if "pct" in th and pct is not None else abs(delta)
    limit = th.get("pct", th.get("abs"))
    direction = "up" if delta > 0 else "down" if delta < 0 else "none"
    return Deviation(delta, pct, direction == th["concern"] and size >= limit, direction)


def sustained(metric: str, series: dict[str, float], target: date, days: int = SUSTAINED_DAYS,
              era_start: date | None = None) -> bool:
    """True when each of the last `days` days (including target) is beyond threshold against its own baseline."""
    for i in range(days):
        d = target - timedelta(days=i)
        v = series.get(d.isoformat())
        if v is None:
            return False
        b = compute_baseline(series, d, era_start=era_start)
        if not b.sufficient or not deviation(metric, v, b).beyond_threshold:
            return False
    return True

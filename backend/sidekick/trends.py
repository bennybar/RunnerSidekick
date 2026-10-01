"""Trend series for the Trends screen: daily values with explicit gaps, personal-range bands, device eras,
weekly running volume and pace-at-HR progress. Descriptive only; no conclusions beyond the stated comparison."""

from __future__ import annotations

import json
from datetime import date, timedelta
from statistics import median

from . import reports as rp
from .analytics import baseline as bl
from .analytics import insights as ins

TRENDS_VERSION = "trends-1.0"
DAILY_METRICS = {
    "sleep_duration": {"title": "Sleep", "unit": "s"},
    "resting_hr": {"title": "Resting heart rate", "unit": "bpm"},
    "hrv_overnight_avg": {"title": "Overnight HRV", "unit": "ms"},
}


def era_starts(conn, source: str, start: date, end: date) -> list[str]:
    """Device-change dates within [start, end] (inferred from activity device IDs)."""
    out = []
    d = start
    prev = rp.device_era_start(conn, source, start)
    while d <= end:
        e = rp.device_era_start(conn, source, d)
        if e != prev and e is not None and start <= e <= end:
            out.append(e.isoformat())
        prev = e
        d += timedelta(days=1)
    return sorted(set(out))


def period_summary(metric: str, values: dict[str, float], start: date, end: date, days: int) -> dict:
    """Median of this period vs the previous period of the same length; 'meaningful' uses the baseline thresholds."""
    cur = [v for k, v in values.items() if start.isoformat() <= k <= end.isoformat()]
    p_end = start - timedelta(days=1)
    p_start = p_end - timedelta(days=days - 1)
    prev = [v for k, v in values.items() if p_start.isoformat() <= k <= p_end.isoformat()]
    min_n = max(3, days // 3)
    s = {"n": len(cur), "previous_n": len(prev), "median": median(cur) if cur else None,
         "previous_median": median(prev) if prev else None, "previous_window": [p_start.isoformat(), p_end.isoformat()],
         "change": None, "meaningful": False, "enough": len(cur) >= min_n and len(prev) >= min_n}
    if s["enough"]:
        s["change"] = s["median"] - s["previous_median"]
        th = bl.THRESHOLDS[metric]
        if "pct" in th and s["previous_median"]:
            s["meaningful"] = abs(100 * s["change"] / s["previous_median"]) >= th["pct"]
        elif "abs" in th:
            s["meaningful"] = abs(s["change"]) >= th["abs"]
    return s


def build_trends(conn, source: str, today: date, days: int, synthetic: bool) -> dict:
    start = today - timedelta(days=days - 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    eras = era_starts(conn, source, start - timedelta(days=days), today)
    metrics = []
    for m, meta in DAILY_METRICS.items():
        method = None
        if m == "hrv_overnight_avg":  # comparable HRV only: the latest method in use
            r = conn.execute("SELECT method FROM daily_observation WHERE source=? AND metric=? AND state='measured' "
                             "ORDER BY local_date DESC LIMIT 1", (source, m)).fetchone()
            method = r["method"] if r else None
        values = rp.series(conn, source, m, today.isoformat(), method)
        points, band = [], []
        for ds in dates:
            d = date.fromisoformat(ds)
            points.append({"date": ds, "value": values.get(ds)})  # None = no measurement that day (never zero)
            b = bl.compute_baseline(values, d, era_start=rp.device_era_start(conn, source, d))
            band.append({"date": ds, "q1": b.q1, "median": b.median, "q3": b.q3} if b.sufficient else {"date": ds})
        metrics.append({
            "metric": m, "title": meta["title"], "unit": meta["unit"], "method": method, "points": points, "band": band,
            "summary": period_summary(m, values, start, today, days),
            "measured_days": sum(1 for p in points if p["value"] is not None),
        })
    # Weekly running volume (calendar weeks overlapping the range)
    acts = rp.activities(conn, source, (start - timedelta(days=start.weekday())).isoformat(), today.isoformat())
    weeks = []
    w = start - timedelta(days=start.weekday())
    while w <= today:
        sel = [a for a in acts if w.isoformat() <= a["local_date"] <= (w + timedelta(days=6)).isoformat()]
        weeks.append({"week_start": w.isoformat(), "runs": len(sel), "distance_m": round(sum(a["distance_m"] or 0 for a in sel), 1),
                      "moving_s": round(sum(a["moving_s"] or 0 for a in sel)), "partial": w + timedelta(days=6) > today,
                      "activity_ids": [a["source_id"] for a in sel]})
        w += timedelta(days=7)
    # Pace at the same heart rate (reuses the insight's per-device computation over the longer history)
    insight = rp_efficiency(conn, source, today)
    progress = {"band_bpm": insight["effect"].get("band_bpm"), "verdict": insight["verdict"], "headline": insight["headline"],
                "series": [{"device": e["device"], "points": [p for p in e["points"] if p["date"] >= start.isoformat()]}
                           for e in insight["effect"].get("eras", [])]}
    return {"type": "trends", "days": days, "start": start.isoformat(), "end": today.isoformat(), "synthetic": synthetic,
            "device_changes": [e for e in eras if e >= start.isoformat()], "metrics": metrics, "weekly_running": weeks,
            "pace_at_hr": progress, "algorithm_version": TRENDS_VERSION}


def rp_efficiency(conn, source: str, today: date) -> dict:
    from datetime import datetime as _dt

    runs = []
    for a in rp.activities(conn, source, (today - timedelta(days=120)).isoformat(), today.isoformat()):
        local = _dt.fromisoformat(a["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=a["utc_offset_s"] or 0)
        runs.append(ins.RunData(a["source_id"], a["local_date"], local.replace(tzinfo=None), a.get("device_id"), a["distance_m"],
                                a["moving_s"], json.loads(a["garmin_metrics_json"]).get("activityTrainingLoad"),
                                rp.samples_for(conn, a["id"]), [], "steady"))
    out = ins.efficiency_trend(runs)
    # points carry source ids so the app can open the run
    for e in out["effect"].get("eras", []):
        ids = {p["date"]: None for p in e["points"]}
        for r in runs:
            if r.device == e["device"] and r.local_date in ids:
                ids[r.local_date] = r.source_id
        for p in e["points"]:
            p["source_id"] = ids.get(p["date"])
    return out

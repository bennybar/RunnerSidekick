"""Key numbers for the last four weeks against the four weeks before: volume, frequency, pace, heart rate, longest
run, climbing and the share of hard running. Plain arithmetic over synced runs."""

from __future__ import annotations

from datetime import date, timedelta

from . import reports as rp
from .analytics import running as rn


def block(conn, source: str, start: date, end: date, zones: dict | None) -> dict:
    acts = rp.activities(conn, source, start.isoformat(), end.isoformat())
    dist = sum(a["distance_m"] or 0 for a in acts)
    moving = sum(a["moving_s"] or 0 for a in acts)
    hrs = [(a["avg_hr"], a["moving_s"]) for a in acts if a.get("avg_hr") and a.get("moving_s")]
    both = [a for a in acts if a.get("distance_m") and a.get("moving_s")]  # pace only where both were measured
    pace_d, pace_s = sum(a["distance_m"] for a in both), sum(a["moving_s"] for a in both)
    hard = None
    if zones:
        from .focus import zone_shares
        sh = [(z["hard"], a["moving_s"]) for a in acts if (z := zone_shares(conn, a, zones["floors"])) and a.get("moving_s")]
        if sh:
            hard = sum(h * m for h, m in sh) / sum(m for _, m in sh)
    return {"runs": len(acts), "km_per_week": dist / 4000, "time_per_week_s": moving / 4,
            "pace_s_per_km": rn.moving_pace(pace_d, pace_s) if pace_d else None,
            "avg_hr": sum(h * m for h, m in hrs) / sum(m for _, m in hrs) if hrs else None,
            "longest_km": max((a["distance_m"] or 0 for a in acts), default=0) / 1000,
            "climb_per_week_m": sum(a["elevation_gain_m"] or 0 for a in acts) / 4, "hard_share": hard}


def four_weeks(conn, source: str, today: date) -> dict:
    zones = rp.hr_zones(conn)
    cur = block(conn, source, today - timedelta(days=27), today, zones)
    prev = block(conn, source, today - timedelta(days=55), today - timedelta(days=28), zones)

    def item(key, label, fmt, higher_is="neutral"):
        v, p = cur[key], prev[key]
        return {"id": key, "label": label, "value": fmt(v) if v is not None else "—",
                "change": (None if v is None or p in (None, 0) else round(100 * (v - p) / p)), "higher_is": higher_is}

    pace = lambda s: rp.fmt_pace(s)  # noqa: E731
    return {"window_days": 28, "items": [
        item("km_per_week", "Distance / week", lambda v: f"{v:.1f} km", "neutral"),
        item("runs", "Runs", lambda v: f"{v}", "neutral"),
        item("time_per_week_s", "Time / week", lambda v: rp.fmt_duration(v), "neutral"),
        item("pace_s_per_km", "Average pace", pace, "lower"),
        item("avg_hr", "Average heart rate", lambda v: f"{round(v)} bpm", "lower"),
        item("longest_km", "Longest run", lambda v: f"{v:.1f} km", "neutral"),
        item("climb_per_week_m", "Climb / week", lambda v: f"{round(v)} m", "neutral"),
        item("hard_share", "Time in zones 4–5", lambda v: f"{round(100 * v)}%", "lower"),
    ], "basis": "Last 28 days against the 28 days before"}

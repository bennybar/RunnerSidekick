"""Training-strain warning: is strain building up? Five signals, each from data the app already has, over the last
7 days against the 4 weeks before. No single one is enough (one signal is noise, as everywhere in the app): the warning
needs two together. It's a nudge toward an easier day or two, not a prediction about the body.

- Load jump: acute load over chronic (readiness's fading averages) of 1.3 or more.
- Monotony: the same load day after day (Foster: mean / standard deviation of daily load) of 2.0 or more, in a week
  heavier than the 4-week weekly average.
- Cadence down at the same pace: recent runs 3+ spm lower than earlier runs within 10 s/km of their pace.
- Heart rate up at the same pace: recent runs 5+ bpm higher than earlier runs within 10 s/km of their pace (hot runs
  left out: heat alone raises it).
- Felt harder than measured: 2 or more of the last 10 days' rated runs felt moderately hard or harder while under 20% of
  their time was in zones 4–5 (needs 3 rated runs)."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median, pstdev

from . import reports as rp
from . import weather as wx
from .db import one

STRAIN_VERSION = "strain-1.0"
LOAD_JUMP = 1.3
MONOTONY = 2.0
CADENCE_DROP_SPM = 3.0
HR_RISE_BPM = 5.0
PACE_MATCH_S = 10.0
FELT_HARD = 6  # on a 1–10 scale: "moderate-hard" and up
FELT_MIN_RATED = 3
NEEDS = 2      # signals that must agree
EFFORT_WORDS = {"very_easy": 2, "easy": 3, "easy_moderate": 4, "moderate": 5, "moderate_hard": 6, "hard": 7, "very_hard": 9}


def pace(a: dict) -> float | None:
    return a["moving_s"] / (a["distance_m"] / 1000) if a.get("distance_m") and a.get("moving_s") else None


def same_pace_shift(recent: list[dict], before: list[dict], field: str) -> float | None:
    """Median difference in `field` between each recent run and earlier runs at a similar pace (±10 s/km)."""
    diffs = []
    for a in recent:
        p, v = pace(a), a.get(field)
        if p is None or v is None:
            continue
        like = [b[field] for b in before if b.get(field) is not None and (q := pace(b)) is not None and abs(q - p) <= PACE_MATCH_S]
        if len(like) >= 2:
            diffs.append(v - median(like))
    return median(diffs) if len(diffs) >= 2 else None


def build(conn, source: str, today: date) -> dict | None:
    from .focus import zone_shares
    from .readiness import moment, run_load, training_load
    zones = rp.hr_zones(conn)
    runs = rp.activities(conn, source, (today - timedelta(days=34)).isoformat(), today.isoformat())
    cut = (today - timedelta(days=6)).isoformat()
    recent = [a for a in runs if a["local_date"] >= cut]
    before = [a for a in runs if a["local_date"] < cut]
    if len(recent) < 2 or len(before) < 4:
        return None
    signals = []

    tl = training_load(conn, source, moment(conn, today), zones)
    if tl and tl["ratio"] >= LOAD_JUMP:
        signals.append({"id": "load", "say": f"this week's load is {round(100 * tl['ratio'])}% of your usual"})

    floors = zones["floors"] if zones else None
    daily = {}
    for a in runs:
        daily[a["local_date"]] = daily.get(a["local_date"], 0.0) + run_load(conn, a, floors)
    week = [daily.get((today - timedelta(days=k)).isoformat(), 0.0) for k in range(7)]
    sd = pstdev(week)
    four_weeks = sum(v for d, v in daily.items() if d < cut) / 4
    if sd > 0 and sum(week) / 7 / sd >= MONOTONY and sum(week) > four_weeks:
        signals.append({"id": "monotony", "say": f"much the same load every day (monotony {sum(week) / 7 / sd:.1f}) in a heavier week"})

    cad = same_pace_shift(recent, before, "avg_cadence_spm")
    if cad is not None and cad <= -CADENCE_DROP_SPM:
        signals.append({"id": "cadence", "say": f"cadence {abs(cad):.0f} spm lower at your usual paces"})

    too_hot = wx.unusually_hot(conn)
    cool = lambda xs: [a for a in xs if a["source_id"] not in too_hot]  # noqa: E731  (like with like)
    hr = same_pace_shift(cool(recent), cool(before), "avg_hr")
    if hr is not None and hr >= HR_RISE_BPM:
        signals.append({"id": "heart_rate", "say": f"heart rate {hr:.0f} bpm higher at your usual paces"})

    rated = []
    for a in [a for a in runs if a["local_date"] >= (today - timedelta(days=9)).isoformat()]:
        intent = one(conn.run_intent, {"activity_source_id": a["source_id"]}) or {}
        rpe = (one(conn.activity_effort, {"activity_source_id": a["source_id"]}) or {}).get("rpe") or EFFORT_WORDS.get(intent.get("effort"))
        if rpe is not None:
            z = zone_shares(conn, a, zones["floors"]) if zones else None
            rated.append((rpe, z["hard"] if z else None))
    harder = sum(1 for rpe, hard in rated if rpe >= FELT_HARD and hard is not None and hard < 0.2)
    if len(rated) >= FELT_MIN_RATED and harder >= 2:
        signals.append({"id": "felt", "say": f"{harder} recent runs felt hard while heart rate stayed mostly easy"})

    if len(signals) < NEEDS:
        return None
    return {"signals": signals, "title": "Strain is building",
            "text": "; ".join(s["say"] for s in signals).capitalize() + ". Consider an easier day or two.",
            "basis": "Two or more of: a load jump, the same load every day, lower cadence or higher heart rate at your usual paces, "
                     "runs feeling harder than heart rate shows. Last 7 days against the 4 weeks before. A nudge, not a diagnosis.",
            "algorithm_version": STRAIN_VERSION}

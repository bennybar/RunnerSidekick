"""Fitness progress: is aerobic fitness improving, stable or declining? Three independent signals, each from different
data: Garmin's VO2 max over 4 weeks, your pace at the same heart rate (efficiency, per watch) and heart-rate drift on
steady runs (durability). Each signal has a direction or says there isn't enough evidence; the verdict needs two
signals, and its confidence says how many agree. Not averaged into the fitness number: these don't share a scale."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from . import reports as rp

PROGRESS_VERSION = "progress-1.0"
EFFICIENCY_S_PER_MONTH = 3.0   # a pace change smaller than this at the same heart rate is "stable"
EFFICIENCY_MIN_RUNS = 6
EFFICIENCY_MAX_AGE_DAYS = 45   # the trend must reach into the last 6 weeks
DRIFT_PP = 1.0                 # a change in median drift smaller than this is "stable"
DRIFT_MIN_RUNS = 3
VO2_STEP = 0.5                 # a 4-week VO2 change smaller than this is "stable"


def signal(sid: str, title: str, direction: str | None, say: str, note: str) -> dict:
    """direction: improving | stable | declining, or None when there isn't enough evidence."""
    return {"id": sid, "title": title, "direction": direction, "say": say, "note": note}


def vo2_signal(conn, source: str, today: date) -> dict:
    from .scores import vo2_on
    now, then = vo2_on(conn, source, today, today), vo2_on(conn, source, today - timedelta(days=28), today)
    note = "Garmin's VO₂ max now against 4 weeks ago; a change under 0.5 counts as stable"
    if not now or not then:
        return signal("vo2", "Aerobic estimate", None, "Needs two VO₂ max readings 4 weeks apart", note)
    d = now[0] - then[0]
    direction = "improving" if d >= VO2_STEP else "declining" if d <= -VO2_STEP else "stable"
    return signal("vo2", "Aerobic estimate", direction, f"VO₂ max {then[0]:.1f} → {now[0]:.1f} in 4 weeks", note)


def efficiency_signal(conn, source: str, today: date) -> dict:
    note = (f"Pace in your most common heart-rate band, per watch (watches measure differently); {EFFICIENCY_MIN_RUNS}+ runs, "
            f"reaching into the last 6 weeks; under {EFFICIENCY_S_PER_MONTH:.0f} s/km a month counts as stable")
    ins = rp.latest_body(conn, "insights") or {}
    eff = next((i for i in ins.get("insights", []) if i["id"] == "efficiency"), None)
    eras = (eff or {}).get("effect", {}).get("eras", [])
    recent = [e for e in eras if e["runs"] >= EFFICIENCY_MIN_RUNS and e["end"] >= (today - timedelta(days=EFFICIENCY_MAX_AGE_DAYS)).isoformat()]
    if not recent:
        return signal("efficiency", "Efficiency", None, "Needs 6+ comparable runs on your current watch", note)
    e = max(recent, key=lambda x: x["end"])
    slope = e["slope_s_per_km_per_30d"]
    direction = "improving" if slope <= -EFFICIENCY_S_PER_MONTH else "declining" if slope >= EFFICIENCY_S_PER_MONTH else "stable"
    lo, hi = eff["effect"]["band_bpm"]
    word = "faster" if slope < 0 else "slower"
    return signal("efficiency", "Efficiency", direction,
                  f"At {lo}–{hi} bpm: {rp.fmt_pace(e['first_half_median_pace'])} → {rp.fmt_pace(e['second_half_median_pace'])} "
                  f"({abs(slope):.0f} s/km a month {word}, {e['runs']} runs)", note)


def drift_signal(conn, source: str, today: date) -> dict:
    note = (f"Heart-rate drift (pace:HR decoupling) on steady runs, last 6 weeks against the 6 before; {DRIFT_MIN_RUNS}+ runs in "
            f"each; under {DRIFT_PP:.0f} point counts as stable. Lower drift = efficiency that holds up")
    latest: dict[str, tuple[str, float]] = {}
    for r in conn.report.find({"type": "post_run", "body.local_date": {"$gte": (today - timedelta(days=84)).isoformat()}},
                              {"subject_key": 1, "revision": 1, "body.local_date": 1, "body.decoupling": 1}).sort("revision", -1):
        if r["subject_key"] in latest:
            continue  # the newest revision of each run only
        dc = r["body"].get("decoupling") or {}
        if dc.get("eligible") and dc.get("decoupling_pct") is not None:
            latest[r["subject_key"]] = (r["body"]["local_date"], dc["decoupling_pct"])
    cut = (today - timedelta(days=42)).isoformat()
    now = [v for d, v in latest.values() if d >= cut]
    before = [v for d, v in latest.values() if d < cut]
    if len(now) < DRIFT_MIN_RUNS:
        return signal("drift", "Durability", None, f"Needs {DRIFT_MIN_RUNS} steady runs in 6 weeks ({len(now)} so far)", note)
    if len(before) < DRIFT_MIN_RUNS:
        return signal("drift", "Durability", None, f"Drift {median(now):.1f}% on recent steady runs; nothing to compare yet", note)
    a, b = median(before), median(now)
    direction = "improving" if b <= a - DRIFT_PP else "declining" if b >= a + DRIFT_PP else "stable"
    return signal("drift", "Durability", direction, f"Drift {a:.1f}% → {b:.1f}% on steady runs ({len(before)} and {len(now)} runs)", note)


def build(conn, source: str, today: date) -> dict:
    sigs = [vo2_signal(conn, source, today), efficiency_signal(conn, source, today), drift_signal(conn, source, today)]
    known = [s for s in sigs if s["direction"]]
    up = sum(s["direction"] == "improving" for s in known)
    down = sum(s["direction"] == "declining" for s in known)
    if len(known) < 2:
        verdict, confidence = "insufficient", None
    else:
        verdict = "improving" if up > down and up >= 1 else "declining" if down > up and down >= 1 else "stable"
        agree = sum(s["direction"] == verdict for s in known)
        confidence = "high" if agree >= 3 else "medium" if agree == 2 else "low"
    # One plain line: the agreement, or the tension between the signals
    names = {"vo2": "your aerobic estimate", "efficiency": "efficiency", "drift": "durability"}
    if verdict == "insufficient":
        summary = "Not enough comparable runs yet to say whether you're improving."
    elif up and down:
        ups = " and ".join(names[s["id"]] for s in known if s["direction"] == "improving")
        downs = " and ".join(names[s["id"]] for s in known if s["direction"] == "declining")
        lead = {"improving": "Getting fitter", "declining": "Slipping", "stable": "Mixed"}[verdict]
        summary = f"{lead}: {ups} improving, though {downs} slipped."
    else:
        summary = {"improving": "You're getting fitter", "declining": "Fitness is slipping", "stable": "Holding steady"}[verdict] + \
                  " (" + ", ".join(f"{names[s['id']]} {s['direction']}" for s in known) + ")."
    return {"verdict": verdict, "confidence": confidence, "summary": summary, "signals": sigs,
            "basis": "Three separate signals from different data; not averaged into the fitness number. Terrain, heat and watch "
                     "changes affect efficiency and drift.", "algorithm_version": PROGRESS_VERSION}

"""Fitness progress: is aerobic fitness improving, stable or declining? Three independent signals, each from different
data: Garmin's VO2 max over 4 weeks, your pace at the same heart rate (efficiency, per watch) and heart-rate drift on
steady runs (durability). Each signal has a direction or says there isn't enough evidence; the verdict needs two
signals, and its confidence says how many agree. Not averaged into the fitness number: these don't share a scale."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from . import reports as rp

PROGRESS_VERSION = "progress-1.3"  # 1.3: one moving signal is an early sign; signal agreement; 1.2: distinct dated VO2 readings, efficiency halves must agree, newest revision only; 1.1: a VO2 estimate dip alone never makes "declining"
from .analytics.insights import TREND_MEANINGFUL_S_PER_KM_PER_MONTH as EFFICIENCY_S_PER_MONTH  # the efficiency insight's own step
EFFICIENCY_MIN_RUNS = 6
EFFICIENCY_MAX_AGE_DAYS = 45   # the trend must reach into the last 6 weeks
DRIFT_PP = 1.0                 # a change in median drift smaller than this is "stable"
DRIFT_MIN_RUNS = 3
VO2_STEP = 0.5                 # a 4-week VO2 change smaller than this is "stable"
VO2_FRESH_DAYS = 14            # the newer reading must be from the last 2 weeks
VO2_MIN_GAP_DAYS = 21          # and at least 3 weeks after the older one (two different measurements)
VO2_OLDEST_DAYS = 56           # the older one no more than 8 weeks back


def signal(sid: str, title: str, direction: str | None, say: str, note: str) -> dict:
    """direction: improving | stable | declining, or None when there isn't enough evidence."""
    return {"id": sid, "title": title, "direction": direction, "say": say, "note": note}


def vo2_signal(conn, source: str, today: date) -> dict:
    from .scores import vo2_on
    now, then = vo2_on(conn, source, today, today), vo2_on(conn, source, today - timedelta(days=28), today)
    note = ("Garmin's VO₂ max estimate now against 4 weeks ago; a change under 0.5 counts as stable. A device estimate "
            "trend: heat, hills, fatigue or a run of easy weeks can lower it for a while without any loss of fitness")
    title = "Garmin VO₂ estimate"
    # Two different, dated measurements: the same old reading twice isn't evidence of stability
    if not now or not then or now[1] < today - timedelta(days=VO2_FRESH_DAYS) or (now[1] - then[1]).days < VO2_MIN_GAP_DAYS \
            or then[1] < today - timedelta(days=VO2_OLDEST_DAYS):
        return signal("vo2", title, None, "Needs a recent VO₂ max reading and one about 4 weeks before it", note)
    d = now[0] - then[0]
    direction = "improving" if d >= VO2_STEP else "declining" if d <= -VO2_STEP else "stable"
    say = f"Estimate {then[0]:.1f} ({then[1].strftime('%-d %b')}) → {now[0]:.1f} ({now[1].strftime('%-d %b')})" + (" (a device estimate dip, not a measured decline)" if direction == "declining" else "")
    return signal("vo2", title, direction, say, note)


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
    # The insight's own rule: the trend and the half-by-half medians must agree, or it's no clear change
    faster, slower = e["second_half_median_pace"] < e["first_half_median_pace"], e["second_half_median_pace"] > e["first_half_median_pace"]
    direction = "improving" if slope <= -EFFICIENCY_S_PER_MONTH and faster else \
        "declining" if slope >= EFFICIENCY_S_PER_MONTH and slower else "stable"
    lo, hi = eff["effect"]["band_bpm"]
    word = "faster" if slope < 0 else "slower"
    return signal("efficiency", "Efficiency", direction,
                  f"At {lo}–{hi} bpm: {rp.fmt_pace(e['first_half_median_pace'])} → {rp.fmt_pace(e['second_half_median_pace'])} "
                  f"({abs(slope):.0f} s/km a month {word}, {e['runs']} runs)", note)


def drift_signal(conn, source: str, today: date) -> dict:
    note = (f"Heart-rate drift (pace:HR decoupling) on steady runs, last 6 weeks against the 6 before; {DRIFT_MIN_RUNS}+ runs in "
            f"each; under {DRIFT_PP:.0f} point counts as stable. Hot, humid runs are left out. Lower drift = efficiency that holds up")
    latest: dict[str, tuple[str, float]] = {}
    seen: set[str] = set()
    for r in conn.report.find({"type": "post_run", "body.local_date": {"$gte": (today - timedelta(days=84)).isoformat()}},
                              {"subject_key": 1, "revision": 1, "body.local_date": 1, "body.decoupling": 1, "body.heat": 1}).sort("revision", -1):
        if r["subject_key"] in seen:
            continue  # the newest revision of each run only, eligible or not
        seen.add(r["subject_key"])
        dc = r["body"].get("decoupling") or {}
        if (r["body"].get("heat") or {}).get("hot"):
            continue  # heat raises drift: hot runs would read as lost durability
        if dc.get("eligible") and dc.get("decoupling_pct") is not None:
            latest[r["subject_key"]] = (r["body"]["local_date"], dc["decoupling_pct"])
    cut = (today - timedelta(days=42)).isoformat()
    now = [v for d, v in latest.values() if d >= cut]
    before = [v for d, v in latest.values() if d < cut]
    if len(now) < DRIFT_MIN_RUNS:
        return signal("drift", "Durability", None, f"Needs {DRIFT_MIN_RUNS} steady runs in 6 weeks ({len(now)} so far)", note)
    if len(before) < DRIFT_MIN_RUNS:
        return signal("drift", "Durability", None, f"Aerobic decoupling {median(now):.1f}% on recent steady runs; nothing to compare yet", note)
    a, b = median(before), median(now)
    direction = "improving" if b <= a - DRIFT_PP else "declining" if b >= a + DRIFT_PP else "stable"
    return signal("drift", "Durability", direction, f"Aerobic decoupling {a:.1f}% → {b:.1f}% on steady runs ({len(before)} and {len(now)} runs)", note)


def build(conn, source: str, today: date) -> dict:
    sigs = [vo2_signal(conn, source, today), efficiency_signal(conn, source, today), drift_signal(conn, source, today)]
    known = [s for s in sigs if s["direction"]]
    up = sum(s["direction"] == "improving" for s in known)
    down = sum(s["direction"] == "declining" for s in known)
    if len(known) < 2:
        verdict, confidence = "insufficient", None
    else:
        # A dip in Garmin's VO2 estimate alone isn't a fitness decline: declining needs a measured signal to decline too
        measured_down = sum(s["direction"] == "declining" for s in known if s["id"] != "vo2")
        verdict = "improving" if up > down and up >= 1 else "declining" if down > up and measured_down >= 1 else "stable"
        agree = sum(s["direction"] == verdict for s in known)
        confidence = "high" if agree >= 3 else "medium" if agree == 2 else "low"
    # One plain line: the agreement, or the tension between the signals
    names = {"vo2": "Garmin's VO₂ estimate", "efficiency": "efficiency", "drift": "durability"}
    verb = lambda s: "dipped" if s["id"] == "vo2" and s["direction"] == "declining" else s["direction"]  # noqa: E731
    agree = sum(s["direction"] == verdict for s in known) if verdict != "insufficient" else 0
    if verdict == "insufficient":
        summary = "Not enough comparable runs yet to say whether you're improving."
    elif verdict in ("improving", "declining") and agree == 1 and not (up and down):
        # One signal moving and the rest stable: an early sign, said as such
        moving = next(s for s in known if s["direction"] == verdict)
        summary = ("Early signs of improvement" if verdict == "improving" else "Early signs of slipping") + \
                  f": {names[moving['id']]} {verb(moving)}, the rest stable."
    elif up and down:
        ups = " and ".join(names[s["id"]] for s in known if s["direction"] == "improving")
        downs = " and ".join(names[s["id"]] for s in known if s["direction"] == "declining")
        lead = {"improving": "Getting fitter", "declining": "Slipping", "stable": "Mixed"}[verdict]
        summary = f"{lead}: {ups} improving, though {downs} dipped."
    else:
        summary = {"improving": "You're getting fitter", "declining": "Fitness is slipping", "stable": "Holding steady"}[verdict] + \
                  " (" + ", ".join(f"{names[s['id']]} {verb(s)}" for s in known) + ")."
    return {"verdict": verdict, "confidence": confidence, "summary": summary, "signals": sigs,
            "agreement": f"{agree} of {len(known)} signals" if verdict != "insufficient" else None,
            "basis": "Three separate signals from different data; not averaged into the fitness number. Terrain, heat and watch "
                     "changes affect efficiency and drift.", "algorithm_version": PROGRESS_VERSION}

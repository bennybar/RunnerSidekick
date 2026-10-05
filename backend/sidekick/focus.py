"""Weekly focus: one thing to work on this week, suggested from the runner's own data, then measured on that week's
runs. Deterministic; each evaluation states its target, what was measured and on which runs."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median

from . import reports as rp
from .analytics import insights as ins
from .analytics import running as rn
from .db import first_weekday, many, one, put, utc_now
from .db import week_start as db_week_start

FOCUS_VERSION = "focus-1.0"
from .analytics.running import FADE_S_PER_KM as FADE_TARGET_S  # "even": the app's one ±5 s/km
EASY_SHARE = 0.7             # an easy run spends >= 70% of moving time below the zone-3 floor
VOLUME_BAND = 0.15           # steady volume = within ±15% of the previous week
from .analytics.running import MIN_ZONE_COVERAGE  # the one rule for everything judged from time in zones

KINDS = {
    "even_pacing": "Start slower and finish even",
    "easy_runs": "Make one run genuinely easy",
    "steady_volume": "Keep this week's volume close to last week's",
    "consistency": "Run on your planned days",
    "recovery": "Prioritise recovery this week",
}

GOAL_ORDER = {
    "performance": ["even_pacing", "easy_runs", "steady_volume", "consistency", "recovery"],
    "distance": ["steady_volume", "easy_runs", "consistency", "even_pacing", "recovery"],
    "consistency": ["consistency", "steady_volume", "easy_runs", "even_pacing", "recovery"],
    "health": ["recovery", "easy_runs", "consistency", "steady_volume", "even_pacing"],
}


def week_start(d: date, first: int = 0) -> date:
    return db_week_start(d, first)


def _runs(conn, source, start: date, end: date) -> list[dict]:
    return rp.activities(conn, source, start.isoformat(), end.isoformat())


def run_fade(conn, a: dict) -> float | None:
    """Second-half minus first-half pace on complete splits, for steady runs only (as in the pacing insight)."""
    laps = rp.laps_for(conn, a["id"])
    if rn.classify(rp.samples_for(conn, a["id"]), laps)["kind"] != "steady":
        return None
    # The app's one fade: halves of complete splits, hill-adjusted where the samples allow it
    splits = rn.splits_from_laps(laps)
    details = rn.split_details(rp.samples_for(conn, a["id"]), laps, None) or [{}] * len(splits)
    sp = [d.get("gap_pace_s_per_km") or s.pace_s_per_km for s, d in zip(splits, details) if s.complete and s.pace_s_per_km]
    if len(sp) < 4:
        return None
    return rn.fade(sp)


def zone_shares(conn, a: dict, floors: list[float]) -> dict | None:
    """Share of valid-HR moving time below zone 3 (easy) and in zones 4–5 (hard). None when HR covers too little of the run."""
    s = rp.samples_for(conn, a["id"])
    if s is None:
        return None
    r = ins.RunData(a["source_id"], a["local_date"], datetime.min, None, a["distance_m"], a["moving_s"], None, s, [], "steady")
    zt = ins.zone_time(r, floors)
    tot = sum(zt)
    # The same coverage rule as the intensity insight: valid heart-rate time is most of the run's moving time
    moving = sum(w for w in rn._weights(s) if w > 0)
    if not tot or tot < MIN_ZONE_COVERAGE * (a["moving_s"] or moving):
        return None
    return {"easy": (zt[0] + zt[1] + zt[2]) / tot, "hard": (zt[4] + zt[5]) / tot}


def easy_share(conn, a: dict, floors: list[float]) -> float | None:
    z = zone_shares(conn, a, floors)
    return z["easy"] if z else None


def options(conn, source: str, today: date) -> list[dict]:
    """Up to three suggested focuses, each with the reason drawn from the runner's data, ordered by goal type."""
    goal = rp.get_setting(conn, "goal_type", None)
    zones = rp.hr_zones(conn)
    insights = {}
    r = rp.latest_body(conn, "insights")
    if r:
        insights = {i["id"]: i for i in r["insights"]}
    garmin = rp.get_setting(conn, "garmin_fitness", None) or {}
    status = ((garmin.get("training_status") or {}).get("phrase") or "").split("_")[0]
    reasons: dict[str, str] = {}
    p = insights.get("pacing")
    if p and p["verdict"] == "pattern":
        reasons["even_pacing"] = p["headline"]
    i = insights.get("intensity")
    if i and i["verdict"] == "pattern" and zones:
        reasons["easy_runs"] = f"{i['headline']}. Easy means below {zones['floors'][2]} bpm on your zones."
    ws = week_start(today, first_weekday(conn))
    last = sum(a["moving_s"] or 0 for a in _runs(conn, source, ws - timedelta(days=7), ws - timedelta(days=1)))
    before = sum(a["moving_s"] or 0 for a in _runs(conn, source, ws - timedelta(days=35), ws - timedelta(days=8))) / 4
    if before and last > 1.5 * before:
        reasons["steady_volume"] = "Last week was a clear jump in volume compared with the four weeks before."
    if status in ("OVERREACHING", "STRAINED", "UNPRODUCTIVE"):
        reasons["recovery"] = f"Garmin rates your training as {status.lower()}."
    reasons.setdefault("consistency", "Regular running is what makes every other trend in the app meaningful.")
    order = GOAL_ORDER.get(goal or "", list(reasons))
    # A race goal sets the priorities by training phase
    from . import race as rc
    rs = rc.status(conn, today)
    if rs:
        order = rc.FOCUS_ORDER[rs["phase"]]
        if rs["phase"] in ("taper", "race_week", "recovery"):
            reasons["recovery"] = f"{rs['headline']}: {rs['phase_note']}"
        reasons.setdefault("easy_runs", f"{rs['phase'].replace('_', ' ').capitalize()} phase for {rs['label']}: most running should be easy.")
    # Reported pain or illness in the last 3 days comes first, as it does in the morning recommendation
    flagged = conn.checkin.find_one({"deleted": False, "$or": [{"pain": True}, {"illness": True}],
                                     "local_date": {"$gte": (today - timedelta(days=3)).isoformat()}})
    if flagged:
        reasons["recovery"] = "You reported pain or feeling unwell in the last few days."
        order = ["recovery"] + [k for k in order if k != "recovery"]
    ranked = sorted(reasons, key=lambda k: order.index(k) if k in order else 99)
    return [{"kind": k, "title": KINDS[k], "reason": reasons[k]} for k in ranked[:3]]


def evaluate(conn, source: str, ws: date, kind: str, today: date, params: dict | None = None) -> dict:
    """How the chosen focus went (or is going) this week. Partial weeks are 'in progress', never 'missed'."""
    we = ws + timedelta(days=6)
    done = today > we
    runs = _runs(conn, source, ws, min(we, today))
    zones = rp.hr_zones(conn)
    rpes = {r["activity_source_id"]: r["rpe"] for r in many(conn.activity_effort)}
    out = {"kind": kind, "title": KINDS.get(kind, kind), "week_start": ws.isoformat(), "complete": done, "runs": [],
           "algorithm_version": FOCUS_VERSION}
    if kind == "even_pacing":
        prior = [f for a in _runs(conn, source, ws - timedelta(days=28), ws - timedelta(days=1)) if (f := run_fade(conn, a)) is not None]
        for a in runs:
            f = run_fade(conn, a)
            if f is not None:
                out["runs"].append({"date": a["local_date"], "source_id": a["source_id"], "value": round(f, 1), "met": f <= FADE_TARGET_S,
                                    "rpe": rpes.get(a["source_id"])})
        met = sum(r["met"] for r in out["runs"])
        out["target"] = f"Second half no more than {FADE_TARGET_S:.0f} s/km slower than the first"
        out["baseline"] = {"label": "typical fade before", "value": round(median(prior), 1) if prior else None, "unit": "s/km", "n": len(prior)}
        out["summary"] = (f"{met} of {len(out['runs'])} runs finished even" if out["runs"] else "No runs with full splits yet this week") + (
            f" (your typical fade before: {median(prior):.0f} s/km)." if prior else ".")
        out["status"] = ("achieved" if out["runs"] and met == len(out["runs"]) else "in_progress" if not done else
                         "unavailable" if not out["runs"] else "partly" if met else "missed")
        if out["status"] == "unavailable":
            out["summary"] = "No steady runs with full splits this week, so pacing couldn't be measured."
    elif kind == "easy_runs":
        if not zones:
            return {**out, "status": "unavailable", "summary": "Needs Garmin heart-rate zones."}
        ceiling = zones["floors"][2]
        for a in runs:
            e = easy_share(conn, a, zones["floors"])
            if e is not None:
                out["runs"].append({"date": a["local_date"], "source_id": a["source_id"], "value": round(100 * e), "met": e >= EASY_SHARE,
                                    "rpe": rpes.get(a["source_id"])})
        met = sum(r["met"] for r in out["runs"])
        out["target"] = f"At least one run with {round(100 * EASY_SHARE)}% of the time below {ceiling} bpm"
        out["summary"] = (f"{met} easy run{'s' if met != 1 else ''} this week" + (
            f"; your easiest had {max(r['value'] for r in out['runs'])}% below {ceiling} bpm." if out["runs"] else "."))
        out["status"] = "achieved" if met >= 1 else "in_progress" if not done else "unavailable" if runs and not out["runs"] else "missed"
        if out["status"] == "unavailable":
            out["summary"] = "This week's runs didn't have enough heart-rate data to judge."
    elif kind == "steady_volume":
        prev = sum(a["moving_s"] or 0 for a in _runs(conn, source, ws - timedelta(days=7), ws - timedelta(days=1)))
        cur = sum(a["moving_s"] or 0 for a in runs)
        lo, hi = prev * (1 - VOLUME_BAND), prev * (1 + VOLUME_BAND)
        out["target"] = f"Between {rp.fmt_duration(lo)} and {rp.fmt_duration(hi)} of running (last week ±{round(100 * VOLUME_BAND)}%)"
        out["baseline"] = {"label": "last week", "value": round(prev), "unit": "s"}
        out["summary"] = f"{rp.fmt_duration(cur) if cur else '0 min'} so far" + (" this week." if not done else " this week, in total.")
        out["status"] = ("achieved" if lo <= cur <= hi else "missed") if done else ("over" if cur > hi else "in_progress")
    elif kind == "consistency":
        planned = (params or {}).get("running_days") or rp.get_setting(conn, "running_days", [0, 2, 4, 5])
        days = [ws + timedelta(days=k) for k in range(7) if (ws + timedelta(days=k)).weekday() in planned and ws + timedelta(days=k) <= today]
        ran = {a["local_date"] for a in runs}
        for d in days:
            out["runs"].append({"date": d.isoformat(), "value": None, "met": d.isoformat() in ran})
        met = sum(r["met"] for r in out["runs"])
        total = sum(1 for k in range(7) if (ws + timedelta(days=k)).weekday() in planned)
        out["target"] = f"Run on your {total} planned days"
        out["summary"] = f"Ran on {met} of {len(days)} planned days so far." if not done else f"Ran on {met} of {total} planned days."
        out["status"] = "achieved" if done and met == total else ("in_progress" if not done else ("partly" if met else "missed"))
    elif kind == "recovery":
        out["target"] = "No hard runs (most of the time in zones 4–5) this week"
        if not zones:
            return {**out, "status": "unavailable", "summary": "Needs Garmin heart-rate zones."}
        hard = []
        for a in runs:
            z = zone_shares(conn, a, zones["floors"])
            if z is not None:
                out["runs"].append({"date": a["local_date"], "source_id": a["source_id"], "value": round(100 * z["hard"]), "met": z["hard"] < 0.5,
                                    "rpe": rpes.get(a["source_id"])})
                hard.append(z["hard"] >= 0.5)
        unmeasured = len(runs) - len(hard)
        out["summary"] = f"{sum(hard)} hard run{'s' if sum(hard) != 1 else ''} this week" + (
            f"; {unmeasured} run{'s' if unmeasured != 1 else ''} without enough heart-rate data." if unmeasured else ".")
        if any(hard):
            out["status"] = "missed" if done else "off_track"
        elif unmeasured:
            out["status"] = "unavailable" if done else "in_progress"
        else:
            out["status"] = "achieved" if done else "in_progress"
    rp_vals = [r["rpe"] for r in out["runs"] if r.get("rpe")]
    if rp_vals:
        out["felt"] = f"You rated these runs {min(rp_vals)}–{max(rp_vals)} out of 10 for effort." if len(rp_vals) > 1 else \
            f"You rated it {rp_vals[0]} out of 10 for effort."
    return out


def current(conn, source: str, today: date) -> dict:
    ws = week_start(today, first_weekday(conn))
    row = one(conn.weekly_focus, {"week_start": ws.isoformat()})
    opts = options(conn, source, today)
    if row is None and opts:
        # Picked for the runner from the data; they can change it, but nothing is required
        conn.weekly_focus.update_one({"week_start": ws.isoformat()}, {"$setOnInsert": {
            "kind": opts[0]["kind"], "params": {"auto": True, "running_days": rp.get_setting(conn, "running_days", [0, 2, 4, 5])},
            "chosen_at": utc_now()}}, upsert=True)
        row = one(conn.weekly_focus, {"week_start": ws.isoformat()})
    elif row and row["params"].get("auto") and opts and opts[0]["kind"] == "recovery" and row["kind"] != "recovery":
        # A focus the app picked follows a safety change (reported pain or illness puts recovery first); one you chose stays
        conn.weekly_focus.update_one({"week_start": ws.isoformat()}, {"$set": {"kind": "recovery", "chosen_at": utc_now()}})
        row = one(conn.weekly_focus, {"week_start": ws.isoformat()})
    prev = one(conn.weekly_focus, {"week_start": (ws - timedelta(days=7)).isoformat()})
    return {
        "week_start": ws.isoformat(),
        "current": ({**evaluate(conn, source, ws, row["kind"], today, row["params"]), "auto": row["params"].get("auto", False)}
                    if row else None),
        "last_week": evaluate(conn, source, ws - timedelta(days=7), prev["kind"], today, prev["params"]) if prev else None,
        "options": opts,
    }


def choose(conn, ws: date, kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(kind)
    put(conn.weekly_focus, {"week_start": ws.isoformat()},
        {"kind": kind, "params": {"running_days": rp.get_setting(conn, "running_days", [0, 2, 4, 5])}, "chosen_at": utc_now()})

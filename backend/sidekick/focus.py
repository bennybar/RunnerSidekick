"""Weekly focus: one thing to work on this week, suggested from the runner's own data, then measured on that week's
runs. Deterministic; each evaluation states its target, what was measured and on which runs."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from statistics import median

from . import reports as rp
from .analytics import insights as ins
from .analytics import running as rn
from .db import utc_now

FOCUS_VERSION = "focus-1.0"
FADE_TARGET_S = 5.0          # "even" = second half no more than 5 s/km slower than the first
EASY_SHARE = 0.7             # an easy run spends >= 70% of moving time below the zone-3 floor
VOLUME_BAND = 0.15           # steady volume = within ±15% of the previous week

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


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _runs(conn, source, start: date, end: date) -> list[dict]:
    return rp.activities(conn, source, start.isoformat(), end.isoformat())


def run_fade(conn, a: dict) -> float | None:
    sp = [s.pace_s_per_km for s in rn.splits_from_laps(rp.laps_for(conn, a["id"])) if s.complete and s.pace_s_per_km]
    if len(sp) < 4:
        return None
    h = len(sp) // 2
    return sum(sp[h:]) / (len(sp) - h) - sum(sp[:h]) / h


def easy_share(conn, a: dict, floors: list[float]) -> float | None:
    s = rp.samples_for(conn, a["id"])
    if s is None:
        return None
    r = ins.RunData(a["source_id"], a["local_date"], datetime.min, None, a["distance_m"], a["moving_s"], None, s, [], "steady")
    zt = ins.zone_time(r, floors)
    tot = sum(zt)
    return (zt[0] + zt[1] + zt[2]) / tot if tot else None


def options(conn, source: str, today: date) -> list[dict]:
    """Up to three suggested focuses, each with the reason drawn from the runner's data, ordered by goal type."""
    goal = rp.get_setting(conn, "goal_type", None)
    zones = rp.get_setting(conn, "source_hr_zones", None)
    insights = {}
    r = conn.execute("SELECT body_json FROM report WHERE type='insights' ORDER BY local_date DESC, revision DESC LIMIT 1").fetchone()
    if r:
        insights = {i["id"]: i for i in json.loads(r["body_json"])["insights"]}
    garmin = rp.get_setting(conn, "garmin_fitness", None) or {}
    status = ((garmin.get("training_status") or {}).get("phrase") or "").split("_")[0]
    reasons: dict[str, str] = {}
    p = insights.get("pacing")
    if p and p["verdict"] == "pattern":
        reasons["even_pacing"] = p["headline"]
    i = insights.get("intensity")
    if i and i["verdict"] == "pattern" and zones:
        reasons["easy_runs"] = f"{i['headline']}. Easy means below {zones['floors'][2]} bpm on your zones."
    ws = week_start(today)
    last = sum(a["moving_s"] or 0 for a in _runs(conn, source, ws - timedelta(days=7), ws - timedelta(days=1)))
    before = sum(a["moving_s"] or 0 for a in _runs(conn, source, ws - timedelta(days=35), ws - timedelta(days=8))) / 4
    if before and last > 1.5 * before:
        reasons["steady_volume"] = "Last week was a clear jump in volume compared with the four weeks before."
    if status in ("OVERREACHING", "STRAINED", "UNPRODUCTIVE"):
        reasons["recovery"] = f"Garmin rates your training as {status.lower()}."
    reasons.setdefault("consistency", "Regular running is what makes every other trend in the app meaningful.")
    order = GOAL_ORDER.get(goal or "", list(reasons))
    ranked = sorted(reasons, key=lambda k: order.index(k) if k in order else 99)
    return [{"kind": k, "title": KINDS[k], "reason": reasons[k]} for k in ranked[:3]]


def evaluate(conn, source: str, ws: date, kind: str, today: date) -> dict:
    """How the chosen focus went (or is going) this week. Partial weeks are 'in progress', never 'missed'."""
    we = ws + timedelta(days=6)
    done = today > we
    runs = _runs(conn, source, ws, min(we, today))
    zones = rp.get_setting(conn, "source_hr_zones", None)
    rpes = {r["activity_source_id"]: r["rpe"] for r in conn.execute("SELECT * FROM activity_effort")}
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
        out["status"] = "achieved" if out["runs"] and met == len(out["runs"]) else ("in_progress" if not done else ("partly" if met else "missed"))
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
        out["status"] = "achieved" if met >= 1 else ("in_progress" if not done else "missed")
    elif kind == "steady_volume":
        prev = sum(a["moving_s"] or 0 for a in _runs(conn, source, ws - timedelta(days=7), ws - timedelta(days=1)))
        cur = sum(a["moving_s"] or 0 for a in runs)
        lo, hi = prev * (1 - VOLUME_BAND), prev * (1 + VOLUME_BAND)
        out["target"] = f"Between {rp.fmt_duration(lo)} and {rp.fmt_duration(hi)} of running (last week ±{round(100 * VOLUME_BAND)}%)"
        out["baseline"] = {"label": "last week", "value": round(prev), "unit": "s"}
        out["summary"] = f"{rp.fmt_duration(cur) if cur else '0 min'} so far" + (" this week." if not done else " this week, in total.")
        out["status"] = ("achieved" if lo <= cur <= hi else "missed") if done else ("over" if cur > hi else "in_progress")
    elif kind == "consistency":
        planned = rp.get_setting(conn, "running_days", [0, 2, 4, 5])
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
        hard = []
        if zones:
            for a in runs:
                e = easy_share(conn, a, zones["floors"])
                if e is not None:
                    out["runs"].append({"date": a["local_date"], "source_id": a["source_id"], "value": round(100 * (1 - e)), "met": e >= 0.5,
                                        "rpe": rpes.get(a["source_id"])})
                    hard.append(e < 0.5)
        out["target"] = "No hard runs (most of the time in zones 4–5) this week"
        out["summary"] = f"{sum(hard)} hard run{'s' if sum(hard) != 1 else ''} this week."
        out["status"] = ("achieved" if not any(hard) else "missed") if done else ("in_progress" if not any(hard) else "off_track")
    rp_vals = [r["rpe"] for r in out["runs"] if r.get("rpe")]
    if rp_vals:
        out["felt"] = f"You rated these runs {min(rp_vals)}–{max(rp_vals)} out of 10 for effort." if len(rp_vals) > 1 else \
            f"You rated it {rp_vals[0]} out of 10 for effort."
    return out


def current(conn, source: str, today: date) -> dict:
    ws = week_start(today)
    row = conn.execute("SELECT * FROM weekly_focus WHERE week_start=?", (ws.isoformat(),)).fetchone()
    opts = options(conn, source, today)
    if row is None and opts:
        # Picked for the runner from the data; they can change it, but nothing is required
        with conn:
            conn.execute("INSERT OR IGNORE INTO weekly_focus (week_start, kind, params_json, chosen_at) VALUES (?,?,?,?)",
                         (ws.isoformat(), opts[0]["kind"], json.dumps({"auto": True}), utc_now()))
        row = conn.execute("SELECT * FROM weekly_focus WHERE week_start=?", (ws.isoformat(),)).fetchone()
    prev = conn.execute("SELECT * FROM weekly_focus WHERE week_start=?", ((ws - timedelta(days=7)).isoformat(),)).fetchone()
    return {
        "week_start": ws.isoformat(),
        "current": ({**evaluate(conn, source, ws, row["kind"], today), "auto": json.loads(row["params_json"]).get("auto", False)}
                    if row else None),
        "last_week": evaluate(conn, source, ws - timedelta(days=7), prev["kind"], today) if prev else None,
        "options": opts,
    }


def choose(conn, ws: date, kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(kind)
    with conn:
        conn.execute("INSERT INTO weekly_focus (week_start, kind, params_json, chosen_at) VALUES (?,?,'{}',?) ON CONFLICT (week_start) DO UPDATE SET"
                     " kind=excluded.kind, params_json='{}', chosen_at=excluded.chosen_at", (ws.isoformat(), kind, utc_now()))

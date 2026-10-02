"""Race goal: one upcoming race (date, distance, optional target time) and the training phase implied by the weeks
left. The phases are common periodisation heuristics, not a prescription: base, build, sharpen, taper, race week and
recovery, with taper length by distance. Garmin's race prediction is compared with the target when both exist."""

from __future__ import annotations

from datetime import date

from .db import get_setting

RACE_VERSION = "race-1.1"
DISTANCES = {"5k": ("5 km", 5000), "10k": ("10 km", 10000), "half": ("half marathon", 21097.5), "marathon": ("marathon", 42195)}
TAPER_WEEKS = {"5k": 1, "10k": 1, "half": 2, "marathon": 3}
RECOVERY_DAYS = {"5k": 4, "10k": 7, "half": 10, "marathon": 21}
SHARPEN_WEEKS = 3
BUILD_WEEKS = 6

PHASE_NOTES = {
    "base": "Base phase: mostly easy running and steady weekly volume; hard sessions are a small share.",
    "build": "Build phase: volume rises gradually and race-specific sessions appear, still with easy days between.",
    "sharpen": "Sharpening: keep the key race-pace sessions, stop adding volume.",
    "taper": "Taper: volume comes down while some short race-pace work stays, so you arrive fresh.",
    "race_week": "Race week: short, easy runs with a few strides; rest and sleep matter most now.",
    "recovery": "Recovery after the race: easy running only until you feel normal again.",
}


def clock(s: float) -> str:
    t = int(round(s))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def goal(conn) -> dict | None:
    d, dist = get_setting(conn, "race_date", None), get_setting(conn, "race_distance", None)
    if not d or dist not in DISTANCES:
        return None
    return {"date": d, "distance": dist, "target_s": get_setting(conn, "race_target_s", None), "name": get_setting(conn, "race_name", None)}


def phase(dist: str, days_to_go: int) -> str | None:
    """Training phase from the days left (negative = after the race). None once recovery is over."""
    if days_to_go < 0:
        return "recovery" if -days_to_go <= RECOVERY_DAYS[dist] else None
    if days_to_go <= 6:
        return "race_week"
    weeks = (days_to_go + 6) // 7
    taper = TAPER_WEEKS[dist]
    if weeks <= taper:
        return "taper"
    if weeks <= taper + SHARPEN_WEEKS:
        return "sharpen"
    if weeks <= taper + SHARPEN_WEEKS + BUILD_WEEKS:
        return "build"
    return "base"


def status(conn, today: date) -> dict | None:
    g = goal(conn)
    if g is None:
        return None
    days = (date.fromisoformat(g["date"]) - today).days
    ph = phase(g["distance"], days)
    if ph is None:
        return None  # the race and its recovery are over
    label, metres = DISTANCES[g["distance"]]
    out = {**g, "label": label, "days_to_go": days, "phase": ph, "phase_note": PHASE_NOTES[ph], "algorithm_version": RACE_VERSION,
           "phase_basis": "Common periodisation rules of thumb by weeks to race; not a personal plan."}
    if g.get("target_s"):
        out["target_pace_s_per_km"] = round(g["target_s"] / (metres / 1000), 1)
    pred = ((get_setting(conn, "garmin_fitness", None) or {}).get("race_predictions") or {}).get(g["distance"])
    if pred:
        out["garmin_prediction_s"] = pred
        if g.get("target_s"):
            gap = pred - g["target_s"]
            out["prediction_vs_target_s"] = gap
            out["prediction_text"] = (f"Garmin predicts {clock(pred)}, {clock(abs(gap))} "
                                      f"{'slower than' if gap > 0 else 'faster than' if gap < 0 else 'equal to'} your target of {clock(g['target_s'])}.")
        else:
            out["prediction_text"] = f"Garmin predicts {clock(pred)}."
    title = g.get("name") or f"Your {label}"
    out["headline"] = (f"{title} today" if days == 0 else f"{title} in {days} day{'s' if days != 1 else ''}" if days > 0
                       else f"{title}: {-days} day{'s' if days != -1 else ''} ago")
    return out


# Weekly focus order by phase (overrides the goal-type order while a race is set)
FOCUS_ORDER = {
    "base": ["easy_runs", "consistency", "steady_volume", "even_pacing", "recovery"],
    "build": ["steady_volume", "consistency", "easy_runs", "even_pacing", "recovery"],
    "sharpen": ["even_pacing", "consistency", "easy_runs", "steady_volume", "recovery"],
    "taper": ["recovery", "easy_runs", "even_pacing", "consistency", "steady_volume"],
    "race_week": ["recovery", "easy_runs", "consistency", "even_pacing", "steady_volume"],
    "recovery": ["recovery", "easy_runs", "consistency", "steady_volume", "even_pacing"],
}


# ---------------------------------------------------------------- the week toward the race
# Volume relative to your recent typical week, by phase (rules of thumb). Never more than +10% a week.
VOLUME_FACTOR = {"base": 1.05, "build": 1.08, "sharpen": 1.0, "taper": 0.7, "race_week": 0.5, "recovery": 0.5}
QUALITY = {"base": ["strides"], "build": ["tempo"], "sharpen": ["race_pace", "intervals"], "taper": ["race_pace"],
           "race_week": ["strides"], "recovery": []}
SESSION_TEXT = {
    "easy": "Easy run", "long": "Long run, easy effort", "tempo": "Tempo: a steady comfortably hard block in the middle",
    "intervals": "Intervals: short hard repeats with easy jogs", "race_pace": "Race-pace segments within an easy run",
    "strides": "Easy run with a few short strides at the end", "race": "Race day", "rest": "Rest",
}
QUALITY_MIN = {"tempo": 45, "intervals": 45, "race_pace": 40, "strides": 35}


def week_plan(conn, source: str, today: date) -> dict | None:
    """This week's sessions toward the race: one long run, the phase's quality sessions, the rest easy, sized from your
    recent typical week. Recomputed every day from what you actually ran, so a missed session is not made up later.
    Guardrails: when today's advice holds intensity back or Garmin rates the load above its range, quality becomes
    optional and volume doesn't grow."""
    from datetime import timedelta

    from . import reports as rp
    from .db import first_weekday, week_start
    st = status(conn, today)
    if st is None:
        return None
    first = first_weekday(conn)
    ws = week_start(today, first)
    days = [ws + timedelta(days=k) for k in range(7)]
    run_days = [d for d in days if d.weekday() in get_setting(conn, "running_days", [0, 2, 4, 5])]
    race_day = date.fromisoformat(st["date"])
    past = [sum(a["moving_s"] or 0 for a in rp.activities(conn, source, (ws - timedelta(days=7 * k)).isoformat(),
                                                           (ws - timedelta(days=7 * k - 6)).isoformat())) for k in range(1, 5)]
    ran_weeks = sorted(v for v in past if v > 0)  # weeks without running (e.g. a watch gap) don't count as "typical"
    recent = ran_weeks[len(ran_weeks) // 2] if ran_weeks else 0
    g = get_setting(conn, "garmin_fitness", None) or {}
    ts = g.get("training_status") or {}
    over = ts.get("acute_load") and ts.get("chronic_max") and ts["acute_load"] > ts["chronic_max"]
    morning = rp.build_morning(conn, source, today, False)["recommendation"]
    held = bool(morning.get("suppress_intensity")) or morning["state"] == "consider_easier"
    factor = VOLUME_FACTOR[st["phase"]]
    guard = None
    if (held or over) and factor > 1:
        factor, guard = 1.0, ("Volume held at your recent level: " + ("Garmin rates your load above its range" if over else
                                                                       "today's advice holds intensity back") + ".")
    target_s = round(recent * factor) if recent else None
    acts = {a["local_date"]: a for a in rp.activities(conn, source, ws.isoformat(), (ws + timedelta(days=6)).isoformat())}
    # Session kinds: race day fixed; long run on the last running day before the weekend ends; quality spread out
    kinds: dict[date, str] = {}
    usable = [d for d in run_days if d != race_day and d < race_day + timedelta(days=1) or race_day > days[-1]]
    if days[0] <= race_day <= days[-1]:
        kinds[race_day] = "race"
        usable = [d for d in usable if d < race_day]
    if usable and st["phase"] not in ("race_week", "recovery"):
        kinds[usable[-1]] = "long"
    for q, d in zip(QUALITY[st["phase"]], [d for d in usable if d not in kinds][::2]):
        kinds[d] = q
    for d in usable:
        kinds.setdefault(d, "easy")
    # Minutes: quality fixed, long ~30% of the target, the rest shared by easy days
    long_min = None
    if target_s:
        # About 30% of the week, but never shorter than your longest run of the last four weeks
        recent_runs = rp.activities(conn, source, (ws - timedelta(days=28)).isoformat(), (ws - timedelta(days=1)).isoformat())
        longest = max((a["moving_s"] or 0 for a in recent_runs), default=0) / 60
        long_min = max(round(0.3 * target_s / 60 / 5) * 5, round(longest / 5) * 5)
    q_total = sum(QUALITY_MIN[k] for k in kinds.values() if k in QUALITY_MIN)
    n_easy = sum(1 for k in kinds.values() if k == "easy")
    easy_min = (max(25, round(((target_s / 60) - (long_min or 0) - q_total) / n_easy / 5) * 5) if target_s and n_easy else None)
    # One shared budget: fixed quality lengths, the easy minimum and the long-run floor can add up to more than the week's
    # target, so every session is scaled down together until they fit (5-minute steps, at least 10 minutes)
    planned = {d: {"long": long_min, "easy": easy_min, "rest": None, "race": None}.get(k, QUALITY_MIN.get(k)) for d, k in kinds.items()}
    total = sum(m for m in planned.values() if m)
    if target_s and total > target_s / 60:
        f = target_s / 60 / total
        planned = {d: (max(10, int(m * f / 5) * 5) if m else m) for d, m in planned.items()}
    sessions = []
    for d in days:
        k = kinds.get(d, "rest")
        ran = acts.get(d.isoformat())
        minutes = planned.get(d)
        status_ = ("done" if ran else "rest" if k == "rest" else "missed" if d < today else "today" if d == today else "planned")
        if ran and k == "rest":
            status_ = "extra"
        sessions.append({"date": d.isoformat(), "kind": k, "text": SESSION_TEXT[k], "minutes": minutes,
                         "optional": k in QUALITY_MIN and k != "strides" and (held or over), "status": status_,
                         "ran_minutes": round((ran["moving_s"] or 0) / 60) if ran else None,
                         "source_id": ran["source_id"] if ran else None})
    # A run on a day off stands in for the earliest missed session (days swapped, not a session lost)
    extras = [x for x in sessions if x["status"] == "extra"]
    for m in [x for x in sessions if x["status"] == "missed"]:
        if not extras:
            break
        e = extras.pop(0)
        m["status"], e["status"] = "moved", "done"
        e["kind"], e["text"], e["minutes"], m["moved_to"] = m["kind"], SESSION_TEXT[m["kind"]] + " (moved)", m["minutes"], e["date"]
    done = sum(a["moving_s"] or 0 for a in acts.values())
    if target_s and done >= target_s:
        guard = (guard + " " if guard else "") + "You've already run this week's target; keep anything else short and easy."
    return {"week_start": ws.isoformat(), "phase": st["phase"], "target_minutes": round(target_s / 60) if target_s else None,
            "recent_minutes": round(recent / 60) if recent else None, "done_minutes": round(done / 60), "sessions": sessions,
            "guardrail": guard, "basis": "Rules of thumb by phase from your running days and recent volume; not a personal "
                                         "coaching plan. Durations, not paces. Missed sessions aren't made up later in the week."}

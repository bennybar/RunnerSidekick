"""Race goal: one upcoming race (date, distance, optional target time) and the training phase implied by the weeks
left. The phases are common periodisation heuristics, not a prescription: base, build, sharpen, taper, race week and
recovery, with taper length by distance. Garmin's race prediction is compared with the target when both exist."""

from __future__ import annotations

from datetime import date

from .db import get_setting

RACE_VERSION = "race-1.0"
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

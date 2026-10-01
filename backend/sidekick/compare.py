"""How the runner compares with people of the same sex and age: VO2 max, fitness age, resting heart rate, HRV and
age-graded running times. Deterministic; every comparison names its reference population, method and caveats.
Positions within a reference are interpolated between published percentiles and never extrapolated beyond them."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from . import reports as rp
from .analytics import norms as nm
from .db import get_setting

COMPARE_VERSION = "compare-1.0"
SEX_WORD = {"male": ("man", "men"), "female": ("woman", "women")}
GRADE_CLASSES = ((90, "world class"), (80, "national class"), (70, "regional class"), (60, "local class"))
DISTANCE_LABELS = {"5k": "5 km", "10k": "10 km", "half": "Half marathon", "marathon": "Marathon"}
MIN_RHR_DAYS = 7


def age_on(birth: str, d: date) -> int:
    b = date.fromisoformat(birth if len(birth) > 4 else f"{birth}-07-01")
    return d.year - b.year - ((d.month, d.day) < (b.month, b.day))


def profile(conn, today: date) -> dict:
    """Sex and birth date: the runner's own setting first, else what Garmin reports."""
    src = get_setting(conn, "source_profile", None) or {}
    sex = get_setting(conn, "profile_sex", None) or src.get("sex")
    birth = get_setting(conn, "profile_birth_date", None) or src.get("birth_date")
    source = "settings" if (get_setting(conn, "profile_sex", None) or get_setting(conn, "profile_birth_date", None)) else src.get("source")
    return {"sex": sex, "birth_date": birth, "age": age_on(birth, today) if birth else None, "source": source,
            "detected": {"sex": src.get("sex"), "birth_date": src.get("birth_date")} if src else None}


def group_label(sex: str, lo: int, hi: int) -> str:
    return f"{SEX_WORD[sex][1]} aged {lo}–{hi}" if hi < 120 else f"{SEX_WORD[sex][1]} aged {lo}+"


def nearest_note(outside: bool, age: int, lo: int, hi: int) -> list[str]:
    return [f"The reference has no group for age {age}; the nearest group ({lo}–{hi}) is used."] if outside else []


# ---------------------------------------------------------------- VO2 max

def vo2_typical_age(sex: str, value: float) -> tuple[float | None, str]:
    """Age at which this VO2 max is typical, using the midpoint of the 40th and 60th percentiles as the typical value
    of each age group and interpolating between group midpoints. 'younger'/'older' when outside the table."""
    mids = [(lo + hi + 1) / 2 for lo, hi in nm.VO2_BANDS]
    typical = [(p[0] + p[1]) / 2 for p in nm.VO2[sex]]  # falls with age
    if value >= typical[0]:
        return None, "younger"
    if value <= typical[-1]:
        return None, "older"
    for i in range(len(mids) - 1):
        a, b = typical[i], typical[i + 1]
        if b <= value <= a:
            return mids[i] + (a - value) / (a - b) * (mids[i + 1] - mids[i]), "within"
    return None, "within"


def vo2_item(sex: str, age: int, g: dict) -> dict:
    v = (g.get("vo2max") or {}).get("value")
    base = {"id": "vo2max", "title": "VO₂ max", "source": nm.VO2_SOURCE}
    if v is None:
        return {**base, "status": "unavailable", "headline": "No VO₂ max from Garmin yet",
                "detail": "Garmin estimates VO₂ max from outdoor runs with heart rate."}
    i, outside = nm.band_index(nm.VO2_BANDS, age)
    lo, hi = nm.VO2_BANDS[i]
    pts = nm.VO2[sex][i]
    pct, where = nm.percentile_of(v, pts, nm.VO2_PERCENTILES)
    rating = "Poor" if v < pts[0] else nm.VO2_RATINGS[max(k for k in range(4) if v >= pts[k])]
    grp = group_label(sex, lo, hi)
    if where == "below":
        pos = f"below the 40th percentile for {grp}"
    elif where == "above":
        pos = f"above the 95th percentile for {grp}"
    else:
        pos = f"higher than about {round(pct)}% of {grp}"
    t_age, t_where = vo2_typical_age(sex, v)
    typical = (f"typical for a {SEX_WORD[sex][0]} of about {round(t_age)}" if t_age is not None else
               f"above the typical level of {SEX_WORD[sex][1]} in their twenties" if t_where == "younger" else
               f"below the typical level of {SEX_WORD[sex][1]} in their seventies")
    lo_dom, hi_dom = pts[0] - 8, pts[-1] + 6
    bands = [{"label": "Poor", "from": lo_dom, "to": pts[0]}] + [
        {"label": nm.VO2_RATINGS[k], "from": pts[k], "to": pts[k + 1] if k < 3 else hi_dom} for k in range(4)]
    return {**base, "status": "ok", "value": v, "unit": "mL/kg/min", "rating": rating, "percentile": round(pct) if pct is not None else None,
            "position": where, "group": grp, "typical_age": round(t_age) if t_age is not None else None,
            "headline": f"{rating} for {grp}",
            "detail": f"Your VO₂ max of {v:.1f} (Garmin, {g['vo2max'].get('date') or 'latest'}) is {pos}. It is {typical}.",
            "method": "Garmin's VO₂ max placed among the Cooper Institute ratings for your sex and age group; the position between "
                      "published percentiles is interpolated. 'Typical' is the midpoint of the 40th and 60th percentiles.",
            "caveats": nearest_note(outside, age, lo, hi) + [
                "Garmin's VO₂ max is a watch estimate from pace and heart rate, not a lab test.",
                "The reference comes from people tested at the Cooper Institute clinic, not the general population."],
            "chart": {"type": "bands", "unit": "mL/kg/min", "bands": bands, "value": v, "higher_is_better": True}}


# ---------------------------------------------------------------- fitness age

def fitness_age_item(age: int, g: dict, vo2: dict) -> dict:
    fa = g.get("fitness_age") or {}
    base = {"id": "fitness_age", "title": "Fitness age", "source": "Garmin"}
    if fa.get("fitnessAge") is None:
        return {**base, "status": "unavailable", "headline": "No fitness age from Garmin yet",
                "detail": "Garmin calculates fitness age from VO₂ max, resting heart rate, activity and BMI."}
    f = fa["fitnessAge"]
    real = fa.get("chronologicalAge") or age
    diff = real - f
    trend = None
    if fa.get("previousFitnessAge") is not None:
        ch = f - fa["previousFitnessAge"]
        trend = "about the same as before" if abs(ch) < 0.3 else (f"{abs(ch):.1f} years younger than Garmin's previous value" if ch < 0
                                                                   else f"{ch:.1f} years older than Garmin's previous value")
    head = (f"{abs(diff):.1f} years younger than your age" if diff >= 0.5 else
            f"{abs(diff):.1f} years older than your age" if diff <= -0.5 else "Close to your actual age")
    detail = f"Garmin puts your fitness age at {f:.1f}, against an actual age of {real}."
    if fa.get("achievableFitnessAge") is not None:
        detail += f" Garmin estimates you could reach {fa['achievableFitnessAge']:.1f} with more vigorous activity."
    if trend:
        detail += f" That is {trend}."
    comps = fa.get("components") or {}
    return {**base, "status": "ok", "fitness_age": round(f, 1), "age": real, "achievable": fa.get("achievableFitnessAge"),
            "previous": fa.get("previousFitnessAge"), "typical_vo2_age": vo2.get("typical_age"), "headline": head, "detail": detail,
            "components": {k: comps[k] for k in ("rhr", "bmi", "vigorousDaysAvg", "vigorousMinutesAvg") if k in comps},
            "method": "Garmin's own fitness age. Shown next to the age at which your VO₂ max is typical in the Cooper Institute ratings.",
            "caveats": ["Garmin doesn't publish the exact formula; it combines VO₂ max, resting heart rate, vigorous activity and BMI."],
            "chart": {"type": "ages", "age": real, "fitness_age": round(f, 1),
                      "achievable": round(fa["achievableFitnessAge"], 1) if fa.get("achievableFitnessAge") is not None else None,
                      "vo2_age": vo2.get("typical_age")}}


# ---------------------------------------------------------------- resting heart rate

def rhr_item(conn, source: str, sex: str, age: int, today: date) -> dict:
    base = {"id": "resting_hr", "title": "Resting heart rate", "source": nm.RHR_SOURCE}
    since = (today - timedelta(days=27)).isoformat()
    vals = [v for k, v in rp.series(conn, source, "resting_hr", today.isoformat()).items() if k >= since]
    if len(vals) < MIN_RHR_DAYS:
        return {**base, "status": "unavailable", "headline": "Not enough resting heart rate data yet",
                "detail": f"Needs {MIN_RHR_DAYS} days with a resting heart rate in the last 4 weeks; {len(vals)} so far."}
    v = median(vals)
    i, outside = nm.band_index(nm.RHR_BANDS, age)
    lo, hi = nm.RHR_BANDS[i]
    pts = nm.RHR[sex][i]
    pct, where = nm.percentile_of(v, pts, nm.RHR_PERCENTILES)
    grp = group_label(sex, lo, hi)
    if where == "below":
        pos, lower_than = f"lower than about 97% of {grp}", 97
    elif where == "above":
        pos, lower_than = f"higher than about 97% of {grp}", 3
    else:
        lower_than = round(100 - pct)
        pos = f"lower than about {lower_than}% of {grp}" if lower_than >= 50 else f"higher than about {100 - lower_than}% of {grp}"
    return {**base, "status": "ok", "value": round(v), "unit": "bpm", "days": len(vals), "lower_than_pct": lower_than, "group": grp,
            "headline": f"Lower than about {lower_than}% of {grp}" if lower_than >= 50 else f"Around or above most {grp}",
            "detail": f"Your typical resting heart rate over the last 4 weeks is {round(v)} bpm (median of {len(vals)} days), {pos} "
                      f"in a US national survey, where the middle was {pts[4]} bpm.",
            "method": "Median of Garmin's daily resting heart rate (last 28 days) placed among the survey's published percentiles.",
            "caveats": nearest_note(outside, age, lo, hi) + [
                "The survey measured a seated pulse after about 4 minutes' rest. Garmin's resting heart rate is the lowest stretch of "
                "the day, usually during sleep, so it reads lower, and this comparison flatters you by a few beats.",
                "A low resting heart rate is common in people who train, but on its own it isn't a measure of health."],
            "chart": {"type": "distribution", "unit": "bpm", "percentiles": list(nm.RHR_PERCENTILES), "points": list(pts), "value": round(v),
                      "higher_is_better": False}}


# ---------------------------------------------------------------- HRV

def hrv_item(conn, source: str, today: date) -> dict:
    """Overnight HRV against your own usual range on the current watch (population norms aren't comparable with a
    whole-night average). Weekly medians for the last 12 weeks; a watch change starts a new segment."""
    from .analytics import baseline as bl
    base = {"id": "hrv", "title": "Overnight HRV", "source": "your own nights"}
    # Comparable HRV only: the measurement method currently in use (as in Trends)
    latest = conn.daily_observation.find_one({"source": source, "metric": "hrv_overnight_avg", "state": "measured"}, sort=[("local_date", -1)])
    if latest is None:
        return {**base, "status": "unavailable", "headline": "No overnight HRV yet", "detail": "Garmin records it while you sleep with the watch on."}
    values = rp.series(conn, source, "hrv_overnight_avg", today.isoformat(), latest.get("method"))
    era = rp.device_era_start(conn, source, today)
    in_era = {d: v for d, v in values.items() if not era or d >= era.isoformat()}
    week = [v for d, v in in_era.items() if d >= (today - timedelta(days=6)).isoformat()]
    b = bl.compute_baseline(in_era, today, era_start=era)
    weeks: list[dict] = []
    prev_era = None  # era start of the previous plotted week (None is a valid era: the first watch)
    for k in range(11, -1, -1):
        ws = today - timedelta(days=today.weekday() + 7 * k)
        vals = [v for d, v in values.items() if ws.isoformat() <= d <= (ws + timedelta(days=6)).isoformat()]
        if not vals:
            continue
        e = rp.device_era_start(conn, source, min(ws + timedelta(days=6), today))
        weeks.append({"week": ws.isoformat(), "value": round(median(vals)), "nights": len(vals), "new_watch": bool(weeks) and e != prev_era})
        prev_era = e
    chart = {"type": "weekly_dots", "unit": "ms", "decimals": 0, "step": 5, "points": weeks,
             "band": [round(b.q1), round(b.q3)] if b.sufficient else None}
    if not week:
        return {**base, "status": "unavailable", "headline": "No overnight HRV this week", "chart": chart,
                "detail": "No nights with HRV in the last 7 days."}
    v = round(median(week))
    if not b.sufficient:
        n = len([d for d in in_era if d >= (today - timedelta(days=bl.WINDOW_DAYS)).isoformat()])
        return {**base, "status": "ok", "value": v, "unit": "ms", "headline": f"This week: {v} ms · still learning your range",
                "detail": f"Your usual range needs {bl.MIN_VALID} nights on this watch in the last {bl.WINDOW_DAYS} days; {n} so far.",
                "caveats": ["HRV readings from different watches aren't compared."] if era else [], "chart": chart}
    where = "below" if v < b.q1 else "above" if v > b.q3 else "within"
    return {**base, "status": "ok", "value": v, "unit": "ms",
            "headline": f"This week: {v} ms, {where} your usual range",
            "detail": f"Median of {len(week)} night{'s' if len(week) != 1 else ''} this week, against your usual {round(b.q1)}–{round(b.q3)} ms "
                      f"(middle half of the last {bl.WINDOW_DAYS} days on this watch). Higher or lower than usual is a change worth "
                      "noticing alongside sleep and training, not a verdict on its own.",
            "method": "Weekly median of Garmin's overnight HRV; your usual range is the 25th–75th percentile of the last 28 days on the "
                      "current watch, as for Today's readings.",
            "caveats": ["Population HRV norms are measured differently (short daytime or early-morning windows), so they aren't used."],
            "chart": chart}


# ---------------------------------------------------------------- age grading

def grade_class(pct: float) -> str:
    return next((label for floor, label in GRADE_CLASSES if pct >= floor), "recreational")


def age_grade(sex: str, age: int, dist: str, seconds: float) -> dict | None:
    std = nm.age_standards()["standards"][sex].get(dist, {})
    a = str(min(max(age, 5), 100))
    if a not in std or not seconds:
        return None
    open_std = min(std.values())  # the open-class (fastest) standard
    pct = 100 * std[a] / seconds
    return {"age_grade_pct": round(pct, 1), "class": grade_class(pct), "standard_s": std[a],
            "age_graded_time_s": round(seconds * open_std / std[a])}


def age_grade_item(conn, source: str, sex: str, birth: str, g: dict, today: date) -> dict:
    base = {"id": "age_grade", "title": "Age-graded running", "source": "USATF / Alan Jones 2025 road age standards"}
    rows = []
    for k, r in rp.records(conn, source).items():
        if k in DISTANCE_LABELS and r["best"]:
            ag = age_grade(sex, age_on(birth, date.fromisoformat(r["best"]["date"])), k, r["best"]["elapsed_s"])
            if ag:
                rows.append({"distance": k, "label": DISTANCE_LABELS[k], "kind": "best", "time_s": r["best"]["elapsed_s"],
                             "date": r["best"]["date"], "source_id": r["best"]["source_id"], **ag})
    pred = g.get("race_predictions") or {}
    today_age = age_on(birth, today)
    for k in DISTANCE_LABELS:
        if pred.get(k):
            ag = age_grade(sex, today_age, k, pred[k])
            if ag:
                rows.append({"distance": k, "label": DISTANCE_LABELS[k], "kind": "prediction", "time_s": pred[k], "date": pred.get("date"), **ag})
    if not rows:
        return {**base, "status": "unavailable", "headline": "No times to grade yet",
                "detail": "Needs a run of 5 km or longer, or Garmin race predictions."}
    best = max((r for r in rows if r["kind"] == "best"), key=lambda r: r["age_grade_pct"], default=None)
    top = best or max(rows, key=lambda r: r["age_grade_pct"])
    what = "best" if top["kind"] == "best" else "Garmin-predicted"
    return {**base, "status": "ok", "rows": rows,
            "headline": f"{top['age_grade_pct']:.0f}% age grade: {top['class']}",
            "detail": f"Your {what} {top['label'].lower()} time is {top['age_grade_pct']:.0f}% of the age standard for a "
                      f"{SEX_WORD[sex][0]} of your age ({top['class']}). 100% is about world-record level for your age.",
            "method": "Age grade = the age standard for your sex, age and distance divided by your time. Classes: 60% local, 70% regional, "
                      "80% national, 90% world class (below 60% is called recreational here). The age-graded time is your time converted to its open-age equivalent.",
            "caveats": ["Your bests are the fastest stretch within a run, not race results; age grading is designed for races.",
                        "Garmin's race predictions are estimates, shown separately from times you actually ran."],
            "chart": {"type": "age_grade", "classes": [c[0] for c in reversed(GRADE_CLASSES)], "rows": rows}}


# ---------------------------------------------------------------- all

def build(conn, source: str, today: date) -> dict:
    p = profile(conn, today)
    missing = [k for k, v in (("sex", p["sex"]), ("birth date", p["birth_date"])) if not v]
    out = {"profile": p, "missing": missing, "items": [], "algorithm_version": COMPARE_VERSION}
    if missing:
        return out
    g = rp.get_setting(conn, "garmin_fitness", None) or {}
    vo2 = vo2_item(p["sex"], p["age"], g)
    out["items"] = [vo2, fitness_age_item(p["age"], g, vo2), rhr_item(conn, source, p["sex"], p["age"], today),
                    age_grade_item(conn, source, p["sex"], p["birth_date"], g, today), hrv_item(conn, source, today)]
    return out

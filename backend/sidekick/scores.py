"""Two headline numbers for Today, each 0–100, with fixed weights and every part tied to a published reference.
Nothing is counted twice; a missing part is listed and the score marked partial; a score needs its required parts
(Fitness: VO2 max; Health: some movement and some sleep). Each score says how it moved over 4 weeks when the same
parts existed then. Deterministic; not a medical score.

Fitness is capacity: Garmin's VO2 max for your age and sex (Cooper/ACSM table; outside the table it says "below the
40th" or "above the 95th percentile" rather than inventing one). Recent age-graded running and training consistency
are shown with it as context, not counted, because they mix capacity with habits.
Health: weekly activity against the WHO guideline (150–300 moderate-equivalent minutes; vigorous counts double), daily
steps (Paluch et al. 2022: benefit levels off around 8,000–10,000 under 60, 6,000–8,000 from 60), sleep length scored
night by night (7 h or more; long nights aren't penalised), sleep regularity (how much mid-sleep moves) and sleep
efficiency (time asleep out of time in bed; 85% is the usual clinical line). Resting heart rate is shown as context
with its own 4-week change: Garmin's lowest-30-minute value isn't comparable to the seated population references.
Left out: Garmin's fitness age (built from VO2 max and resting HR), HRV (readiness uses it), Garmin's sedentary time
(includes standing, so it isn't comparable to sitting-time research), sleep stages and stress (no solid reference
ranges for consumer watches)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median, pstdev

from . import compare
from . import reports as rp
from .analytics import norms as nm

SCORES_VERSION = "scores-3.0"
FITNESS_WEIGHTS = {"vo2max": 100}  # capacity only; performance and consistency are shown as context
HEALTH_WEIGHTS = {"activity": 30, "steps": 25, "sleep_length": 20, "sleep_regularity": 15, "sleep_efficiency": 10}
# A score needs one part from each group: Fitness a VO2 max; Health some movement and some sleep
FITNESS_REQUIRED = [{"vo2max"}]
HEALTH_REQUIRED = [{"activity", "steps"}, {"sleep_length"}]
MIN_HISTORY_WEEKS = 4
TREND_DAYS = 28


def clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def vo2_points(sex: str, age: int, v: float) -> float:
    """The VO2 max percentile for your group; below the published 40th or above the 95th it is extended linearly
    (10 mL/kg/min below the 40th point = 0) and capped at 0–100."""
    i, _ = nm.band_index(nm.VO2_BANDS, age)
    pts = nm.VO2[sex][i]
    pct, where = nm.percentile_of(v, pts, nm.VO2_PERCENTILES)
    if where == "below":
        return clamp(40 * (v - (pts[0] - 10)) / 10)
    if where == "above":
        return clamp(95 + (v - pts[-1]))
    return pct


def label(score: int) -> str:
    return "Excellent" if score >= 85 else "Very good" if score >= 70 else "Good" if score >= 55 else "Fair" if score >= 40 else "Low"


def combine(parts: list[dict], weights: dict[str, int]) -> dict:
    have = [p for p in parts if p.get("points") is not None]
    if len(have) < 2:
        return {"status": "unavailable", "components": parts, "detail": "Needs at least two of the readings below."}
    total = sum(weights[p["id"]] for p in have)
    score = round(sum(p["points"] * weights[p["id"]] for p in have) / total)
    for p in parts:
        p["weight_pct"] = round(100 * weights[p["id"]] / total) if p.get("points") is not None else 0
    return {"status": "ok", "score": score, "label": label(score), "components": parts, "used": len(have), "of": len(parts)}


def verdict(points: int | None) -> str:
    return "unknown" if points is None else "good" if points >= 75 else "ok" if points >= 50 else "low"


def part(pid: str, title: str, points: float | None, say: str, note: str, improve: tuple | None = None) -> dict:
    """improve: (a step worked out from this part's numbers, the points the part would reach, the time it takes)."""
    pts = None if points is None else round(clamp(points))
    out = {"id": pid, "title": title, "points": pts, "say": say, "note": note, "verdict": verdict(pts), "value": say if pts is not None else None}
    if improve and pts is not None and improve[1] > pts:
        out["improve"] = {"text": improve[0], "target_points": round(clamp(improve[1])), "horizon": improve[2] if len(improve) > 2 else None}
    return out


def clock(sec: float) -> str:
    t = round(sec)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def vo2_on(conn, source: str, d: date, today: date) -> float | None:
    """Garmin's VO2 max as of d: the latest daily reading up to then (today also falls back to Garmin's current value)."""
    s = rp.series(conn, source, "garmin_vo2max_running", d.isoformat())
    recent = [v for k, v in sorted(s.items()) if k >= (d - timedelta(days=60)).isoformat()]
    if recent:
        return recent[-1]
    return ((rp.get_setting(conn, "garmin_fitness", None) or {}).get("vo2max") or {}).get("value") if d == today else None


def history_start(conn, source: str) -> date | None:
    """The first day with any synced activity: weeks before it are unknown, not missed."""
    a = conn.activity.find_one({"source": source}, sort=[("local_date", 1)])
    return date.fromisoformat(a["local_date"]) if a else None


def fitness_parts(conn, source: str, d: date, today: date, sex: str, birth: str, hold_back: bool = False) -> list[dict]:
    age = compare.age_on(birth, d)
    parts = []
    v = vo2_on(conn, source, d, today)
    if v:
        i, _ = nm.band_index(nm.VO2_BANDS, age)
        lo, hi = nm.VO2_BANDS[i]
        pts = vo2_points(sex, age, v)
        grp = compare.group_label(sex, lo, hi)
        _, where = nm.percentile_of(v, nm.VO2[sex][i], nm.VO2_PERCENTILES)
        # Inside the published table: its percentile. Outside it: only the table's edge, never an invented percentile.
        rank = ("below the 40th percentile" if where == "below" else "above the 95th percentile" if where == "above"
                else f"better than about {round(pts)}%")
        nxt = next(((t, p) for t, p in zip(nm.VO2[sex][i], nm.VO2_PERCENTILES) if t > v), None)
        how = ("keep building easy running now; add a harder session once readiness allows" if hold_back
               else "mostly easy running with one harder session a week is the usual way up")
        imp = (f"Reaching VO₂ max {nxt[0]:.1f} (+{nxt[0] - v:.1f}) would put you above {nxt[1]}% of {grp}: {how}", vo2_points(sex, age, nxt[0]),
               "over months") if nxt else None
        parts.append(part("vo2max", "VO₂ max for your age", pts, f"{v:.1f} · {rank} of {grp}",
                          "Garmin's VO₂ max against the Cooper/ACSM table for your age and sex", imp))
    else:
        parts.append(part("vo2max", "VO₂ max for your age", None, "No VO₂ max from Garmin yet", "Needs a recent VO₂ max from Garmin"))
    # Context: recent age-graded running (the best graded effort of the last 90 days)
    best = None
    for a in rp.activities(conn, source, (d - timedelta(days=89)).isoformat(), d.isoformat()):
        for k, e in rp.efforts_for(conn, a).items():
            if k in compare.DISTANCE_LABELS:
                ag = compare.age_grade(sex, compare.age_on(birth, date.fromisoformat(a["local_date"])), k, e["elapsed_s"])
                if ag and (best is None or ag["age_grade_pct"] > best[0]):
                    best = (ag["age_grade_pct"], ag["class"], compare.DISTANCE_LABELS[k])
    parts.append(context(part("age_grade", "Recent running, age-graded", (best[0] - 40) * 2 if best else None,
                              f"{best[0]:.0f}% ({best[1]}) · best {best[2].lower()} stretch of the last 90 days" if best else "No 5 km+ effort in 90 days",
                              "Fastest stretch inside any run, not necessarily a hard effort; shown for context")))
    # Context: training consistency over the weeks history actually covers (up to 8), never counting unknown weeks
    ws = rp.week_start(d, rp.first_weekday(conn))
    first = history_start(conn, source)
    weeks = [w for w in (ws - timedelta(days=7 * k) for k in range(1, 9)) if first and w >= rp.week_start(first, rp.first_weekday(conn))]
    if len(weeks) >= MIN_HISTORY_WEEKS:
        runs = rp.activities(conn, source, weeks[-1].isoformat(), (ws - timedelta(days=1)).isoformat())
        good = 0
        for w in weeks:
            wk = [a for a in runs if w.isoformat() <= a["local_date"] <= (w + timedelta(days=6)).isoformat()]
            minutes = sum(a["moving_s"] or 0 for a in wk) / 60
            good += (len(wk) >= 2 and minutes >= 40) or minutes >= 75  # two short jogs alone don't make a training week
        parts.append(context(part("regularity", "Training consistency", 100 * good / len(weeks),
                                  f"{good} of the last {len(weeks)} weeks with 2+ runs (40+ min) or 75+ min",
                                  "Weeks with synced history only; shown for context")))
    else:
        parts.append(context(part("regularity", "Training consistency", None, f"Needs {MIN_HISTORY_WEEKS} weeks of history",
                                  "Weeks with synced history only")))
    return parts


def context(p: dict) -> dict:
    """Shown in the breakdown, not counted in the score."""
    p["context"] = True
    p.pop("improve", None)
    return p


def health_parts(conn, source: str, d: date, age: int | None) -> list[dict]:
    parts = []
    # Activity against the WHO guideline: moderate + 2 × vigorous minutes, weekly average over days with data (10+ of 28)
    since = (d - timedelta(days=27)).isoformat()
    mod = {k: v for k, v in rp.series(conn, source, "intensity_minutes_moderate", d.isoformat()).items() if k >= since}
    vig = {k: v for k, v in rp.series(conn, source, "intensity_minutes_vigorous", d.isoformat()).items() if k >= since}
    days = sorted(set(mod) | set(vig))
    if len(days) >= 10:
        m = 7 * sum(mod.get(x, 0) + 2 * vig.get(x, 0) for x in days) / len(days)
        goal = 150 if m < 150 else 300
        parts.append(part("activity", "Weekly activity", 70 * m / 150 if m <= 150 else 70 + 30 * min(1, (m - 150) / 150),
                          f"{round(m)} min a week · WHO: 150–300",
                          f"Garmin's intensity minutes, vigorous counted double, over {len(days)} days with data in the last 4 weeks; "
                          "150 scores 70, 300 scores 100",
                          (f"About {round(goal - m)} more active minutes a week would reach {goal}; vigorous minutes count double",
                           70 if goal == 150 else 100, "over 4 weeks")))
    else:
        parts.append(part("activity", "Weekly activity", None, f"Needs 10 days of intensity minutes ({len(days)} so far)",
                          "Garmin's intensity minutes, last 4 weeks"))
    # Daily steps against Paluch et al. 2022 (mortality falls up to about 8,000 under 60, about 6,000–8,000 from 60)
    target = 6000 if age is not None and age >= 60 else 8000
    st = [v for k, v in rp.series(conn, source, "steps", d.isoformat()).items() if k >= (d - timedelta(days=13)).isoformat()]
    if len(st) >= 7:
        avg = sum(st) / len(st)
        parts.append(part("steps", "Daily steps", 100 * (avg - 2000) / (target - 2000), f"{round(avg):,} a day · benefit levels off near {target:,}",
                          f"Average of the last 2 weeks ({len(st)} days); 2,000 scores 0, {target:,} scores 100 (Paluch et al. 2022)",
                          (f"About {round(target - avg):,} more steps a day would reach {target:,}", 100, "over 2 weeks")))
    else:
        parts.append(part("steps", "Daily steps", None, "Needs 7 days of steps", "Average of the last 2 weeks"))
    # Sleep length, night by night: each night under 7 h loses points; long nights aren't penalised
    nights = [v for k, v in rp.series(conn, source, "sleep_duration", d.isoformat()).items() if k >= (d - timedelta(days=13)).isoformat()]
    if len(nights) >= 5:
        hrs = [n / 3600 for n in nights]
        short = sum(1 for h in hrs if h < 7)
        typ = median(hrs)
        parts.append(part("sleep_length", "Sleep length", sum(clamp(100 - 40 * max(0, 7 - h)) for h in hrs) / len(hrs),
                          f"{int(typ)} h {round((typ % 1) * 60):02d} min typical · {short} of {len(hrs)} nights under 7 h",
                          "Each night: 7 h or more scores 100, −40 per hour short; long nights aren't penalised (a heuristic)",
                          (f"Getting {short} short night{'s' if short != 1 else ''} up to 7 hours", 100, "over 2 weeks") if short else None))
    else:
        parts.append(part("sleep_length", "Sleep length", None, "Needs 5 nights in two weeks", "Night by night, last two weeks"))
    sessions = list(conn.sleep_session.find({"source": source, "is_nap": {"$ne": True},
                                             "wake_date": {"$gte": (d - timedelta(days=13)).isoformat(), "$lte": d.isoformat()}}))
    # Regularity: spread of the mid-sleep time
    mids = []
    for s in sessions:
        try:
            st_ = datetime.fromisoformat(s["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=s.get("utc_offset_s") or 0)
            en = datetime.fromisoformat(s["end_utc"].replace("Z", "+00:00")) + timedelta(seconds=s.get("utc_offset_s") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        mid = st_ + (en - st_) / 2
        mids.append(((mid.hour * 60 + mid.minute) - 12 * 60) % (24 * 60))
    if len(mids) >= 5:
        sd = pstdev(mids)
        parts.append(part("sleep_regularity", "Sleep regularity", 100 if sd <= 30 else 100 - (sd - 30) * 4 / 3,
                          f"Mid-sleep varies about ±{round(sd)} min", "Spread of mid-sleep over two weeks; ±30 min scores 100, ±105 scores 0",
                          (f"Keeping bed and wake times within about 30 minutes, weekends too (now ±{round(sd)} min)", 100, "over 2 weeks")
                          if sd > 30 else None))
    else:
        parts.append(part("sleep_regularity", "Sleep regularity", None, "Needs 5 nights in two weeks", "Spread of mid-sleep"))
    # Efficiency: time asleep out of time in bed (asleep + awake)
    eff = [s["duration_s"] / (s["duration_s"] + (s.get("awake_s") or 0)) for s in sessions if s.get("duration_s")]
    if len(eff) >= 5:
        e = sum(eff) / len(eff)
        parts.append(part("sleep_efficiency", "Sleep efficiency", (100 * e - 75) * 100 / 15, f"{100 * e:.0f}% of time in bed asleep",
                          "Average over two weeks; 90% or more scores 100, 75% scores 0 (85% is the usual clinical line)"))
    else:
        parts.append(part("sleep_efficiency", "Sleep efficiency", None, "Needs 5 nights in two weeks", "Time asleep out of time in bed"))
    # Context: resting heart rate as your own 4-week change (not a population rank: different measurement)
    def med(end: date) -> float | None:
        v = [x for k, x in rp.series(conn, source, "resting_hr", end.isoformat()).items() if k >= (end - timedelta(days=27)).isoformat()]
        return median(v) if len(v) >= 7 else None
    now, then = med(d), med(d - timedelta(days=28))
    say = ("Not enough days yet" if now is None else f"{round(now)} bpm · 4-week median" + (
        "" if then is None else " · same as 4 weeks before" if round(now) == round(then)
        else f" · {abs(round(now - then))} {'lower' if now < then else 'higher'} than 4 weeks before"))
    rhr = part("resting_hr", "Resting heart rate", None, say, "Garmin's lowest 30-minute value of the day; your own trend, not counted")
    rhr["verdict"] = "info" if now is not None else "unknown"
    parts.append(context(rhr))
    return parts


IMPROVE_SHOWN = 2


def score(parts: list[dict], weights: dict[str, int], required: list[set]) -> dict:
    scored = [p for p in parts if not p.get("context")]
    have = {p["id"] for p in scored if p["points"] is not None}
    missing = [p["title"] for p in scored if p["points"] is None]
    if not all(group & have for group in required):
        return {"status": "unavailable", "components": parts, "missing": missing,
                "detail": "Needs " + " and ".join(" or ".join(next(p["title"].lower() for p in scored if p["id"] == i) for i in sorted(g))
                                                  for g in required if not g & have) + "."}
    total = sum(weights[p["id"]] for p in scored if p["points"] is not None)
    for p in scored:
        p["weight_pct"] = round(100 * weights[p["id"]] / total) if p["points"] is not None else 0
    value = round(sum(p["points"] * weights[p["id"]] for p in scored if p["points"] is not None) / total)
    out = {"status": "partial" if missing else "ok", "score": value, "label": label(value), "components": parts, "missing": missing,
           "used": len(have), "of": len(scored)}
    # Potential score changes: what the formula would give if a part reached its target (not a prediction of effort)
    steps = [{"part": p["title"], "text": p["improve"]["text"], "horizon": p["improve"].get("horizon"),
              "gain": round(p["weight_pct"] * (p["improve"]["target_points"] - p["points"]) / 100)}
             for p in scored if p.get("improve") and p["points"] is not None]
    out["improve"] = sorted((x for x in steps if x["gain"] >= 1), key=lambda x: -x["gain"])[:IMPROVE_SHOWN]
    return out


def build(conn, source: str, today: date, hold_back: bool = False) -> dict:
    prof = compare.profile(conn, today)
    age = compare.age_on(prof["birth_date"], today) if prof["birth_date"] else None
    health = score(health_parts(conn, source, today, age), HEALTH_WEIGHTS, HEALTH_REQUIRED)
    old_health = score(health_parts(conn, source, today - timedelta(days=TREND_DAYS), age), HEALTH_WEIGHTS, HEALTH_REQUIRED)
    if prof["sex"] and prof["birth_date"]:
        fitness = score(fitness_parts(conn, source, today, today, prof["sex"], prof["birth_date"], hold_back), FITNESS_WEIGHTS, FITNESS_REQUIRED)
        old_fit = score(fitness_parts(conn, source, today - timedelta(days=TREND_DAYS), today, prof["sex"], prof["birth_date"]),
                        FITNESS_WEIGHTS, FITNESS_REQUIRED)
    else:
        fitness = {"status": "unavailable", "components": [], "missing": [], "detail": "Needs your sex and birth date (from Garmin or Settings)."}
        old_fit = fitness
    # Trend only between comparable calculations: the same scored parts available then and now
    for cur, old in ((fitness, old_fit), (health, old_health)):
        same = {p["id"] for p in cur["components"] if p["points"] is not None and not p.get("context")} == \
               {p["id"] for p in old["components"] if p["points"] is not None and not p.get("context")}
        if cur.get("score") is not None and old.get("score") is not None and same:
            cur["trend"] = {"delta": cur["score"] - old["score"], "days": TREND_DAYS}
    return {"status": "ok", "age": age, "sex": prof["sex"], "fitness": fitness, "health": health,
            "basis": "Fixed weights; every counted part is tied to a published reference. Missing parts are listed, never guessed. "
                     "Context lines aren't counted. A summary of the readings, not a medical score.",
            "algorithm_version": SCORES_VERSION}

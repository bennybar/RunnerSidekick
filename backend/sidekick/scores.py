"""Two headline numbers for Today: a fitness score and a health score, each 0–100. Every part is tied to a published
reference, nothing is counted twice, and the weights are fixed. A missing part is listed as missing and the score is
marked partial (it's then the weighted average of the parts that exist; at least two are needed). Each score also
says how it moved over 4 weeks. Deterministic; not a medical score.

Fitness: VO2 max for your age and sex (Cooper/ACSM percentiles), recent age-graded running (USATF/Alan Jones 2025
standards, best of the last 90 days) and training regularity (weeks with 2+ runs or 75+ minutes).
Health: weekly activity against the WHO guideline (150–300 moderate-equivalent minutes; vigorous counts double),
resting heart rate for your age and sex (CDC/NHANES), sleep length (7–9 h) and sleep regularity (how much the middle of
your sleep moves night to night). Garmin's fitness age (built from VO2 max and resting HR) and HRV (a day-to-day
recovery signal, used by readiness) are left out on purpose."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median, pstdev

from . import compare
from . import reports as rp
from .analytics import norms as nm

SCORES_VERSION = "scores-2.0"
FITNESS_WEIGHTS = {"vo2max": 50, "age_grade": 25, "regularity": 25}
HEALTH_WEIGHTS = {"activity": 30, "resting_hr": 25, "sleep_length": 25, "sleep_regularity": 20}
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


def part(pid: str, title: str, points: float | None, say: str, note: str, improve: tuple[str, float] | None = None) -> dict:
    """improve: one concrete step worked out from this part's numbers, and the points the part would reach with it."""
    pts = None if points is None else round(clamp(points))
    out = {"id": pid, "title": title, "points": pts, "say": say, "note": note, "verdict": verdict(pts), "value": say if pts is not None else None}
    if improve and pts is not None and improve[1] > pts:
        out["improve"] = {"text": improve[0], "target_points": round(clamp(improve[1]))}
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


def fitness_parts(conn, source: str, d: date, today: date, sex: str, birth: str) -> list[dict]:
    age = compare.age_on(birth, d)
    parts = []
    v = vo2_on(conn, source, d, today)
    if v:
        i, _ = nm.band_index(nm.VO2_BANDS, age)
        lo, hi = nm.VO2_BANDS[i]
        pts = vo2_points(sex, age, v)
        grp = compare.group_label(sex, lo, hi)
        nxt = next(((t, p) for t, p in zip(nm.VO2[sex][i], nm.VO2_PERCENTILES) if t > v), None)
        imp = (f"VO₂ max {nxt[0]:.1f} (+{nxt[0] - v:.1f}) would put you above {nxt[1]}% of {grp}; mostly easy running with one "
               "harder session a week is the usual way up", vo2_points(sex, age, nxt[0])) if nxt else None
        parts.append(part("vo2max", "VO₂ max for your age", pts, f"{v:.1f} · better than about {round(pts)}% of {grp}"
                          if 0 < pts < 100 else f"{v:.1f}", "Garmin's VO₂ max as a percentile of your age and sex group (Cooper/ACSM)", imp))
    else:
        parts.append(part("vo2max", "VO₂ max for your age", None, "No VO₂ max from Garmin yet", "Needs a recent VO₂ max from Garmin"))
    # Recent age-graded running: the best graded effort of the last 90 days, not an all-time best
    best = None
    for a in rp.activities(conn, source, (d - timedelta(days=89)).isoformat(), d.isoformat()):
        for k, e in rp.efforts_for(conn, a).items():
            if k in compare.DISTANCE_LABELS:
                ag = compare.age_grade(sex, compare.age_on(birth, date.fromisoformat(a["local_date"])), k, e["elapsed_s"])
                if ag and (best is None or ag["age_grade_pct"] > best[0]):
                    best = (ag["age_grade_pct"], ag["class"], compare.DISTANCE_LABELS[k], e["elapsed_s"], ag["standard_s"])
    imp = None
    if best:
        goal = best[0] + 5
        imp = (f"A {best[2].lower()} in {clock(best[4] * 100 / goal)} (now {clock(best[3])}) would be a {goal:.0f}% age grade", (goal - 40) * 2)
    parts.append(part("age_grade", "Recent running, age-graded", (best[0] - 40) * 2 if best else None,
                      f"{best[0]:.0f}% ({best[1]}) · best {best[2].lower()} effort of the last 90 days" if best else "No 5 km+ effort in 90 days",
                      "Age grade of your best effort in the last 90 days; 40% scores 0, 90% (world class) scores 100", imp))
    # Regularity: weeks with a real training stimulus (2+ runs or 75+ minutes), last 8 complete weeks
    ws = rp.week_start(d, rp.first_weekday(conn))
    weeks = [ws - timedelta(days=7 * k) for k in range(1, 9)]
    runs = rp.activities(conn, source, weeks[-1].isoformat(), (ws - timedelta(days=1)).isoformat())
    good = 0
    for w in weeks:
        wk = [a for a in runs if w.isoformat() <= a["local_date"] <= (w + timedelta(days=6)).isoformat()]
        good += len(wk) >= 2 or sum(a["moving_s"] or 0 for a in wk) >= 75 * 60
    parts.append(part("regularity", "Training regularity", 100 * good / 8, f"{good} of 8 weeks with 2+ runs or 75+ min",
                      "Last 8 complete weeks; a week counts with at least 2 runs or 75 minutes of running",
                      (f"Make every week count: at least 2 runs or 75 minutes. {8 - good} of the last 8 weeks fell short", 100)))
    return parts


def health_parts(conn, source: str, d: date, sex: str, birth: str) -> list[dict]:
    age = compare.age_on(birth, d)
    parts = []
    # Activity against the WHO guideline: moderate + 2 × vigorous minutes, as a weekly average over the days with data in
    # the last 4 weeks (at least 10 of them)
    since = (d - timedelta(days=27)).isoformat()
    mod = {k: v for k, v in rp.series(conn, source, "intensity_minutes_moderate", d.isoformat()).items() if k >= since}
    vig = {k: v for k, v in rp.series(conn, source, "intensity_minutes_vigorous", d.isoformat()).items() if k >= since}
    days = sorted(set(mod) | set(vig))
    if len(days) >= 10:
        m = 7 * sum(mod.get(x, 0) + 2 * vig.get(x, 0) for x in days) / len(days)
        pts = 70 * m / 150 if m <= 150 else 70 + 30 * min(1, (m - 150) / 150)
        goal = 150 if m < 150 else 300
        parts.append(part("activity", "Weekly activity", pts, f"{round(m)} min a week · WHO: 150–300",
                          f"Garmin's intensity minutes, vigorous counted double, weekly average over {len(days)} days with data in the last "
                          "4 weeks; 150 scores 70, 300 scores 100",
                          (f"About {round(goal - m)} more active minutes a week reaches {'the WHO minimum' if goal == 150 else 'the top of the WHO range'} "
                           f"({goal}); vigorous minutes count double", 70 if goal == 150 else 100)))
    else:
        parts.append(part("activity", "Weekly activity", None, f"Needs 10 days of intensity minutes ({len(days)} so far)",
                          "Garmin's intensity minutes, last 4 weeks"))
    r = compare.rhr_item(conn, source, sex, age, d)
    parts.append(part("resting_hr", "Resting heart rate for your age", r.get("lower_than_pct") if r["status"] == "ok" else None,
                      f"{r['value']} bpm · lower than about {r['lower_than_pct']}% of {r['group']}" if r["status"] == "ok" else "Not enough days yet",
                      "Your 4-week median against the CDC/NHANES distribution for your age and sex",
                      ("Resting heart rate usually comes down with regular easy running and enough sleep", 75)
                      if r["status"] == "ok" and r["lower_than_pct"] < 75 else None))
    nights = [s for k, s in rp.series(conn, source, "sleep_duration", d.isoformat()).items() if k >= (d - timedelta(days=13)).isoformat()]
    if len(nights) >= 5:
        h = median(nights) / 3600
        parts.append(part("sleep_length", "Sleep length", 100 if 7 <= h <= 9 else 100 - 40 * (7 - h) if h < 7 else 100 - 40 * (h - 9),
                          f"{int(h)} h {round((h % 1) * 60):02d} min a night", "Typical night over two weeks; 7–9 h scores 100, −40 per hour outside",
                          (f"About {round((7 - h) * 60)} more minutes of sleep a night reaches 7 hours", 100) if h < 7 else None))
    else:
        parts.append(part("sleep_length", "Sleep length", None, "Needs 5 nights in two weeks", "Typical night over two weeks"))
    # Regularity: how far the middle of your sleep moves from night to night (standard deviation, main sleep only)
    mids = []
    for s in conn.sleep_session.find({"source": source, "is_nap": {"$ne": True}, "wake_date": {"$gte": (d - timedelta(days=13)).isoformat(),
                                                                                              "$lte": d.isoformat()}}):
        try:
            st = datetime.fromisoformat(s["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=s.get("utc_offset_s") or 0)
            en = datetime.fromisoformat(s["end_utc"].replace("Z", "+00:00")) + timedelta(seconds=s.get("utc_offset_s") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        mid = st + (en - st) / 2
        mids.append(((mid.hour * 60 + mid.minute) - 12 * 60) % (24 * 60))  # minutes after noon, so nights don't wrap
    if len(mids) >= 5:
        sd = pstdev(mids)
        parts.append(part("sleep_regularity", "Sleep regularity", 100 if sd <= 30 else 100 - (sd - 30) * 4 / 3,
                          f"Mid-sleep varies about ±{round(sd)} min", "Spread of your mid-sleep time over two weeks; ±30 min or less scores 100, ±105 scores 0",
                          (f"Keep bed and wake times within about 30 minutes, weekends too (now ±{round(sd)} min)", 100) if sd > 30 else None))
    else:
        parts.append(part("sleep_regularity", "Sleep regularity", None, "Needs 5 nights in two weeks", "Spread of your mid-sleep time"))
    return parts


IMPROVE_SHOWN = 2


def score(parts: list[dict], weights: dict[str, int]) -> dict:
    out = combine(parts, weights)
    if out["status"] == "ok":
        missing = [p["title"] for p in parts if p["points"] is None]
        if missing:
            out.update(status="partial", missing=missing)
        # The steps that would lift this score most, each with the points it would add (from the part's weight)
        steps = [{"part": p["title"], "text": p["improve"]["text"],
                  "gain": round(p["weight_pct"] * (p["improve"]["target_points"] - p["points"]) / 100)}
                 for p in parts if p.get("improve") and p["points"] is not None]
        out["improve"] = sorted((x for x in steps if x["gain"] >= 1), key=lambda x: -x["gain"])[:IMPROVE_SHOWN]
    return out


def build(conn, source: str, today: date) -> dict:
    prof = compare.profile(conn, today)
    if not prof["sex"] or not prof["birth_date"]:
        return {"status": "unavailable", "missing": [k for k in ("sex", "birth_date") if not prof[k]], "algorithm_version": SCORES_VERSION}
    sex, birth = prof["sex"], prof["birth_date"]
    fitness = score(fitness_parts(conn, source, today, today, sex, birth), FITNESS_WEIGHTS)
    health = score(health_parts(conn, source, today, sex, birth), HEALTH_WEIGHTS)
    # How each score moved: the same calculation 4 weeks ago, compared only when the same parts were available
    then = today - timedelta(days=TREND_DAYS)
    for cur, old in ((fitness, score(fitness_parts(conn, source, then, today, sex, birth), FITNESS_WEIGHTS)),
                     (health, score(health_parts(conn, source, then, sex, birth), HEALTH_WEIGHTS))):
        same = {p["id"] for p in cur["components"] if p["points"] is not None} == {p["id"] for p in old["components"] if p["points"] is not None}
        if cur.get("score") is not None and old.get("score") is not None and same:
            cur["trend"] = {"delta": cur["score"] - old["score"], "days": TREND_DAYS}
    return {"status": "ok", "age": compare.age_on(birth, today), "sex": sex, "fitness": fitness, "health": health,
            "basis": "Each part is tied to a published reference for your age and sex where one exists, with fixed weights. "
                     "Missing parts are listed, never guessed. A summary of the readings, not a medical score.",
            "algorithm_version": SCORES_VERSION}

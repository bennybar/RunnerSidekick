"""Two headline numbers for Today: a fitness score and a health score, each 0–100 and judged against people of your
age and sex where a reference exists. Deterministic and transparent: every component shows its value, its points and
its weight. Missing components are left out and the remaining weights are rescaled; a score needs at least two
components. Not a medical score."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from . import compare
from . import reports as rp
from .analytics import norms as nm

SCORES_VERSION = "scores-1.0"
FITNESS_WEIGHTS = {"vo2max": 50, "age_grade": 25, "consistency": 25}
HEALTH_WEIGHTS = {"resting_hr": 30, "fitness_age": 25, "sleep": 25, "hrv": 20}


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


def build(conn, source: str, today: date) -> dict:
    cmp = compare.build(conn, source, today)
    if cmp["missing"]:
        return {"status": "unavailable", "missing": cmp["missing"], "algorithm_version": SCORES_VERSION}
    sex, age = cmp["profile"]["sex"], cmp["profile"]["age"]
    items = {i["id"]: i for i in cmp["items"]}
    g = rp.get_setting(conn, "garmin_fitness", None) or {}

    # ---- fitness
    f_parts = []
    v = (g.get("vo2max") or {}).get("value")
    f_parts.append({"id": "vo2max", "title": "VO₂ max for your age", "value": f"{v:.1f}" if v else None,
                    "points": round(vo2_points(sex, age, v)) if v else None,
                    "note": items["vo2max"].get("headline") if v else "No VO₂ max from Garmin yet"})
    ag = items.get("age_grade") or {}
    best = max((r["age_grade_pct"] for r in ag.get("rows", []) if r["kind"] == "best"), default=None)
    if best is None:
        best = max((r["age_grade_pct"] for r in ag.get("rows", [])), default=None)
    f_parts.append({"id": "age_grade", "title": "Age-graded running", "value": f"{best:.0f}%" if best else None,
                    "points": round(clamp((best - 40) * 2)) if best else None,  # 40% → 0, 90% (world class) → 100
                    "note": "Your best age grade; 40% scores 0 and 90% scores 100" if best else "No graded times yet"})
    first = rp.first_weekday(conn)
    ws = rp.week_start(today, first)
    weeks = [ws - timedelta(days=7 * k) for k in range(1, 9)]
    runs = rp.activities(conn, source, weeks[-1].isoformat(), (ws - timedelta(days=1)).isoformat())
    active = sum(1 for w in weeks if any(w.isoformat() <= a["local_date"] <= (w + timedelta(days=6)).isoformat() for a in runs))
    f_parts.append({"id": "consistency", "title": "Consistency", "value": f"{active} of 8 weeks",
                    "points": round(100 * active / 8), "note": "Weeks with at least one run, last 8 complete weeks"})

    # ---- health
    h_parts = []
    rhr = items.get("resting_hr") or {}
    h_parts.append({"id": "resting_hr", "title": "Resting heart rate for your age", "value": f"{rhr['value']} bpm" if rhr.get("status") == "ok" else None,
                    "points": rhr.get("lower_than_pct") if rhr.get("status") == "ok" else None,
                    "note": rhr.get("headline") if rhr.get("status") == "ok" else "Not enough resting heart rate data yet"})
    fa = (g.get("fitness_age") or {})
    if fa.get("fitnessAge") is not None:
        diff = (fa.get("chronologicalAge") or age) - fa["fitnessAge"]
        h_parts.append({"id": "fitness_age", "title": "Fitness age vs your age", "value": f"{fa['fitnessAge']:.1f}",
                        "points": round(clamp(50 + 10 * diff)), "note": f"{abs(diff):.1f} years {'younger' if diff >= 0 else 'older'} than your age (Garmin)"})
    else:
        h_parts.append({"id": "fitness_age", "title": "Fitness age vs your age", "value": None, "points": None, "note": "No fitness age from Garmin yet"})
    sleep = [s for d, s in rp.series(conn, source, "sleep_duration", today.isoformat()).items() if d >= (today - timedelta(days=13)).isoformat()]
    if len(sleep) >= 5:
        h = median(sleep) / 3600
        pts = 100 if 7 <= h <= 9 else clamp(100 - 50 * (7 - h)) if h < 7 else clamp(100 - 50 * (h - 9))
        h_parts.append({"id": "sleep", "title": "Sleep", "value": f"{int(h)} h {round((h % 1) * 60):02d} min",
                        "points": round(pts), "note": f"Typical night over the last two weeks ({len(sleep)} nights); 7–9 h scores 100"})
    else:
        h_parts.append({"id": "sleep", "title": "Sleep", "value": None, "points": None, "note": "Needs 5 nights in the last two weeks"})
    hrv = items.get("hrv") or {}
    band = (hrv.get("chart") or {}).get("band")
    if hrv.get("status") == "ok" and band and hrv.get("value") is not None:
        lo, hi = band
        val = hrv["value"]
        pts = 100 if lo <= val <= hi else clamp(100 - 100 * (lo - val) / max(lo, 1) * 2) if val < lo else 90
        h_parts.append({"id": "hrv", "title": "HRV vs your usual", "value": f"{val} ms", "points": round(pts),
                        "note": f"This week against your usual {lo}–{hi} ms"})
    else:
        h_parts.append({"id": "hrv", "title": "HRV vs your usual", "value": None, "points": None,
                        "note": "Your usual range is still being learned"})

    return {"status": "ok", "age": age, "sex": sex, "fitness": combine(f_parts, FITNESS_WEIGHTS), "health": combine(h_parts, HEALTH_WEIGHTS),
            "basis": f"Compared with {'men' if sex == 'male' else 'women'} of your age where a reference exists. A summary of the "
                     "readings below, not a medical score.", "algorithm_version": SCORES_VERSION}


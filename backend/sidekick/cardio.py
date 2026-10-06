"""Cardio fitness (experimental): the evidence about your aerobic capacity, shown side by side and never blended.

1. From your runs: a VO2 max estimate per qualifying run. The oxygen cost of the run's hill-adjusted pace (ACSM running
   equation, VO2 = 3.5 + 0.2 × speed in m/min) against how far heart rate rose into its reserve, using Swain's finding
   that the share of heart-rate reserve tracks the share of oxygen-uptake reserve:
   VO2max = 3.5 + (VO2 − 3.5) / ((HR − HRrest) / (HRmax − HRrest)). An experimental combination of published parts, not a
   validated package. The app's own additions are only these choices: which runs qualify (steady, outdoors, known and
   not hot weather, flat (≤10 m/km climb), 20+ minutes after a 10-minute warm-up, 90%+ valid heart rate, 80% of the time
   within 50–90% of heart-rate reserve) and how maximum heart rate is chosen. Recorded speed, no hill adjustment. Every
   run left out says why. The spread between runs is shown as
   variability, not accuracy, and how much the estimate leans on the assumed maximum heart rate is shown too.
2. Questionnaire-based: Jackson et al. 1990 (MSSE 22:863), the BMI model, with its own inputs: age, sex, BMI and the
   NASA/JSC activity rating (0–7) for the previous month. Its standard error was about 5.7 ml/kg/min across the study
   group, not a promise for one person. The rating tops out at 7, so it can't tell regular runners apart beyond that.
3. Running performance: Daniels' VDOT from your best stretches within runs. It includes running economy, so it's a
   performance number, not oxygen capacity, and is reported on its own.
4. Garmin's own VO2 max estimate, for reference.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import median

from . import compare as cp
from . import reports as rp
from . import weather as wx
from .analytics import running as rn
from .db import get_setting

CARDIO_VERSION = "cardio-0.1"
WARMUP_S, MIN_SEGMENT_S, MIN_HR_COVERAGE = 600.0, 1200.0, 0.9
HRR_RANGE = (0.5, 0.9)      # the share of heart-rate reserve where the relationship is used
IN_RANGE_SHARE = 0.8        # ...for at least this share of the stretch
MAX_NET_GRADE = 0.01        # the analysed stretch's overall rise or fall, at most 1%
MAX_CLIMB_PER_KM = 10.0     # m/km, up and down each; flatter runs only: the ACSM equation used is the flat-ground one (no hill model of the app's)
MIN_RUN_SPEED = 134.0 / 60  # m/s; slower is walking, where the running equation doesn't apply
RECENT_DAYS, RECENT_RUNS = 60, 8
SUSTAINED_S = 60.0          # the observed maximum is the highest heart rate held for a minute, not a one-off spike

# NASA/JSC Physical Activity Rating, worded as published (Jackson et al. 1990), for the previous month
PAR_SCALE = [
    (0, "Avoid walking or exertion, e.g. always use the elevator, drive whenever possible."),
    (1, "Walk for pleasure, routinely use stairs, occasionally exercise enough to breathe heavily or perspire."),
    (2, "Regular modest activity (golf, horseback riding, calisthenics, gymnastics, table tennis, bowling, weight lifting, "
        "yard work): 10 to 60 minutes a week."),
    (3, "Regular modest activity (as above): over one hour a week."),
    (4, "Regular heavy exercise (running or jogging, swimming, cycling, rowing, skipping rope, or vigorous aerobic sports such as "
        "tennis, basketball or handball): run less than 1 mile a week, or less than 30 minutes a week of comparable activity."),
    (5, "Regular heavy exercise (as above): run 1 to 5 miles a week, or 30 to 60 minutes a week of comparable activity."),
    (6, "Regular heavy exercise (as above): run 5 to 10 miles a week, or 1 to 3 hours a week of comparable activity."),
    (7, "Regular heavy exercise (as above): run more than 10 miles a week, or more than 3 hours a week of comparable activity."),
]


def _dated(conn, key):
    v = get_setting(conn, key, None)
    return (v, get_setting(conn, key + "_at", None)) if v is not None else (None, None)


MAX_GAP_S = 5.0  # a "sustained" minute has no gap in valid heart rate longer than this


def sustained_max(s) -> float | None:
    """The highest heart rate held over a full minute: a time-weighted mean (each reading counts for the time until the
    next), over windows with continuous valid readings only. A few seconds of spike barely move it; a gap disqualifies."""
    if s is None or not s.hr:
        return None
    pts = [(t, h) for t, h in zip(s.t, s.hr) if t is not None]
    best = None
    for i in range(1, len(pts)):
        end = pts[i][0]
        acc = span = 0.0
        ok = True
        j = i
        while j > 0 and span < SUSTAINED_S:
            (t0, h0), (t1, _) = pts[j - 1], pts[j]
            dt = t1 - t0
            if h0 is None or dt <= 0 or dt > MAX_GAP_S:
                ok = False
                break
            acc += h0 * dt
            span += dt
            j -= 1
        if ok and span >= SUSTAINED_S:
            m = acc / span
            best = m if best is None or m > best else best
    return best


def hr_max(conn, source: str, today: date) -> dict:
    """The maximum heart rate the estimates use, with where it comes from: yours when you set it; else the higher of
    Garmin's configured maximum and the highest heart rate you've held for a minute (if you held it, your maximum is at
    least that)."""
    mine, at = _dated(conn, "hr_max")
    if mine:
        return {"value": float(mine), "source": "set by you" + (f" on {at}" if at else "")}
    zones = rp.hr_zones(conn) or {}
    garmin = zones.get("max_hr")
    seen = None
    for a in rp.activities(conn, source, (today - timedelta(days=365)).isoformat(), today.isoformat()):
        m = sustained_max(rp.samples_for(conn, a["id"]))
        if m and (seen is None or m > seen[0]):
            seen = (m, a["local_date"])
    if seen and (not garmin or seen[0] > garmin):
        return {"value": round(seen[0]), "source": f"the highest you've held for a minute ({seen[1]})"}
    if garmin:
        return {"value": float(garmin), "source": "Garmin's maximum heart rate setting"}
    return {"value": None, "source": None}


def run_estimate(conn, a: dict, hr_rest: float | None, hrmax: float | None) -> tuple[dict | None, str | None]:
    """One run's VO2 max estimate, or None and why it was left out."""
    if hr_rest is None or not hrmax:
        return None, "resting or maximum heart rate not known yet"
    an = rp.run_analysis(conn, a)
    if (an.get("classification") or {}).get("kind") != "steady":
        return None, "not steady"
    if a.get("sport") == "treadmill_running":
        return None, "treadmill (speed not measured outdoors)"
    ht = wx.heat(wx.stored(conn, a["source_id"]))
    if ht is None:
        return None, "weather unknown"
    if ht["hot"]:
        return None, "hot and humid"
    if a.get("elevation_gain_m") is None or a.get("elevation_loss_m") is None or not a.get("distance_m"):
        return None, "elevation not recorded"  # unknown isn't flat
    km = a["distance_m"] / 1000
    if a["elevation_gain_m"] / km > MAX_CLIMB_PER_KM or a["elevation_loss_m"] / km > MAX_CLIMB_PER_KM:
        return None, "hilly (the running equation used is for flat ground)"
    s = rp.samples_for(conn, a["id"])
    if s is None:
        return None, "no samples"
    w = rn._weights(s)
    moved, seg, with_hr, sv, sh = 0.0, 0.0, 0.0, 0.0, 0.0
    first = last = None  # the analysed stretch's (distance, elevation) at its ends: it has to be level overall too
    for wi, v, h, d, e in zip(w, s.speed, s.hr, s.dist, s.elev):
        if wi <= 0:
            continue
        moved += wi
        if moved <= WARMUP_S or v is None:
            continue
        if d is not None and e is not None:
            first = first or (d, e)
            last = (d, e)
        seg += wi
        if h is not None:
            with_hr += wi
            sv += v * wi
            sh += h * wi
    if seg < MIN_SEGMENT_S:
        return None, "under 20 minutes after the warm-up"
    if not first or last[0] - first[0] < 1000:
        return None, "elevation not recorded"
    if abs(last[1] - first[1]) / (last[0] - first[0]) > MAX_NET_GRADE:
        return None, "the stretch climbs or descends overall"
    if with_hr < MIN_HR_COVERAGE * seg:
        return None, "heart-rate gaps"
    v, hr = sv / with_hr, sh / with_hr
    if v < MIN_RUN_SPEED:
        return None, "walking pace"
    # The relationship holds within the submaximal range: most of the stretch has to be inside it, not just its average
    inside = 0.0
    moved = 0.0
    for wi, h in zip(w, s.hr):
        if wi <= 0:
            continue
        moved += wi
        if moved > WARMUP_S and h is not None and HRR_RANGE[0] <= (h - hr_rest) / (hrmax - hr_rest) <= HRR_RANGE[1]:
            inside += wi
    if inside < IN_RANGE_SHARE * with_hr:
        return None, "heart rate outside the reliable range for much of the run"
    share = (hr - hr_rest) / (hrmax - hr_rest)
    if share < HRR_RANGE[0]:
        return None, "too easy for a reliable reading"
    if share > HRR_RANGE[1]:
        return None, "too hard for a reliable reading"
    vo2 = 3.5 + 0.2 * v * 60
    return {"date": a["local_date"], "source_id": a["source_id"], "value": round(3.5 + (vo2 - 3.5) / share, 1),
            "hrr_share": round(share, 2), "speed_m_s": round(v, 3), "hr": round(hr, 1), "hr_rest": hr_rest, "vo2": round(vo2, 2)}, None


def with_hr_max(e: dict, hrmax: float) -> float:
    """The same run's observation recalculated with another maximum heart rate (nothing else changes)."""
    return 3.5 + (e["vo2"] - 3.5) / ((e["hr"] - e["hr_rest"]) / (hrmax - e["hr_rest"]))


def vdot(metres: float, seconds: float) -> float:
    """Daniels & Gilbert: the oxygen cost of the pace over the share of VO2 max sustainable for that long."""
    v, t = metres / seconds * 60, seconds / 60
    cost = -4.60 + 0.182258 * v + 0.000104 * v * v
    share = 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)
    return cost / share


def build(conn, source: str, today: date) -> dict:
    out = {"algorithm_version": CARDIO_VERSION, "experimental": True}
    hm = hr_max(conn, source, today)
    out["hr_max"] = hm
    rhr = rp.series(conn, source, "resting_hr", today.isoformat())

    def rest_before(d: str):
        vals = [v for k, v in rhr.items() if (date.fromisoformat(d) - timedelta(days=28)).isoformat() <= k <= d]
        return median(vals) if len(vals) >= 7 else None

    # 1. From your runs
    since = (today - timedelta(days=RECENT_DAYS)).isoformat()
    runs = rp.activities(conn, source, since, today.isoformat())
    used, left = [], {}
    for a in runs:
        e, why = run_estimate(conn, a, rest_before(a["local_date"]), hm["value"])
        if e:
            used.append(e)
        else:
            left[why] = left.get(why, 0) + 1
    recent = used[-RECENT_RUNS:]
    runs_part = {"id": "runs", "title": "From your runs", "runs_used": len(used), "left_out": left,
                 "points": used, "caveat": "An experimental combination of published equations (ACSM running equation, Swain's heart-rate reserve). "
                 "The spread is how much your runs vary, not how accurate the estimate is."}
    if len(recent) >= 3:
        vals = [e["value"] for e in recent]
        mid = median(vals)
        # How much the estimate leans on the assumed maximum heart rate: the same runs and readings, only that changed
        lower = [with_hr_max(e, hm["value"] - 5) for e in recent]
        runs_part.update(status="ok", value=round(mid), spread=[round(min(vals)), round(max(vals))],
                         sensitivity=f"With a maximum heart rate 5 beats lower ({hm['value'] - 5:.0f}), the same runs would give "
                                     f"about {round(median(lower))}.",
                         headline=f"from your last {len(recent)} qualifying runs",
                         detail=f"Your runs vary from {round(min(vals))} to {round(max(vals))}. Maximum heart rate used: "
                                f"{hm['value']:.0f} bpm ({hm['source']}); resting heart rate: Garmin's overnight value (the "
                                f"published relationship used seated resting measurements).")
    else:
        runs_part.update(status="not_enough", headline="Not enough qualifying runs yet",
                         detail=f"Needs 3 steady, cool runs with good heart rate and 20+ minutes after the warm-up in the last "
                                f"{RECENT_DAYS} days; {len(used)} so far.")
    out["runs"] = runs_part

    # 2. Questionnaire-based (Jackson 1990, BMI model)
    p = cp.profile(conn, today)
    par, par_at = _dated(conn, "activity_par")
    weight, weight_at = _dated(conn, "profile_weight_kg")
    height, height_at = _dated(conn, "profile_height_cm")
    src = get_setting(conn, "source_profile", None) or {}
    if weight is None and src.get("weight_kg"):
        weight, weight_at = src["weight_kg"], "from Garmin"
    if height is None and src.get("height_cm"):
        height, height_at = src["height_cm"], "from Garmin"
    q = {"id": "questionnaire", "title": "Questionnaire-based estimate", "source": "Jackson et al. 1990 (non-exercise model, BMI)",
         "inputs": {"activity_par": par, "activity_par_at": par_at, "weight_kg": weight, "weight_at": weight_at,
                    "height_cm": height, "height_at": height_at, "age": p.get("age"), "sex": p.get("sex")},
         "caveat": "The study's standard error was about 5.7 ml/kg/min across its group; for one person it can be further off. "
                   "The activity scale tops out at 7, so it can't tell regular runners apart beyond that."}
    missing = [n for n, v in (("your activity level", par), ("weight", weight), ("height", height), ("age", p.get("age")),
                              ("sex", p.get("sex"))) if v is None]
    if missing:
        q.update(status="needs_input", headline="Needs a few answers", detail="Needs " + ", ".join(missing) + " (your answers, below).")
    else:
        bmi = weight / (height / 100) ** 2
        v = 56.363 + 1.921 * par - 0.381 * p["age"] - 0.754 * bmi + 10.987 * (1 if p["sex"] == "male" else 0)
        q.update(status="ok", value=round(v), bmi=round(bmi, 1), headline="from your answers",
                 detail=f"From your age ({p['age']}), sex, BMI {bmi:.1f} and activity level {par} of 7"
                        + (f" (answered {par_at})" if par_at else "") + ".")
    out["questionnaire"] = q
    out["inputs"] = {"weight_kg": weight, "weight_from": weight_at, "height_cm": height, "height_from": height_at}

    # 3. Running performance (VDOT)
    best = None
    for k, metres in (("5k", 5000.0), ("10k", 10000.0), ("half", 21097.5)):
        b = (rp.records(conn, source).get(k) or {}).get("best")
        if b:
            vd = vdot(metres, b["elapsed_s"])
            if best is None or vd > best["value"]:
                best = {"value": round(vd, 1), "distance": cp.DISTANCE_LABELS[k], "metres": metres, "time_s": b["elapsed_s"], "date": b["date"],
                        "source_id": b["source_id"]}
    out["performance"] = ({"id": "performance", "title": "Running performance (VDOT)", "status": "ok", **best,
                           "headline": f"from your best {best['distance'].lower()} stretch",
                           "detail": f"From your fastest {best['distance'].lower()} stretch within a run ({rp.fmt_pace(best['time_s'] / (best['metres'] / 1000))}, {best['date']}). "
                                     "A performance number: it includes running economy and comes from training runs, not races, "
                                     "so it isn't comparable with the VO₂ max estimates."}
                          if best else {"id": "performance", "title": "Running performance (VDOT)", "status": "not_enough",
                                        "headline": "Needs a run of 5 km or longer", "detail": ""})

    # 4. Garmin
    from .scores import vo2_on
    found = vo2_on(conn, source, today, today)  # the newest reading, from the daily series or Garmin's snapshot, and not stale
    gv = (found[0], found[1].isoformat()) if found else None
    out["garmin"] = ({"id": "garmin", "title": "Garmin's VO₂ max", "status": "ok", "value": round(gv[0]), "date": gv[1],
                      "headline": f"as of {gv[1]}", "detail": "Garmin's (Firstbeat's) estimate from your runs' heart rate and pace."}
                     if gv else {"id": "garmin", "title": "Garmin's VO₂ max", "status": "unavailable", "headline": "Not from Garmin yet"})

    # Each VO2 max estimate placed among people of your sex and age (performance isn't: a different quantity)
    if p.get("sex") and p.get("age"):
        for k in ("runs", "questionnaire", "garmin"):
            v = out[k].get("value")
            if v is None:
                continue
            it = cp.vo2_item(p["sex"], p["age"], {"vo2max": {"value": float(v)}})
            if it.get("status") != "ok":
                continue
            pos = ("below the 40th percentile" if it["position"] == "below" else "above the 95th percentile" if it["position"] == "above"
                   else f"higher than about {it['percentile']}%")
            out[k]["comparison"] = {"headline": f"{it['rating']} for {it['group']}", "percentile": it["percentile"],
                                    "detail": f"{v} is {pos} of {it['group']}" + (f"; typical for a {cp.SEX_WORD[p['sex']][0]} of about {it['typical_age']}"
                                                                                 if it.get("typical_age") else "") + ".",
                                    "source": cp.nm.VO2_SOURCE}

    # How the VO2 max estimates relate (performance stays out of this: a different quantity)
    notes = []
    r, gg, qq = out["runs"].get("value"), out["garmin"].get("value"), out["questionnaire"].get("value")
    if r is not None and gg is not None:
        notes.append(f"Your runs and Garmin {'are within 2 of each other' if abs(r - gg) <= 2 else f'differ by {abs(r - gg)}'}. Both read "
                     "heart rate against pace, but with different methods and assumptions"
                     + ("." if abs(r - gg) <= 2 else ". Possible reasons include the maximum heart rate assumed, how resting heart rate "
                        "is measured, running economy, conditions and data quality; the app can't tell which. The line above shows how "
                        "much the maximum heart rate alone moves the estimate."))
    if qq is not None and (r is not None or gg is not None):
        notes.append("The questionnaire estimate is a broad baseline from who you are and how active you say you are, not from "
                     "your heart rate; it can be several points away for one person.")
    out["notes"] = notes
    out["basis"] = ("Experimental. The estimates are shown side by side and not combined: they share some inputs, so agreeing "
                    "doesn't make them more certain. Only a laboratory test measures VO₂ max.")
    out["par_scale"] = [{"value": v, "text": t} for v, t in PAR_SCALE]
    return out

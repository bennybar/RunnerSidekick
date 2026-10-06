"""Cardio fitness (experimental): the evidence about your aerobic capacity, shown side by side and never blended.

1. From your runs: a VO2 max estimate per qualifying run. The oxygen cost of the run's hill-adjusted pace (ACSM running
   equation, VO2 = 3.5 + 0.2 × speed in m/min) against how far heart rate rose into its reserve, using Swain's finding
   that the share of heart-rate reserve tracks the share of oxygen-uptake reserve:
   VO2max = 3.5 + (VO2 − 3.5) / ((HR − HRrest) / (HRmax − HRrest)). An experimental combination of published parts, not a
   validated package. Only steady, cool, well-recorded runs of 20+ minutes after a 10-minute warm-up, in the submaximal
   range (50–90% of heart-rate reserve), count; every run left out says why. The spread between runs is shown as
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


def sustained_max(s) -> float | None:
    """The highest heart rate held over a minute (a time-weighted rolling mean), so a sensor spike doesn't count."""
    if s is None or not s.hr:
        return None
    best, j, acc, n = None, 0, 0.0, 0
    pts = [(t, h) for t, h in zip(s.t, s.hr) if h is not None]
    for i, (t, h) in enumerate(pts):
        acc += h
        n += 1
        while pts[j][0] < t - SUSTAINED_S:
            acc -= pts[j][1]
            n -= 1
            j += 1
        if t - pts[j][0] >= SUSTAINED_S * 0.9 and n >= 6:  # a full minute, with enough samples in it
            m = acc / n
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
    ht = wx.heat(wx.stored(conn, a["source_id"]))
    if ht and ht["hot"]:
        return None, "hot and humid"
    s = rp.samples_for(conn, a["id"])
    if s is None:
        return None, "no samples"
    w, gap = rn._weights(s), rn.gap_speeds(s)
    moved, seg, with_hr, sv, sh = 0.0, 0.0, 0.0, 0.0, 0.0
    for wi, v, h in zip(w, gap, s.hr):
        if wi <= 0:
            continue
        moved += wi
        if moved <= WARMUP_S or v is None:
            continue
        seg += wi
        if h is not None:
            with_hr += wi
            sv += v * wi
            sh += h * wi
    if seg < MIN_SEGMENT_S:
        return None, "under 20 minutes after the warm-up"
    if with_hr < MIN_HR_COVERAGE * seg:
        return None, "heart-rate gaps"
    v, hr = sv / with_hr, sh / with_hr
    if v < MIN_RUN_SPEED:
        return None, "walking pace"
    share = (hr - hr_rest) / (hrmax - hr_rest)
    if share < HRR_RANGE[0]:
        return None, "too easy for a reliable reading"
    if share > HRR_RANGE[1]:
        return None, "too hard for a reliable reading"
    vo2 = 3.5 + 0.2 * v * 60
    return {"date": a["local_date"], "source_id": a["source_id"], "value": round(3.5 + (vo2 - 3.5) / share, 1),
            "hrr_share": round(share, 2), "speed_m_s": round(v, 3), "hr": round(hr)}, None


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
        # How much the estimate leans on the assumed maximum heart rate: the same runs with it 5 beats lower
        lower = [run_estimate(conn, a, rest_before(a["local_date"]), hm["value"] - 5)[0] for a in runs
                 if a["source_id"] in {e["source_id"] for e in recent}]
        lower = [e["value"] for e in lower if e]
        runs_part.update(status="ok", value=round(mid), spread=[round(min(vals)), round(max(vals))],
                         sensitivity=(f"With a maximum heart rate 5 beats lower ({hm['value'] - 5:.0f}), it would be about "
                                      f"{round(median(lower))}." if len(lower) >= 3 else None),
                         headline=f"About {round(mid)}, from your last {len(recent)} qualifying runs",
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
        q.update(status="needs_input", headline="Needs a few answers", detail="Needs " + ", ".join(missing) + " (Settings → About you).")
    else:
        bmi = weight / (height / 100) ** 2
        v = 56.363 + 1.921 * par - 0.381 * p["age"] - 0.754 * bmi + 10.987 * (1 if p["sex"] == "male" else 0)
        q.update(status="ok", value=round(v), bmi=round(bmi, 1), headline=f"About {round(v)}",
                 detail=f"From your age ({p['age']}), sex, BMI {bmi:.1f} and activity level {par} of 7"
                        + (f" (answered {par_at})" if par_at else "") + ".")
    out["questionnaire"] = q

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
                           "headline": f"VDOT {best['value']:.0f}",
                           "detail": f"From your fastest {best['distance'].lower()} stretch within a run ({rp.fmt_pace(best['time_s'] / (best['metres'] / 1000))}, {best['date']}). "
                                     "A performance number: it includes running economy and comes from training runs, not races, "
                                     "so it isn't comparable with the VO₂ max estimates."}
                          if best else {"id": "performance", "title": "Running performance (VDOT)", "status": "not_enough",
                                        "headline": "Needs a run of 5 km or longer", "detail": ""})

    # 4. Garmin
    g = rp.series(conn, source, "garmin_vo2max_running", today.isoformat())
    gv = max(g.items())[::-1] if g else None
    gnow = ((get_setting(conn, "garmin_fitness", None) or {}).get("vo2max") or {})
    if gv is None and gnow.get("value"):
        gv = (gnow["value"], gnow.get("date"))
    out["garmin"] = ({"id": "garmin", "title": "Garmin's VO₂ max", "status": "ok", "value": round(gv[0]), "date": gv[1],
                      "headline": f"{round(gv[0])}", "detail": "Garmin's (Firstbeat's) estimate from your runs' heart rate and pace."}
                     if gv else {"id": "garmin", "title": "Garmin's VO₂ max", "status": "unavailable", "headline": "Not from Garmin yet"})

    # How the VO2 max estimates relate (performance stays out of this: a different quantity)
    notes = []
    r, gg, qq = out["runs"].get("value"), out["garmin"].get("value"), out["questionnaire"].get("value")
    if r is not None and gg is not None:
        notes.append(f"Your runs and Garmin {'agree closely' if abs(r - gg) <= 2 else f'differ by {abs(r - gg)}'}: both read heart rate "
                     "against pace, with different assumptions (maximum heart rate, oxygen cost), so a few points apart is normal"
                     + ("." if abs(r - gg) <= 2 else "; the maximum heart rate is the usual cause."))
    if qq is not None and (r is not None or gg is not None):
        notes.append("The questionnaire estimate is a broad baseline from who you are and how active you say you are, not from "
                     "your heart rate; it can be several points away for one person.")
    out["notes"] = notes
    out["basis"] = ("Experimental. The estimates are shown side by side and not combined: they share some inputs, so agreeing "
                    "doesn't make them more certain. Only a laboratory test measures VO₂ max.")
    out["par_scale"] = [{"value": v, "text": t} for v, t in PAR_SCALE]
    return out

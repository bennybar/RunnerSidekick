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

CARDIO_VERSION = "cardio-0.7"  # 0.7: bands and percentiles from unrounded values, sensitivity from unrounded readings; 0.6: HUNT with the model's activity coding and a seated pulse, the median for comparison only, medians at full precision; 0.5: HUNT non-exercise estimate, the combined median; 0.4: altitude coverage for every run, smoothed gradients (running-1.11); 0.3: 0.3: hill-adjusted pace on every run (no switch at 10 m/km), gradient coverage, one all-weather basis with subgroup medians; 0.2: runs up to 20 m/km; all watches
WARMUP_S, MIN_SEGMENT_S, MIN_HR_COVERAGE = 600.0, 1200.0, 0.9
HRR_RANGE = (0.5, 0.9)      # the share of heart-rate reserve where the relationship is used
IN_RANGE_SHARE = 0.8        # ...for at least this share of the stretch
MAX_NET_GRADE = 0.01        # the analysed stretch's overall rise or fall, at most 1%
MAX_CLIMB_PER_KM = 10.0     # m/km, up and down each: flat enough for the ACSM level-ground equation on the recorded pace
HILLY_MAX_CLIMB_PER_KM = 20.0  # m/km: up to here (VO2 estimate only) the hill-adjusted pace stands in for the recorded one
MIN_GRADE_COVERAGE = 0.9       # ...and every run needs a gradient for 90% of its stretch
OUTLIER_VO2 = 5.0              # a run this far from the median is flagged for review (kept: high or low isn't proof of error)
MIN_RUN_SPEED = 134.0 / 60  # m/s; slower is walking, where the running equation doesn't apply
RECENT_DAYS, RECENT_RUNS = 60, 8
SUSTAINED_S = 60.0          # the observed maximum is the highest heart rate held for a minute, not a one-off spike

# HUNT non-exercise VO2 peak (Nes et al. 2011, Med Sci Sports Exerc 43:2024; coefficients as reproduced in the HUNT
# polygenic-fitness paper, PMC12265795): intercept, and per year of age, cm of waist, bpm of resting heart rate, point
# of the PA index
HUNT_EQ = {"male": (100.27, 0.296, 0.369, 0.155, 0.226), "female": (74.74, 0.247, 0.259, 0.114, 0.198)}
# The model's own activity index (weighting intensity more than HUNT's general questionnaire index): frequency × duration
# × intensity, coded as reported by a study applying Nes et al. (US DOT report 55934, 2021): frequency 0 (never or less
# than weekly) / 1 / 2 / 3, duration 1 (under 30 min) / 1.5 (30 min or more), intensity 0 / 5 / 10. Not checked against
# the original paper's table, which wasn't available.
HUNT_WEIGHTS_SOURCE = "as coded from Nes et al. by a study applying the model (US DOT report 55934, 2021)"
HUNT_FREQUENCY = [("never", "Never", 0.0), ("lt_weekly", "Less than once a week", 0.0), ("weekly", "Once a week", 1.0),
                  ("2_3_weekly", "2–3 times a week", 2.0), ("almost_daily", "Almost every day", 3.0)]
HUNT_INTENSITY = [("easy", "No sweating or heavy breathing", 0.0), ("sweat", "Sweating and heavy breathing", 5.0),
                  ("exhaustion", "Push myself to exhaustion", 10.0)]
HUNT_DURATION = [("lt15", "Less than 15 minutes", 1.0), ("15_30", "15 to under 30 minutes", 1.0), ("30_60", "30–60 minutes", 1.5),
                 ("gt60", "More than 60 minutes", 1.5)]


def hunt_part(conn, source: str, sex: str | None, age: int | None, today: date) -> dict:
    """VO2 max from the HUNT non-exercise formula: age, sex, waist, resting heart rate and the three-question activity
    index. A population formula: a broad baseline, several units off for one person. The study measured resting heart
    rate seated after rest; without that answer, the watch's overnight 4-week median stands in, read lower, so the
    estimate reads high (10 bpm ≈ 1.5 for men) and is labelled adapted."""
    base = {"id": "hunt", "title": "HUNT formula (non-exercise)", "source": "Nes et al. 2011, the HUNT Study, Norway"}
    waist, waist_at = _dated(conn, "profile_waist_cm")
    seated, seated_at = _dated(conn, "resting_pulse_seated")
    ans = {k: get_setting(conn, k, None) for k in ("hunt_frequency", "hunt_intensity", "hunt_duration")}
    since = (today - timedelta(days=27)).isoformat()
    rhr = [v for k, v in rp.series(conn, source, "resting_hr", today.isoformat()).items() if k >= since]
    missing = [w for w, ok in (("sex and birth date", sex and age), ("waist", waist), ("the three activity answers", all(ans.values())),
                               ("a resting pulse", seated or len(rhr) >= 7)) if not ok]
    caveat = ("A population formula from who you are and how active you say you are, not from a run. Activity points "
              + HUNT_WEIGHTS_SOURCE + ".")
    if missing:
        return {**base, "status": "needs_input", "headline": "Needs " + ", ".join(missing), "caveat": caveat}
    pts = {k: dict((key, w) for key, _, w in opts)[ans[k]] for k, opts in
           (("hunt_frequency", HUNT_FREQUENCY), ("hunt_intensity", HUNT_INTENSITY), ("hunt_duration", HUNT_DURATION))}
    pa = pts["hunt_frequency"] * pts["hunt_intensity"] * pts["hunt_duration"]
    b0, b_age, b_waist, b_rhr, b_pa = HUNT_EQ[sex]
    r = seated if seated else median(rhr)
    v = b0 - b_age * age - b_waist * waist - b_rhr * r + b_pa * pa
    if not seated:
        caveat += (" Adapted: the study used a seated resting pulse; your watch's overnight value reads lower, so this "
                   f"estimate reads higher (each 10 bpm adds about {10 * b_rhr:.1f}). Add a seated pulse below, measured as the study did.")
    return {**base, "status": "ok", "value": round(v), "value_exact": v, "pa_index": pa, "rhr_basis": "seated" if seated else "overnight",
            "headline": "from your answers and seated pulse" if seated else "adapted: with your watch's overnight resting heart rate",
            "caveat": caveat,
            "detail": f"{b0} − {b_age}×age {age} − {b_waist}×waist {waist:g} cm − {b_rhr}×resting heart rate {r:.0f} "
                      f"({'seated' + (f', set {seated_at}' if seated_at else '') if seated else 'overnight, 4-week median'}) + {b_pa}×activity "
                      f"index {pa:g} = {v:.1f}" + (f" (waist set {waist_at})" if waist_at else "") + "."}


def combined(out: dict) -> dict | None:
    """For comparison only (scores and fitness age use the VO2 max source you chose): the median of the estimates
    available (ours from your runs, the watch's, HUNT with a seated pulse, the questionnaire). They share inputs (age,
    sex, heart rate, activity), so agreeing doesn't make it more certain."""
    parts = [(k, out[k]) for k in ("runs", "garmin", "hunt", "questionnaire") if out.get(k, {}).get("value") is not None
             and not (k == "hunt" and out[k].get("rhr_basis") != "seated")]
    if not parts:
        return None
    vals = [float(p.get("value_exact", p["value"])) for _, p in parts]
    names = {"runs": "your runs", "garmin": f"{out['garmin'].get('maker', 'the watch')}'s", "hunt": "HUNT formula",
             "questionnaire": "questionnaire"}
    return {"value": round(median(vals), 1), "inputs": [{"id": k, "title": names[k], "value": round(v, 1)} for (k, _), v in zip(parts, vals)],
            "spread": [round(min(vals), 1), round(max(vals), 1)]}


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


def steady_stretch(conn, a: dict, allow_hot: bool = False, allow_hills: bool = False) -> tuple[dict | None, str | None]:
    """A run's steady, level, well-recorded stretch after the warm-up: its time-weighted speed and heart rate, and whether
    the day was hot. Or None and why the run doesn't qualify. Shared by cardio fitness and pace at a reference heart rate."""
    an = rp.run_analysis(conn, a)
    if (an.get("classification") or {}).get("kind") != "steady":
        return None, "not steady"
    if a.get("sport") == "treadmill_running":
        return None, "treadmill (speed not measured outdoors)"
    ht = wx.heat(wx.stored(conn, a["source_id"]))
    if ht is None:
        return None, "weather unknown"
    # Only runs unusually hot for you are left out (humid, and 3 °C or more above your usual dew point), as in trends: an
    # absolute bar would drop most runs in a humid climate. A warm run reads a little low (heat raises heart rate).
    if ht["hot"] and not allow_hot and a["source_id"] in wx.unusually_hot(conn):
        return None, "unusually hot and humid for you"
    if a.get("elevation_gain_m") is None or a.get("elevation_loss_m") is None or not a.get("distance_m"):
        return None, "elevation not recorded"  # unknown isn't flat
    km = a["distance_m"] / 1000
    climb = max(a["elevation_gain_m"], a["elevation_loss_m"]) / km
    # Hillier than flat: with allow_hills, the hill-adjusted pace (the app's Minetti-based flat-equivalent, grades over
    # ~50 m so GPS altitude jitter is smoothed) stands in for the recorded pace, up to 20 m/km
    hill_adjusted = climb > MAX_CLIMB_PER_KM
    if hill_adjusted and not (allow_hills and climb <= HILLY_MAX_CLIMB_PER_KM):
        return None, ("too hilly (over 20 m of climb per km)" if allow_hills else "hilly (the running equation used is for flat ground)")
    s = rp.samples_for(conn, a["id"])
    if s is None:
        return None, "no samples"
    w = rn._weights(s)
    # The VO2 estimate uses the hill-adjusted pace on every run it takes (practically the recorded pace on the flat), so
    # there's no switch of method at 10 m/km; "hill_adjusted" only names the runs above it
    speeds = rn.gap_speeds(s) if allow_hills else s.speed
    graded = rn.grades(s) if allow_hills else [None] * len(s.t)
    moved, seg, with_hr, with_grade, sv, sh = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    first = last = None  # the analysed stretch's (distance, elevation) at its ends: it has to be level overall too
    for wi, v, h, d, e, g in zip(w, speeds, s.hr, s.dist, s.elev, graded):
        if wi <= 0:
            continue
        moved += wi
        if moved <= WARMUP_S or v is None:
            continue
        if d is not None and e is not None:
            first = first or (d, e)
            last = (d, e)
        seg += wi
        with_grade += wi if g is not None else 0.0
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
    if allow_hills and with_grade < MIN_GRADE_COVERAGE * seg:  # every run is hill-adjusted: a missing gradient would count as flat
        return None, "altitude missing for part of the run (needed to hill-adjust it)"
    v, hr = sv / with_hr, sh / with_hr
    if v < MIN_RUN_SPEED:
        return None, "walking pace"
    return {"v": v, "hr": hr, "hot": ht["hot"], "s": s, "w": w, "hill_adjusted": hill_adjusted}, None


def run_estimate(conn, a: dict, hr_rest: float | None, hrmax: float | None) -> tuple[dict | None, str | None]:
    """One run's VO2 max estimate, or None and why it was left out."""
    if hr_rest is None or not hrmax:
        return None, "resting or maximum heart rate not known yet"
    st, why = steady_stretch(conn, a, allow_hills=True)
    if st is None:
        return None, why
    v, hr, s, w, with_hr = st["v"], st["hr"], st["s"], st["w"], None
    # The relationship holds within the submaximal range: most of the stretch has to be inside it, not just its average
    inside = 0.0
    moved = 0.0
    for wi, h in zip(w, s.hr):
        if wi <= 0:
            continue
        moved += wi
        if moved > WARMUP_S and h is not None and HRR_RANGE[0] <= (h - hr_rest) / (hrmax - hr_rest) <= HRR_RANGE[1]:
            inside += wi
    with_hr = sum(wi for wi, h, k in zip(w, s.hr, _after_warmup(w)) if wi > 0 and k and h is not None)
    if inside < IN_RANGE_SHARE * with_hr:
        return None, "heart rate outside the reliable range for much of the run"
    share = (hr - hr_rest) / (hrmax - hr_rest)
    if share < HRR_RANGE[0]:
        return None, "too easy for a reliable reading"
    if share > HRR_RANGE[1]:
        return None, "too hard for a reliable reading"
    vo2 = 3.5 + 0.2 * v * 60
    return {"date": a["local_date"], "source_id": a["source_id"], "value": round(3.5 + (vo2 - 3.5) / share, 1),
            "exact": 3.5 + (vo2 - 3.5) / share, "hot": st["hot"],
            "hill_adjusted": st["hill_adjusted"],
            "hrr_share": round(share, 2), "speed_m_s": round(v, 3), "hr": hr, "hr_rest": hr_rest, "vo2": vo2}, None  # hr and cost unrounded: the sensitivity recalculates from them


def _after_warmup(w) -> list[bool]:
    out, moved = [], 0.0
    for wi in w:
        if wi > 0:
            moved += wi
        out.append(moved > WARMUP_S)
    return out


def with_hr_max(e: dict, hrmax: float) -> float:
    """The same run's observation recalculated with another maximum heart rate (nothing else changes)."""
    return 3.5 + (e["vo2"] - 3.5) / ((e["hr"] - e["hr_rest"]) / (hrmax - e["hr_rest"]))


def vdot(metres: float, seconds: float) -> float:
    """Daniels & Gilbert: the oxygen cost of the pace over the share of VO2 max sustainable for that long."""
    v, t = metres / seconds * 60, seconds / 60
    cost = -4.60 + 0.182258 * v + 0.000104 * v * v
    share = 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)
    return cost / share


def watch_of(a: dict) -> str:
    return "samsung" if a.get("manufacturer") == "Samsung" else "garmin"


def rest_on(conn, source: str, day: str) -> float | None:
    """The resting heart rate around a day: the median of the 28 days up to it, from 7 days, whichever watch measured
    them (Samsung's is our own estimate)."""
    since = (date.fromisoformat(day) - timedelta(days=28)).isoformat()
    vals = [v for k, v in rp.series(conn, source, "resting_hr", day).items() if k >= since]
    return median(vals) if len(vals) >= 7 else None


def run_estimates(conn, source: str, d: date, hm: dict) -> tuple[list[dict], dict[str, int]]:
    """The per-run estimates of the 60 days up to d, oldest first, and how many runs were left out for each reason. Runs
    from every watch count (the runner's choice), each estimate keeping which watch it came from."""
    used, left = [], {}
    held = set(get_setting(conn, "vo2_held_out", []) or [])
    for a in rp.activities(conn, source, (d - timedelta(days=RECENT_DAYS)).isoformat(), d.isoformat()):
        if a["source_id"] in held:  # the runner left it out (e.g. heart rate that looked wrong)
            left["held out by you"] = left.get("held out by you", 0) + 1
            continue
        e, why = run_estimate(conn, a, rest_on(conn, source, a["local_date"]), hm["value"])
        if e:
            e["watch"] = watch_of(a)
            used.append(e)
        else:
            left[why] = left.get(why, 0) + 1
    return used, left


def estimate_for_run(conn, source: str, a: dict) -> dict:
    """This run's own VO2 max estimate (as one of the runs behind 'ours'), or why it doesn't give one: {"value": ...} or
    {"value": None, "why": ...}."""
    d = date.fromisoformat(a["local_date"])
    hm = hr_max(conn, source, d)
    e, why = run_estimate(conn, a, rest_on(conn, source, a["local_date"]), hm.get("value"))
    out = {k: e[k] for k in ("value", "hrr_share", "hot", "hill_adjusted")} if e else {"value": None, "why": why}
    return {**out, "held_out": a["source_id"] in set(get_setting(conn, "vo2_held_out", []) or [])}


def own_vo2(conn, source: str, d: date) -> tuple[float, date] | None:
    """Runner Sidekick's VO2 max as of d (the median of the last 8 qualifying runs of the 60 days before, from 3), with the
    day of the newest of them; None until there are 3. What the scores use when the runner chose ours in Settings."""
    hm = hr_max(conn, source, d)
    if not hm.get("value"):
        return None
    # One stable basis: the last 8 qualifying runs whatever the weather (choosing by weather made the value jump when a
    # cool run arrived, with nothing changed); the cool and warm medians are shown beside it on the Cardio page
    recent = run_estimates(conn, source, d, hm)[0][-RECENT_RUNS:]
    if len(recent) < 3:
        return None
    return median(e["exact"] for e in recent), date.fromisoformat(recent[-1]["date"])


def build(conn, source: str, today: date) -> dict:
    out = {"algorithm_version": CARDIO_VERSION, "experimental": True}
    hm = hr_max(conn, source, today)
    out["hr_max"] = hm
    # 1. From your runs, whichever watch recorded them
    used, left = run_estimates(conn, source, today, hm)
    recent = used[-RECENT_RUNS:]
    runs_part = {"id": "runs", "title": "From your runs (experimental)", "runs_used": len(used), "left_out": left,
                 "points": used, "caveat": "An experimental combination of published equations (ACSM running equation, Swain's heart-rate "
                 "reserve), not a validated VO₂ max test. The spread is how much your runs vary, not how accurate the estimate is."}
    if len(recent) >= 3:
        vals = [e["exact"] for e in recent]
        mid = median(vals)
        # How much the estimate leans on the assumed maximum heart rate: the same runs and readings, only that changed
        lower = median(with_hr_max(e, hm["value"] - 5) for e in recent)
        higher = median(with_hr_max(e, hm["value"] + 5) for e in recent)

        def sub_median(rows: list[dict]) -> str | None:
            return f"{median(e['exact'] for e in rows):.1f} ({len(rows)} run{'s' if len(rows) != 1 else ''})" if rows else None
        # What's in the median, so its effect is visible: by weather, by watch, and runs far from it (kept, for review)
        groups = [(lab, sub_median([e for e in recent if f(e)])) for lab, f in (
            ("cool runs", lambda e: not e["hot"]), ("warm runs", lambda e: e["hot"]))]
        watches = sorted({e["watch"] for e in recent})
        if len(watches) > 1:
            groups += [(f"{w.capitalize()} runs", sub_median([e for e in recent if e["watch"] == w])) for w in watches]
        odd = [e for e in recent if abs(e["exact"] - mid) >= OUTLIER_VO2]
        for e in used:
            e["unusual"] = abs(e["exact"] - mid) >= OUTLIER_VO2
        n_hill = sum(e["hill_adjusted"] for e in recent)
        runs_part.update(status="ok", value=round(mid), value_exact=mid, spread=[round(min(vals)), round(max(vals))],
                         breakdown=[{"label": lab, "value": v} for lab, v in groups if v],
                         sensitivity=f"If your actual maximum heart rate were 5 beats lower or higher ({hm['value'] - 5:.0f} or "
                                     f"{hm['value'] + 5:.0f}), this estimate would be about {round(lower)}–{round(higher)}. An example of "
                                     "how much it leans on that one number, not an uncertainty range.",
                         headline=f"from your last {len(recent)} qualifying runs",
                         detail=f"The median of your last {len(recent)} qualifying runs, whatever the weather; its observed run range "
                                f"is {round(min(vals))}–{round(max(vals))} (how much runs differ, not the likely range of your true VO₂ max). "
                                "Beside it, descriptive subgroup medians: " + "; ".join(f"{lab} {v}" for lab, v in groups if v) + ". "
                                "Different runs, dates and conditions: these don't isolate watch accuracy or the effect of heat. "
                                + ("Heat raises heart rate, which tends to lower a run's estimate; it isn't corrected for. "
                                   if any(e["hot"] for e in recent) else "")
                                + (f"The estimate mixes {' and '.join(w.capitalize() for w in watches)} runs. " if len(watches) > 1 else "")
                                + (f"{n_hill} {'run was' if n_hill == 1 else 'runs were'} hilly (10–20 m/km), on hill-adjusted pace: "
                                   "less precise than on the flat. " if n_hill else "")
                                + ("Unusual heart rate for this pace (kept unless you hold it out on the run): "
                                   + ", ".join(f"{e['date']} ({e['value']:.1f})" for e in odd) + ". " if odd else "")
                                + f"Maximum heart rate used: {hm['value']:.0f} bpm ({hm['source']}), an assumption, not a test; "
                                "resting heart rate: your watch's overnight value.")
    else:
        runs_part.update(status="not_enough", headline="Not enough qualifying runs yet",
                         detail=f"Needs 3 steady runs with good heart rate and 20+ minutes after the warm-up in the last "
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
        q.update(status="ok", value=round(v), value_exact=v, bmi=round(bmi, 1), headline="from your answers",
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
    from .scores import watch_vo2
    found = watch_vo2(conn, source, today, today)  # this place is the watch's own estimate, whatever the scores use  # the newest reading, from the daily series or Garmin's snapshot, and not stale
    gv = (found[0], found[1].isoformat()) if found else None
    out["garmin"] = ({"id": "garmin", "maker": "Garmin", "title": "Garmin's VO₂ max", "status": "ok", "value": round(gv[0]), "value_exact": gv[0], "date": gv[1],
                      "headline": f"as of {gv[1]}", "detail": "Garmin's (Firstbeat's) estimate from your runs' heart rate and pace."}
                     if gv else {"id": "garmin", "maker": "Garmin", "title": "Garmin's VO₂ max", "status": "unavailable", "headline": "Not from Garmin yet"})
    # With the Samsung watch, this place is Samsung's estimate instead (its own formula, so not Garmin's series)
    from .samsung import SAMSUNG, watch_on
    from .scores import VO2_MAX_AGE_DAYS
    if watch_on(conn, today.isoformat()) == SAMSUNG:
        sv = [(k, v) for k, v in rp.series(conn, source, "samsung_vo2max_running", today.isoformat()).items()
              if k >= (today - timedelta(days=VO2_MAX_AGE_DAYS)).isoformat()]
        out["garmin"] = ({"id": "garmin", "maker": "Samsung", "title": "Samsung's VO₂ max", "status": "ok", "value": round(max(sv)[1]), "value_exact": max(sv)[1], "date": max(sv)[0],
                          "headline": f"as of {max(sv)[0]}", "detail": "Samsung's estimate from your runs with the watch."}
                         if sv else {"id": "garmin", "maker": "Samsung", "title": "Samsung's VO₂ max", "status": "unavailable",
                                     "headline": "After a run with the Samsung watch"})

    # 5. The HUNT non-exercise formula
    out["hunt"] = hunt_part(conn, source, p.get("sex"), p.get("age"), today)

    # Each VO2 max estimate placed among people of your sex and age (performance isn't: a different quantity)
    if p.get("sex") and p.get("age"):
        for k in ("runs", "questionnaire", "garmin", "hunt"):
            v = out[k].get("value")
            if v is None:
                continue
            # Placed by the unrounded value (46.45 is in the band from 46.4; rounded to 46 it wouldn't be), shown rounded
            it = cp.vo2_item(p["sex"], p["age"], {"vo2max": {"value": float(out[k].get("value_exact", v))}})
            if it.get("status") != "ok":
                continue
            pos = ("below the 40th percentile" if it["position"] == "below" else "above the 95th percentile" if it["position"] == "above"
                   else f"around the {cp.ordinal(it['percentile'])} percentile")
            out[k]["comparison"] = {"headline": f"In the table's {it['rating']} band for {it['group']}", "percentile": it["percentile"],
                                    "detail": f"{v} is {pos} for {it['group']} (the reference group)" + (f"; typical for a {cp.SEX_WORD[p['sex']][0]} of about {it['typical_age']}"
                                                                                 if it.get("typical_age") else "") + ".",
                                    "source": cp.nm.VO2_SOURCE}

    # How the VO2 max estimates relate (performance stays out of this: a different quantity)
    notes = []
    r, gg, qq = out["runs"].get("value"), out["garmin"].get("value"), out["questionnaire"].get("value")
    if r is not None and gg is not None:
        notes.append(f"Your runs and {out['garmin']['maker']} {'are within 2 of each other' if abs(r - gg) <= 2 else f'differ by {abs(r - gg)}'}. Both read "
                     "heart rate against pace, but with different methods and assumptions"
                     + ("." if abs(r - gg) <= 2 else ". Possible reasons include the maximum heart rate assumed, how resting heart rate "
                        "is measured, running economy, conditions and data quality; the app can't tell which. The line above shows how "
                        "much the maximum heart rate alone moves the estimate."))
    hh = out["hunt"].get("value")
    if (qq is not None or hh is not None) and (r is not None or gg is not None):
        which = "The questionnaire and HUNT estimates are broad baselines" if qq is not None and hh is not None else \
            f"The {'questionnaire' if qq is not None else 'HUNT'} estimate is a broad baseline"
        notes.append(which + " from who you are and how active you say you are, not from your runs; they can be several "
                     "points away for one person.")
    out["notes"] = notes
    out["combined"] = combined(out)
    out["basis"] = ("Experimental. The estimates are shown side by side, with their median for comparison; scores and fitness age "
                    "use the VO₂ max source chosen in Settings. They share some inputs, so agreeing doesn't make them more certain. "
                    "Only a laboratory test measures VO₂ max.")
    out["par_scale"] = [{"value": v, "text": t} for v, t in PAR_SCALE]
    out["hunt_questions"] = [{"key": key, "title": title, "options": [{"value": v, "text": txt} for v, txt, _ in opts]}
                             for key, title, opts in (("hunt_frequency", "How often do you exercise?", HUNT_FREQUENCY),
                                                      ("hunt_intensity", "How hard do you usually push yourself?", HUNT_INTENSITY),
                                                      ("hunt_duration", "How long does a session usually last?", HUNT_DURATION))]
    return out

"""Insight engine: a fixed, pre-registered set of questions answered from the user's own data.

Rules (see docs/analysis-rules.md, "Insights"):
  * The question list is fixed in INSIGHTS. We never scan many associations and surface the largest.
  * Every insight reports its verdict, including "no clear pattern" and "not enough data", with sample sizes,
    the method, and known confounders.
  * Comparisons involving heart rate never mix devices (device eras from activity device IDs).
  * Wording is descriptive and associational. Practical notes are framed as options, not prescriptions.
  * Confidence starts at "emerging" and becomes "consistent" only after the same verdict holds on later data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean, median, pstdev

from ..connectors.base import Samples
from . import running as rn

INSIGHTS_VERSION = "insights-1.1"  # 1.1: easy pace
MIN_RUNS = 8
MIN_NIGHTS = 8
EVENING_HOUR = 18
SLEEP_MEANINGFUL_S = 20 * 60
HRV_MEANINGFUL_PCT = 10.0
RHR_MEANINGFUL_BPM = 2.0
TREND_MEANINGFUL_S_PER_KM_PER_MONTH = 5.0


@dataclass
class RunData:
    source_id: str
    local_date: str
    local_start: datetime
    device: str | None
    distance_m: float | None
    moving_s: float | None
    load: float | None
    samples: Samples | None
    splits: list
    classification: str


def insight(iid: str, question: str, category: str, verdict: str, headline: str, detail: str, *, n: int | None = None,
            effect: dict | None = None, evidence: list[str] | None = None, date_range: list[str] | None = None,
            method: str, confounders: list[str] | None = None, practical: str | None = None, chart: dict | None = None) -> dict:
    """verdict: pattern | no_clear_pattern | not_enough_data"""
    return {"id": iid, "question": question, "category": category, "verdict": verdict, "headline": headline,
            "detail": detail, "sample_size": n, "effect": effect or {}, "evidence": {"record_ids": evidence or [], "date_range": date_range or []},
            "method": method, "confounders": confounders or [], "practical": practical, "chart": chart,
            "algorithm_version": INSIGHTS_VERSION, "derived": True}


def theil_sen(points: list[tuple[float, float]]) -> float | None:
    """Robust slope: median of pairwise slopes."""
    slopes = [(y2 - y1) / (x2 - x1) for i, (x1, y1) in enumerate(points) for (x2, y2) in points[i + 1:] if x2 != x1]
    return median(slopes) if slopes else None


def fmt_pace(s: float) -> str:
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d} /km"


def fmt_dur(s: float) -> str:
    m = int(round(s / 60))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


# ---------------------------------------------------------------- I1 intensity distribution

def zone_time(r: RunData, floors: list[float]) -> list[float]:
    """Moving seconds below zone 1 and in zones 1..5 (index 0..5) for one run; stops, gaps and invalid HR excluded."""
    zt = [0.0] * 6
    if not r.samples:
        return zt
    for i, wi in enumerate(rn._weights(r.samples)):
        h = r.samples.hr[i]
        if wi > 0 and h is not None and 60 <= h <= 220:
            zt[sum(1 for f in floors if h >= f)] += wi
    return zt


def intensity_distribution(runs: list[RunData], zones: dict | None) -> dict:
    q = "How is your running time spread across heart-rate zones?"
    if not zones or not zones.get("floors"):
        return insight("intensity", q, "training", "not_enough_data", "Heart-rate zones not available",
                       "Garmin heart-rate zones couldn't be read, so intensity can't be grouped.", method="time in Garmin HR zones")
    floors = zones["floors"]  # zone1..zone5 floors in bpm
    usable = [r for r in runs if r.samples and sum(zone_time(r, floors)) > 0]  # runs with usable heart rate
    if len(usable) < MIN_RUNS:
        return insight("intensity", q, "training", "not_enough_data", "Not enough runs yet",
                       f"Needs {MIN_RUNS} runs with heart rate; {len(usable)} so far.", n=len(usable), method="time in Garmin HR zones")
    totals = [0.0] * 6
    hard_runs = 0
    per_run = []
    for r in usable:
        zt = zone_time(r, floors)
        tot = sum(zt)
        if tot <= 0:
            continue
        hard = (zt[4] + zt[5]) / tot
        per_run.append({"date": r.local_date, "hard_share": round(hard, 3)})
        hard_runs += hard >= 0.5
        totals = [a + b for a, b in zip(totals, zt)]
    T = sum(totals)
    share = {f"z{k}": round(totals[k] / T, 3) for k in range(1, 6)}
    easy = (totals[0] + totals[1] + totals[2]) / T
    hard = (totals[4] + totals[5]) / T
    n = len(per_run)
    effect = {"share": share, "easy_share": round(easy, 3), "hard_share": round(hard, 3), "hard_runs": hard_runs, "runs": n}
    caveat = [f"Zones from Garmin ({zones.get('method')}, max HR {zones.get('max_hr')} bpm). If max HR is estimated rather than "
              "measured, zones may be shifted.", "Wrist heart rate can lag at the start of runs."]
    chart = {"type": "stacked_share", "labels": ["Z1", "Z2", "Z3", "Z4", "Z5"], "values": [share[f"z{k}"] for k in range(1, 6)]}
    if hard >= 0.5:
        return insight("intensity", q, "training", "pattern", f"Most of your running is hard: {round(100 * hard)}% in zones 4–5",
                       f"{hard_runs} of {n} runs spent at least half their moving time above {floors[3]} bpm (your zone 4). "
                       f"Only {round(100 * easy)}% of running time was in zones 1–3.",
                       n=n, effect=effect, evidence=[r.source_id for r in usable], date_range=[usable[0].local_date, usable[-1].local_date],
                       method="Moving-time share per Garmin HR zone, all runs, gaps and stops excluded.", confounders=caveat, chart=chart,
                       practical=f"Many endurance plans keep most running easy, below about {floors[2]} bpm on your zones. "
                                 "If building endurance is the goal, some genuinely easy runs could be worth trying. "
                                 "If hard running is deliberate, this is just a description.")
    return insight("intensity", q, "training", "no_clear_pattern", f"Mixed intensity: {round(100 * easy)}% easy, {round(100 * hard)}% hard",
                   "Your running time is spread across zones rather than concentrated at high intensity.", n=n, effect=effect,
                   evidence=[r.source_id for r in usable], method="Moving-time share per Garmin HR zone.", confounders=caveat, chart=chart)


# ---------------------------------------------------------------- I2 aerobic efficiency trend

def efficiency_trend(runs: list[RunData]) -> dict:
    q = "Are you getting faster at the same heart rate?"
    # Use the most common 10-bpm band across runs so the band reflects how this person actually runs
    band_time: dict[int, float] = {}
    for r in runs:
        if not r.samples:
            continue
        for i, wi in enumerate(rn._weights(r.samples)):
            h = r.samples.hr[i]
            if wi > 0 and h and 100 <= h < 200:
                band_time[int(h // 10) * 10] = band_time.get(int(h // 10) * 10, 0.0) + wi
    if not band_time:
        return insight("efficiency", q, "fitness", "not_enough_data", "No heart-rate data on runs yet", "", method="pace at fixed HR band")
    lo = max(band_time, key=band_time.get)
    hi = lo + 10
    eras: dict[str, list[tuple[RunData, float, float]]] = {}
    for r in runs:
        if not r.samples:
            continue
        t = d = 0.0
        mv = 0.0
        for i, wi in enumerate(rn._weights(r.samples)):
            if wi <= 0:
                continue
            mv += wi
            h = r.samples.hr[i]
            if mv >= 600 and h is not None and lo <= h < hi:  # skip the first 10 min: wrist HR lags
                t += wi
                d += wi * r.samples.speed[i]
        if t >= 300:
            eras.setdefault(r.device or "unknown", []).append((r, t / d * 1000.0, t))
    results = []
    for dev, pts in eras.items():
        if len(pts) < 6:
            continue
        span = (date.fromisoformat(pts[-1][0].local_date) - date.fromisoformat(pts[0][0].local_date)).days
        if span < 21:
            continue
        x0 = date.fromisoformat(pts[0][0].local_date)
        slope = theil_sen([((date.fromisoformat(r.local_date) - x0).days, p) for r, p, _ in pts])
        half = len(pts) // 2
        first, last = median(p for _, p, _ in pts[:half]), median(p for _, p, _ in pts[half:])
        results.append({"device": dev, "runs": len(pts), "span_days": span, "slope_s_per_km_per_30d": round(slope * 30, 1),
                        "first_half_median_pace": round(first), "second_half_median_pace": round(last),
                        "start": pts[0][0].local_date, "end": pts[-1][0].local_date,
                        "points": [{"date": r.local_date, "pace_s_per_km": round(p)} for r, p, _ in pts], "ids": [r.source_id for r, _, _ in pts]})
    method = (f"Pace while heart rate was {lo}–{hi - 1} bpm (your most common band), first 10 min of each run excluded, "
              "stops excluded. Robust (Theil–Sen) trend, computed separately per watch.")
    conf = ["Heat, terrain and fatigue also change pace at a given heart rate; weather isn't included.",
            "Different watches measure heart rate differently, so trends are never compared across devices."]
    if not results:
        return insight("efficiency", q, "fitness", "not_enough_data", "Not enough comparable runs yet",
                       f"Needs 6 runs on the same watch over at least 3 weeks with time at {lo}–{hi - 1} bpm.", method=method, confounders=conf)
    improving = [x for x in results if x["slope_s_per_km_per_30d"] <= -TREND_MEANINGFUL_S_PER_KM_PER_MONTH
                 and x["second_half_median_pace"] < x["first_half_median_pace"]]
    worsening = [x for x in results if x["slope_s_per_km_per_30d"] >= TREND_MEANINGFUL_S_PER_KM_PER_MONTH
                 and x["second_half_median_pace"] > x["first_half_median_pace"]]
    n = sum(x["runs"] for x in results)
    effect = {"band_bpm": [lo, hi - 1], "eras": [{k: v for k, v in x.items() if k != "ids"} for x in results]}
    ids = [i for x in results for i in x["ids"]]
    chart = {"type": "pace_trend", "series": [{"device": x["device"], "points": x["points"]} for x in results]}
    parts = [f"{fmt_pace(x['first_half_median_pace'])} → {fmt_pace(x['second_half_median_pace'])} ({x['start'][5:]}–{x['end'][5:]}, {x['runs']} runs)"
             for x in results]
    if improving and not worsening:
        best = min(improving, key=lambda x: x["slope_s_per_km_per_30d"])
        return insight("efficiency", q, "fitness", "pattern", f"Faster at the same heart rate: about {abs(best['slope_s_per_km_per_30d']):.0f} s/km per month",
                       f"At {lo}–{hi - 1} bpm your typical pace went " + "; ".join(parts) + ".",
                       n=n, effect=effect, evidence=ids, method=method, confounders=conf, chart=chart,
                       practical="A common sign of improving aerobic fitness. It's descriptive: a few weeks of data, no weather adjustment.")
    if worsening and not improving:
        return insight("efficiency", q, "fitness", "pattern", f"Slower at the same heart rate recently",
                       f"At {lo}–{hi - 1} bpm your typical pace went " + "; ".join(parts) + ".", n=n, effect=effect, evidence=ids,
                       method=method, confounders=conf + ["Rising temperatures often cause this in summer."], chart=chart)
    return insight("efficiency", q, "fitness", "no_clear_pattern", "No clear change in pace at the same heart rate",
                   f"At {lo}–{hi - 1} bpm: " + "; ".join(parts) + ".", n=n, effect=effect, evidence=ids, method=method, confounders=conf, chart=chart)


# ---------------------------------------------------------------- I3 pacing pattern

def pacing_pattern(runs: list[RunData]) -> dict:
    q = "How do you usually pace your runs?"
    data = []
    for r in runs:
        sp = [s.pace_s_per_km for s in r.splits if s.complete and s.pace_s_per_km]
        if len(sp) >= 4 and r.classification == "steady":
            h = len(sp) // 2
            data.append((r, mean(sp[:h]), mean(sp[h:]), sp[0], mean(sp[1:])))
    if len(data) < MIN_RUNS:
        return insight("pacing", q, "running", "not_enough_data", "Not enough steady runs yet",
                       f"Needs {MIN_RUNS} steady runs with at least 4 full splits; {len(data)} so far.", n=len(data), method="split comparison")
    pos = sum(1 for _, a, b, _, _ in data if b > a + 3)
    neg = sum(1 for _, a, b, _, _ in data if b < a - 3)
    fast_start = sum(1 for _, _, _, f, rest in data if f < rest - 5)
    n = len(data)
    fade = median(b - a for _, a, b, _, _ in data)
    method = "Complete splits only. Positive split = second half >3 s/km slower than the first; fast start = first km >5 s/km faster than the rest."
    conf = ["Route profile (e.g. uphill finish) and planned progression runs affect splits."]
    effect = {"positive": pos, "negative": neg, "even": n - pos - neg, "fast_start": fast_start, "median_fade_s_per_km": round(fade, 1)}
    if pos / n >= 0.6:
        return insight("pacing", q, "running", "pattern", f"You usually slow down: {pos} of {n} runs faded",
                       f"The second half was typically {fade:.0f} s/km slower than the first. In {fast_start} runs the first km "
                       "was clearly faster than the rest.", n=n, effect=effect, evidence=[r.source_id for r, *_ in data], method=method,
                       confounders=conf, practical="Starting a little slower often gives a more even run. "
                                                   "Worth trying on a familiar route and comparing the splits.")
    return insight("pacing", q, "running", "no_clear_pattern", "Pacing is fairly even across your runs",
                   f"{pos} positive, {neg} negative and {n - pos - neg} even splits.", n=n, effect=effect,
                   evidence=[r.source_id for r, *_ in data], method=method, confounders=conf)


# ---------------------------------------------------------------- I4 evening runs and sleep

def evening_runs_sleep(runs: list[RunData], obs: dict[str, dict[str, float]], bedtimes: dict[str, float]) -> dict:
    q = "Do evening runs affect your sleep?"
    nights = {(r.local_start.date() + timedelta(days=1)).isoformat() for r in runs if r.local_start.hour >= EVENING_HOUR}
    sleep = obs.get("sleep_duration", {})
    hrv = obs.get("hrv_overnight_avg", {})
    a = [d for d in sleep if d in nights]
    b = [d for d in sleep if d not in nights]
    method = f"Nights after a run starting at or after {EVENING_HOUR}:00 vs all other nights with sleep data; medians."
    conf = ["Weekday/weekend schedule and other evening activities aren't accounted for.", "Observational: an association, not a cause."]
    if len(a) < MIN_NIGHTS or len(b) < MIN_NIGHTS:
        return insight("evening_sleep", q, "sleep", "not_enough_data", "Not enough nights to compare yet",
                       f"Needs {MIN_NIGHTS} nights of each kind; have {len(a)} after evening runs and {len(b)} others.",
                       n=len(a) + len(b), method=method, confounders=conf)
    ds = median(sleep[d] for d in a) - median(sleep[d] for d in b)
    ha = [hrv[d] for d in a if d in hrv]
    hb = [hrv[d] for d in b if d in hrv]
    dh = (100 * (median(ha) - median(hb)) / median(hb)) if len(ha) >= MIN_NIGHTS and len(hb) >= MIN_NIGHTS and median(hb) else None
    ba = [bedtimes[d] for d in a if d in bedtimes]
    bb = [bedtimes[d] for d in b if d in bedtimes]
    dbed = (median(ba) - median(bb)) * 60 if ba and bb else None
    effect = {"nights_after": len(a), "nights_other": len(b), "sleep_diff_s": round(ds), "hrv_diff_pct": round(dh, 1) if dh is not None else None,
              "bedtime_diff_min": round(dbed) if dbed is not None else None}
    meaningful = abs(ds) >= SLEEP_MEANINGFUL_S or (dh is not None and abs(dh) >= HRV_MEANINGFUL_PCT)
    sign = "less" if ds < 0 else "more"
    detail = (f"After evening runs you slept {fmt_dur(abs(ds))} {sign} (median)"
              + (f", overnight HRV was {abs(dh):.0f}% {'lower' if dh < 0 else 'higher'}" if dh is not None else "")
              + (f", bedtime {abs(dbed):.0f} min {'later' if dbed > 0 else 'earlier'}" if dbed is not None else "")
              + f". Based on {len(a)} nights after evening runs and {len(b)} other nights.")
    if meaningful:
        return insight("evening_sleep", q, "sleep", "pattern", f"Evening runs go with {'shorter' if ds < 0 else 'longer'} or different sleep",
                       detail, n=len(a) + len(b), effect=effect, method=method, confounders=conf,
                       evidence=sorted(a)[-10:], date_range=[min(sleep), max(sleep)],
                       practical="If sleep matters most on a given day, an earlier run is something you could compare.")
    return insight("evening_sleep", q, "sleep", "no_clear_pattern", "Evening runs don't seem to affect your sleep",
                   detail, n=len(a) + len(b), effect=effect, method=method, confounders=conf, evidence=sorted(a)[-10:],
                   date_range=[min(sleep), max(sleep)])


# ---------------------------------------------------------------- I5 recovery after harder runs

def recovery_after_load(runs: list[RunData], obs: dict[str, dict[str, float]]) -> dict:
    q = "How does your body respond the morning after a harder run?"
    loads = {(date.fromisoformat(r.local_date) + timedelta(days=1)).isoformat(): r.load for r in runs if r.load}
    if len(loads) < MIN_NIGHTS:
        return insight("recovery", q, "recovery", "not_enough_data", "Not enough runs with Garmin training load",
                       "", n=len(loads), method="next-morning HRV/RHR by Garmin load")
    cut = median(loads.values())
    hrv, rhr = obs.get("hrv_overnight_avg", {}), obs.get("resting_hr", {})
    hi = [d for d in hrv if d in loads and loads[d] >= cut]
    rest = [d for d in hrv if d not in loads]
    method = "Overnight HRV and resting HR the morning after runs in the upper half of Garmin training load, vs mornings after no run."
    conf = ["Garmin training load is Garmin's own estimate.", "Life stress, alcohol and late meals also move HRV."]
    if len(hi) < MIN_NIGHTS or len(rest) < MIN_NIGHTS:
        return insight("recovery", q, "recovery", "not_enough_data", "Not enough mornings to compare yet",
                       f"Needs {MIN_NIGHTS} of each; have {len(hi)} after harder runs and {len(rest)} after rest days.",
                       n=len(hi) + len(rest), method=method, confounders=conf)
    dh = 100 * (median(hrv[d] for d in hi) - median(hrv[d] for d in rest)) / median(hrv[d] for d in rest)
    rh = [rhr[d] for d in hi if d in rhr]
    rr = [rhr[d] for d in rest if d in rhr]
    dr = median(rh) - median(rr) if rh and rr else None
    effect = {"hrv_diff_pct": round(dh, 1), "rhr_diff_bpm": dr, "mornings_after_hard": len(hi), "mornings_after_rest": len(rest)}
    detail = (f"Morning after a harder run: HRV {abs(dh):.0f}% {'lower' if dh < 0 else 'higher'}"
              + ("" if dr is None else ", resting HR about the same" if abs(dr) < 1 else
                 f", resting HR {abs(dr):.0f} bpm {'higher' if dr > 0 else 'lower'}")
              + f" than after rest days ({len(hi)} vs {len(rest)} mornings).")
    if dh <= -HRV_MEANINGFUL_PCT or (dr is not None and dr >= RHR_MEANINGFUL_BPM):
        return insight("recovery", q, "recovery", "pattern", "Harder runs show up in your next-morning readings", detail,
                       n=len(hi) + len(rest), effect=effect, method=method, confounders=conf, evidence=sorted(hi)[-10:],
                       practical="So a lower reading the day after a hard run is expected for you, rather than a warning sign by itself.")
    return insight("recovery", q, "recovery", "no_clear_pattern", "Your mornings look similar after harder runs and rest days", detail,
                   n=len(hi) + len(rest), effect=effect, method=method, confounders=conf, evidence=sorted(hi)[-10:],
                   practical="So a low HRV morning is less likely to be explained by the previous day's run.")


# ---------------------------------------------------------------- I6 consistency

def consistency(runs: list[RunData], today: date) -> dict:
    q = "How consistent is your running week to week?"
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=8)
    weeks = [(start + timedelta(weeks=i)) for i in range(8)]
    vol = []
    for w in weeks:
        s = sum(r.moving_s or 0 for r in runs if w <= date.fromisoformat(r.local_date) < w + timedelta(days=7))
        vol.append(s)
    if sum(1 for v in vol if v > 0) < 4:
        return insight("consistency", q, "training", "not_enough_data", "Not enough weeks of running yet", "", method="weekly moving time")
    avg = mean(vol)
    cv = pstdev(vol) / avg if avg else 0
    jumps = [(weeks[i + 1], vol[i + 1] - vol[i]) for i in range(len(vol) - 1)]
    big = max(jumps, key=lambda x: x[1])
    effect = {"weeks": [{"start": w.isoformat(), "moving_s": round(v)} for w, v in zip(weeks, vol)], "cv": round(cv, 2), "mean_s": round(avg)}
    chart = {"type": "weekly_bars", "points": effect["weeks"]}
    method = "Running moving time per calendar week over the last 8 complete weeks; coefficient of variation."
    if cv >= 0.4:
        return insight("consistency", q, "training", "pattern", "Your weekly running varies a lot",
                       f"Weekly running ranged from {fmt_dur(min(vol))} to {fmt_dur(max(vol))} (average {fmt_dur(avg)}). "
                       f"The biggest jump was +{fmt_dur(big[1])} in the week of {big[0].isoformat()[5:]}.",
                       n=8, effect=effect, method=method, chart=chart, confounders=["Travel, illness or a second sport aren't visible here."],
                       practical="Steadier weekly volume is generally easier to absorb than big swings.")
    return insight("consistency", q, "training", "no_clear_pattern", "Your weekly running is fairly steady",
                   f"Average {fmt_dur(avg)} per week over 8 weeks.", n=8, effect=effect, method=method, chart=chart)


# ---------------------------------------------------------------- I7 durability (drift on steady runs)

def durability(drifts: list[tuple[str, str, float]]) -> dict:
    q = "Does your heart rate drift on steady runs?"
    method = "Pace:HR decoupling on eligible steady runs (≥30 min after a 10-min warm-up, ≥90% HR coverage)."
    if len(drifts) < 4:
        return insight("durability", q, "running", "not_enough_data", "Not enough long steady runs yet",
                       f"Needs 4 eligible runs (about 40+ min, steady); {len(drifts)} so far.", n=len(drifts), method=method)
    vals = [v for _, _, v in drifts]
    med = median(vals)
    effect = {"median_pct": round(med, 1), "values": [{"date": d, "pct": v} for d, _, v in drifts]}
    if med <= 5:
        return insight("durability", q, "running", "no_clear_pattern", f"Heart rate holds steady on longer runs (median drift {med:.1f}%)",
                       f"Across {len(vals)} eligible runs, efficiency changed little between halves.", n=len(vals), effect=effect,
                       evidence=[s for _, s, _ in drifts], method=method, confounders=["Only runs of about 40 minutes or more qualify."])
    return insight("durability", q, "running", "pattern", f"Heart rate tends to drift on longer runs (median {med:.1f}%)",
                   f"Across {len(vals)} eligible runs, efficiency dropped in the second half.", n=len(vals), effect=effect,
                   evidence=[s for _, s, _ in drifts], method=method, confounders=["Heat and hydration also cause drift."])


def compute_all(runs: list[RunData], obs: dict, bedtimes: dict, zones: dict | None, drifts: list, today: date) -> list[dict]:
    order = [
        intensity_distribution(runs, zones), easy_pace(runs, zones, today), efficiency_trend(runs), pacing_pattern(runs),
        evening_runs_sleep(runs, obs, bedtimes), recovery_after_load(runs, obs), consistency(runs, today), durability(drifts),
    ]
    rank = {"pattern": 0, "no_clear_pattern": 1, "not_enough_data": 2}
    return sorted(order, key=lambda i: rank[i["verdict"]])


# ---------------------------------------------------------------- your easy pace

def easy_pace(runs: list[RunData], zones: dict | None, today: date) -> dict:
    """Pace that corresponds to easy running (Garmin zones 1–2, i.e. below the zone-3 floor) on the current watch.
    Measured from samples when there's enough easy running; otherwise estimated from the pace–HR relationship of
    1-minute blocks (robust Theil–Sen fit), clearly labelled as an estimate with a range."""
    q = "What is easy pace for you?"
    if not zones or not zones.get("floors"):
        return insight("easy_pace", q, "training", "not_enough_data", "Heart-rate zones not available", "", method="pace in zones 1–2")
    ceiling = zones["floors"][2]
    cutoff = (today - timedelta(days=42)).isoformat()
    recent = [r for r in runs if r.local_date >= cutoff and r.samples]
    if not recent:
        return insight("easy_pace", q, "training", "not_enough_data", "No recent runs with heart rate", "", method="pace in zones 1–2")
    device = recent[-1].device
    recent = [r for r in recent if r.device == device]
    easy_t = easy_d = 0.0
    blocks: list[tuple[float, float]] = []  # (hr, speed) per minute of moving time, after the first 10 minutes
    for r in recent:
        w = rn._weights(r.samples)
        mv = acc_t = acc_h = acc_s = 0.0
        for i, wi in enumerate(w):
            h, sp = r.samples.hr[i], r.samples.speed[i]
            if wi <= 0 or h is None or not 60 <= h <= 220:
                continue
            mv += wi
            if mv < 600:
                continue
            if h < ceiling:
                easy_t += wi
                easy_d += wi * sp
            acc_t += wi; acc_h += wi * h; acc_s += wi * sp
            if acc_t >= 60:
                blocks.append((acc_h / acc_t, acc_s / acc_t))
                acc_t = acc_h = acc_s = 0.0
    method = (f"Pace while heart rate was below {ceiling} bpm (top of your zone 2), last 6 weeks, current watch, "
              "first 10 min of each run excluded.")
    conf = ["Heat, hills and fatigue change the pace that feels easy.", f"Zones are Garmin's ({zones.get('method')}, max HR {zones.get('max_hr')})."]
    if easy_t >= 600:
        pace = easy_t / easy_d * 1000
        return insight("easy_pace", q, "training", "pattern", f"Easy for you is about {fmt_pace(pace)}",
                       f"Measured from {round(easy_t / 60)} minutes of running below {ceiling} bpm across {len(recent)} runs.",
                       n=len(recent), effect={"pace_s_per_km": round(pace), "ceiling_bpm": ceiling, "measured": True},
                       method=method, confounders=conf,
                       practical=f"Keeping easy runs at or slower than {fmt_pace(pace)} keeps them in zone 2.")
    if len(blocks) < 20:
        return insight("easy_pace", q, "training", "not_enough_data", "Not enough recent running to estimate easy pace",
                       f"Needs about 20 minutes of steady running data on this watch; have {len(blocks)}.", n=len(blocks), method=method)
    xs = [h for h, _ in blocks]
    lowest = sorted(xs)[len(xs) // 10]  # 10th percentile of minute-average HR
    if lowest > ceiling + 10:
        # Extrapolating this far below anything actually run would be guesswork, so say so and say how to measure it.
        return insight("easy_pace", q, "training", "pattern", "You haven't run easy recently, so your easy pace is unknown",
                       f"Almost all of your recent running was above {round(lowest)} bpm; your zone 2 ends at {ceiling} bpm. "
                       f"Your pace barely changes across the heart rates you do run at, so it can't be extrapolated reliably.",
                       n=len(recent), effect={"ceiling_bpm": ceiling, "p10_hr": round(lowest), "measured": False},
                       method=method, confounders=conf,
                       practical=f"To find it: one run by heart rate, keeping it below {ceiling} bpm for 30 minutes whatever the pace. "
                                 "Walk breaks are fine. The app will then measure your easy pace from that run.")
    slope = theil_sen([(h, sp) for h, sp in blocks])
    if slope is None or slope <= 0:
        return insight("easy_pace", q, "training", "no_clear_pattern", "Pace and heart rate don't line up clearly enough to estimate",
                       "Your recent runs don't show a consistent pace–heart-rate relationship.", n=len(blocks), method=method)
    intercept = median(sp - slope * h for h, sp in blocks)
    target = ceiling - 3
    resid = sorted(sp - (intercept + slope * h) for h, sp in blocks)
    lo_sp = intercept + slope * target + resid[int(0.25 * (len(resid) - 1))]
    hi_sp = intercept + slope * target + resid[int(0.75 * (len(resid) - 1))]
    mid = intercept + slope * target
    if mid <= 0.5 or lo_sp <= 0.3:
        return insight("easy_pace", q, "training", "not_enough_data", "Easy pace can't be estimated reliably yet",
                       "Your runs are too far above zone 2 to extrapolate.", n=len(blocks), method=method)
    far = min(xs) - target
    return insight("easy_pace", q, "training", "pattern",
                   f"Easy for you is probably around {fmt_pace(1000 / mid)} (estimated)",
                   f"You rarely run below {ceiling} bpm, so this is estimated from how your pace changes with heart rate "
                   f"in {len(blocks)} minutes of recent running: likely between {fmt_pace(1000 / hi_sp)} and {fmt_pace(1000 / lo_sp)}.",
                   n=len(blocks), effect={"pace_s_per_km": round(1000 / mid), "range_s_per_km": [round(1000 / hi_sp), round(1000 / lo_sp)],
                                          "ceiling_bpm": ceiling, "measured": False, "extrapolated_bpm": round(far)},
                   method=method + f" Estimated at {target} bpm from a robust pace–HR line, which extrapolates about {round(far)} bpm "
                                   "below your easiest recorded minute.",
                   confounders=conf + ["An estimate outside the range you actually ran: check it by running at that pace and watching your heart rate."],
                   practical=f"Try an easy run at about {fmt_pace(1000 / mid)} and see whether heart rate settles below {ceiling} bpm.")

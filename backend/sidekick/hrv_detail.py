"""Garmin's detailed overnight HRV: a reading every 5 minutes through the night, with Garmin's sleep stages.

1. The night's curve. HRV usually rises through the night; the first 3 hours of sleep (early) and the last 3 (late)
   are each compared with your own usual. Early low with late back to usual reads "low early, back by morning", a
   pattern often seen after a hard or late day, alcohol or a late meal. Both low reads "low all night".
2. Stability over 7 days (Plews et al. 2012/2013): the rolling 7-day mean of ln(nightly HRV) against your baseline band
   (the 8 weeks before, mean ± 0.5 SD of the nightly ln values, the smallest worthwhile change), and the night-to-night
   swing (CV of the 7 ln values) against your usual swing. Lower and swinging more is the pattern Plews and Flatt
   describe when training isn't being absorbed; higher and steadier when it is.
3. HRV by sleep stage (context only, no verdict): deep sleep comes early in the night, when HRV is lowest, and each
   5-minute value can straddle a stage change, so it largely repeats the night curve.
4. The day before: early-night HRV (against the 14 nights before) after rest days and after hard runs (the top third of
   run loads). Shown only once each has 10 nights and the difference is at least 5% and twice its standard error;
   until then it says what it still needs.

Garmin gives 5-minute values, not beat-to-beat intervals: no spectral analysis is possible. Not medical advice."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median, pstdev

from .connectors.base import Observation

HRV_DETAIL_VERSION = "hrv-detail-1.0"
METHOD = "garmin_5min_hrv"
PART_H = 3.0            # the first and the last 3 hours of sleep
MIN_PART = 12           # ...each needs an hour of readings
MIN_NIGHT = 24          # a night needs 2 hours of readings
MIN_STAGE = 6           # half an hour of readings in a stage
STAGES = {0: "deep", 1: "light", 2: "rem", 3: "awake"}  # Garmin's sleepLevels activityLevel (checked against its stage totals)
USUAL_DAYS, USUAL_MIN = 28, 7
LOW_EARLY, BACK_LATE, LOW_ALL = 0.85, 0.90, 0.90
BASELINE_DAYS, BASELINE_MIN = 56, 14     # Plews baseline: the 8 weeks before the 7-day window
WEEK_MIN = 5                             # a 7-day value needs 5 nights
SWING_MORE = 1.5                         # a swing 1.5× your usual (and 1 point more) is "swinging more"
LINK_DAYS, LINK_MIN, LINK_DIFF = 120, 10, 0.05


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace(".0", "")).replace(tzinfo=timezone.utc)


def readings(hrv: dict | None) -> list[tuple[datetime, float]]:
    return [(ts(x["readingTimeGMT"]), float(x["hrvValue"])) for x in (hrv or {}).get("hrvReadings") or []
            if x.get("hrvValue") is not None and x.get("readingTimeGMT")]


def night_values(hrv: dict | None, sleep: dict | None) -> dict[str, float | None]:
    """One night's early, late and per-stage means from Garmin's payloads; None where there's too little."""
    r = readings(hrv)
    out: dict[str, float | None] = {"hrv_early_avg": None, "hrv_late_avg": None, "hrv_deep_avg": None,
                                    "hrv_light_avg": None, "hrv_rem_avg": None}
    if len(r) < MIN_NIGHT:
        return out
    start = ts(hrv["sleepStartTimestampGMT"]) if hrv.get("sleepStartTimestampGMT") else r[0][0]
    end = ts(hrv["sleepEndTimestampGMT"]) if hrv.get("sleepEndTimestampGMT") else r[-1][0]
    early = [v for t, v in r if (t - start).total_seconds() < PART_H * 3600]
    late = [v for t, v in r if (end - t).total_seconds() < PART_H * 3600 and (t - start).total_seconds() >= PART_H * 3600]
    out["hrv_early_avg"] = round(mean(early), 1) if len(early) >= MIN_PART else None
    out["hrv_late_avg"] = round(mean(late), 1) if len(late) >= MIN_PART else None
    levels = [(ts(x["startGMT"]), ts(x["endGMT"]), round(x["activityLevel"])) for x in (sleep or {}).get("sleepLevels") or []
              if x.get("startGMT") and x.get("endGMT") and x.get("activityLevel") is not None]
    by: dict[int, list[float]] = {}
    for t, v in r:
        k = next((c for a, b, c in levels if a <= t < b), None)
        if k is not None:
            by.setdefault(k, []).append(v)
    for k, name in ((0, "deep"), (1, "light"), (2, "rem")):
        xs = by.get(k, [])
        out[f"hrv_{name}_avg"] = round(mean(xs), 1) if len(xs) >= MIN_STAGE else None
    return out


def night_obs(d: str, hrv: dict | None, sleep: dict | None) -> list[Observation]:
    """The night's derived values as observations, kept after Garmin's raw payloads are purged."""
    return [Observation(local_date=d, metric=m, value=v, state="measured" if v is not None else "not_measured", method=METHOD)
            for m, v in night_values(hrv, sleep).items()]


# ---------------------------------------------------------------- analysis

def series(conn, source: str, metric: str, lo: str, hi: str) -> dict[str, float]:
    q = {"source": source, "metric": metric, "state": "measured", "local_date": {"$gte": lo, "$lte": hi}}
    if metric == "hrv_overnight_avg":
        q["method"] = "garmin_overnight_hrv"  # Garmin's own nightly value only (never mixed with another watch's)
    return {r["local_date"]: r["value"] for r in conn.daily_observation.find(q, {"_id": 0, "local_date": 1, "value": 1})}


def iso(d: date, back: int = 0) -> str:
    return (d - timedelta(days=back)).isoformat()


def usual(vals: dict[str, float], d: date, days: int = USUAL_DAYS, need: int = USUAL_MIN) -> float | None:
    xs = [v for k, v in vals.items() if iso(d, days) <= k < d.isoformat()]
    return median(xs) if len(xs) >= need else None


def night(conn, source: str, d: date) -> dict | None:
    ds = d.isoformat()
    early_s = series(conn, source, "hrv_early_avg", iso(d, USUAL_DAYS), ds)
    late_s = series(conn, source, "hrv_late_avg", iso(d, USUAL_DAYS), ds)
    e, l = early_s.get(ds), late_s.get(ds)
    if e is None and l is None:
        return None
    ue, ul = usual(early_s, d), usual(late_s, d)
    if e is None or l is None or ue is None or ul is None:
        status, say = "learning", "Learning your usual night"
    elif e < LOW_EARLY * ue and l >= BACK_LATE * ul:
        status, say = "low_early", "Low in the first hours of sleep, back to your usual by morning"
    elif e < LOW_ALL * ue and l < LOW_ALL * ul:
        status, say = "low_all_night", "Lower than usual all night"
    else:
        status, say = "usual", "A usual night"
    out = {"status": status, "say": say, "early": e, "late": l, "usual_early": ue, "usual_late": ul, "curve": [], "stages": None}
    raw = conn.raw_payload.find_one({"source": source, "kind": "hrv", "source_key": ds})
    r = readings((raw or {}).get("payload"))
    if r:
        p = raw["payload"]
        start = ts(p["sleepStartTimestampGMT"]) if p.get("sleepStartTimestampGMT") else r[0][0]
        out["curve"] = [{"min": round((t - start).total_seconds() / 60), "value": v} for t, v in r]
        out["sleep_start_local"] = p.get("sleepStartTimestampLocal")
    st = {k: (conn.daily_observation.find_one({"source": source, "metric": f"hrv_{k}_avg", "local_date": ds, "state": "measured"}) or {}).get("value")
          for k in ("deep", "light", "rem")}
    if any(v is not None for v in st.values()):
        out["stages"] = {**st, "say": "Garmin's sleep stages. Deep sleep comes early in the night, when HRV is lowest, so a "
                                      "lower deep-sleep value is usual; shown for context, not judged."}
    return out


def week_point(vals: dict[str, float], d: date) -> tuple[float, float] | None:
    """Plews: the mean and CV (%) of ln(nightly HRV) over the 7 days to d, from 5 nights."""
    xs = [math.log(v) for k, v in vals.items() if iso(d, 6) <= k <= d.isoformat() and v and v > 0]
    if len(xs) < WEEK_MIN:
        return None
    m = mean(xs)
    return m, 100 * pstdev(xs) / m


def stability(conn, source: str, d: date) -> dict | None:
    vals = series(conn, source, "hrv_overnight_avg", iso(d, BASELINE_DAYS + 7 + 60), d.isoformat())
    now = week_point(vals, d)
    if not now:
        return None
    base = [math.log(v) for k, v in vals.items() if iso(d, BASELINE_DAYS + 6) <= k < iso(d, 6) and v and v > 0]
    trend = []
    for k in range(41, -1, -1):  # six weeks of the 7-day value, for the chart
        p = week_point(vals, d - timedelta(days=k))
        trend.append({"date": iso(d, k), "value": round(math.exp(p[0]), 1) if p else None})
    cvs = [p[1] for p in (week_point(vals, d - timedelta(days=k)) for k in range(7, 67)) if p]
    usual_cv = median(cvs) if len(cvs) >= 10 else None
    out = {"mean_ms": round(math.exp(now[0]), 1), "ln_mean": round(now[0], 3), "cv_pct": round(now[1], 1), "usual_cv_pct": None,
           "band_ms": None, "level": "learning", "swing": "learning", "status": "learning", "trend": trend}
    if len(base) >= BASELINE_MIN:
        bm, bsd = mean(base), pstdev(base)
        lo, hi = bm - 0.5 * bsd, bm + 0.5 * bsd
        out["band_ms"] = [round(math.exp(lo), 1), round(math.exp(hi), 1)]
        out["level"] = "below" if now[0] < lo else "above" if now[0] > hi else "within"
    if usual_cv is not None:
        out["usual_cv_pct"] = round(usual_cv, 1)
        out["swing"] = "more" if now[1] > SWING_MORE * usual_cv and now[1] - usual_cv >= 1 else "usual"
    lv, sw = out["level"], out["swing"]
    if lv == "learning":
        say, status = "Learning your 7-day range (needs 2 weeks of nights before this week)", "learning"
    elif lv == "below" and sw == "more":
        say, status = ("Lower than your usual range and swinging more night to night: a pattern often seen when training or "
                       "other stress isn't being absorbed"), "watch"
    elif lv == "below":
        say, status = "Below your usual range this week", "watch"
    elif lv == "above" and sw != "more":
        say, status = "Above your usual range and steady, usually a good sign", "good"
    elif sw == "more":
        say, status = "Within your usual range, but swinging more night to night than usual", "usual"
    else:
        say, status = "Within your usual range" + (", steady" if sw == "usual" else ""), "usual"
    out["say"], out["status"] = say, status
    return out


def day_before(conn, source: str, d: date) -> dict:
    """Early-night HRV after rest days and after hard runs, once the evidence is there."""
    early = series(conn, source, "hrv_early_avg", iso(d, LINK_DAYS + 14), d.isoformat())
    latest: dict[str, dict] = {}
    for r in conn.report.find({"type": "post_run", "local_date": {"$gte": iso(d, LINK_DAYS + 1), "$lte": d.isoformat()}},
                              {"subject_key": 1, "revision": 1, "local_date": 1, "body.load": 1}):
        if r["subject_key"] not in latest or r["revision"] > latest[r["subject_key"]]["revision"]:
            latest[r["subject_key"]] = r
    load: dict[str, float] = {}
    for r in latest.values():
        if (r.get("body") or {}).get("load") is not None:
            load[r["local_date"]] = load.get(r["local_date"], 0) + r["body"]["load"]
    loads = sorted(load.values())
    hard_cut = loads[len(loads) * 2 // 3] if len(loads) >= 6 else None
    rest, hard = [], []
    for k, v in early.items():
        if k < iso(d, LINK_DAYS):
            continue
        u = usual(early, date.fromisoformat(k), 14, 5)
        if u is None:
            continue
        prev = iso(date.fromisoformat(k), 1)
        if prev not in load:
            rest.append(v / u)
        elif hard_cut is not None and load[prev] >= hard_cut:
            hard.append(v / u)
    out = {"rest_nights": len(rest), "hard_nights": len(hard), "status": "learning", "diff_pct": None}
    if len(rest) < LINK_MIN or len(hard) < LINK_MIN:
        need = [f"{LINK_MIN - n} more nights after {w}" for n, w in ((len(rest), "rest days"), (len(hard), "hard runs")) if n < LINK_MIN]
        out["say"] = "Not enough nights yet to compare: needs " + " and ".join(need)
        return out
    diff = mean(hard) - mean(rest)
    se = math.sqrt(pstdev(hard) ** 2 / len(hard) + pstdev(rest) ** 2 / len(rest))
    out["diff_pct"] = round(100 * diff, 1)
    if abs(diff) >= LINK_DIFF and abs(diff) >= 2 * se:
        out["status"] = "shown"
        out["say"] = (f"After hard runs your early-night HRV is about {abs(100 * diff):.0f}% {'lower' if diff < 0 else 'higher'} "
                      f"than after rest days ({len(hard)} and {len(rest)} nights)")
    else:
        out["status"] = "no_difference"
        out["say"] = f"No clear difference yet between nights after hard runs and after rest days ({len(hard)} and {len(rest)} nights)"
    return out


def build(conn, source: str, d: date) -> dict | None:
    n, s = night(conn, source, d), stability(conn, source, d)
    if n is None and s is None:
        return None
    return {"night": n, "stability": s, "day_before": day_before(conn, source, d), "version": HRV_DETAIL_VERSION,
            "note": "From Garmin's HRV readings every 5 minutes overnight (not beat-to-beat). Your own patterns, not medical advice."}


def findings(conn, source: str, d: date) -> list[dict]:
    """For the morning briefing: the night's shape and the 7-day trend when they say something. Informational: they never
    change the day's advice (Garmin's nightly HRV already feeds it)."""
    ds, out = d.isoformat(), []
    base = {"category": "recovery", "comparison": None, "delta": None, "status": "info", "priority": 4, "sample_size": None,
            "coverage": None, "algorithm_version": HRV_DETAIL_VERSION, "derived": True}
    n = night(conn, source, d)
    if n and n["status"] in ("low_early", "low_all_night"):
        out.append({**base, "id": f"m:{ds}:hrv_night", "metric": "hrv_night_shape", "title": "HRV through the night",
                    "observed": {"value": n["early"], "unit": "ms", "late": n["late"]},
                    "comparison": {"kind": "own_usual_28d", "early": round(n["usual_early"], 1), "late": round(n["usual_late"], 1)},
                    "statement": (f"First 3 hours of sleep {n['early']:.0f} ms (usual {n['usual_early']:.0f}), last 3 hours "
                                  f"{n['late']:.0f} ms (usual {n['usual_late']:.0f})."),
                    "interpretation": n["say"] + ("; often after a hard or late day, alcohol or a late meal." if n["status"] == "low_early" else "."),
                    "evidence": {"record_ids": [f"{source}:{ds}:hrv"], "date_range": [iso(d, USUAL_DAYS), ds]},
                    "limitations": ["Garmin's readings every 5 minutes, not beat-to-beat.", "Your own pattern, not a diagnosis."]})
    s = stability(conn, source, d)
    if s and s["status"] in ("watch", "good"):
        out.append({**base, "id": f"m:{ds}:hrv_week", "metric": "hrv_7d_stability", "title": "HRV over 7 days",
                    "observed": {"value": s["mean_ms"], "unit": "ms", "cv_pct": s["cv_pct"]},
                    "comparison": {"kind": "own_baseline_8w", "band_ms": s["band_ms"], "usual_cv_pct": s["usual_cv_pct"]},
                    "statement": (f"7-day HRV {s['mean_ms']:.0f} ms against your usual {s['band_ms'][0]:.0f}–{s['band_ms'][1]:.0f}; "
                                  f"night-to-night swing {s['cv_pct']:.1f}%" + (f" (usual {s['usual_cv_pct']:.1f}%)." if s["usual_cv_pct"] else ".")),
                    "interpretation": s["say"] + ".",
                    "evidence": {"record_ids": [f"{source}:{ds}:hrv_7d"], "date_range": [iso(d, BASELINE_DAYS + 6), ds]},
                    "limitations": ["Log-transformed 7-day average (Plews et al.); the band is the smallest worthwhile change.",
                                    "Your own pattern, not a diagnosis."]})
    return out

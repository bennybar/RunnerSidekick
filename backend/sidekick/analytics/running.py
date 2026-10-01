"""Deterministic run analysis. See docs/analysis-rules.md for definitions and rationale.

Pace basis: moving time (samples with speed >= MOVING_SPEED) unless stated otherwise.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median, pstdev

from ..connectors.base import Samples

RUNNING_VERSION = "running-1.2"  # 1.1: uniform INTERVAL lap labels no longer imply intervals; 1.2: grade-adjusted drift, 20-min segments

MOVING_SPEED = 0.5          # m/s; below this a sample counts as stopped
MAX_SAMPLE_GAP = 10.0       # s; a longer gap between samples is a gap, not weighted time
WARMUP_EXCLUDE_S = 600.0    # drift analysis ignores the first 10 minutes of moving time
MIN_SEGMENT_S = 1200.0      # eligible steady segment must be >= 20 min of moving time (20–30 min flagged as short)
RELIABLE_SEGMENT_S = 1800.0
MIN_HR_COVERAGE = 0.90      # share of moving time with a valid HR sample
MAX_GAIN_PER_KM = 40.0      # m/km; drift uses grade-adjusted speed, so only very hilly runs are excluded
STEADY_MAX_CV = 0.08        # coefficient of variation of 1-min moving speed blocks
HR_VALID = (60.0, 220.0)
COMPLETE_LAP_RATIO = 0.95   # a lap shorter than 95% of the typical lap is incomplete


@dataclass
class Split:
    idx: int
    distance_m: float | None
    moving_s: float | None
    elapsed_s: float | None
    avg_hr: float | None
    elevation_gain_m: float | None
    pace_s_per_km: float | None   # moving-time pace
    complete: bool


def splits_from_laps(laps: list[dict]) -> list[Split]:
    dists = [l["distance_m"] for l in laps if l.get("distance_m")]
    typical = median(dists) if dists else None
    out = []
    for l in laps:
        d, mv = l.get("distance_m"), l.get("moving_s")
        complete = bool(d and typical and d >= COMPLETE_LAP_RATIO * typical)
        out.append(Split(l["idx"], d, mv, l.get("elapsed_s"), l.get("avg_hr"), l.get("elevation_gain_m"),
                         (mv / (d / 1000.0)) if d and mv else None, complete))
    return out


def _weights(s: Samples) -> list[float]:
    """Time each sample represents (to the next sample); 0 across gaps or when stopped."""
    w = []
    for i in range(len(s.t)):
        dt = (s.t[i + 1] - s.t[i]) if i + 1 < len(s.t) else 0.0
        sp = s.speed[i]
        w.append(dt if 0 < dt <= MAX_SAMPLE_GAP and sp is not None and sp >= MOVING_SPEED else 0.0)
    return w


def classify(s: Samples | None, laps: list[dict]) -> dict:
    """steady | variable | unknown, with the evidence used."""
    # Only rest/recovery laps indicate structure. Garmin labels every lap INTERVAL on some devices, even for
    # auto-laps on an ordinary run (observed in live data 2026-10-01), so that label alone carries no signal.
    intensities = {(l.get("intensity") or "").upper() for l in laps}
    if intensities & {"REST", "RECOVERY"}:
        return {"kind": "variable", "reason": "source laps include rest/recovery laps"}
    if s is None or len(s.t) < 10:
        return {"kind": "unknown", "reason": "no sample data"}
    w = _weights(s)
    blocks, acc_t, acc_d = [], 0.0, 0.0
    for i, wi in enumerate(w):
        if wi <= 0:
            continue
        acc_t += wi
        acc_d += wi * s.speed[i]
        if acc_t >= 60.0:
            blocks.append(acc_d / acc_t)
            acc_t = acc_d = 0.0
    if len(blocks) < 10:
        return {"kind": "unknown", "reason": "fewer than 10 minutes of moving data"}
    # Ignore warm-up/cool-down blocks so an easy start does not mask a steady run
    core = blocks[len(blocks) // 10: len(blocks) - len(blocks) // 10] or blocks
    cv = pstdev(core) / (sum(core) / len(core))
    return {"kind": "steady" if cv <= STEADY_MAX_CV else "variable", "reason": f"1-min speed CV {cv:.3f}",
            "speed_cv": round(cv, 4), "threshold": STEADY_MAX_CV}


def decoupling(s: Samples | None, laps: list[dict], distance_m: float | None, gain_m: float | None) -> dict:
    """Pace:HR decoupling = 100 * (EF1 - EF2) / EF1 on the eligible steady segment.

    EF = time-weighted mean speed / time-weighted mean HR. Halves split by moving time.
    Speed is grade-adjusted (Minetti) when elevation is recorded, so hills don't masquerade as drift.
    Returns {"eligible": False, "reasons": [...]} when prerequisites are not met.
    """
    reasons = []
    graded = s is not None and any(e is not None for e in s.elev)
    if graded:
        s = with_gap(s)
    cls = classify(s, laps)
    if cls["kind"] != "steady":
        reasons.append(f"run is not steady ({cls['reason']})")
    if distance_m and gain_m is not None and distance_m > 0 and gain_m / (distance_m / 1000.0) > MAX_GAIN_PER_KM:
        reasons.append(f"hilly: {gain_m / (distance_m / 1000.0):.0f} m/km gain exceeds {MAX_GAIN_PER_KM:.0f}")
    if s is None:
        return {"eligible": False, "reasons": reasons or ["no sample data"], "classification": cls}
    w = _weights(s)
    # exclude warm-up by moving time
    seg, moving = [], 0.0
    for i, wi in enumerate(w):
        if wi <= 0:
            continue
        if moving >= WARMUP_EXCLUDE_S:
            seg.append(i)
        moving += wi
    seg_time = sum(w[i] for i in seg)
    hr_ok = [i for i in seg if s.hr[i] is not None and HR_VALID[0] <= s.hr[i] <= HR_VALID[1]]
    coverage = (sum(w[i] for i in hr_ok) / seg_time) if seg_time else 0.0
    if seg_time < MIN_SEGMENT_S:
        reasons.append(f"eligible segment {seg_time / 60:.0f} min < {MIN_SEGMENT_S / 60:.0f} min after warm-up")
    if coverage < MIN_HR_COVERAGE:
        reasons.append(f"heart-rate coverage {coverage:.0%} < {MIN_HR_COVERAGE:.0%}")
    if reasons:
        return {"eligible": False, "reasons": reasons, "classification": cls, "hr_coverage": round(coverage, 3)}
    half = seg_time / 2.0
    acc, first, second = 0.0, [], []
    for i in seg:
        (first if acc < half else second).append(i)
        acc += w[i]

    def ef(idx: list[int]) -> tuple[float, float, float]:
        valid = [i for i in idx if i in hr_set]
        tw = sum(w[i] for i in valid)
        sp = sum(w[i] * s.speed[i] for i in valid) / tw
        hr = sum(w[i] * s.hr[i] for i in valid) / tw
        return sp / hr, sp, hr

    hr_set = set(hr_ok)
    ef1, sp1, hr1 = ef(first)
    ef2, sp2, hr2 = ef(second)
    return {
        "eligible": True, "decoupling_pct": round(100.0 * (ef1 - ef2) / ef1, 2),
        "first_half": {"mean_speed_mps": round(sp1, 4), "mean_hr": round(hr1, 1), "ef": round(ef1, 6)},
        "second_half": {"mean_speed_mps": round(sp2, 4), "mean_hr": round(hr2, 1), "ef": round(ef2, 6)},
        "segment_moving_s": round(seg_time), "hr_coverage": round(coverage, 3), "classification": cls,
        "grade_adjusted": graded, "short_segment": seg_time < RELIABLE_SEGMENT_S,
        "method": ("grade-adjusted speed (Minetti), " if graded else "") +
                  "time-weighted, warm-up 10 min excluded, stopped samples and gaps > 10 s excluded",
    }


def moving_pace(distance_m: float | None, moving_s: float | None) -> float | None:
    return moving_s / (distance_m / 1000.0) if distance_m and moving_s else None


def similar_runs(target: dict, candidates: list[dict], limit: int = 5) -> dict:
    """Transparent matching: same sport, distance ±20%, elevation gain per km within ±8 m/km, steady both."""
    def gpk(a):
        return (a["elevation_gain_m"] or 0.0) / (a["distance_m"] / 1000.0) if a.get("distance_m") else None

    criteria = {"sport": target["sport"], "distance_ratio": [0.8, 1.2], "gain_per_km_tolerance": 8.0, "classification": "steady"}
    tg = gpk(target)
    matches = []
    for c in candidates:
        if c["source_id"] == target["source_id"] or c["sport"] != target["sport"] or not c.get("distance_m"):
            continue
        if not (0.8 <= c["distance_m"] / target["distance_m"] <= 1.2):
            continue
        cg = gpk(c)
        if tg is not None and cg is not None and abs(cg - tg) > 8.0:
            continue
        if c.get("classification") != "steady":
            continue
        matches.append(c)
    matches.sort(key=lambda c: c["start_utc"], reverse=True)
    matches = matches[:limit]
    out = {"criteria": criteria, "n": len(matches), "runs": [], "summary": None}
    tp = moving_pace(target["distance_m"], target["moving_s"])
    for m in matches:
        out["runs"].append({"source_id": m["source_id"], "local_date": m["local_date"], "distance_m": m["distance_m"],
                            "pace_s_per_km": moving_pace(m["distance_m"], m["moving_s"]), "avg_hr": m["avg_hr"]})
    paces = [r["pace_s_per_km"] for r in out["runs"] if r["pace_s_per_km"]]
    hrs = [r["avg_hr"] for r in out["runs"] if r["avg_hr"]]
    if len(paces) >= 3 and tp:
        out["summary"] = {
            "median_pace_s_per_km": median(paces), "pace_delta_s_per_km": round(tp - median(paces), 1),
            "median_avg_hr": median(hrs) if len(hrs) >= 3 else None,
            "avg_hr_delta": round(target["avg_hr"] - median(hrs), 1) if len(hrs) >= 3 and target.get("avg_hr") else None,
        }
    return out


def workload(acts: list[dict], start: str, end: str) -> dict:
    sel = [a for a in acts if start <= a["local_date"] <= end]
    return {
        "start": start, "end": end, "runs": len(sel),
        "distance_m": round(sum(a["distance_m"] or 0 for a in sel), 1),
        "moving_s": round(sum(a["moving_s"] or 0 for a in sel)),
        "elevation_gain_m": round(sum(a["elevation_gain_m"] or 0 for a in sel), 1),
        "activity_ids": [a["source_id"] for a in sel],
    }


def as_dict(x) -> dict:
    return asdict(x)


# ---------------------------------------------------------------- grade-adjusted pace (Minetti et al. 2002)

GRADE_WINDOW_M = 50.0   # grade measured over ~50 m of distance to smooth GPS/barometer noise
GRADE_CLAMP = 0.30      # outside ±30% the energy-cost model isn't reliable; clamp


def minetti_cost(i: float) -> float:
    """Energy cost of running (J/kg/m) at gradient i (rise/run), Minetti et al. 2002, J Appl Physiol 93:1039."""
    return 155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3 + 46.3 * i**2 + 19.5 * i + 3.6


def grades(s: Samples) -> list[float | None]:
    """Per-sample gradient from distance and elevation over a ~50 m window; None where either is missing."""
    out: list[float | None] = [None] * len(s.t)
    j = 0
    for i in range(len(s.t)):
        if s.dist[i] is None or s.elev[i] is None:
            continue
        while j < i and (s.dist[j] is None or s.elev[j] is None or s.dist[i] - s.dist[j] > GRADE_WINDOW_M):
            j += 1
        if s.dist[j] is not None and s.elev[j] is not None and s.dist[i] - s.dist[j] >= GRADE_WINDOW_M * 0.6:
            g = (s.elev[i] - s.elev[j]) / (s.dist[i] - s.dist[j])
            out[i] = max(-GRADE_CLAMP, min(GRADE_CLAMP, g))
    return out


def gap_speeds(s: Samples) -> list[float | None]:
    """Grade-adjusted speed: the flat-ground speed with the same energy cost. Flat = unchanged; uphill = faster."""
    c0 = minetti_cost(0.0)
    out = []
    for sp, g in zip(s.speed, grades(s)):
        out.append(None if sp is None else sp * (minetti_cost(g) / c0 if g is not None else 1.0))
    return out


def with_gap(s: Samples) -> Samples:
    return Samples(s.t, s.hr, gap_speeds(s), s.dist, s.elev, s.cad)


# ---------------------------------------------------------------- best efforts

BEST_EFFORT_DISTANCES = {"1k": 1000.0, "5k": 5000.0, "10k": 10000.0, "half": 21097.5}


def best_efforts(s: Samples | None) -> dict[str, dict]:
    """Fastest continuous segment for each distance, by elapsed time within the run (stops included, as a race would
    count them). Boundaries are linearly interpolated between samples. Gaps > 30 s end a segment's eligibility."""
    if s is None or len(s.t) < 2:
        return {}
    pts = [(s.t[i], s.dist[i]) for i in range(len(s.t)) if s.dist[i] is not None]
    if len(pts) < 2:
        return {}
    out = {}
    for key, target in BEST_EFFORT_DISTANCES.items():
        if pts[-1][1] - pts[0][1] < target:
            continue
        best = None
        j = 0
        for i in range(len(pts)):
            # advance j to the last point at least `target` metres behind i
            while j + 1 < i and pts[i][1] - pts[j + 1][1] >= target:
                j += 1
            if pts[i][1] - pts[j][1] < target:
                continue
            (t0, d0), (t1, d1) = pts[j], pts[j + 1] if j + 1 <= i else pts[j]
            # interpolate the start so the segment is exactly `target` long
            need = pts[i][1] - target
            ts = t0 + (t1 - t0) * ((need - d0) / (d1 - d0)) if d1 > d0 else t0
            if any(pts[k + 1][0] - pts[k][0] > 30 for k in range(j, i)):
                continue
            dur = pts[i][0] - ts
            if dur > 0 and (best is None or dur < best[0]):
                best = (dur, ts, pts[i][0])
        if best:
            out[key] = {"distance_m": target, "elapsed_s": round(best[0], 1), "start_t": round(best[1], 1), "end_t": round(best[2], 1),
                        "pace_s_per_km": round(best[0] / (target / 1000.0), 1)}
    return out


# ---------------------------------------------------------------- run story (km by km)

def split_details(s: Samples | None, laps: list[dict], floors: list[float] | None) -> list[dict]:
    """Per lap: GAP pace, dominant HR zone and cadence from the samples falling inside the lap."""
    if s is None:
        return []
    gap = gap_speeds(s)
    w = _weights(s)
    out, t_start = [], 0.0
    for lap in laps:
        dur = lap.get("elapsed_s") or 0
        t_end = t_start + dur
        idx = [i for i, t in enumerate(s.t) if t_start <= t < t_end and w[i] > 0]
        tw = sum(w[i] for i in idx)
        gsp = sum(w[i] * gap[i] for i in idx if gap[i]) / tw if tw else None
        cads = [s.cad[i] for i in idx if s.cad[i]]
        zone = None
        if floors and idx:
            zt = [0.0] * 6
            for i in idx:
                h = s.hr[i]
                if h is not None and 60 <= h <= 220:
                    zt[sum(1 for f in floors if h >= f)] += w[i]
            zone = max(range(6), key=lambda k: zt[k]) if sum(zt) else None
        out.append({"idx": lap["idx"], "gap_pace_s_per_km": round(1000.0 / gsp, 1) if gsp else None,
                    "cadence_spm": round(sum(cads) / len(cads)) if cads else None, "zone": zone})
        t_start = t_end
    return out


def run_story(splits: list[Split], details: list[dict], fmt_pace) -> list[str]:
    """A few deterministic sentences describing how the run unfolded. Complete splits only."""
    full = [(s, d) for s, d in zip(splits, details or [{}] * len(splits)) if s.complete and s.pace_s_per_km]
    if len(full) < 3:
        return []
    paces = [s.pace_s_per_km for s, _ in full]
    out = []
    fastest = min(full, key=lambda x: x[0].pace_s_per_km)[0]
    slowest = max(full, key=lambda x: x[0].pace_s_per_km)[0]
    out.append(f"Fastest km was #{fastest.idx + 1} ({fmt_pace(fastest.pace_s_per_km)}); slowest was #{slowest.idx + 1} "
               f"({fmt_pace(slowest.pace_s_per_km)}).")
    h = len(paces) // 2
    fade = sum(paces[h:]) / (len(paces) - h) - sum(paces[:h]) / h
    if fade > 5:
        mean_first = sum(paces[:h]) / h
        k = next((s.idx for s, _ in full[h:] if s.pace_s_per_km > mean_first + 5), None)
        out.append(f"You faded by about {fade:.0f} s/km in the second half" + (f", from km #{k + 1}." if k is not None else "."))
    elif fade < -5:
        out.append(f"You finished strongly: the second half was {abs(fade):.0f} s/km faster (a negative split).")
    else:
        out.append("Pacing was even from start to finish.")
    zones = [d.get("zone") for _, d in full if d.get("zone") is not None]
    if zones:
        first_hard = next((s.idx for s, d in full if (d.get("zone") or 0) >= 4), None)
        if first_hard is not None:
            out.append(f"Heart rate was mostly in zone 4 or higher from km #{first_hard + 1}" +
                       (" onwards." if all((d.get("zone") or 0) >= 4 for s, d in full if s.idx >= first_hard) else ", with some easier stretches."))
        else:
            out.append("Heart rate stayed at or below zone 3 throughout.")
    cads = [d.get("cadence_spm") for _, d in full if d.get("cadence_spm")]
    if len(cads) >= 3:
        drop = cads[0] - cads[-1]
        out.append(f"Cadence dropped from {cads[0]} to {cads[-1]} steps/min by the end." if drop >= 4 else
                   f"Cadence held steady around {round(sum(cads) / len(cads))} steps/min.")
    hilly = [(s, d) for s, d in full if d.get("gap_pace_s_per_km") and s.pace_s_per_km - d["gap_pace_s_per_km"] > 8]
    if hilly:
        s, d = max(hilly, key=lambda x: x[0].pace_s_per_km - x[1]["gap_pace_s_per_km"])
        out.append(f"Km #{s.idx + 1} was uphill: {fmt_pace(s.pace_s_per_km)} actual, about {fmt_pace(d['gap_pace_s_per_km'])} on the flat.")
    return out

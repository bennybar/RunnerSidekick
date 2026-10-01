"""Deterministic run analysis. See docs/analysis-rules.md for definitions and rationale.

Pace basis: moving time (samples with speed >= MOVING_SPEED) unless stated otherwise.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median, pstdev

from ..connectors.base import Samples

RUNNING_VERSION = "running-1.1"  # 1.1: uniform INTERVAL lap labels no longer imply intervals

MOVING_SPEED = 0.5          # m/s; below this a sample counts as stopped
MAX_SAMPLE_GAP = 10.0       # s; a longer gap between samples is a gap, not weighted time
WARMUP_EXCLUDE_S = 600.0    # drift analysis ignores the first 10 minutes of moving time
MIN_SEGMENT_S = 1800.0      # eligible steady segment must be >= 30 min of moving time
MIN_HR_COVERAGE = 0.90      # share of moving time with a valid HR sample
MAX_GAIN_PER_KM = 15.0      # m/km; hillier runs are not eligible for drift analysis
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
    Returns {"eligible": False, "reasons": [...]} when prerequisites are not met.
    """
    reasons = []
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
        "method": "time-weighted, warm-up 10 min excluded, stopped samples and gaps > 10 s excluded",
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

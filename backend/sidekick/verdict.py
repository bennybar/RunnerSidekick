"""How a run went against what it was meant to be: one verdict per run, not a score.

Training runs are judged on execution against the runner's intent for the run, else the day's plan: On target, Harder
than planned, Easier than planned, Shortened, or Not enough data. A run with neither isn't judged against a type
inferred from the run itself (that would always come out "on target"). Only races and time trials get a number: the
age grade (USATF/Alan Jones road standards) for their actual distance and time, when that's a standard distance.
Calculated from the run's report; no language model."""

from __future__ import annotations

import re
from datetime import date
from statistics import mean, pstdev

from . import reports as rp
from .db import one

VERDICT_VERSION = "verdict-1.0"
EASY_KINDS = {"easy", "recovery", "long"}
EASY_MIN_SHARE, EASY_MAX_HARD = 0.5, 0.1  # easy: at least half below zone 3, at most 10% in zones 4–5 (of moving time)
STEADY_MAX_HARD = 0.3
HARD_MIN_SHARE = {"tempo": 0.3, "threshold": 0.3, "intervals": 0.2}
REPEAT_CV = 0.05            # work laps within 5% of each other's pace are consistent
SHORT_SHARE = 0.8           # under 80% of the planned minutes is a shortened run
HR_CAP_OVER = 0.1           # a heart-rate cap is kept with at most 10% of the time above it
RACE_DIST_TOL = 0.02        # a race is age-graded when its distance is within 2% of a standard one
RACE_DIST = {"5k": 5000, "10k": 10000, "half": 21097.5, "marathon": 42195}
WORDS = {"on_target": "On target", "harder": "Harder than planned", "easier": "Easier than planned",
         "shortened": "Shortened", "not_enough_data": "Not enough data", "race": "Race"}


def out(verdict: str, judged: str | None, basis: str | None, say: str, **extra) -> dict:
    return {"verdict": verdict, "label": WORDS[verdict], "judged_as": judged, "basis": basis, "say": say,
            "algorithm_version": VERDICT_VERSION, **extra}


def build(conn, source: str, report: dict, act: dict, laps: list[dict], today: date) -> dict | None:
    intent = report.get("intent") or {}
    kind = intent.get("kind") if intent.get("source") in ("user", "plan") else None
    basis = {"user": "your intent for the run", "plan": "the day's plan"}.get(intent.get("source"))
    if kind is None:
        return out("not_enough_data", None, None, "Set what the run was meant to be to see how it went against it.")
    if kind in ("free", "other"):
        return None
    if kind == "race":
        return race(conn, report, act, today, basis)

    # Shortened: against the plan's minutes, when the plan gave some
    plan = one(conn.day_plan, {"local_date": act["local_date"]})
    planned_s = 60 * plan["minutes"] if plan and plan.get("minutes") else None
    if planned_s and (act.get("moving_s") or 0) < SHORT_SHARE * planned_s:
        return out("shortened", kind, basis, f"{round((act.get('moving_s') or 0) / 60)} of the planned {plan['minutes']} minutes.")

    # A heart-rate cap written as the target ("HR <= 150", "HR < 150", "under 150 bpm")
    cap = re.search(r"(?:hr\s*(?:<=|<|≤)|under)\s*(\d{2,3})", (intent.get("target") or "").lower())
    zones = rp.hr_zones(conn)
    from .focus import zone_shares
    z = zone_shares(conn, act, zones["floors"]) if zones else None
    if cap:
        over = above_share(conn, act, int(cap.group(1)))
        if over is None:
            return out("not_enough_data", kind, basis, "Too little heart rate recorded to check the target.")
        return out("on_target" if over <= HR_CAP_OVER else "harder", kind, basis,
                   f"{round(100 * over)}% of the time above {cap.group(1)} bpm (target: {intent['target']}).")
    if kind == "progression":
        splits = [s for s in report.get("splits", []) if s.get("complete") and s.get("pace_s_per_km")]
        if len(splits) < 4:
            return out("not_enough_data", kind, basis, "Too few full kilometres to judge a progression.")
        from .analytics import running as rn
        fade = rn.fade([s.get("gap_pace_s_per_km") or s["pace_s_per_km"] for s in splits])
        return out("on_target" if fade < -rn.FADE_S_PER_KM else "easier", kind, basis,
                   f"Second half {abs(round(fade))} s/km {'faster' if fade < 0 else 'slower'} (hill-adjusted).")
    if z is None:
        return out("not_enough_data", kind, basis, "Not enough heart rate in zones to judge the effort.")
    easy, hard = z["easy"], z["hard"]
    if kind in EASY_KINDS:
        v = "harder" if easy < EASY_MIN_SHARE or hard > EASY_MAX_HARD else "on_target"
        return out(v, kind, basis, f"{round(100 * easy)}% below zone 3, {round(100 * hard)}% in zones 4–5.",
                   hr_note=hr_caveat(report))
    if kind == "steady":
        return out("on_target" if hard <= STEADY_MAX_HARD else "harder", kind, basis, f"{round(100 * hard)}% in zones 4–5.",
                   hr_note=hr_caveat(report))
    if kind in HARD_MIN_SHARE:
        if hard < HARD_MIN_SHARE[kind]:
            return out("easier", kind, basis, f"{round(100 * hard)}% in zones 4–5, light for a {kind} session.", hr_note=hr_caveat(report))
        if kind == "intervals":
            work = [l for l in laps if (l.get("intensity") or "").upper() not in ("REST", "RECOVERY", "WARMUP", "COOLDOWN")
                    and l.get("distance_m") and l.get("moving_s")]
            if not any((l.get("intensity") or "").upper() in ("REST", "RECOVERY") for l in laps) or len(work) < 3:
                return out("on_target", kind, basis, f"{round(100 * hard)}% in zones 4–5; repeats not judged (no recorded "
                                                     "work and recovery laps).", hr_note=hr_caveat(report))
            paces = [l["moving_s"] / (l["distance_m"] / 1000) for l in work]
            cv = pstdev(paces) / mean(paces)
            return out("on_target" if cv <= REPEAT_CV else "harder", kind, basis,
                       f"{len(work)} repeats, pace varied {100 * cv:.0f}% between them; {round(100 * hard)}% in zones 4–5.",
                       hr_note=hr_caveat(report))
        return out("on_target", kind, basis, f"{round(100 * hard)}% in zones 4–5.", hr_note=hr_caveat(report))
    return None


def race(conn, report: dict, act: dict, today: date, basis: str | None) -> dict:
    """A race or time trial: its age grade for the actual distance and time, when that's a standard distance."""
    from . import compare as cp
    p = cp.profile(conn, today)
    dist = act.get("distance_m") or 0
    key = next((k for k, m in RACE_DIST.items() if abs(dist - m) <= RACE_DIST_TOL * m), None)
    if key is None or not p.get("sex") or not p.get("birth_date"):
        why = "not a standard distance (5 km, 10 km, half, marathon)" if key is None else "needs your sex and birth date"
        return out("race", "race", basis, f"No age grade: {why}.")
    age = cp.age_on(p["birth_date"], date.fromisoformat(act["local_date"]))
    ag = cp.age_grade(p["sex"], age, key, act.get("elapsed_s") or 0)
    if ag is None:
        return out("race", "race", basis, "No age grade for this age.")
    return out("race", "race", basis, f"{cp.DISTANCE_LABELS[key]} in {rp.fmt_duration_s(act['elapsed_s'])}: age grade "
               f"{ag['age_grade_pct']:.1f}% ({ag['class']}).", age_grade=ag, distance=key,
               note="Age grade from the USATF/Alan Jones road standards for your age and sex; elapsed time, as recorded.")


def above_share(conn, act: dict, cap: int) -> float | None:
    """Share of moving time with heart rate above `cap`."""
    s = rp.samples_for(conn, act["id"])
    if s is None:
        return None
    from .analytics.running import MAX_SAMPLE_GAP, MOVING_SPEED
    tot = over = 0.0
    for i in range(1, len(s.t)):
        dt = s.t[i] - s.t[i - 1]
        if 0 < dt <= MAX_SAMPLE_GAP and (s.speed[i] or 0) >= MOVING_SPEED and s.hr[i] is not None:
            tot += dt
            over += dt if s.hr[i] > cap else 0.0
    return over / tot if tot >= 300 else None


def hr_caveat(report: dict) -> str | None:
    q = report.get("hr_quality") or {}
    return f"The heart-rate recording looked {q['grade']} in parts, so this verdict is less certain." if q.get("grade") in ("questionable", "poor") else None

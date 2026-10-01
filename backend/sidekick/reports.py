"""Deterministic report generation. Every finding carries its evidence; reports are revisioned by input hash.

A report is regenerated only when its inputs hash differently. Old revisions are kept, so the
journal shows what was known at the time rather than re-deriving the past with current baselines.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta
from statistics import median, pstdev

from .analytics import baseline as bl
from .analytics import running as rn
from .analytics.recommend import RULES_VERSION, recommend
from .connectors.base import GARMIN_PROPRIETARY, Samples
from .db import utc_now

REPORT_VERSION = "report-2.1"  # 2.0: plans, run intent, insight novelty/state; 2.1: R1e  # 1.1: boolean check-in flags, wording; 1.2: subjective-only rule R4s; 1.3: wording; 1.4: device eras ; 1.5: sparkline while learning; 1.6: best efforts, run story, GAP splits
ALGORITHMS = {"report": REPORT_VERSION, "baseline": bl.BASELINE_VERSION, "running": rn.RUNNING_VERSION, "rules": RULES_VERSION}

CORE_METRICS = ("sleep_duration", "resting_hr", "hrv_overnight_avg")
METRIC_TITLES = {"sleep_duration": "Sleep", "resting_hr": "Resting heart rate", "hrv_overnight_avg": "Overnight HRV"}
CATEGORY = {"sleep_duration": "sleep", "resting_hr": "recovery", "hrv_overnight_avg": "recovery"}


# ---------------------------------------------------------------- formatting for template statements

def fmt_duration(s: float) -> str:
    m = int(round(s / 60.0))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def fmt_value(metric: str, v: float) -> str:
    if metric == "sleep_duration":
        return fmt_duration(v)
    return f"{v:.0f} {'bpm' if metric == 'resting_hr' else 'ms'}"


def fmt_delta(metric: str, d: float) -> str:
    sign = "+" if d > 0 else "−" if d < 0 else "±"
    if metric == "sleep_duration":
        return f"{sign}{fmt_duration(abs(d))}"
    return f"{sign}{abs(d):.0f} {'bpm' if metric == 'resting_hr' else 'ms'}"


def fmt_duration_s(s: float) -> str:
    s = int(round(s))
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def fmt_pace(s_per_km: float) -> str:
    m, s = divmod(int(round(s_per_km)), 60)
    return f"{m}:{s:02d} /km"


# ---------------------------------------------------------------- queries

def series(conn, source: str, metric: str, until: str, method: str | None = None) -> dict[str, float]:
    q = "SELECT local_date, value FROM daily_observation WHERE source=? AND metric=? AND state='measured' AND local_date<=?"
    args = [source, metric, until]
    if method:
        q += " AND method=?"
        args.append(method)
    return {r["local_date"]: r["value"] for r in conn.execute(q, args)}


def day_obs(conn, source: str, d: str) -> dict[str, sqlite3.Row]:
    return {r["metric"]: r for r in conn.execute("SELECT * FROM daily_observation WHERE source=? AND local_date=?", (source, d))}


def checkin_for(conn, d: str) -> dict | None:
    r = conn.execute("SELECT * FROM checkin WHERE local_date=? AND deleted=0 ORDER BY client_updated_at DESC LIMIT 1", (d,)).fetchone()
    if not r:
        return None
    c = dict(r)
    c["tags"] = json.loads(c.pop("tags_json"))
    c["pain"], c["illness"], c["deleted"] = bool(c["pain"]), bool(c["illness"]), bool(c["deleted"])
    return c


def activities(conn, source: str, start: str, end: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM activity WHERE source=? AND local_date BETWEEN ? AND ? AND sport!='other' ORDER BY start_utc", (source, start, end))]


def activity_by_source_id(conn, source: str, sid: str) -> dict | None:
    r = conn.execute("SELECT * FROM activity WHERE source=? AND source_id=?", (source, sid)).fetchone()
    return dict(r) if r else None


def laps_for(conn, aid: int) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM activity_lap WHERE activity_id=? ORDER BY idx", (aid,))]


def samples_for(conn, aid: int) -> Samples | None:
    r = conn.execute("SELECT samples_json FROM activity_samples WHERE activity_id=?", (aid,)).fetchone()
    return Samples.from_json(json.loads(r["samples_json"])) if r else None


def device_era_start(conn, source: str, d: date) -> date | None:
    """First day of the device era containing d, inferred from activity device IDs (daily payloads carry none).
    The era starts the day after the last run recorded by a different device. Precision is limited to the days
    between runs."""
    rows = conn.execute("SELECT local_date, device_id FROM activity WHERE source=? AND device_id IS NOT NULL ORDER BY start_utc",
                        (source,)).fetchall()
    if not rows:
        return None
    ds = d.isoformat()
    before = [r for r in rows if r["local_date"] <= ds]
    current = before[-1]["device_id"] if before else rows[0]["device_id"]
    others = [r["local_date"] for r in before if r["device_id"] != current]
    return date.fromisoformat(max(others)) + timedelta(days=1) if others else None


def get_setting(conn, key: str, default):
    r = conn.execute("SELECT value_json FROM user_settings WHERE key=?", (key,)).fetchone()
    return json.loads(r["value_json"]) if r else default


def data_cutoff(conn, source: str) -> str | None:
    r = conn.execute("SELECT last_success_at FROM source_connection WHERE source=?", (source,)).fetchone()
    return r["last_success_at"] if r else None


# ---------------------------------------------------------------- revisioned storage

def input_hash(inputs: object) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:20]


def save_report(conn, rtype: str, key: str, local_date: str, body: dict, ihash: str, cutoff: str | None) -> dict:
    prev = conn.execute("SELECT id, revision, input_hash, body_json FROM report WHERE type=? AND subject_key=? ORDER BY revision DESC LIMIT 1",
                        (rtype, key)).fetchone()
    if prev and prev["input_hash"] == ihash:
        return json.loads(prev["body_json"])
    rev = (prev["revision"] + 1) if prev else 1
    body.update(revision=rev, input_hash=ihash, generated_at=utc_now(), data_cutoff=cutoff, algorithm_version=ALGORITHMS)
    with conn:
        cur = conn.execute(
            "INSERT INTO report (type, subject_key, local_date, revision, generated_at, data_cutoff, input_hash, algorithm_version, body_json)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (rtype, key, local_date, rev, body["generated_at"], cutoff or "", ihash, json.dumps(ALGORITHMS), "{}"))
        body["id"] = cur.lastrowid
        conn.execute("UPDATE report SET body_json=? WHERE id=?", (json.dumps(body), cur.lastrowid))
    return body


# ---------------------------------------------------------------- morning report

def metric_finding(conn, source: str, metric: str, d: date, obs_row) -> dict | None:
    ds = d.isoformat()
    fid = f"m:{ds}:{metric}"
    if obs_row is None or obs_row["state"] != "measured":
        return {"id": fid, "category": CATEGORY[metric], "metric": metric, "title": METRIC_TITLES[metric], "status": "missing",
                "statement": f"No {METRIC_TITLES[metric].lower()} recorded for {ds}" + (" (not yet synced)." if obs_row is None else "."),
                "observed": None, "comparison": None, "delta": None, "priority": 9,
                "evidence": {"record_ids": [], "date_range": [ds, ds]}, "sample_size": 0, "coverage": None,
                "limitations": ["Missing data is shown as missing, never as zero."], "interpretation": None,
                "algorithm_version": bl.BASELINE_VERSION, "derived": False}
    value, method = obs_row["value"], obs_row["method"]
    # HRV comparability: only compare measurements of the same method
    s = series(conn, source, metric, ds, method if metric == "hrv_overnight_avg" else None)
    era = device_era_start(conn, source, d)
    b = bl.compute_baseline(s, d, era_start=era)
    window_days = bl.WINDOW_DAYS
    base = {
        "id": fid, "category": CATEGORY[metric], "metric": metric, "title": METRIC_TITLES[metric],
        "observed": {"value": value, "unit": obs_row["unit"], "date": ds, "method": method, "label": obs_row["label"]},
        "evidence": {"record_ids": [obs_row["source_record_id"] or f"{source}:{ds}:{metric}"] + [f"{source}:{x}:{metric}" for x in b.dates],
                     "date_range": [b.window_start, ds]},
        "sample_size": b.n, "coverage": {"valid_days": b.n, "window_days": window_days},
        "algorithm_version": bl.BASELINE_VERSION, "derived": True,
        "limitations": [], "interpretation": None,
    }
    if metric == "hrv_overnight_avg":
        base["limitations"].append("Compared only with overnight HRV of the same measurement type.")
    if era is not None and era > d - timedelta(days=window_days):
        base["limitations"].append(f"Your watch changed around {era.isoformat()}; earlier days aren't compared, "
                                   "because different devices measure differently.")
        base["device_era_start"] = era.isoformat()
    # Raw 14-day trend (descriptive), shown even while the personal range is still being learned
    base["sparkline"] = [{"date": k, "value": s[k]} for k in sorted(s)
                         if k >= (d - timedelta(days=13)).isoformat() and (era is None or k >= era.isoformat())]
    if not b.sufficient:
        base.update(status="learning", priority=8, comparison=None, delta=None,
                    statement=f"{METRIC_TITLES[metric]} {fmt_value(metric, value)}. Still learning your usual range ({b.n} of {bl.MIN_VALID} days needed).")
        base["limitations"].append(f"Personal range needs at least {bl.MIN_VALID} valid days in the previous {window_days}.")
        return base
    dev = bl.deviation(metric, value, b)
    sus = dev.beyond_threshold and bl.sustained(metric, s, d, era_start=era)
    th = bl.THRESHOLDS[metric]
    base["comparison"] = {"kind": "personal_reference_range", "median": b.median, "q1": b.q1, "q3": b.q3, "n": b.n,
                          "window": [b.window_start, b.window_end],
                          "threshold": {k: th[k] for k in ("abs", "pct") if k in th}, "concern_direction": th["concern"]}
    base["delta"] = {"abs": round(dev.delta_abs, 2), "pct": round(dev.delta_pct, 1) if dev.delta_pct is not None else None}
    rel = "above" if dev.direction == "up" else "below" if dev.direction == "down" else "at"
    if dev.beyond_threshold:
        base.update(status="sustained" if sus else "outside", priority=1 if sus else 2)
        base["statement"] = (f"{METRIC_TITLES[metric]} {fmt_value(metric, value)}, {fmt_delta(metric, dev.delta_abs)} vs your usual "
                             f"{fmt_value(metric, b.median)}" + (f" — {bl.SUSTAINED_DAYS} days in a row." if sus else "."))
        base["interpretation"] = "Outside your personal range in the direction that may deserve attention. One reading alone is often noise."
    else:
        base.update(status="within", priority=5)
        base["statement"] = f"{METRIC_TITLES[metric]} {fmt_value(metric, value)}, {rel} your usual {fmt_value(metric, b.median)}." if rel != "at" else \
            f"{METRIC_TITLES[metric]} {fmt_value(metric, value)}, right at your usual level."
        base["interpretation"] = "Within your usual variation."
    base["limitations"].append("Personal reference range (28-day median and interquartile range), not a clinical norm.")
    return base


def load_finding(conn, source: str, d: date) -> dict | None:
    end = d - timedelta(days=1)  # completed days only
    acts = activities(conn, source, (d - timedelta(days=35)).isoformat(), end.isoformat())
    last7 = rn.workload(acts, (end - timedelta(days=6)).isoformat(), end.isoformat())
    prior = rn.workload(acts, (end - timedelta(days=34)).isoformat(), (end - timedelta(days=7)).isoformat())
    if prior["runs"] < 4:
        return None
    weekly_mean = prior["moving_s"] / 4.0
    ratio = last7["moving_s"] / weekly_mean if weekly_mean else None
    fid = f"m:{d.isoformat()}:load7"
    high = ratio is not None and ratio > 1.5
    return {
        "id": fid, "category": "training_load", "metric": "running_moving_time_7d", "title": "Running time, last 7 days",
        "observed": {"value": last7["moving_s"], "unit": "s", "runs": last7["runs"], "distance_m": last7["distance_m"]},
        "comparison": {"kind": "prior_4_week_weekly_mean", "value": round(weekly_mean), "window": [prior["start"], prior["end"]], "n": prior["runs"]},
        "delta": {"abs": round(last7["moving_s"] - weekly_mean), "pct": round(100 * (ratio - 1), 1) if ratio else None},
        "status": "outside" if high else "within", "priority": 3 if high else 6,
        "statement": (f"{fmt_duration(last7['moving_s'])} of running in the last 7 days ({last7['runs']} runs), "
                      f"vs a weekly average of {fmt_duration(weekly_mean)} over the previous 4 weeks."),
        "interpretation": "Noticeably more than your recent weekly average." if high else "Similar to your recent weeks.",
        "evidence": {"record_ids": last7["activity_ids"] + prior["activity_ids"], "date_range": [prior["start"], last7["end"]]},
        "sample_size": last7["runs"] + prior["runs"], "coverage": None,
        "limitations": ["Trailing 7 completed days, not the calendar week.", "Describes volume only; not an injury-risk estimate."],
        "algorithm_version": rn.RUNNING_VERSION, "derived": True,
    }


def build_morning(conn, source: str, d: date, synthetic: bool) -> dict:
    ds = d.isoformat()
    obs = day_obs(conn, source, ds)
    checkin = checkin_for(conn, ds)
    findings = [metric_finding(conn, source, m, d, obs.get(m)) for m in CORE_METRICS]
    lf = load_finding(conn, source, d)
    if lf:
        findings.append(lf)
    signals: dict[str, list[str]] = {}
    for f in findings:
        if f["status"] in ("outside", "sustained"):
            group = {"sleep_duration": "sleep", "running_moving_time_7d": "load"}.get(f["metric"], "overnight_autonomic")
            signals.setdefault(group, []).append(f["id"])
            if f["status"] == "sustained":
                signals.setdefault("sustained", []).append(f["id"])
    if checkin and ((checkin.get("energy") or 5) <= 2 or (checkin.get("recovery") or 5) <= 2 or (checkin.get("soreness") or 1) >= 4):
        signals["subjective"] = ["checkin"]
    has_overnight = any(f["metric"] in CORE_METRICS and f["status"] != "missing" for f in findings)
    any_baseline = any(f.get("comparison") and f["metric"] in CORE_METRICS for f in findings)
    rec = recommend(signals, checkin, has_overnight, any_baseline)
    running_days = get_setting(conn, "running_days", [0, 2, 4, 5])
    rec["planned_run_day"] = d.weekday() in running_days
    plan_row = conn.execute("SELECT * FROM day_plan WHERE local_date=?", (ds,)).fetchone()
    plan = {"kind": plan_row["kind"], "minutes": plan_row["minutes"]} if plan_row else None
    zones = get_setting(conn, "source_hr_zones", None)
    rec["plan"] = plan
    rec["suggestion"] = suggestion_text(rec, plan, zones["floors"][2] if zones else None, get_setting(conn, "available_minutes", None))
    findings.sort(key=lambda f: f["priority"])
    top = [f for f in findings if f["status"] not in ("missing",)][:3]
    garmin_ctx = []
    for m in sorted(GARMIN_PROPRIETARY):
        r = obs.get(m)
        if r is not None and r["state"] == "measured":
            garmin_ctx.append({"metric": m, "value": r["value"], "unit": r["unit"], "label": r["label"], "origin": "Garmin"})
    completeness = {m: (obs[m]["state"] if m in obs else "not_synced") for m in CORE_METRICS}
    completeness["checkin"] = checkin is not None
    recent = activities(conn, source, (d - timedelta(days=7)).isoformat(), ds)
    recent_run = None
    if recent:
        a = recent[-1]
        recent_run = {k: a[k] for k in ("source_id", "local_date", "name", "distance_m", "moving_s", "avg_hr", "start_utc")}
    body = {
        "type": "morning", "local_date": ds, "synthetic": synthetic,
        "provisional": completeness["sleep_duration"] != "measured",
        "headline": headline(rec, findings, checkin), "recommendation": rec,
        "top_finding_ids": [f["id"] for f in top], "findings": findings, "garmin_context": garmin_ctx,
        "completeness": completeness, "checkin": checkin, "recent_run": recent_run, "narrative": None,
    }
    inputs = {"findings": [{k: f.get(k) for k in ("id", "observed", "comparison", "status")} for f in findings],
              "checkin": checkin, "running_days": running_days, "garmin": garmin_ctx, "recent": recent_run, "v": ALGORITHMS,
              "plan": plan, "available": get_setting(conn, "available_minutes", None)}
    return save_report(conn, "morning", ds, ds, body, input_hash(inputs), data_cutoff(conn, source))


def headline(rec: dict, findings: list[dict], checkin: dict | None) -> str:
    st, rule = rec["state"], rec["rule_id"]
    if rule == "R0":
        return "You reported feeling unwell or in pain."
    if st == "insufficient_data":
        return {"R1b": "Still learning your usual ranges.", "R1d": "Still learning your usual ranges, and you feel fine.",
                "R1c": "No overnight data yet, but you feel fine."}.get(rule, "Waiting for today's data.")
    if rule == "R4s":
        return "Readings look typical, but you feel less recovered."
    if rule == "R1e":
        return "Recent running is well above your usual." if "load" in rec.get("reason", "") or "running" in rec.get("reason", "") \
            else "One reading stands out; ranges still being learned."
    off = [f for f in findings if f["status"] in ("outside", "sustained")]
    within = [f for f in findings if f["status"] == "within"]
    if st == "consider_easier":
        return "Mixed recovery signals today." if within else "Several recovery signals are off today."
    if st == "check_in_needed":
        return f"{off[0]['title']} is outside your usual range." if off else "One reading is outside your usual range."
    if rule == "R4":
        return "Mostly typical, with one reading to watch."
    return "Recovery signals look typical today."


HARD_KINDS = {"tempo", "intervals", "race"}
PLAN_NAMES = {"easy": "easy run", "long": "long run", "tempo": "tempo run", "intervals": "interval session", "race": "race",
              "other": "planned session"}


def suggestion_text(rec: dict, plan: dict | None = None, easy_ceiling: float | None = None, available_min: int | None = None) -> str:
    """What to do today. With a plan, the advice speaks to that session; numbers come only from the runner's own
    settings (planned minutes, usual time) and Garmin zones."""
    st, suppress = rec["state"], rec["suppress_intensity"]
    if plan:
        kind = plan["kind"]
        name = PLAN_NAMES.get(kind, "planned session")
        mins = f" of about {plan['minutes']} min" if plan.get("minutes") else ""
        easy_hint = f" Keep it below {round(easy_ceiling)} bpm to stay easy." if easy_ceiling else ""
        if kind == "rest":
            return "Rest day planned. That fits." if st != "usual_plan" or suppress else "Rest day planned. Enjoy it."
        if st == "consider_easier":
            return (f"Consider swapping the {name} for an easy run or rest." if kind in HARD_KINDS else
                    f"Consider keeping the {name} short and easy, or resting.") + (easy_hint if kind != "race" else "")
        if st == "check_in_needed":
            return f"Do a quick check-in first, then decide on the {name}."
        if st == "insufficient_data" or suppress:
            return (f"Keep the {name} conditional on how you feel; make the hard parts optional." if kind in HARD_KINDS else
                    f"An {name}{mins} by feel fits." if kind == "easy" else f"Your {name}{mins} is fine; keep the effort comfortable.")
        return f"Go ahead with your {name}{mins}." + (easy_hint if kind == "easy" else "")
    if not rec["planned_run_day"] and st != "consider_easier":
        return "Not a planned running day. Rest or easy movement fits."
    if st == "usual_plan" and rec["suppress_intensity"]:
        return "Your usual plan is fine, but keep the effort easy or moderate today."
    if st == "usual_plan" and available_min:
        return f"Go ahead with your planned session (your usual is about {available_min} min)."
    return {
        "usual_plan": "Go ahead with your planned session.",
        "consider_easier": "Consider an easier or shorter session, or a rest day.",
        "check_in_needed": "Take a 10-second check-in to tailor today's suggestion. Until then, keep any hard session optional.",
        "insufficient_data": "Train by feel. Keep any hard session conditional on how you feel.",
    }[st]


# ---------------------------------------------------------------- post-run report

_class_cache: dict[tuple[int, str], dict] = {}


def run_analysis(conn, a: dict) -> dict:
    key = (a["id"], a["content_hash"])
    if key not in _class_cache:
        laps = laps_for(conn, a["id"])
        s = samples_for(conn, a["id"])
        dc = rn.decoupling(s, laps, a["distance_m"], a["elevation_gain_m"])
        # One classification for the whole report: the grade-adjusted one the drift analysis used
        _class_cache[key] = {"classification": dc["classification"], "decoupling": dc}
    return _class_cache[key]


_effort_cache: dict[tuple[int, str], dict] = {}

EFFORT_LABELS = {"1k": "1 km", "5k": "5 km", "10k": "10 km", "half": "half marathon"}


def efforts_for(conn, a: dict) -> dict:
    key = (a["id"], a["content_hash"])
    if key not in _effort_cache:
        _effort_cache[key] = rn.best_efforts(samples_for(conn, a["id"]))
    return _effort_cache[key]


def records(conn, source: str) -> dict:
    """Best effort per distance across synced history, with the progression of bests over time."""
    out: dict[str, dict] = {}
    for a in activities(conn, source, "0000-01-01", "9999-12-31"):
        for k, e in efforts_for(conn, a).items():
            r = out.setdefault(k, {"label": EFFORT_LABELS[k], "best": None, "progression": []})
            if r["best"] is None or e["elapsed_s"] < r["best"]["elapsed_s"]:
                r["best"] = {**e, "date": a["local_date"], "source_id": a["source_id"]}
                r["progression"].append({"date": a["local_date"], "elapsed_s": e["elapsed_s"], "source_id": a["source_id"]})
    return out


def build_post_run(conn, source: str, sid: str, synthetic: bool) -> dict | None:
    a = activity_by_source_id(conn, source, sid)
    if a is None or a["sport"] == "other":
        return None
    d = date.fromisoformat(a["local_date"])
    laps = laps_for(conn, a["id"])
    an = run_analysis(conn, a)
    splits = rn.splits_from_laps(laps)
    findings = []
    pace = rn.moving_pace(a["distance_m"], a["moving_s"])
    complete = [s for s in splits if s.complete and s.pace_s_per_km]
    if len(complete) >= 4 and an["classification"]["kind"] == "steady":
        paces = [s.pace_s_per_km for s in complete]
        half = len(paces) // 2
        first, second = sum(paces[:half]) / half, sum(paces[half:]) / (len(paces) - half)
        cv = pstdev(paces) / (sum(paces) / len(paces))
        findings.append({
            "id": f"r:{sid}:pacing", "category": "running", "metric": "split_consistency", "title": "Pacing",
            "observed": {"value": round(100 * cv, 1), "unit": "%", "first_half_pace_s_per_km": round(first, 1),
                         "second_half_pace_s_per_km": round(second, 1)},
            "comparison": None, "delta": {"abs": round(second - first, 1), "pct": None},
            "status": "info", "priority": 3,
            "statement": (f"Splits varied by {100 * cv:.1f}% (moving pace). "
                          + (f"Second half was {abs(second - first):.0f} s/km faster than the first." if second < first - 1 else
                             f"Second half was {abs(second - first):.0f} s/km slower than the first." if second > first + 1 else
                             "Both halves were about even.")),
            "interpretation": "Describes pacing only; terrain and stops are not adjusted for.",
            "evidence": {"record_ids": [f"{source}:{sid}:lap{s.idx}" for s in complete], "date_range": [a["local_date"]] * 2},
            "sample_size": len(complete), "coverage": {"complete_splits": len(complete), "total_splits": len(splits)},
            "limitations": ["Incomplete final split excluded."] if len(complete) < len(splits) else [],
            "algorithm_version": rn.RUNNING_VERSION, "derived": True,
        })
    dc = an["decoupling"]
    if dc["eligible"]:
        v = dc["decoupling_pct"]
        findings.append({
            "id": f"r:{sid}:decoupling", "category": "running", "metric": "pace_hr_decoupling", "title": "Heart-rate drift",
            "observed": {"value": v, "unit": "%"}, "comparison": {"kind": "heuristic", "value": 5.0},
            "delta": None, "status": "outside" if v > 5 else "within", "priority": 2,
            "statement": (f"Efficiency (speed per heartbeat) was {abs(v):.1f}% "
                          + ("lower" if v > 0 else "higher") + " in the second half of the steady segment."),
            "interpretation": ("Heart rate rose relative to pace. One run is not a trend." if v > 5 else
                               "Heart rate stayed stable relative to pace."),
            "evidence": {"record_ids": [f"{source}:{sid}:samples"], "date_range": [a["local_date"]] * 2},
            "sample_size": None, "coverage": {"hr_coverage": dc["hr_coverage"], "segment_moving_s": dc["segment_moving_s"]},
            "limitations": ["5% is a common coaching heuristic, not a validated threshold.", dc["method"]],
            "algorithm_version": rn.RUNNING_VERSION, "derived": True,
        })
    prior = activities(conn, source, (d - timedelta(days=120)).isoformat(), a["local_date"])
    cands = []
    for c in prior:
        if c["start_utc"] >= a["start_utc"]:
            continue
        cands.append({**c, "classification": run_analysis(conn, c)["classification"]["kind"]})
    comp = rn.similar_runs({**a, "classification": an["classification"]["kind"]}, cands) \
        if an["classification"]["kind"] == "steady" and a["distance_m"] else {"n": 0, "runs": [], "summary": None, "criteria": None}
    if comp["summary"]:
        sm = comp["summary"]
        hd = sm.get("avg_hr_delta")
        hr_part = "" if hd is None else " at a similar average HR" if abs(hd) < 1 else \
            f" at {abs(hd):.0f} bpm {'higher' if hd > 0 else 'lower'} average HR"
        findings.append({
            "id": f"r:{sid}:comparable", "category": "running", "metric": "comparable_runs", "title": "Compared with similar runs",
            "observed": {"value": pace, "unit": "s/km"}, "comparison": {"kind": "median_of_similar", "value": sm["median_pace_s_per_km"], "n": comp["n"]},
            "delta": {"abs": sm["pace_delta_s_per_km"], "pct": None}, "status": "info", "priority": 1,
            "statement": ((f"{abs(sm['pace_delta_s_per_km']):.0f} s/km {'faster' if sm['pace_delta_s_per_km'] < 0 else 'slower'} than"
                           if abs(sm["pace_delta_s_per_km"]) >= 1 else "About the same pace as")
                          + f" the median of {comp['n']} similar steady runs{hr_part}."),
            "interpretation": "Descriptive comparison; a few runs do not establish a fitness change.",
            "evidence": {"record_ids": [r["source_id"] for r in comp["runs"]],
                         "date_range": [comp["runs"][-1]["local_date"], a["local_date"]]},
            "sample_size": comp["n"], "coverage": None,
            "limitations": ["Matched on distance (±20%), elevation gain per km (±8 m) and steady effort. Weather is not considered."],
            "algorithm_version": rn.RUNNING_VERSION, "derived": True,
        })
    # Best efforts in this run, compared with every earlier run in synced history
    mine = efforts_for(conn, a)
    earlier = [x for x in activities(conn, source, "0000-01-01", a["local_date"]) if x["start_utc"] < a["start_utc"]]
    best_efforts = {}
    for k, e in mine.items():
        prev = [efforts_for(conn, x)[k]["elapsed_s"] for x in earlier if k in efforts_for(conn, x)]
        best_efforts[k] = {**e, "label": EFFORT_LABELS[k], "previous_best_s": min(prev) if prev else None,
                           "is_best": bool(prev) and e["elapsed_s"] < min(prev), "compared_runs": len(prev)}
    new_bests = [k for k, e in best_efforts.items() if e["is_best"]]
    if new_bests:
        k = max(new_bests, key=lambda x: rn.BEST_EFFORT_DISTANCES[x])
        e = best_efforts[k]
        findings.append({
            "id": f"r:{sid}:best_{k}", "category": "running", "metric": "best_effort", "title": f"New best {e['label']}",
            "observed": {"value": e["elapsed_s"], "unit": "s"}, "comparison": {"kind": "previous_best", "value": e["previous_best_s"], "n": e["compared_runs"]},
            "delta": {"abs": round(e["elapsed_s"] - e["previous_best_s"], 1), "pct": None}, "status": "info", "priority": 0,
            "statement": (f"Your fastest {e['label']} in synced history: {fmt_duration_s(e['elapsed_s'])}, "
                          f"{abs(e['elapsed_s'] - e['previous_best_s']):.0f} s faster than your previous best."),
            "interpretation": "Fastest continuous segment of this distance inside a run, by elapsed time.",
            "evidence": {"record_ids": [sid], "date_range": [a["local_date"]] * 2}, "sample_size": e["compared_runs"] + 1, "coverage": None,
            "limitations": ["Only runs synced to Runner Sidekick count; GPS distance has some error."],
            "algorithm_version": rn.RUNNING_VERSION, "derived": True,
        })
    zones = get_setting(conn, "source_hr_zones", None)
    details = rn.split_details(samples_for(conn, a["id"]), laps, zones["floors"] if zones else None)
    story = rn.run_story(splits, details, fmt_pace)
    intent = run_intent(conn, a)
    if intent and intent["kind"] in ("easy", "recovery") and zones:
        from .focus import easy_share
        es = easy_share(conn, a, zones["floors"])
        if es is not None and es < 0.5:
            findings.append({
                "id": f"r:{sid}:intent", "category": "running", "metric": "intent_vs_actual", "title": "Meant to be easy",
                "observed": {"value": round(100 * (1 - es)), "unit": "%"}, "comparison": {"kind": "intent", "value": None},
                "delta": None, "status": "outside", "priority": 0,
                "statement": (f"You planned this as {'an easy' if intent['kind'] == 'easy' else 'a recovery'} run, but "
                              f"{round(100 * (1 - es))}% of it was at or above {zones['floors'][2]} bpm (zone 3+)."),
                "interpretation": "Easy running only does its job when it's actually easy.",
                "evidence": {"record_ids": [sid], "date_range": [a["local_date"]] * 2}, "sample_size": 1, "coverage": None,
                "limitations": ["Garmin zones; wrist heart rate can read high early in a run."],
                "algorithm_version": rn.RUNNING_VERSION, "derived": True,
            })
    week_start = d - timedelta(days=d.weekday())
    week_acts = activities(conn, source, week_start.isoformat(), a["local_date"])
    rpe = conn.execute("SELECT rpe FROM activity_effort WHERE activity_source_id=?", (sid,)).fetchone()
    effort = None
    if rpe and a["moving_s"]:
        effort = {"rpe": rpe["rpe"], "session_rpe_load": round(rpe["rpe"] * a["moving_s"] / 60.0),
                  "note": "Session-RPE load = RPE × moving minutes. A separate measure; not combined with Garmin load."}
    body = {
        "type": "post_run", "local_date": a["local_date"], "synthetic": synthetic,
        "activity": {k: a[k] for k in ("source_id", "name", "sport", "start_utc", "utc_offset_s", "local_date", "distance_m",
                                        "elapsed_s", "moving_s", "timer_s", "avg_hr", "max_hr", "elevation_gain_m",
                                        "elevation_loss_m", "avg_cadence_spm")},
        "pace_moving_s_per_km": pace, "pace_basis": "moving",
        "garmin_metrics": json.loads(a["garmin_metrics_json"]),
        "splits": [{**rn.as_dict(s), **{k: v for k, v in dt.items() if k != "idx"}}
                   for s, dt in zip(splits, details or [{}] * len(splits))],
        "story": story, "best_efforts": best_efforts,
        "classification": an["classification"], "decoupling": dc,
        "comparable": comp, "calendar_week": rn.workload(week_acts, week_start.isoformat(), a["local_date"]),
        "findings": sorted(findings, key=lambda f: f["priority"]), "effort": effort,
        "next_focus": next_focus(an, dc, comp, splits, details, intent, zones["floors"][2] if zones else None),
        "intent": intent, "narrative": None,
    }
    inputs = {"a": a["content_hash"], "comp": [r["source_id"] for r in comp["runs"]], "rpe": rpe["rpe"] if rpe else None, "v": ALGORITHMS,
              "prev_bests": {k: e["previous_best_s"] for k, e in best_efforts.items()}, "zones": zones, "intent": intent}
    return save_report(conn, "post_run", sid, a["local_date"], body, input_hash(inputs), data_cutoff(conn, source))


def run_intent(conn, a: dict) -> dict | None:
    """User-stated intent, else pre-filled from the day's plan (marked as such)."""
    r = conn.execute("SELECT * FROM run_intent WHERE activity_source_id=?", (a["source_id"],)).fetchone()
    if r:
        return {"kind": r["kind"], "note": r["note"], "source": r["source"]}
    p = conn.execute("SELECT * FROM day_plan WHERE local_date=?", (a["local_date"],)).fetchone()
    if p and p["kind"] != "rest":
        return {"kind": "easy" if p["kind"] == "easy" else p["kind"], "note": None, "source": "plan"}
    return None


def next_focus(an: dict, dc: dict, comp: dict, splits=None, details=None, intent: dict | None = None,
               easy_ceiling: float | None = None) -> str:
    """One practical focus from this run, most specific first. No pace or HR prescriptions beyond the run's own numbers."""
    full = [s for s in (splits or []) if s.complete and s.pace_s_per_km]
    zones = [d.get("zone") for d in (details or []) if d.get("zone") is not None]
    hard_share = (sum(1 for z in zones if z >= 4) / len(zones)) if zones else 0
    if intent and intent["kind"] in ("easy", "recovery") and hard_share >= 0.5 and easy_ceiling:
        return f"This was meant to be easy. Next time, keep heart rate below {round(easy_ceiling)} bpm, even if that means a slower pace."
    if intent and intent["kind"] == "intervals":
        return "Interval session: compare the repeated efforts with each other rather than with steady runs."
    cls = an["classification"]
    structured = "rest/recovery" in cls.get("reason", "") or (cls.get("speed_cv") or 0) > 0.15 or bool(intent and intent["kind"] == "intervals")
    if cls["kind"] == "variable" and structured:
        return "Interval-style session: drift analysis doesn't apply. Compare the repeated efforts with each other instead."
    if dc.get("eligible") and dc["decoupling_pct"] > 5:
        return "See whether heart-rate drift repeats on your next comparable steady run before reading much into it."
    if len(full) >= 4:
        h = len(full) // 2
        first = sum(s.pace_s_per_km for s in full[:h]) / h
        fade = sum(s.pace_s_per_km for s in full[h:]) / (len(full) - h) - first
        if fade > 8:
            return (f"You faded by about {fade:.0f} s/km. Next time, try starting about 10 s/km slower than {fmt_pace(first)} "
                    "and see if the second half holds.")
    if zones and sum(1 for z in zones if z >= 4) >= 0.8 * len(zones):
        return "Almost the whole run was in zone 4 or higher. If it was meant to be easy, it wasn't; if it was a hard run, that fits."
    if cls["kind"] == "variable":
        return "Pace was uneven enough that drift and similar-run comparisons were skipped. A steadier effort makes them possible."
    if comp.get("n", 0) < 3:
        return "A few more similar runs will make comparisons meaningful."
    return "Nothing stands out. Keep building consistent, comparable runs."


# ---------------------------------------------------------------- insights

def build_insights(conn, source: str, today: date, synthetic: bool) -> dict:
    from datetime import datetime as _dt
    from .analytics import insights as ins

    acts = activities(conn, source, (today - timedelta(days=120)).isoformat(), today.isoformat())
    runs, drifts = [], []
    for a in acts:
        an = run_analysis(conn, a)
        local = _dt.fromisoformat(a["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=a["utc_offset_s"] or 0)
        runs.append(ins.RunData(a["source_id"], a["local_date"], local.replace(tzinfo=None), a.get("device_id"), a["distance_m"],
                                a["moving_s"], json.loads(a["garmin_metrics_json"]).get("activityTrainingLoad"),
                                samples_for(conn, a["id"]), rn.splits_from_laps(laps_for(conn, a["id"])), an["classification"]["kind"]))
        if an["decoupling"]["eligible"]:
            drifts.append((a["local_date"], a["source_id"], an["decoupling"]["decoupling_pct"]))
    since = (today - timedelta(days=120)).isoformat()
    obs: dict[str, dict[str, float]] = {}
    for r in conn.execute("SELECT local_date, metric, value FROM daily_observation WHERE source=? AND state='measured' AND local_date>=?",
                          (source, since)):
        obs.setdefault(r["metric"], {})[r["local_date"]] = r["value"]
    bedtimes = {}
    for r in conn.execute("SELECT wake_date, start_utc, utc_offset_s FROM sleep_session WHERE source=? AND is_nap=0 AND wake_date>=?", (source, since)):
        st = _dt.fromisoformat(r["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=r["utc_offset_s"] or 0)
        bedtimes[r["wake_date"]] = st.hour + st.minute / 60 + (24 if st.hour < 12 else 0)
    zones = get_setting(conn, "source_hr_zones", None)
    items = ins.compute_all(runs, obs, bedtimes, zones, drifts, today)
    # Confidence: a pattern is "consistent" only if an insights report from >= 14 days earlier reached the same verdict.
    prev = conn.execute("SELECT body_json FROM report WHERE type='insights' AND local_date<=? ORDER BY local_date DESC, revision DESC LIMIT 1",
                        ((today - timedelta(days=14)).isoformat(),)).fetchone()
    prev_v = {i["id"]: i["verdict"] for i in json.loads(prev["body_json"])["insights"]} if prev else {}
    for i in items:
        i["confidence"] = None if i["verdict"] == "not_enough_data" else ("consistent" if prev_v.get(i["id"]) == i["verdict"] else "emerging")
    # Novelty vs the most recent earlier snapshot, and the runner's own dismissals / "working on it"
    last = conn.execute("SELECT body_json FROM report WHERE type='insights' AND local_date<? ORDER BY local_date DESC, revision DESC LIMIT 1",
                        (today.isoformat(),)).fetchone()
    last_i = {i["id"]: i for i in json.loads(last["body_json"])["insights"]} if last else {}
    states = {r["insight_id"]: dict(r) for r in conn.execute("SELECT * FROM insight_state")}
    for i in items:
        p = last_i.get(i["id"])
        i["novelty"] = ("new" if p is None or (p["verdict"] != "pattern" and i["verdict"] == "pattern") else
                        "changed" if p["verdict"] != i["verdict"] or p["headline"] != i["headline"] else "continuing")
        st = states.get(i["id"])
        # A dismissal lapses when the verdict changes, so a new development is never hidden
        i["user_state"] = st["state"] if st and st["verdict_at_dismissal"] == i["verdict"] else None
    body = {"type": "insights", "local_date": today.isoformat(), "synthetic": synthetic, "insights": items, "narrative": None,
            "window": [since, today.isoformat()]}
    inputs = {"items": [{k: i.get(k) for k in ("id", "verdict", "effect", "sample_size", "confidence", "novelty", "user_state")} for i in items], "v": ALGORITHMS,
              "iv": ins.INSIGHTS_VERSION}
    return save_report(conn, "insights", today.isoformat(), today.isoformat(), body, input_hash(inputs), data_cutoff(conn, source))


def regenerate(conn, source: str, synthetic: bool, changed_dates: set[str], changed_activities: list[str], today: date,
               morning_lookback_days: int = 7) -> None:
    """Regenerate reports affected by new/changed inputs. Morning reports older than the lookback stay as they were,
    except on first generation (backfill), so the journal reflects what was known at the time."""
    existing = {r["subject_key"] for r in conn.execute("SELECT DISTINCT subject_key FROM report WHERE type='morning'")}
    dates = set(changed_dates) | {today.isoformat()}
    # A changed day also changes the baseline of the following days within the lookback
    for ds in sorted(dates):
        dd = date.fromisoformat(ds)
        if dd > today:
            continue
        recent = (today - dd).days <= morning_lookback_days
        if recent or ds not in existing:
            build_morning(conn, source, dd, synthetic)
    for i in range(morning_lookback_days + 1):
        dd = today - timedelta(days=i)
        if dd.isoformat() in existing or dd.isoformat() in dates:
            build_morning(conn, source, dd, synthetic)
    for sid in changed_activities:
        build_post_run(conn, source, sid, synthetic)
    if changed_dates or changed_activities or not conn.execute("SELECT 1 FROM report WHERE type='insights' AND subject_key=?",
                                                               (today.isoformat(),)).fetchone():
        build_insights(conn, source, today, synthetic)
    from .weekly import regenerate_weeklies
    regenerate_weeklies(conn, source, today, synthetic)

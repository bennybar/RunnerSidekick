"""Deterministic report generation. Every finding carries its evidence; reports are revisioned by input hash.

A report is regenerated only when its inputs hash differently. Old revisions are kept, so the
journal shows what was known at the time rather than re-deriving the past with current baselines.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from statistics import median, pstdev

from pymongo.errors import DuplicateKeyError

from .analytics import baseline as bl
from .analytics import running as rn
from .analytics.recommend import RULES_VERSION, recommend
from .connectors.base import GARMIN_PROPRIETARY, Samples
from .db import first_weekday, get_setting, many, next_id, one, plain, utc_now
from .db import week_start

REPORT_VERSION = "report-2.5"  # 2.5: "Aerobic decoupling" wording; 2.4: Garmin readiness on the run's day; 2.3: athlete context, intent-aware next focus, data classification; 2.0: plans, run intent, insight novelty/state; 2.1: R1e  # 1.1: boolean check-in flags, wording; 1.2: subjective-only rule R4s; 1.3: wording; 1.4: device eras ; 1.5: sparkline while learning; 1.6: best efforts, run story, GAP splits
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
    q = {"source": source, "metric": metric, "state": "measured", "local_date": {"$lte": until}}
    if method:
        q["method"] = method
    return {r["local_date"]: r["value"] for r in conn.daily_observation.find(q, {"_id": 0, "local_date": 1, "value": 1})}


def day_obs(conn, source: str, d: str) -> dict[str, dict]:
    return {r["metric"]: r for r in many(conn.daily_observation, {"source": source, "local_date": d})}


def checkin_for(conn, d: str) -> dict | None:
    return one(conn.checkin, {"local_date": d, "deleted": False}, sort=[("client_updated_at", -1)])


def activities(conn, source: str, start: str, end: str) -> list[dict]:
    return many(conn.activity, {"source": source, "local_date": {"$gte": start, "$lte": end}, "sport": {"$ne": "other"}},
                sort=[("start_utc", 1)])


def activity_by_source_id(conn, source: str, sid: str) -> dict | None:
    return one(conn.activity, {"source": source, "source_id": sid})


def laps_for(conn, aid: int) -> list[dict]:
    return many(conn.activity_lap, {"activity_id": aid}, sort=[("idx", 1)])


def samples_for(conn, aid: int) -> Samples | None:
    r = one(conn.activity_samples, {"activity_id": aid})
    return Samples.from_json(r["samples"]) if r else None


def device_era_start(conn, source: str, d: date) -> date | None:
    """First day of the device era containing d, inferred from activity device IDs (daily payloads carry none).
    The era starts the day after the last run recorded by a different device. Precision is limited to the days
    between runs."""
    rows = list(conn.activity.find({"source": source, "device_id": {"$ne": None}}, {"_id": 0, "local_date": 1, "device_id": 1},
                                   sort=[("start_utc", 1)]))
    if not rows:
        return None
    ds = d.isoformat()
    before = [r for r in rows if r["local_date"] <= ds]
    current = before[-1]["device_id"] if before else rows[0]["device_id"]
    others = [r["local_date"] for r in before if r["device_id"] != current]
    return date.fromisoformat(max(others)) + timedelta(days=1) if others else None


def hr_zones(conn) -> dict | None:
    """The heart-rate zones analysis should use: Garmin's, unless the runner chose not to use zones."""
    if get_setting(conn, "hr_zone_source", "garmin") == "none":
        return None
    return get_setting(conn, "source_hr_zones", None)


def data_cutoff(conn, source: str) -> str | None:
    r = one(conn.source_connection, {"source": source})
    return r["last_success_at"] if r else None


# ---------------------------------------------------------------- revisioned storage

def input_hash(inputs: object) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:20]


def save_report(conn, rtype: str, key: str, local_date: str, body: dict, ihash: str, cutoff: str | None) -> dict:
    prev = one(conn.report, {"type": rtype, "subject_key": key}, sort=[("revision", -1)])
    if prev and prev["input_hash"] == ihash:
        return prev["body"]
    rev = (prev["revision"] + 1) if prev else 1
    body.update(revision=rev, input_hash=ihash, generated_at=utc_now(), data_cutoff=cutoff, algorithm_version=ALGORITHMS)
    body["id"] = next_id(conn, "report")
    body = plain(body)
    try:
        conn.report.insert_one({"id": body["id"], "type": rtype, "subject_key": key, "local_date": local_date, "revision": rev,
                                "generated_at": body["generated_at"], "data_cutoff": cutoff or "", "input_hash": ihash,
                                "algorithm_version": ALGORITHMS, "body": body})
    except DuplicateKeyError:
        # Another process (the hourly sync, or a second request) wrote this revision a moment ago: use the newest one
        latest = one(conn.report, {"type": rtype, "subject_key": key}, sort=[("revision", -1)])
        return latest["body"]
    return body


def latest_body(conn, rtype: str, filt: dict | None = None) -> dict | None:
    """Body of the newest report of a type (by date, then revision)."""
    r = one(conn.report, {"type": rtype, **(filt or {})}, sort=[("local_date", -1), ("revision", -1)])
    return r["body"] if r else None


# ---------------------------------------------------------------- morning report

def metric_finding(conn, source: str, metric: str, d: date, obs_row) -> dict | None:
    ds = d.isoformat()
    fid = f"m:{ds}:{metric}"
    if obs_row is None or obs_row["state"] != "measured":
        # Today's value isn't in yet: point to the most recent measured one (last 3 days) so it doesn't look lost
        prior = {k: v for k, v in series(conn, source, metric, (d - timedelta(days=1)).isoformat()).items()
                 if k >= (d - timedelta(days=3)).isoformat()}
        last = {"date": max(prior), "value": prior[max(prior)]} if prior else None
        return {"id": fid, "last": last, "category": CATEGORY[metric], "metric": metric, "title": METRIC_TITLES[metric], "status": "missing",
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
    plan_row = one(conn.day_plan, {"local_date": ds})
    plan = {"kind": plan_row["kind"], "minutes": plan_row["minutes"]} if plan_row else None
    zones = hr_zones(conn)
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
    # The app no longer asks how you feel: Garmin's data drives the advice (a check-in, if one exists, still counts)
    checkin_prompt = {"ask": False, "reason": None}
    body = {
        "type": "morning", "local_date": ds, "synthetic": synthetic, "checkin_prompt": checkin_prompt,
        "provisional": completeness["sleep_duration"] != "measured",
        "headline": headline(rec, findings, checkin), "recommendation": rec,
        "top_finding_ids": [f["id"] for f in top], "findings": findings, "garmin_context": garmin_ctx,
        "completeness": completeness, "checkin": checkin, "recent_run": recent_run, "narrative": None,
    }
    inputs = {"findings": [{k: f.get(k) for k in ("id", "observed", "comparison", "status", "last")} for f in findings],
              "checkin": checkin, "running_days": running_days, "garmin": garmin_ctx, "recent": recent_run, "v": ALGORITHMS,
              "plan": plan, "available": get_setting(conn, "available_minutes", None), "zones": zones,
              # everything displayed, so no input that changes the text can leave an old revision in place
              "shown": [body["headline"], rec["suggestion"], rec["reason"], checkin_prompt]}
    return save_report(conn, "morning", ds, ds, body, input_hash(inputs), data_cutoff(conn, source))


def headline(rec: dict, findings: list[dict], checkin: dict | None) -> str:
    st, rule = rec["state"], rec["rule_id"]
    if rule == "R0":
        return "You reported feeling unwell or in pain."
    if st == "insufficient_data":
        return {"R1b": "Still learning your usual ranges.", "R1d": "Still learning your usual ranges, and you feel fine.",
                "R1c": "No overnight data yet, but you feel fine."}.get(rule, "Waiting for today's data.")
    if rule == "R4s":
        # Only call readings typical when there are comparable readings
        typical = any(f["status"] == "within" and f.get("comparison") for f in findings if f["metric"] in CORE_METRICS)
        return "Readings look typical, but you feel less recovered." if typical else "You feel less recovered today."
    if rule == "R1e":
        return "Recent running is well above your usual." if "load" in rec.get("reason", "") or "running" in rec.get("reason", "") \
            else "One reading stands out; ranges still being learned."
    off = [f for f in findings if f["status"] in ("outside", "sustained")]
    within = [f for f in findings if f["status"] == "within"]
    if st == "consider_easier":
        return "Mixed recovery signals today." if within else "Several recovery signals are off today."
    if rule == "R3":
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
        "insufficient_data": "Train by feel. Keep any hard session conditional on how you feel.",
    }[st]


# ---------------------------------------------------------------- post-run report

_class_cache: dict[tuple, dict] = {}


def run_key(conn, a: dict) -> tuple:
    """Cache key for anything computed from a run's samples: per user database and per revision of the run (a re-read
    run, e.g. with corrected samples, gets a new updated_at)."""
    return conn.name, a["id"], a["content_hash"], a.get("updated_at")


def run_analysis(conn, a: dict) -> dict:
    key = run_key(conn, a)
    if key not in _class_cache:
        laps = laps_for(conn, a["id"])
        s = samples_for(conn, a["id"])
        dc = rn.decoupling(s, laps, a["distance_m"], a["elevation_gain_m"])
        # One classification for the whole report: the grade-adjusted one the drift analysis used
        _class_cache[key] = {"classification": dc["classification"], "decoupling": dc}
    return _class_cache[key]


_effort_cache: dict[tuple, dict] = {}

EFFORT_LABELS = {"1k": "1 km", "5k": "5 km", "10k": "10 km", "half": "half marathon"}


def efforts_for(conn, a: dict) -> dict:
    key = run_key(conn, a)
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
        first, second = rn.halves(paces)  # the app's one definition of the halves; recorded pace for the numbers shown
        gap = {d["idx"]: d.get("gap_pace_s_per_km") for d in rn.split_details(samples_for(conn, a["id"]), laps, None)}
        adj = rn.fade([gap.get(s.idx) or s.pace_s_per_km for s in complete])  # and hill-adjusted for the verdict, as everywhere
        cv = pstdev(paces) / (sum(paces) / len(paces))
        findings.append({
            "id": f"r:{sid}:pacing", "category": "running", "metric": "split_consistency", "title": "Pacing",
            "observed": {"value": round(100 * cv, 1), "unit": "%", "first_half_pace_s_per_km": round(first, 1),
                         "second_half_pace_s_per_km": round(second, 1)},
            "comparison": None, "delta": {"abs": round(second - first, 1), "pct": None},
            "status": "info", "priority": 3,
            "statement": (f"Splits varied by {100 * cv:.1f}% (moving pace). "
                          + (f"Second half was {abs(adj):.0f} s/km faster than the first (hill-adjusted)." if adj < -rn.FADE_S_PER_KM else
                             f"Second half was {abs(adj):.0f} s/km slower than the first (hill-adjusted)." if adj > rn.FADE_S_PER_KM else
                             "Both halves were about even.")),
            "interpretation": "Describes pacing; hills are adjusted for, stops are not.",
            "evidence": {"record_ids": [f"{source}:{sid}:lap{s.idx}" for s in complete], "date_range": [a["local_date"]] * 2},
            "sample_size": len(complete), "coverage": {"complete_splits": len(complete), "total_splits": len(splits)},
            "limitations": ["Incomplete final split excluded."] if len(complete) < len(splits) else [],
            "algorithm_version": rn.RUNNING_VERSION, "derived": True,
        })
    dc = an["decoupling"]
    if dc["eligible"]:
        v = dc["decoupling_pct"]
        findings.append({
            "id": f"r:{sid}:decoupling", "category": "running", "metric": "pace_hr_decoupling", "title": "Aerobic decoupling",
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
    zones = hr_zones(conn)
    details = rn.split_details(samples_for(conn, a["id"]), laps, zones["floors"] if zones else None)
    story = rn.run_story(splits, details, fmt_pace)
    intent = run_intent(conn, a)
    if intent and intent["kind"] in ("easy", "recovery") and intent["source"] != "inferred" and zones:
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
    vo2_series = series(conn, source, "garmin_vo2max_running", a["local_date"])
    recent_vo2 = [k for k in vo2_series if k >= (d - timedelta(days=7)).isoformat()]
    vo2_day = {"value": vo2_series[max(recent_vo2)], "date": max(recent_vo2)} if recent_vo2 else None
    # Garmin's training readiness on the morning of the run (that day only)
    tr = one(conn.daily_observation, {"source": source, "metric": "garmin_training_readiness", "local_date": a["local_date"], "state": "measured"})
    readiness_day = {"value": tr["value"], "date": a["local_date"], "label": tr.get("label")} if tr and tr.get("value") is not None else None
    week_begin = week_start(d, first_weekday(conn))
    week_acts = activities(conn, source, week_begin.isoformat(), a["local_date"])
    rpe = one(conn.activity_effort, {"activity_source_id": sid})
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
        "garmin_metrics": a["garmin_metrics"],
        # Garmin's headline (smoothed, one decimal) VO2 max as of the run's day; the run's own vO2MaxValue is a separate,
        # whole-number per-run estimate and often differs by a point
        "garmin_vo2max_day": vo2_day, "garmin_readiness_day": readiness_day,
        "splits": [{**rn.as_dict(s), **{k: v for k, v in dt.items() if k != "idx"}}
                   for s, dt in zip(splits, details or [{}] * len(splits))],
        "story": story, "best_efforts": best_efforts,
        "classification": an["classification"], "decoupling": dc,
        "comparable": comp, "calendar_week": rn.workload(week_acts, week_begin.isoformat(), a["local_date"]),
        "findings": sorted(findings, key=lambda f: f["priority"]), "effort": effort,
        "next_focus": next_focus(an, dc, comp, splits, details, intent, zones["floors"][2] if zones else None, a.get("avg_hr")),
        # What the data alone says, kept beside a stated intent (never in its place)
        "intent": intent, "classified": intent if intent and intent["source"] == "inferred" else infer_intent(conn, a),
        "narrative": None,
    }
    inputs = {"a": a["content_hash"], "comp": [r["source_id"] for r in comp["runs"]], "rpe": rpe["rpe"] if rpe else None, "v": ALGORITHMS,
              "prev_bests": {k: e["previous_best_s"] for k, e in best_efforts.items()}, "zones": zones, "intent": intent,
              "week_first": first_weekday(conn), "vo2_day": vo2_day, "readiness_day": readiness_day}
    return save_report(conn, "post_run", sid, a["local_date"], body, input_hash(inputs), data_cutoff(conn, source))


CONTEXT_FIELDS = ("target", "effort", "feel", "limiter", "limiter2", "health")  # the runner's own report on a run, all optional


def run_intent(conn, a: dict) -> dict | None:
    """User-stated intent (with whatever the runner added about the run), else pre-filled from the day's plan (marked as
    such), else inferred from the data. Explicit intent always wins: nothing downstream re-infers over it."""
    r = one(conn.run_intent, {"activity_source_id": a["source_id"]})
    if r:
        return {"kind": r["kind"], "note": r["note"], "source": r["source"], **{k: r[k] for k in CONTEXT_FIELDS if r.get(k)}}
    p = one(conn.day_plan, {"local_date": a["local_date"]})
    if p and p["kind"] != "rest":
        return {"kind": "easy" if p["kind"] == "easy" else p["kind"], "note": None, "source": "plan"}
    return infer_intent(conn, a)


def infer_intent(conn, a: dict) -> dict | None:
    """What the run looks like from the data alone (labelled 'inferred', with a confidence and the reason; never used to
    flag 'meant to be easy')."""
    zones = hr_zones(conn)
    an = run_analysis(conn, a)
    cls = an["classification"]
    out = lambda kind, conf, why: {"kind": kind, "note": None, "source": "inferred", "confidence": conf, "reason": why}  # noqa: E731
    if "rest/recovery" in cls.get("reason", ""):
        return out("intervals", "high", "laps alternate work and rest")
    if (cls.get("speed_cv") or 0) > 0.15:
        return out("intervals", "medium", f"pace varied a lot (variation {100 * cls['speed_cv']:.0f}%)")
    recent = [x["moving_s"] for x in activities(conn, a["source"], (date.fromisoformat(a["local_date"]) - timedelta(days=42)).isoformat(),
                                                   a["local_date"]) if x["moving_s"]]
    if a["moving_s"] and recent and a["moving_s"] >= max(3600, 1.3 * median(recent)):
        return out("long", "medium", f"{a['moving_s'] / 60:.0f} min, well above your usual {median(recent) / 60:.0f} min")
    if zones:
        from .focus import zone_shares
        z = zone_shares(conn, a, zones["floors"])
        if z is not None:
            easy, hard = round(100 * z["easy"]), round(100 * z["hard"])
            if z["easy"] >= 0.7:
                return out("easy", "high" if z["easy"] >= 0.85 else "medium", f"{easy}% of moving time below Garmin HR zone 3")
            if z["easy"] < 0.4:
                return out("tempo", "high" if z["hard"] >= 0.6 else "medium", f"{hard}% of moving time in Garmin HR zones 4–5")
            return out("other", "low", f"mixed: {easy}% below zone 3, {hard}% in zones 4–5")
    return None


STEADY_KINDS = {"easy", "recovery", "steady", "long"}  # explicit intents where pace is meant to follow effort, not lead it


def hr_cap(target: str | None) -> int | None:
    """A heart-rate cap from the runner's target text ("HR <= 160", "below 150 bpm"), or None."""
    m = re.search(r"(?:hr|heart|bpm|≤|<=|<|below|under)\D{0,12}(\d{3})|(\d{3})\s*bpm", (target or "").lower())
    v = int(m.group(1) or m.group(2)) if m else None
    return v if v and 100 <= v <= 210 else None


def next_focus(an: dict, dc: dict, comp: dict, splits=None, details=None, intent: dict | None = None,
               easy_ceiling: float | None = None, avg_hr: float | None = None) -> str:
    """One practical focus from this run, most specific first, judged against what the runner meant the run to be when
    they said so. No pace or HR prescriptions beyond the run's own numbers and the runner's own target."""
    pairs = [(s, d) for s, d in zip(splits or [], details or [{}] * len(splits or [])) if s.complete and s.pace_s_per_km]
    zones = [d.get("zone") for d in (details or []) if d.get("zone") is not None]
    hard_share = (sum(1 for z in zones if z >= 4) / len(zones)) if zones else 0
    said = intent if intent and intent.get("source") != "inferred" else None  # the runner's (or the plan's) intent
    kind = said["kind"] if said else None
    if kind in ("easy", "recovery") and hard_share >= 0.5 and easy_ceiling:
        return f"This was meant to be easy. Next time, keep heart rate below {round(easy_ceiling)} bpm, even if that means a slower pace."
    if kind == "intervals":
        return "Interval session: compare the repeated efforts with each other rather than with steady runs."
    cap = hr_cap(said.get("target")) if said else None
    if cap and avg_hr:
        if avg_hr <= cap + 2:
            return (f"The heart-rate cap worked ({round(avg_hr)} bpm average against {cap}). Keep heart rate as the governor on "
                    "hills and let pace vary; on the next comparable run, watch whether the same heart rate gives a faster pace "
                    "or lower drift.")
        return (f"Heart rate averaged {round(avg_hr)} bpm, above your {cap} bpm cap. Next time, start slower and let pace drop "
                "on the climbs to stay under it.")
    cls = an["classification"]
    structured = "rest/recovery" in cls.get("reason", "") or (cls.get("speed_cv") or 0) > 0.15
    if cls["kind"] == "variable" and structured:
        return "Interval-style session: drift analysis doesn't apply. Compare the repeated efforts with each other instead."
    if dc.get("eligible") and dc["decoupling_pct"] > 5:
        return "See whether aerobic decoupling stays above 5% on your next comparable steady run before reading much into it."
    if kind in STEADY_KINDS:
        return ("Pace follows effort on a run like this. On the next comparable run, watch whether the same heart rate gives "
                "a faster pace or lower drift.")
    if len(pairs) >= 4 and kind not in ("progression",):
        # Hill-adjusted pace where the samples allow it, so a climb late in the run doesn't read as a fade
        paces = [d.get("gap_pace_s_per_km") or s.pace_s_per_km for s, d in pairs]
        first = rn.halves(paces)[0]
        fade = rn.fade(paces)
        if fade > rn.FADE_S_PER_KM:
            return (f"You faded by about {fade:.0f} s/km (hill-adjusted). Next time, try starting 5–10 s/km slower than "
                    f"{fmt_pace(first)} and see if the second half holds.")
    if zones and sum(1 for z in zones if z >= 4) >= 0.8 * len(zones):
        if kind in ("tempo", "threshold", "race"):
            return "Hard all the way, as a run like this should be. Compare it with your next one of the same kind."
        return "Almost the whole run was in zone 4 or higher. If it was meant to be easy, it wasn't; if it was a hard run, that fits."
    if cls["kind"] == "variable":
        return "Pace was uneven enough that drift and similar-run comparisons were skipped. A steadier effort makes them possible."
    if comp.get("n", 0) < 3:
        return "A few more similar runs will make comparisons meaningful."
    return "Nothing stands out. Keep building consistent, comparable runs."


# ---------------------------------------------------------------- insights

def pattern_key(i: dict) -> tuple[str, str]:
    """An insight's verdict and which way it points: its headline with the numbers masked ("Faster at the same heart rate:
    about # s/km per month" and "Slower at the same heart rate recently" are both patterns, but not the same one)."""
    return i["verdict"], re.sub(r"[\d.,]+", "#", i.get("headline") or "")


def build_insights(conn, source: str, today: date, synthetic: bool) -> dict:
    from datetime import datetime as _dt
    from .analytics import insights as ins

    acts = activities(conn, source, (today - timedelta(days=120)).isoformat(), today.isoformat())
    runs, drifts = [], []
    for a in acts:
        an = run_analysis(conn, a)
        local = _dt.fromisoformat(a["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=a["utc_offset_s"] or 0)
        runs.append(ins.RunData(a["source_id"], a["local_date"], local.replace(tzinfo=None), a.get("device_id"), a["distance_m"],
                                a["moving_s"], (a["garmin_metrics"] or {}).get("activityTrainingLoad"),
                                samples_for(conn, a["id"]), rn.splits_from_laps(laps_for(conn, a["id"])), an["classification"]["kind"]))
        if an["decoupling"]["eligible"]:
            drifts.append((a["local_date"], a["source_id"], an["decoupling"]["decoupling_pct"]))
    since = (today - timedelta(days=120)).isoformat()
    obs: dict[str, dict[str, float]] = {}
    for r in conn.daily_observation.find({"source": source, "state": "measured", "local_date": {"$gte": since}},
                                         {"_id": 0, "local_date": 1, "metric": 1, "value": 1}):
        obs.setdefault(r["metric"], {})[r["local_date"]] = r["value"]
    bedtimes = {}
    for r in many(conn.sleep_session, {"source": source, "is_nap": False, "wake_date": {"$gte": since}}):
        st = _dt.fromisoformat(r["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=r["utc_offset_s"] or 0)
        bedtimes[r["wake_date"]] = st.hour + st.minute / 60 + (24 if st.hour < 12 else 0)
    zones = hr_zones(conn)
    items = ins.compute_all(runs, obs, bedtimes, zones, drifts, today, first_weekday(conn))
    # Confidence: "consistent" only if an insights report from >= 14 days earlier reached the same verdict pointing the
    # same way ("faster" vs "slower" are both patterns): the headline with its numbers masked is that direction
    prev = latest_body(conn, "insights", {"local_date": {"$lte": (today - timedelta(days=14)).isoformat()}})
    prev_v = {i["id"]: pattern_key(i) for i in prev["insights"]} if prev else {}
    for i in items:
        i["confidence"] = None if i["verdict"] == "not_enough_data" else ("consistent" if prev_v.get(i["id"]) == pattern_key(i) else "emerging")
    # Novelty vs the most recent earlier snapshot, and the runner's own dismissals / "working on it"
    last = latest_body(conn, "insights", {"local_date": {"$lt": today.isoformat()}})
    last_i = {i["id"]: i for i in last["insights"]} if last else {}
    states = {r["insight_id"]: r for r in many(conn.insight_state)}
    for i in items:
        p = last_i.get(i["id"])
        i["novelty"] = ("new" if p is None or (p["verdict"] != "pattern" and i["verdict"] == "pattern") else
                        "changed" if p["verdict"] != i["verdict"] or p["headline"] != i["headline"] else "continuing")
        st = states.get(i["id"])
        # A dismissal lapses when the verdict changes, so a new development is never hidden
        i["user_state"] = st["state"] if st and st["verdict_at_dismissal"] == i["verdict"] else None
    body = {"type": "insights", "local_date": today.isoformat(), "synthetic": synthetic, "insights": items, "narrative": None,
            "window": [since, today.isoformat()]}
    inputs = {"items": [{k: i.get(k) for k in ("id", "verdict", "effect", "sample_size", "confidence", "novelty", "user_state", "headline", "detail",
                                                "practical")} for i in items], "v": ALGORITHMS,
              "iv": ins.INSIGHTS_VERSION}
    return save_report(conn, "insights", today.isoformat(), today.isoformat(), body, input_hash(inputs), data_cutoff(conn, source))


def regenerate(conn, source: str, synthetic: bool, changed_dates: set[str], changed_activities: list[str], today: date,
               morning_lookback_days: int = 7) -> None:
    """Regenerate reports affected by new/changed inputs. Morning reports older than the lookback stay as they were,
    except on first generation (backfill), so the journal reflects what was known at the time."""
    existing = set(conn.report.distinct("subject_key", {"type": "morning"}))
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
    if changed_dates or changed_activities or not conn.report.find_one({"type": "insights", "subject_key": today.isoformat()}):
        build_insights(conn, source, today, synthetic)
    from .weekly import regenerate_weeklies
    regenerate_weeklies(conn, source, today, synthetic)

"""Weekly review for a completed Mon–Sun local week: consistency, intensity, performance, recovery context,
check-ins and a next-week focus. Deterministic, revisioned like the other reports."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median

from . import reports as rp
from .db import many, one
from .analytics import baseline as bl
from .analytics import insights as ins

WEEKLY_VERSION = "weekly-1.0"
FREEZE_AFTER_DAYS = 14  # weekly reviews older than this are not regenerated (history keeps its original context)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _runs(conn, source, start: str, end: str) -> list[ins.RunData]:
    out = []
    for a in rp.activities(conn, source, start, end):
        local = datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=a["utc_offset_s"] or 0)
        out.append(ins.RunData(a["source_id"], a["local_date"], local.replace(tzinfo=None), a.get("device_id"), a["distance_m"],
                               a["moving_s"], (a["garmin_metrics"] or {}).get("activityTrainingLoad"),
                               rp.samples_for(conn, a["id"]), [], "steady"))
    return out


def _f(fid, category, metric, title, statement, *, observed=None, comparison=None, delta=None, status="info", n=None,
       evidence=None, date_range=None, limitations=None, interpretation=None) -> dict:
    return {"id": fid, "category": category, "metric": metric, "title": title, "status": status, "statement": statement,
            "interpretation": interpretation, "observed": observed, "comparison": comparison, "delta": delta,
            "evidence": {"record_ids": evidence or [], "date_range": date_range or []}, "sample_size": n,
            "limitations": limitations or [], "algorithm_version": WEEKLY_VERSION, "derived": True}


def build_weekly(conn, source: str, ws: date, synthetic: bool) -> dict:
    we = ws + timedelta(days=6)
    wid = ws.isoformat()
    week = _runs(conn, source, ws.isoformat(), we.isoformat())
    prior = _runs(conn, source, (ws - timedelta(days=28)).isoformat(), (ws - timedelta(days=1)).isoformat())
    findings = []

    # Consistency
    mv = sum(r.moving_s or 0 for r in week)
    dist = sum(r.distance_m or 0 for r in week)
    prior_weeks = 4
    p_mv = sum(r.moving_s or 0 for r in prior) / prior_weeks
    ratio = mv / p_mv if p_mv else None
    status = "outside" if ratio is not None and (ratio > 1.5 or ratio < 0.5) else "within"
    findings.append(_f(
        f"w:{wid}:volume", "training_load", "weekly_moving_time", "Running this week",
        f"{len(week)} runs, {dist / 1000:.1f} km, {rp.fmt_duration(mv) if mv else '0 min'} of running"
        + (f" vs a {rp.fmt_duration(p_mv)} weekly average over the previous 4 weeks." if p_mv else "."),
        observed={"value": mv, "unit": "s", "runs": len(week), "distance_m": round(dist, 1)},
        comparison={"kind": "prior_4_week_weekly_mean", "value": round(p_mv), "n": len(prior)} if p_mv else None,
        delta={"abs": round(mv - p_mv), "pct": round(100 * (ratio - 1), 1) if ratio else None} if p_mv else None,
        status=status, n=len(week) + len(prior), evidence=[r.source_id for r in week], date_range=[wid, we.isoformat()],
        limitations=["Calendar week, Monday to Sunday, in your local time zone."]))

    # Intensity (Garmin zones)
    zones = rp.hr_zones(conn)
    hard = None
    if zones and week:
        totals = [0.0] * 6
        for r in week:
            totals = [a + b for a, b in zip(totals, ins.zone_time(r, zones["floors"]))]
        if sum(totals) > 0:
            hard = (totals[4] + totals[5]) / sum(totals)
            easy = sum(totals[:4]) / sum(totals)
            findings.append(_f(
                f"w:{wid}:intensity", "training", "hard_share", "Intensity",
                f"{round(100 * hard)}% of this week's running was in zones 4–5 (above {zones['floors'][3]} bpm), "
                f"{round(100 * easy)}% in zones 1–3.",
                observed={"value": round(100 * hard), "unit": "%"}, n=len(week), evidence=[r.source_id for r in week],
                date_range=[wid, we.isoformat()], status="outside" if hard >= 0.7 else "within",
                limitations=[f"Garmin zones ({zones.get('method')}, max HR {zones.get('max_hr')})."]))

    # Performance: pace at the user's usual HR band, this week vs the previous 4 weeks on the same watch
    eff = ins.efficiency_trend(prior + week)
    for era in eff["effect"].get("eras", []):
        this = [p["pace_s_per_km"] for p in era["points"] if wid <= p["date"] <= we.isoformat()]
        before = [p["pace_s_per_km"] for p in era["points"] if (ws - timedelta(days=28)).isoformat() <= p["date"] < wid]
        if this and len(before) >= 3:
            d = median(this) - median(before)
            lo, hi = eff["effect"]["band_bpm"]
            findings.append(_f(
                f"w:{wid}:pace_at_hr", "fitness", "pace_at_hr", "Pace at the same heart rate",
                f"At {lo}–{hi} bpm you ran {ins.fmt_pace(median(this))}, "
                + (f"{abs(d):.0f} s/km {'faster' if d < 0 else 'slower'} than" if abs(d) >= 2 else "about the same as")
                + f" the previous 4 weeks ({ins.fmt_pace(median(before))}).",
                observed={"value": round(median(this)), "unit": "s/km"}, comparison={"kind": "prior_4_weeks_median", "value": round(median(before)), "n": len(before)},
                delta={"abs": round(d, 1), "pct": None}, n=len(this) + len(before), date_range=[(ws - timedelta(days=28)).isoformat(), we.isoformat()],
                limitations=["Same watch only. Heat and terrain aren't adjusted for."]))

    # Recovery context: the week's median vs the personal range at the end of the week
    for m, title in (("sleep_duration", "Sleep"), ("resting_hr", "Resting heart rate"), ("hrv_overnight_avg", "Overnight HRV")):
        s = rp.series(conn, source, m, we.isoformat())
        vals = [v for k, v in s.items() if wid <= k <= we.isoformat()]
        if len(vals) < 4:
            findings.append(_f(f"w:{wid}:{m}", "recovery" if m != "sleep_duration" else "sleep", m, title,
                               f"{title}: only {len(vals)} of 7 nights recorded, too few to summarise.", status="missing", n=len(vals)))
            continue
        b = bl.compute_baseline(s, ws, era_start=rp.device_era_start(conn, source, we))
        med = median(vals)
        if b.sufficient:
            dev = bl.deviation(m, med, b)
            stmt = f"{title} averaged {rp.fmt_value(m, med)} over {len(vals)} nights, vs your usual {rp.fmt_value(m, b.median)}."
            findings.append(_f(f"w:{wid}:{m}", "recovery" if m != "sleep_duration" else "sleep", m, title, stmt,
                               observed={"value": med, "unit": bl.THRESHOLDS[m]["unit"]},
                               comparison={"kind": "personal_reference_range", "median": b.median, "q1": b.q1, "q3": b.q3, "n": b.n,
                                           "window": [b.window_start, b.window_end]},
                               delta={"abs": round(dev.delta_abs, 1), "pct": round(dev.delta_pct, 1) if dev.delta_pct is not None else None},
                               status="outside" if dev.beyond_threshold else "within", n=len(vals), date_range=[wid, we.isoformat()]))
        else:
            findings.append(_f(f"w:{wid}:{m}", "recovery" if m != "sleep_duration" else "sleep", m, title,
                               f"{title} averaged {rp.fmt_value(m, med)} over {len(vals)} nights. Your usual range is still being learned.",
                               observed={"value": med, "unit": bl.THRESHOLDS[m]["unit"]}, status="learning", n=len(vals)))

    # Check-ins
    cis = many(conn.checkin, {"deleted": False, "local_date": {"$gte": wid, "$lte": we.isoformat()}})
    flagged_days = sorted({c["local_date"] for c in cis if c["pain"] or c["illness"]})
    if cis:
        en = [c["energy"] for c in cis if c["energy"]]
        findings.append(_f(f"w:{wid}:checkins", "subjective", "checkins", "How you felt",
                           f"{len(cis)} check-ins" + (f", median energy {median(en):.0f}/5" if en else "")
                           + (f"; pain or illness reported on {len(flagged_days)} day(s)." if flagged_days else "."),
                           n=len(cis), status="outside" if flagged_days else "within"))

    focus = next_week_focus(flagged_days, ratio, hard, zones, len(week))
    from . import focus as fc
    chosen = one(conn.weekly_focus, {"week_start": wid})
    focus_result = fc.evaluate(conn, source, ws, chosen["kind"], we + timedelta(days=1), chosen["params"]) if chosen else None
    if focus_result:
        findings.insert(0, _f(f"w:{wid}:focus", "focus", "weekly_focus", f"Your focus: {focus_result['title']}",
                              focus_result["summary"] + (" " + focus_result["felt"] if focus_result.get("felt") else ""),
                              status={"achieved": "within", "partly": "info"}.get(focus_result["status"], "outside"),
                              n=len(focus_result["runs"]), evidence=[r["source_id"] for r in focus_result["runs"] if r.get("source_id")],
                              date_range=[wid, we.isoformat()], limitations=[focus_result.get("target", "")]))
    body = {"type": "weekly", "local_date": we.isoformat(), "week_start": wid, "week_end": we.isoformat(), "synthetic": synthetic,
            "headline": weekly_headline(len(week), ratio, hard), "findings": findings, "next_week_focus": focus,
            "focus_result": focus_result, "narrative": None}
    inputs = {"f": [{k: f.get(k) for k in ("id", "observed", "comparison", "status", "statement")} for f in findings], "focus": focus,
              "v": rp.ALGORITHMS, "w": WEEKLY_VERSION}
    return rp.save_report(conn, "weekly", wid, we.isoformat(), body, rp.input_hash(inputs), rp.data_cutoff(conn, source))


def weekly_headline(runs: int, ratio: float | None, hard: float | None) -> str:
    if runs == 0:
        return "A week without runs."
    if ratio is not None and ratio > 1.5:
        return f"A bigger week: {runs} runs, well above your recent average."
    if ratio is not None and ratio < 0.5:
        return f"A lighter week: {runs} run{'s' if runs != 1 else ''}."
    if hard is not None and hard >= 0.7:
        return f"{runs} runs, mostly at high intensity."
    return f"A steady week: {runs} run{'s' if runs != 1 else ''}."


def next_week_focus(flagged_days: list[str], ratio: float | None, hard: float | None, zones: dict | None, runs: int) -> dict:
    """Small conservative rule table; one focus, with the rule that produced it."""
    if flagged_days:
        return {"rule": "F1", "text": "You reported pain or illness this week. Let that guide next week. If it persists, get it checked."}
    if ratio is not None and ratio > 1.5:
        return {"rule": "F2", "text": "This week was a clear jump in volume. Keeping next week similar, rather than adding more, gives it time to settle."}
    if hard is not None and hard >= 0.7 and zones:
        return {"rule": "F3", "text": f"Most running was hard. If endurance is the goal, try making one run genuinely easy, "
                                      f"below about {zones['floors'][2]} bpm on your zones."}
    if runs == 0 or (ratio is not None and ratio < 0.5):
        return {"rule": "F4", "text": "A lighter week. If you're returning after a break, build back gradually."}
    return {"rule": "F5", "text": "Keep the same rhythm. Consistency is what makes the trends meaningful."}


def regenerate_weeklies(conn, source: str, today: date, synthetic: bool) -> None:
    """Build the last completed week's review (revision if inputs changed); create missing older ones once."""
    last_complete = week_start(today) - timedelta(days=7)
    r = conn.daily_observation.find_one({"source": source}, sort=[("local_date", 1)])
    first = r["local_date"] if r else None
    if not first:
        return
    existing = set(conn.report.distinct("subject_key", {"type": "weekly"}))
    ws = week_start(date.fromisoformat(first))
    while ws <= last_complete:
        recent = (today - (ws + timedelta(days=6))).days <= FREEZE_AFTER_DAYS
        if recent or ws.isoformat() not in existing:
            build_weekly(conn, source, ws, synthetic)
        ws += timedelta(days=7)

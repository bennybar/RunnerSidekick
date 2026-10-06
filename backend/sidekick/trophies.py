"""Trophies: your records in one place. Garmin's own all-time personal records (fastest 1 km, mile, 5 km..., longest
run, most steps, goal streaks) next to the app's bests from the synced history (the fastest stretch within a run, the
longest run, the biggest week, the most climbing, the highest VO2 max estimate, the lowest resting heart rate), with how
they compare with your age and sex where a published reference exists (age grading for 5 km to the marathon, VO2 max
and resting heart rate percentiles). Each record names where it comes from and links to its run when the app has it."""

from __future__ import annotations

from datetime import date, timedelta

from . import compare as cp
from . import reports as rp
from .db import get_setting

TROPHIES_VERSION = "trophies-1.1"  # 1.1: each record's history of improvements; runs that set a record
# Garmin's personal-record type ids (running and daily records; cycling and swimming ones are left out)
GARMIN_TYPES = {1: ("1k", "Fastest 1 km"), 2: ("mile", "Fastest mile"), 3: ("5k", "Fastest 5 km"), 4: ("10k", "Fastest 10 km"),
                5: ("half", "Fastest half marathon"), 6: ("marathon", "Fastest marathon"), 7: ("longest", "Longest run"),
                12: ("steps_day", "Most steps in a day"), 13: ("steps_week", "Most steps in a week"),
                14: ("steps_month", "Most steps in a month"), 15: ("streak_best", "Longest step-goal streak"),
                16: ("streak_now", "Current step-goal streak")}
DISTANCES = [("1k", "Fastest 1 km", 1000.0), ("mile", "Fastest mile", 1609.344), ("5k", "Fastest 5 km", 5000.0),
             ("10k", "Fastest 10 km", 10000.0), ("half", "Fastest half marathon", 21097.5), ("marathon", "Fastest marathon", 42195.0)]


def build(conn, source: str, today: date) -> dict:
    garmin = {GARMIN_TYPES[r["type"]][0]: r for r in (get_setting(conn, "garmin_records", None) or {}).get("records", [])
              if r["type"] in GARMIN_TYPES}
    ours = rp.records(conn, source)
    runs = rp.activities(conn, source, "0000-01-01", today.isoformat())
    since = runs[0]["local_date"] if runs else None
    p = cp.profile(conn, today)
    sex, birth = p.get("sex"), p.get("birth_date")
    have = {a["source_id"] for a in runs}

    def link(sid):
        return sid if sid in have else None

    def comparison(dist, seconds, when):
        if not (sex and birth and dist in cp.DISTANCE_LABELS and seconds):
            return None
        ag = cp.age_grade(sex, cp.age_on(birth, date.fromisoformat(when) if when else today), dist, seconds)
        return ag and {"headline": f"{ag['age_grade_pct']:.0f}% age grade · {ag['class']}",
                       "detail": f"Against the age standard for a {cp.SEX_WORD[sex][0]} of your age then (USATF road standards); "
                                 f"100% is about world-record level for your age.", "percent": ag["age_grade_pct"]}

    fastest = []
    for key, title, metres in DISTANCES:
        g, o = garmin.get(key), ours.get(key, {}).get("best")
        cands = ([{"seconds": g["value"], "date": g["date"], "source_id": link(g["activity_id"]), "from": "Garmin's all-time record"}] if g else []) + \
                ([{"seconds": o["elapsed_s"], "date": o["date"], "source_id": o["source_id"],
                   "from": "the fastest stretch within a run" + (f" since {since}" if since else "")}] if o else [])
        if not cands:
            continue
        best = min(cands, key=lambda c: c["seconds"])
        fastest.append({"id": key, "title": title, "value": _hms(best["seconds"]),
                        "seconds": round(best["seconds"], 1), "pace_s_per_km": round(best["seconds"] / (metres / 1000), 1),
                        "date": best["date"], "source_id": best["source_id"], "source": best["from"],
                        "comparison": comparison(key, best["seconds"], best["date"])})

    longest = []
    if runs:
        far = max(runs, key=lambda a: a["distance_m"] or 0)
        g = garmin.get("longest")
        if g and g["value"] > (far["distance_m"] or 0):
            longest.append({"id": "longest", "title": "Longest run", "value": f"{g['value'] / 1000:.1f} km", "metres": g["value"],
                            "date": g["date"], "source_id": link(g["activity_id"]), "source": "Garmin's all-time record"})
        else:
            longest.append({"id": "longest", "title": "Longest run", "value": f"{(far['distance_m'] or 0) / 1000:.1f} km",
                            "metres": far["distance_m"], "date": far["local_date"], "source_id": far["source_id"], "source": "your runs"})
        long_t = max(runs, key=lambda a: a["moving_s"] or 0)
        longest.append({"id": "longest_time", "title": "Longest time running", "value": _hms(long_t["moving_s"] or 0),
                        "seconds": long_t["moving_s"], "date": long_t["local_date"], "source_id": long_t["source_id"], "source": "your runs"})
        climb = max(runs, key=lambda a: a["elevation_gain_m"] or 0)
        if (climb["elevation_gain_m"] or 0) >= 20:
            longest.append({"id": "climb", "title": "Most climbing in a run", "value": f"{climb['elevation_gain_m']:.0f} m",
                            "date": climb["local_date"], "source_id": climb["source_id"], "source": "your runs"})
        first = rp.first_weekday(conn)
        weeks: dict[str, float] = {}
        for a in runs:
            d = date.fromisoformat(a["local_date"])
            ws = d - timedelta(days=(d.weekday() - first) % 7)
            weeks[ws.isoformat()] = weeks.get(ws.isoformat(), 0.0) + (a["distance_m"] or 0)
        wk = max(weeks, key=weeks.get)
        longest.append({"id": "week", "title": "Biggest week", "value": f"{weeks[wk] / 1000:.1f} km", "metres": weeks[wk],
                        "date": wk, "source_id": None, "source": "the week starting that day"})

    body = []
    vo2 = rp.series(conn, source, "garmin_vo2max_running", today.isoformat())
    now = ((get_setting(conn, "garmin_fitness", None) or {}).get("vo2max") or {})
    if not vo2 and now.get("value") and now.get("date"):
        vo2 = {now["date"]: float(now["value"])}  # no daily history yet: Garmin's current estimate
    if vo2:
        d, v = max(vo2.items(), key=lambda kv: (kv[1], kv[0]))
        cmp = None
        if sex and birth:
            it = cp.vo2_item(sex, cp.age_on(birth, date.fromisoformat(d)), {"vo2max": {"value": v}})
            cmp = {"headline": it.get("headline"), "detail": it.get("detail")} if it.get("status") == "ok" else None
        body.append({"id": "vo2max", "title": "Highest VO₂ max", "value": f"{v:.0f}", "date": d, "source_id": None,
                     "source": "Garmin's estimate", "comparison": cmp})
    rhr = rp.series(conn, source, "resting_hr", today.isoformat())
    if len(rhr) >= 7:
        d, v = min(rhr.items(), key=lambda kv: (kv[1], kv[0]))
        cmp = None
        if sex and birth:
            it = cp.rhr_item(conn, source, sex, cp.age_on(birth, today), today)
            cmp = {"headline": f"Your usual: {it.get('headline')[0].lower()}{it.get('headline')[1:]}",
                   "detail": "Your usual resting heart rate (last 4 weeks) against people of your age and sex."} \
                if it.get("status") == "ok" else None
        body.append({"id": "resting_hr", "title": "Lowest resting heart rate", "value": f"{v:.0f} bpm", "date": d, "source_id": None,
                     "source": "your nights", "comparison": cmp})
    hrv = rp.series(conn, source, "hrv_overnight_avg", today.isoformat())
    if len(hrv) >= 7:
        d, v = max(hrv.items(), key=lambda kv: (kv[1], kv[0]))
        body.append({"id": "hrv", "title": "Highest overnight HRV", "value": f"{v:.0f} ms", "date": d, "source_id": None,
                     "source": "your nights (no age reference: HRV varies too much between people)"})

    daily = []
    for key in ("steps_day", "steps_week", "steps_month", "streak_best", "streak_now"):
        g = garmin.get(key)
        if g:
            unit = ("day" if g["value"] == 1 else "days") if key.startswith("streak") else "steps"
            daily.append({"id": key, "title": dict(GARMIN_TYPES.values())[key], "value": f"{g['value']:,.0f} {unit}",
                          "date": g["date"], "source_id": None, "source": "Garmin's record"})

    hist = progressions(conn, source, today)
    for item in fastest + longest + body:
        item["history"] = [{"date": pt["date"], "value": fmt(item["id"], pt["value"]), "v": pt["value"], "source_id": link(pt["source_id"]),
                            "garmin": pt.get("garmin", False)} for pt in hist.get(item["id"], [])]
        item["lower_is_better"] = item["id"] in LOWER_IS_BETTER

    groups = [{"id": "fastest", "title": "Fastest", "items": fastest}, {"id": "longest", "title": "Longest and biggest", "items": longest},
              {"id": "body", "title": "Heart and fitness", "items": body}, {"id": "daily", "title": "Steps and streaks", "items": daily}]
    return {"groups": [g for g in groups if g["items"]], "history_since": since, "algorithm_version": TROPHIES_VERSION,
            "basis": "Garmin's all-time personal records, and the app's bests from the runs and nights it has synced"
                     + (f" (since {since})" if since else "") + ". Age comparisons use published references and are shown only "
                     "when your age and sex are known."}


def _hms(s: float) -> str:
    s = round(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


LOWER_IS_BETTER = {k for k, _, _ in DISTANCES} | {"resting_hr"}
TITLES = {**{k: t for k, t, _ in DISTANCES}, "longest": "Longest run", "longest_time": "Longest time running",
          "climb": "Most climbing in a run", "week": "Biggest week", "vo2max": "Highest VO₂ max",
          "resting_hr": "Lowest resting heart rate", "hrv": "Highest overnight HRV"}
RUN_RECORDS = {k for k, _, _ in DISTANCES} | {"longest", "longest_time", "climb"}  # set by a single run


def fmt(rid: str, v: float) -> str:
    if rid in LOWER_IS_BETTER - {"resting_hr"} or rid == "longest_time":
        return _hms(v)
    return {"longest": f"{v / 1000:.1f} km", "week": f"{v / 1000:.1f} km", "climb": f"{v:.0f} m", "vo2max": f"{v:.0f}",
            "resting_hr": f"{v:.0f} bpm", "hrv": f"{v:.0f} ms"}[rid]


def progressions(conn, source: str, today: date) -> dict[str, list[dict]]:
    """Each record's history in time order, one point per improvement: {id: [{date, value, source_id, garmin?}]}. The
    first point is where the history starts, not an improvement. For records Garmin also keeps, Garmin's all-time record
    from before the synced history is that starting point: a run only counts as a new best if it beats it."""
    garmin = {GARMIN_TYPES[r["type"]][0]: r for r in (get_setting(conn, "garmin_records", None) or {}).get("records", [])
              if r["type"] in GARMIN_TYPES}
    runs = rp.activities(conn, source, "0000-01-01", today.isoformat())
    since = runs[0]["local_date"] if runs else None
    out: dict[str, list[dict]] = {}

    def track(rid, seq, lower, g=None):
        """seq: (date, value, source_id) in time order. g: Garmin's record for this, if it keeps one."""
        pts = []
        if g and g.get("date") and since and g["date"] < since:
            pts.append({"date": g["date"], "value": g["value"], "source_id": None, "garmin": True})  # older than our history
        elif g and g.get("date"):
            seq = sorted(seq + [(g["date"], g["value"], g.get("activity_id"))], key=lambda x: x[0])  # Garmin's own count of a run we have
        for d, v, sid in seq:
            if v is None:
                continue
            if not pts or (v < pts[-1]["value"] if lower else v > pts[-1]["value"]):
                if pts and sid and pts[-1]["source_id"] == sid:
                    pts.pop()  # the same run measured twice (ours and Garmin's count): one improvement, the better value
                pts.append({"date": d, "value": v, "source_id": sid})
        if pts:
            out[rid] = pts

    ours = rp.records(conn, source)
    for key, _, _ in DISTANCES:
        track(key, [(p["date"], p["elapsed_s"], p["source_id"]) for p in ours.get(key, {}).get("progression", [])], True, garmin.get(key))
    track("longest", [(a["local_date"], a["distance_m"], a["source_id"]) for a in runs], False, garmin.get("longest"))
    track("longest_time", [(a["local_date"], a["moving_s"], a["source_id"]) for a in runs], False)
    track("climb", [(a["local_date"], a["elevation_gain_m"], a["source_id"]) for a in runs if (a["elevation_gain_m"] or 0) >= 20], False)
    first = rp.first_weekday(conn)
    weeks: dict[str, float] = {}
    for a in runs:
        d = date.fromisoformat(a["local_date"])
        ws = (d - timedelta(days=(d.weekday() - first) % 7)).isoformat()
        weeks[ws] = weeks.get(ws, 0.0) + (a["distance_m"] or 0)
    track("week", [(w, v, None) for w, v in sorted(weeks.items())], False)
    for rid, metric, lower in (("vo2max", "garmin_vo2max_running", False), ("resting_hr", "resting_hr", True), ("hrv", "hrv_overnight_avg", False)):
        track(rid, [(d, v, None) for d, v in sorted(rp.series(conn, source, metric, today.isoformat()).items())], lower)
    return out


def records_set(conn, source: str, today: date) -> dict[str, list[dict]]:
    """The records each run set (beat an earlier best), by run: {source_id: [{id, title, value}]}."""
    out: dict[str, list[dict]] = {}
    for rid, pts in progressions(conn, source, today).items():
        if rid not in RUN_RECORDS:
            continue
        for pt in pts[1:]:
            if pt["source_id"]:
                out.setdefault(pt["source_id"], []).append({"id": rid, "title": TITLES[rid], "value": fmt(rid, pt["value"])})
    return out

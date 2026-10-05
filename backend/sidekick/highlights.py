"""What stands out today, for the top of the Today screen: Garmin's training verdict, load against Garmin's range,
new personal bests, VO2 max movement, the weekly focus going off track or done, notable comparisons and a run that
didn't match its intent. Deterministic; each item names its source and links to where it's explained. At most
MAX_ITEMS, attention first."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from . import reports as rp
from .db import many

HIGHLIGHTS_VERSION = "highlights-1.0"
MAX_ITEMS = 4
TONE_ORDER = {"attention": 0, "positive": 1, "info": 2}
ATTENTION_STATUS = {"OVERREACHING", "STRAINED", "UNPRODUCTIVE", "DETRAINING"}
GOOD_STATUS = {"PRODUCTIVE", "PEAKING"}
BEST_WINDOW_DAYS = 7
VO2_WINDOW_DAYS = 28
VO2_MIN_CHANGE = 0.5


def _clock(s: float) -> str:
    t = int(round(s))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def _weekday(ds: str) -> str:
    return datetime.fromisoformat(ds).strftime("%a")


def _day(ds: str) -> str:
    d = datetime.fromisoformat(ds[:10])
    return f"{d:%a} {d.day} {d:%b}"


def build(conn, source: str, today: date, comparison: dict | None = None, focus: dict | None = None,
          race: dict | None = None) -> list[dict]:
    out: list[dict] = []
    g = rp.get_setting(conn, "garmin_fitness", None) or {}

    # Strain building (two or more signals agreeing over the last week): first, since it's about what to do now
    from . import strain
    sw = strain.build(conn, source, today)
    if sw:
        out.append({"id": "strain", "tone": "attention", "kind": "recovery", "title": sw["title"], "text": sw["text"],
                    "target": {"type": "insights"}, "source": "your runs"})

    st = g.get("training_status") or {}
    status = (st.get("phrase") or "").split("_")[0]
    if status in ATTENTION_STATUS | GOOD_STATUS:
        out.append({"id": "training_status", "tone": "attention" if status in ATTENTION_STATUS else "positive", "kind": "fitness",
                    "title": f"Garmin: {status.capitalize()}",
                    "text": "Garmin's training status" + (f" since {_day(st['since'])}" if st.get("since") else "") + ".",
                    "target": {"type": "insights"}, "source": "Garmin"})
    acute, hi, lo = st.get("acute_load"), st.get("chronic_max"), st.get("chronic_min")
    if acute is not None and hi and acute > hi:
        out.append({"id": "load", "tone": "attention", "kind": "training", "title": "Load above Garmin's optimal range",
                    "text": f"Acute load {round(acute)}, range {round(lo or 0)}–{round(hi)}.", "target": {"type": "insights"},
                    "source": "Garmin"})

    # New personal bests in the last week (from the post-run reports)
    since = (today - timedelta(days=BEST_WINDOW_DAYS - 1)).isoformat()
    seen: set[str] = set()
    for r in many(conn.report, {"type": "post_run", "local_date": {"$gte": since}}, sort=[("local_date", -1), ("revision", -1)]):
        # Only each run's latest revision, and only runs that still exist: an older revision's "best" may since have been
        # revised away (a re-sync, a corrected run)
        if r["subject_key"] in seen:
            continue
        seen.add(r["subject_key"])
        if rp.activity_by_source_id(conn, source, r["subject_key"]) is None:
            continue
        b = r["body"]
        for k, e in (b.get("best_efforts") or {}).items():
            if e.get("is_best") and not any(h["id"] == f"best:{k}" for h in out):
                out.append({"id": f"best:{k}", "tone": "positive", "kind": "running", "title": f"New {e['label']} best: {_clock(e['elapsed_s'])}",
                            "text": f"{_weekday(b['local_date'])}'s run, {e['previous_best_s'] - e['elapsed_s']:.0f} s faster than before.",
                            "target": {"type": "run", "id": b["activity"]["source_id"]}, "source": "your runs"})

    # VO2 max movement over four weeks (Garmin's values)
    # Only readings from the current watch: a device change makes earlier values incomparable
    era = rp.device_era_start(conn, source, today)
    vo2 = {d: v for d, v in rp.series(conn, source, "garmin_vo2max_running", today.isoformat()).items() if not era or d >= era.isoformat()}
    # The same freshness rule as fitness progress: a recent reading, and an earlier one 3–8 weeks before it
    from .progress import VO2_FRESH_DAYS, VO2_MIN_GAP_DAYS, VO2_OLDEST_DAYS
    latest_d = max(vo2) if vo2 else None
    if latest_d and latest_d >= (today - timedelta(days=VO2_FRESH_DAYS)).isoformat():
        ld = date.fromisoformat(latest_d)
        earlier = [d for d in vo2 if d <= (ld - timedelta(days=max(VO2_WINDOW_DAYS, VO2_MIN_GAP_DAYS))).isoformat()
                   and d >= (today - timedelta(days=VO2_OLDEST_DAYS)).isoformat()]
        if earlier:
            ch = vo2[latest_d] - vo2[max(earlier)]
            weeks = round((ld - date.fromisoformat(max(earlier))).days / 7)
            if abs(ch) >= VO2_MIN_CHANGE:
                out.append({"id": "vo2_change", "tone": "positive" if ch > 0 else "info", "kind": "fitness",
                            "title": f"VO₂ estimate {'up' if ch > 0 else 'down'} {abs(ch):.1f} in {weeks} weeks",
                            "text": f"Now {vo2[latest_d]:.1f} (Garmin).", "target": {"type": "insights"}, "source": "Garmin"})

    # Weekly focus outcome so far
    cur = (focus or {}).get("current") or {}
    if cur.get("status") in ("off_track", "achieved"):
        out.append({"id": "focus", "tone": "attention" if cur["status"] == "off_track" else "positive", "kind": "habits",
                    "title": f"Focus {'off track' if cur['status'] == 'off_track' else 'done'}: {cur['title']}",
                    "text": cur.get("summary") or "", "target": {"type": "focus"}, "source": "your runs"})

    # One standout comparison with people of your age and sex
    items = {i["id"]: i for i in (comparison or {}).get("items", []) if i.get("status") == "ok"}
    fa, v = items.get("fitness_age"), items.get("vo2max")
    if fa and fa["age"] - fa["fitness_age"] >= 2:
        out.append({"id": "compare", "tone": "positive", "kind": "fitness", "title": f"Fitness age {fa['fitness_age']:.1f}",
                    "text": f"{fa['age'] - fa['fitness_age']:.1f} years younger than your age (Garmin).", "target": {"type": "compare"},
                    "source": "Garmin"})
    elif v and v.get("percentile") is not None and v["percentile"] >= 75:
        out.append({"id": "compare", "tone": "positive", "kind": "fitness", "title": f"VO₂ max: {v['rating']} for your age",
                    "text": v["headline"], "target": {"type": "compare"}, "source": v.get("source")})

    # The latest run didn't match what it was meant to be
    last = next(iter(many(conn.report, {"type": "post_run"}, sort=[("local_date", -1), ("revision", -1)], limit=1)), None)
    if last and last["local_date"] >= (today - timedelta(days=2)).isoformat():
        f = next((x for x in last["body"].get("findings", []) if x.get("metric") == "intent_vs_actual"), None)
        if f:
            out.append({"id": "intent", "tone": "info", "kind": "running", "title": f"{_weekday(last['local_date'])}'s easy run wasn't easy",
                        "text": f["statement"], "target": {"type": "run", "id": last["body"]["activity"]["source_id"]},
                        "source": "your runs"})

    out.sort(key=lambda h: TONE_ORDER[h["tone"]])
    if race:
        # An upcoming race frames everything else, so it always leads
        out.insert(0, {"id": "race", "tone": "info", "kind": "running", "title": f"{race['headline']} · {race['phase'].replace('_', ' ').capitalize()}",
                       "text": race.get("prediction_text") or race["phase_note"], "target": {"type": "race"}, "source": "your race goal"})
    return out[:MAX_ITEMS]

"""Training readiness (0–100) and the next run, both calculated, no language model. Readiness combines last night's
HRV and resting heart rate against your usual level, sleep, the last 7 days of running against the 4 weeks before, and
how hard your most recent run was. The next run turns that into a session: kind, distance, a heart-rate cap and a
pace guide, sized from your own recent runs and Garmin's zones. Garmin's own training readiness is not used."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import exp
from zoneinfo import ZoneInfo
from statistics import median

from . import reports as rp
from .scores import clamp, combine

READINESS_VERSION = "readiness-1.1"
WEIGHTS = {"hrv": 20, "resting_hr": 15, "sleep": 20, "load": 20, "recovery": 25}
# Training load: Edwards' heart-rate-zone method (minutes × 1 to 5 by zone, half below zone 1), as fitness/fatigue
# averages that fade exponentially (Banister-style): acute over about 7 days, chronic over about 28.
ZONE_WEIGHT = [0.5, 1, 2, 3, 4, 5]
ACUTE_DAYS, CHRONIC_DAYS, RECOVERY_HOURS = 7, 28, 48
LOAD_OK, LOAD_SLOPE = 1.1, 160      # acute/chronic up to 1.1 scores 100; 1.35 → 60; 1.6 → 20
RECOVERY_SLOPE = 80                 # recovery points = 100 − 80 × (remaining effort / typical run)
CAP_ABOVE_LOWEST = 40  # the score is never more than 40 points above its weakest part
HARD_SHARE = 0.3
OVERNIGHT = {"hrv", "resting_hr", "sleep"}
PAIN_CAP = 35  # reported pain or illness: never above this  # a run with at least 30% of its time in zones 4–5 counts as hard


def label(score: int) -> str:
    return "High" if score >= 75 else "Moderate" if score >= 50 else "Low"


def current(f: dict | None, today: date) -> tuple[float | None, str | None]:
    """Today's value, or yesterday's when today's isn't in yet; with a note on which."""
    if f is None:
        return None, None
    if (f.get("observed") or {}).get("value") is not None:
        return f["observed"]["value"], None
    last = f.get("last")
    if last and last["date"] >= (today - timedelta(days=1)).isoformat():
        return last["value"], "yesterday's value"
    return None, None


def usual(f: dict, today: date) -> tuple[float | None, str]:
    """Your usual level: the personal range's median, or while that's still being learned, the median of at least 4
    earlier days of the last two weeks (marked provisional)."""
    if f.get("comparison"):
        return f["comparison"]["median"], "your usual"
    prior = [p["value"] for p in f.get("sparkline") or [] if p["date"] < today.isoformat()]
    if len(prior) >= 4:
        return median(prior), f"your last {len(prior)} days (provisional)"
    return None, ""


def recent_runs(conn, source: str, today: date, zones: dict | None) -> list[dict]:
    """Runs of the last 2 days, newest first, each with whether it was hard."""
    from .focus import zone_shares
    out = []
    for a in reversed(rp.activities(conn, source, (today - timedelta(days=2)).isoformat(), today.isoformat())):
        z = zone_shares(conn, a, zones["floors"]) if zones else None
        hard = (z["hard"] >= HARD_SHARE) if z else bool(zones and a.get("avg_hr") and a["avg_hr"] >= zones["floors"][3])
        out.append({"days_ago": (today - date.fromisoformat(a["local_date"])).days, "hard": hard, "a": a})
    return out


_load_cache: dict[tuple, float] = {}


def run_load(conn, a: dict, floors: list[float] | None) -> float:
    """Edwards training load of one run: moving minutes in each heart-rate zone times 1–5. Without usable heart rate,
    the run's minutes times 2 (a moderate guess)."""
    # Per user database (activity ids are per user) and per revision of the run's data (corrected samples recompute)
    key = (conn.name, a["id"], a.get("content_hash"), a.get("updated_at"), a.get("moving_s"), tuple(floors or ()))
    if key in _load_cache:
        return _load_cache[key]
    from .analytics import insights as ins
    from .focus import MIN_HR_COVERAGE
    mins = (a.get("moving_s") or 0) / 60
    load = 2 * mins
    s = rp.samples_for(conn, a["id"]) if floors else None
    if s is not None:
        r = ins.RunData(a["source_id"], a["local_date"], datetime.min, None, a["distance_m"], a["moving_s"], None, s, [], "steady")
        zt = ins.zone_time(r, floors)
        if sum(zt) and sum(zt) >= MIN_HR_COVERAGE * (a.get("moving_s") or 0):
            load = sum(w * t / 60 for w, t in zip(ZONE_WEIGHT, zt)) * (a["moving_s"] / sum(zt))
    _load_cache[key] = load
    return load


def moment(conn, d: date) -> datetime:
    """When readiness is judged: now for today, 8:00 local for an earlier day."""
    tz = ZoneInfo(rp.get_setting(conn, "timezone", "UTC"))
    now = datetime.now(timezone.utc)
    if d >= now.astimezone(tz).date():
        return now
    return datetime.combine(d, time(8), tz).astimezone(timezone.utc)


def training_load(conn, source: str, at: datetime, zones: dict | None) -> dict | None:
    """Acute and chronic load (exponentially fading sums per day) and the effort of recent runs not yet recovered from.
    None with fewer than 3 weeks of runs."""
    runs = [a for a in rp.activities(conn, source, (at.date() - timedelta(days=84)).isoformat(), at.date().isoformat())
            if a.get("start_utc") and a.get("moving_s")]
    ends = [(datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=a["moving_s"]), a) for a in runs]
    ends = [(e, a) for e, a in ends if e <= at]
    if len(ends) < 6 or (at - ends[0][0]).days < 21:
        return None
    floors = zones["floors"] if zones else None
    loads = [(e, run_load(conn, a, floors)) for e, a in ends]
    # Fading averages per day (a per-day rate, so acute and chronic are comparable)
    # Fading averages start from zero; divided by the share of each one's weight the history actually covers, so a short
    # history doesn't read as a spike (the slower chronic average would otherwise lag far behind)
    span = (at - ends[0][0]).total_seconds() / 86400 + 1
    acute = sum(l * exp(-(at - e).total_seconds() / 86400 / ACUTE_DAYS) for e, l in loads) / ACUTE_DAYS / (1 - exp(-span / ACUTE_DAYS))
    chronic = sum(l * exp(-(at - e).total_seconds() / 86400 / CHRONIC_DAYS) for e, l in loads) / CHRONIC_DAYS / (1 - exp(-span / CHRONIC_DAYS))
    typical = median(l for e, l in loads if (at - e).days < 28) if any((at - e).days < 28 for e, _ in loads) else median(l for _, l in loads)
    fatigue = sum(l * exp(-(at - e).total_seconds() / 3600 / RECOVERY_HOURS) for e, l in loads) / typical if typical else 0
    days = (at.date() - ends[-1][0].date()).days
    return {"ratio": acute / chronic if chronic else 1.0, "fatigue": fatigue, "acute": acute, "chronic": chronic, "typical": typical,
            "last_when": "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago" if days < 7 else None}


def build(conn, source: str, today: date, morning: dict) -> dict:
    by = {f["metric"]: f for f in morning["findings"]}
    zones = rp.hr_zones(conn)
    parts = []

    f = by.get("hrv_overnight_avg")
    v, when = current(f, today)
    base, against = usual(f, today) if v is not None else (None, "")
    if base:
        pct = 100 * (v - base) / base
        parts.append({"id": "hrv", "title": "HRV", "value": f"{round(v)} ms", "points": round(100 if pct >= -5 else clamp(100 + 4 * (pct + 5))),
                      "say": "Normal for you" if pct >= -5 else f"Lower than usual ({pct:.0f}%)",
                      "note": f"{pct:+.0f}% vs {against} {round(base)} ms" + (f" · {when}" if when else "") + "; 5% below or better scores 100"})
    else:
        parts.append({"id": "hrv", "title": "HRV", "value": f"{round(v)} ms" if v else None, "points": None, "say": "Not known yet",
                      "note": "Needs a few nights to know your usual"})

    f = by.get("resting_hr")
    v, when = current(f, today)
    base, against = usual(f, today) if v is not None else (None, "")
    if base:
        d = v - base
        parts.append({"id": "resting_hr", "title": "Resting heart rate", "value": f"{round(v)} bpm",
                      "points": round(100 if d <= 1 else clamp(100 - 12 * (d - 1))),
                      "say": "Normal for you" if d <= 1 else f"Higher than usual (+{d:.0f} bpm)",
                      "note": f"{d:+.0f} bpm vs {against} {round(base)}" + (f" · {when}" if when else "") + "; each bpm over +1 costs 12 points"})
    else:
        parts.append({"id": "resting_hr", "title": "Resting heart rate", "value": f"{round(v)} bpm" if v else None, "points": None,
                      "say": "Not known yet",
                      "note": "Needs a few days to know your usual"})

    v, when = current(by.get("sleep_duration"), today)
    if v is not None:
        h = v / 3600
        hm = f"{int(h)} h {round((h % 1) * 60):02d} min"
        parts.append({"id": "sleep", "title": "Sleep", "value": hm, "points": round(100 if h >= 7 else clamp(100 - 40 * (7 - h))),
                      "say": f"Enough ({hm})" if h >= 7 else f"Short ({hm})",
                      "note": "7 h or more scores 100; each hour short costs 40 points" + (f" · {when}" if when else "")})
    else:
        parts.append({"id": "sleep", "title": "Sleep", "value": None, "points": None, "say": "Not in yet", "note": "Not in yet"})

    at = moment(conn, today)
    tl = training_load(conn, source, at, zones)
    if tl:
        r = tl["ratio"]
        parts.append({"id": "load", "title": "Training load", "value": f"{round(100 * r)}% of usual",
                      "points": round(100 if r <= LOAD_OK else clamp(100 - LOAD_SLOPE * (r - LOAD_OK))),
                      "say": "Normal for you" if r <= LOAD_OK else f"{'Heavier' if r <= 1.4 else 'Much heavier'} than usual ({round(100 * r)}%)",
                      "note": "Last week's effort (heart-rate zones × minutes, fading over 7 days) against your usual (fading over 28 days)"})
        f = tl["fatigue"]
        when = tl["last_when"]
        parts.append({"id": "recovery", "title": "Recovery", "value": f"{round(100 * f)}% of a typical run",
                      "points": round(clamp(100 - RECOVERY_SLOPE * f)),
                      "say": ("Recovered" if f < 0.15 else "Mostly recovered" if f < 0.4 else "Still recovering" if f < 0.8
                              else "Tired from recent runs") + (f" (last run {when})" if when else ""),
                      "note": "Effort of recent runs still left after fading over about 2 days, against your typical run"})
    else:
        parts.append({"id": "load", "title": "Training load", "value": None, "points": None, "say": "Not known yet",
                      "note": "Needs 3 weeks of runs"})
        parts.append({"id": "recovery", "title": "Recovery", "value": None, "points": None, "say": "Not known yet",
                      "note": "Needs 3 weeks of runs"})

    for p in parts:
        pts = p.get("points")
        p["verdict"] = "unknown" if pts is None else "good" if pts >= 85 else "ok" if pts >= 60 else "low"
        if p["id"] == "load" and p["verdict"] == "good" and not p["say"].startswith("Normal"):
            p["verdict"] = "ok"  # "heavier than usual" never reads as good
    out = combine(parts, WEIGHTS)
    # Load and recovery both come from the running history: without any overnight reading there's no score
    if out["status"] == "ok" and not any(p.get("points") is not None for p in parts if p["id"] in OVERNIGHT):
        out = {"status": "unavailable", "components": parts, "detail": "Waiting for last night's sleep, HRV or resting heart rate."}
    if out["status"] == "ok":
        # One very low part (a big jump in running, a short night) limits the whole score
        low = min(p["points"] for p in parts if p.get("points") is not None)
        if out["score"] > low + CAP_ABOVE_LOWEST:
            out["score"], out["capped_by"] = low + CAP_ABOVE_LOWEST, next(p["id"] for p in parts if p.get("points") == low)
        out["label"] = label(out["score"])
        out["headline"] = {"High": "Ready to train", "Moderate": "Fine for an easy run", "Low": "Take it easy or rest"}[out["label"]]
        weak = [p for p in parts if p.get("points") is not None and p["points"] < 85]
        if weak:
            out["held_back_by"] = min(weak, key=lambda p: p["points"])["title"]
        if morning["recommendation"]["rule_id"] == "R0":
            # Reported pain or illness overrides every reading
            out.update(score=min(out["score"], PAIN_CAP), label="Low", headline="Take it easy or rest", held_back_by="What you reported")
    out.update(algorithm_version=READINESS_VERSION,
               basis="Calculated from your own data, not Garmin's training readiness. The weakest part caps the score at 40 points "
                     "above it. A guide, not a medical score.")
    return out


# ---------------------------------------------------------------- the next run

KIND_TITLE = {"rest": "Rest or a short walk", "easy": "Easy run", "steady": "Steady run", "long": "Long run, easy effort",
              "tempo": "Tempo run", "intervals": "Intervals", "race_pace": "Race-pace session", "race": "Race day"}


def next_day(conn, source: str, today: date) -> date:
    """Today if it's a running day without a run yet, otherwise the next running day."""
    days = rp.get_setting(conn, "running_days", [0, 2, 4, 5]) or list(range(7))
    ran_today = bool(rp.activities(conn, source, today.isoformat(), today.isoformat()))
    start = 1 if ran_today else 0
    return next(today + timedelta(days=k) for k in range(start, start + 8) if (today + timedelta(days=k)).weekday() in days)


def day_label(d: date, today: date) -> str:
    return "Today" if d == today else "Tomorrow" if d == today + timedelta(days=1) else d.strftime("%A")


def next_run(conn, source: str, today: date, morning: dict, ready: dict, race: dict | None, hold: str | None = None) -> dict | None:
    """hold: why intensity is held back today (from decide.hold_reason), or None."""
    zones = rp.hr_zones(conn)
    runs = rp.activities(conn, source, (today - timedelta(days=27)).isoformat(), today.isoformat())
    if len(runs) < 3:
        return None
    rec = morning["recommendation"]
    day = next_day(conn, source, today)
    score = ready.get("score")
    rr = recent_runs(conn, source, today, zones)
    hard_recent = any(r["hard"] for r in rr)
    from .stats import block
    hard_share = block(conn, source, today - timedelta(days=27), today, zones)["hard_share"]
    typical = median(a["distance_m"] or 0 for a in runs) / 1000
    longest = max(a["distance_m"] or 0 for a in runs) / 1000
    why = [f"Readiness {score} ({ready['label'].lower()})"] if score is not None else []

    # 1. Choose one session. Safety first, then the race week's session for that day (any kind), then the history rules.
    planned = next((s for s in (race or {}).get("week", {}).get("sessions", []) if s["date"] == day.isoformat()), None) if race else None
    if day == today and rec["rule_id"] == "R0":
        kind = "rest"
        why.append("you reported pain or illness")
    elif day == today and score is not None and score < 40:
        kind = "rest"
        why.append("readiness is very low today")
    elif planned and planned["kind"] == "race":
        kind = "race"
        why.append(f"race day: {race['label']}")
    elif day == today and hold:
        kind = "easy"
        why.append(hold)
    elif planned and planned["kind"] != "rest":
        kind = "easy" if planned["kind"] == "strides" else planned["kind"]
        why.append(f"your race week plan ({race['label']})")
    elif hard_recent:
        kind = "easy"
        why.append("your last run was hard")
    elif hard_share is not None and hard_share > HARD_SHARE:
        kind = "easy"
        why.append(f"{round(100 * hard_share)}% of your last 4 weeks was in zones 4–5; easy running builds the base")
    elif day.weekday() == max(rp.get_setting(conn, "running_days", [0, 2, 4, 5]) or [6]):
        kind = "long"
        why.append("the last running day of your week")
    else:
        kind = "steady"
        why.append("you're fresh and recent running was balanced")

    # 2. Derive distance, time and effort from that one session, so they always agree with each other
    easy_pace = None
    ins = rp.latest_body(conn, "insights")
    if ins:
        e = next((i for i in ins["insights"] if i["id"] == "easy_pace" and i["verdict"] == "pattern"), None)
        easy_pace = (e or {}).get("effect", {}).get("pace_s_per_km")
    paced = [a for a in runs if a.get("distance_m") and a.get("moving_s")]
    typical_pace = median(a["moving_s"] / (a["distance_m"] / 1000) for a in paced) if paced else None
    pace_s = easy_pace if kind in ("easy", "long") else typical_pace if kind in ("steady", "tempo", "intervals", "race_pace") else None
    km = minutes = None
    if kind == "race":
        from .race import DISTANCES
        km = round(DISTANCES[race["distance"]][1] / 1000, 1)
    elif kind != "rest" and planned and planned.get("minutes") and kind == (planned["kind"] if planned["kind"] != "strides" else "easy"):
        minutes = planned["minutes"]  # the plan's duration leads; the distance follows from it at your pace
        km = round(minutes * 60 / pace_s * 2) / 2 if pace_s else None
    elif kind != "rest":
        km = {"easy": typical * (0.7 if score is not None and score < 60 else 0.9), "steady": typical,
              "long": min(longest * 1.1, max(longest, typical * 1.3))}.get(kind, typical)
        km = max(1.0, round(km * 2) / 2)  # half-km steps; no larger floor, so "shorter" stays shorter
        minutes = round(km * pace_s / 60 / 5) * 5 if pace_s else None
    hr = None
    if zones:
        f = [round(x) for x in zones["floors"]]
        hr = {"easy": {"max": f[2], "text": f"under {f[2]} bpm (zone 2)"}, "long": {"max": f[2], "text": f"under {f[2]} bpm (zone 2)"},
              "steady": {"min": f[2], "max": f[3], "text": f"{f[2]}–{f[3]} bpm (zone 3)"},
              "tempo": {"min": f[3], "max": f[4], "text": f"{f[3]}–{f[4]} bpm (zone 4) in the middle block"},
              "intervals": {"min": f[3], "text": f"repeats above {f[3]} bpm, easy jogs between"}}.get(kind)
    pace = (f"about {rp.fmt_pace(easy_pace)} or slower" if easy_pace and kind in ("easy", "long") else
            f"around {rp.fmt_pace(race['target_pace_s_per_km'])}" if kind in ("race", "race_pace") and race and race.get("target_pace_s_per_km")
            else None)
    return {"date": day.isoformat(), "day_label": day_label(day, today), "kind": kind, "title": KIND_TITLE[kind],
            "distance_km": km, "minutes": minutes, "hr": hr, "pace": pace, "why": why, "algorithm_version": READINESS_VERSION,
            "basis": "Sized from your runs of the last 4 weeks (typical distance, longest run), Garmin's heart-rate zones and "
                     "your easy pace. Calculated, not written by AI."}

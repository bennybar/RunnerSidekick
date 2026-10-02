"""Training readiness (0–100) and the next run, both calculated, no language model. Readiness combines last night's
HRV and resting heart rate against your usual level, sleep, the last 7 days of running against the 4 weeks before, and
how hard your most recent run was. The next run turns that into a session: kind, distance, a heart-rate cap and a
pace guide, sized from your own recent runs and Garmin's zones. Garmin's own training readiness is not used."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from . import reports as rp
from .scores import clamp, combine

READINESS_VERSION = "readiness-1.0"
WEIGHTS = {"hrv": 25, "resting_hr": 20, "sleep": 25, "load": 15, "recent": 15}
CAP_ABOVE_LOWEST = 50  # the score is never more than 50 points above its weakest part
HARD_SHARE = 0.3  # a run with at least 30% of its time in zones 4–5 counts as hard


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
        parts.append({"id": "sleep", "title": "Sleep", "value": hm, "points": round(100 if h >= 7 else clamp(100 - 30 * (7 - h))),
                      "say": f"Enough ({hm})" if h >= 7 else f"Short ({hm})",
                      "note": "7 h or more scores 100; each hour short costs 30 points" + (f" · {when}" if when else "")})
    else:
        parts.append({"id": "sleep", "title": "Sleep", "value": None, "points": None, "say": "Not in yet", "note": "Not in yet"})

    f = by.get("running_moving_time_7d")
    if f and f.get("comparison", {}).get("value"):
        ratio = f["observed"]["value"] / f["comparison"]["value"]
        parts.append({"id": "load", "title": "Running this week", "value": f"{round(100 * ratio)}% of usual",
                      "points": round(100 if ratio <= 1.2 else clamp(100 - 100 * (ratio - 1.2) / 0.6)),
                      "say": "A normal amount" if ratio <= 1.2 else f"{'More' if ratio <= 1.5 else 'Much more'} than usual ({round(100 * ratio)}%)",
                      "note": "Against your weekly average of the 4 weeks before; up to 120% scores 100, 180% scores 0"})
    else:
        parts.append({"id": "load", "title": "Running this week", "value": None, "points": None, "say": "Not known yet",
                      "note": "Needs 4 weeks of runs"})

    rr = recent_runs(conn, source, today, zones)
    if rr:
        r = rr[0]
        when = ["today", "yesterday", "2 days ago"][r["days_ago"]]
        pts = (40 if r["days_ago"] == 0 else 60 if r["days_ago"] == 1 else 85) if r["hard"] else (75 if r["days_ago"] == 0 else 90 if r["days_ago"] == 1 else 100)
        say = (f"Hard, {when}: " + ("still recovering" if r["days_ago"] <= 1 else "mostly recovered")) if r["hard"] else f"Easy, {when}"
        parts.append({"id": "recent", "title": "Last run", "value": f"{'hard' if r['hard'] else 'easy'}, {when}", "points": pts, "say": say,
                      "note": "Hard means 30% or more of the time in zones 4–5; points come back over 2–3 days"})
    else:
        parts.append({"id": "recent", "title": "Last run", "value": "none in 2 days", "points": 100, "say": "None in 2 days: rested",
                      "note": "Rested legs"})

    for p in parts:
        pts = p.get("points")
        p["verdict"] = "unknown" if pts is None else "good" if pts >= 85 else "ok" if pts >= 60 else "low"
        if p["id"] == "load" and p["verdict"] == "good" and not p["say"].startswith("A normal"):
            p["verdict"] = "ok"  # "more than usual" never reads as good
    out = combine(parts, WEIGHTS)
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
    out.update(algorithm_version=READINESS_VERSION,
               basis="Calculated from your own data, not Garmin's training readiness. The weakest part caps the score at 50 points "
                     "above it. A guide, not a medical score.")
    return out


# ---------------------------------------------------------------- the next run

KIND_TITLE = {"rest": "Rest or a short walk", "easy": "Easy run", "steady": "Steady run", "long": "Long run, easy effort"}


def next_day(conn, source: str, today: date) -> date:
    """Today if it's a running day without a run yet, otherwise the next running day."""
    days = rp.get_setting(conn, "running_days", [0, 2, 4, 5]) or list(range(7))
    ran_today = bool(rp.activities(conn, source, today.isoformat(), today.isoformat()))
    start = 1 if ran_today else 0
    return next(today + timedelta(days=k) for k in range(start, start + 8) if (today + timedelta(days=k)).weekday() in days)


def day_label(d: date, today: date) -> str:
    return "Today" if d == today else "Tomorrow" if d == today + timedelta(days=1) else d.strftime("%A")


def next_run(conn, source: str, today: date, morning: dict, ready: dict, race: dict | None) -> dict | None:
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

    # The race week's session for that day, when a race goal is set
    planned = next((s for s in (race or {}).get("week", {}).get("sessions", []) if s["date"] == day.isoformat()), None) if race else None
    if day == today and score is not None and score < 40:
        kind = "rest"
        why.append("readiness is very low today")
    elif day == today and (rec["state"] == "consider_easier" or rec["suppress_intensity"] or (score is not None and score < 60)):
        kind = "easy"
        why.append("readiness is low for anything harder" if score is not None and score < 60 else
                   "today's sleep and HRV aren't in yet" if rec["rule_id"] in ("R1", "R1c") else
                   "your usual ranges are still being learned" if rec["state"] == "insufficient_data" else
                   "today's readings suggest easier" if rec["state"] == "consider_easier" else "one reading stands out today")
    elif planned and planned["kind"] in ("long", "easy"):
        kind = planned["kind"]
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

    km = {"rest": None, "easy": typical * (0.7 if score is not None and score < 60 else 0.9), "steady": typical,
          "long": min(longest * 1.1, max(longest, typical * 1.3))}[kind]
    km = max(3.0, round(km * 2) / 2) if km else None
    easy_pace = None
    ins = rp.latest_body(conn, "insights")
    if ins:
        e = next((i for i in ins["insights"] if i["id"] == "easy_pace" and i["verdict"] == "pattern"), None)
        easy_pace = (e or {}).get("effect", {}).get("pace_s_per_km")
    hr = None
    if zones and kind in ("easy", "long"):
        hr = {"max": round(zones["floors"][2]), "text": f"under {round(zones['floors'][2])} bpm (zone 2)"}
    elif zones and kind == "steady":
        hr = {"min": round(zones["floors"][2]), "max": round(zones["floors"][3]),
              "text": f"{round(zones['floors'][2])}–{round(zones['floors'][3])} bpm (zone 3)"}
    pace = f"about {rp.fmt_pace(easy_pace)} or slower" if easy_pace and kind in ("easy", "long") else None
    minutes = round(km * easy_pace / 60 / 5) * 5 if km and easy_pace and kind in ("easy", "long") else None
    if planned and planned.get("minutes") and kind == planned["kind"]:
        minutes = planned["minutes"]
    return {"date": day.isoformat(), "day_label": day_label(day, today), "kind": kind, "title": KIND_TITLE[kind],
            "distance_km": km, "minutes": minutes, "hr": hr, "pace": pace, "why": why, "algorithm_version": READINESS_VERSION,
            "basis": "Sized from your runs of the last 4 weeks (typical distance, longest run), Garmin's heart-rate zones and "
                     "your easy pace. Calculated, not written by AI."}

"""Your health, last night, as one card on Today: a plain headline, then sleep, HRV, resting heart rate, Body Battery and
stress, each with its value, a few words and a status (good, usual, watch, learning, missing) and its last 7 days.
Deterministic wording from the morning report's findings and the watch's own scores; both apps show it as is."""

from __future__ import annotations

from datetime import date, timedelta

HEALTH_VERSION = "health-1.0"

# Garmin's own bands: stress 0–25 rest, 26–50 low, 51–75 medium, 76–100 high; sleep score 90+ excellent, 80+ good,
# 60+ fair, below poor. Body Battery has no published bands; a night that charges it to 75+ is a good recharge.
STRESS_BANDS = [(25, "restful", "good"), (50, "low", "usual"), (75, "medium", "watch"), (100, "high", "watch")]
SLEEP_SCORE_BANDS = [(90, "excellent"), (80, "good"), (60, "fair"), (0, "poor")]
BATTERY_GOOD, BATTERY_LOW = 75, 50

# Which way is better when a reading leaves your usual range
BETTER_WHEN = {"sleep_duration": 1, "hrv_overnight_avg": 1, "resting_hr": -1}


def _hm(s: float) -> str:
    m = int(round(s / 60))
    return f"{m // 60} h {m % 60:02d} min"


def _spark(points: list[dict] | None, d: date) -> list[float | None]:
    """The 7 days to d (oldest first), None where there is no value."""
    by = {p["date"]: p["value"] for p in points or []}
    return [by.get((d - timedelta(days=k)).isoformat()) for k in range(6, -1, -1)]


def _series(conn, source: str, metric: str, d: date) -> list[float | None]:
    q = {"source": source, "metric": metric, "state": "measured",
         "local_date": {"$gte": (d - timedelta(days=6)).isoformat(), "$lte": d.isoformat()}}
    s = {r["local_date"]: r["value"] for r in conn.daily_observation.find(q, {"_id": 0, "local_date": 1, "value": 1})}
    return [s.get((d - timedelta(days=k)).isoformat()) for k in range(6, -1, -1)]


def _finding_status(f: dict) -> tuple[str, str | None]:
    """The row's status and a word on how it sits against your usual range."""
    st = f.get("status")
    if st == "within":
        return "usual", "as usual"
    if st in ("outside", "sustained"):
        d = (f.get("delta") or {}).get("abs") or 0
        up = d > 0
        better = (1 if up else -1) == BETTER_WHEN.get(f["metric"], 0)
        word = ("above" if up else "below") + " your usual" + (" 3 days running" if st == "sustained" else "")
        return ("good" if better else "watch"), word
    if st == "learning":
        return "learning", "learning your usual"
    if st == "not_compared":
        return "usual", "daytime value, not compared"
    return "missing", None


def build(body: dict, conn, source: str, d: date) -> dict | None:
    findings = {f["metric"]: f for f in body.get("findings", [])}
    ctx = {g["metric"]: g for g in body.get("garmin_context", [])}
    rows: list[dict] = []

    f = findings.get("sleep_duration")
    if f:
        v = (f.get("observed") or {}).get("value")
        status, word = _finding_status(f)
        score = ctx.get("garmin_sleep_score") or ctx.get("samsung_sleep_score")
        parts = []
        if score:
            band = next(b for lo, b in SLEEP_SCORE_BANDS if score["value"] >= lo)
            parts.append(f"score {round(score['value'])}, {band}")
        if v is not None and v < 7 * 3600:
            parts.append("short of 7 h")  # the 7–9 hours most adults need
        elif word and status != "usual":
            parts.append(word)
        rows.append({"id": "sleep", "title": "Sleep", "value": _hm(v) if v is not None else None, "detail": " · ".join(parts) or word,
                     "status": status, "metric": "sleep_duration", "spark": _spark(f.get("sparkline"), d)})

    for m, title, unit in (("hrv_overnight_avg", "HRV", "ms"), ("resting_hr", "Resting heart rate", "bpm")):
        f = findings.get(m)
        if not f:
            continue
        v = (f.get("observed") or {}).get("value")
        status, word = _finding_status(f)
        rows.append({"id": "hrv" if m == "hrv_overnight_avg" else "resting_hr", "title": title,
                     "value": f"{round(v)} {unit}" if v is not None else None, "detail": word, "status": status, "metric": m,
                     "spark": _spark(f.get("sparkline"), d)})

    hi, lo = ctx.get("body_battery_high"), ctx.get("body_battery_low")
    if hi:
        h = round(hi["value"])
        status, word = ("good", "well recharged") if h >= BATTERY_GOOD else ("usual", "partly recharged") if h >= BATTERY_LOW \
            else ("watch", "low recharge")
        rows.append({"id": "body_battery", "title": "Body Battery",
                     "value": f"{round(lo['value'])} → {h}" if lo else f"{h}", "detail": f"{word} (Garmin)", "status": status,
                     "metric": None, "spark": _series(conn, source, "body_battery_high", d)})

    s = ctx.get("avg_stress")
    if s:
        v = round(s["value"])
        word, status = next((w, st) for top, w, st in STRESS_BANDS if v <= top)
        rows.append({"id": "stress", "title": "Stress", "value": f"{v} avg", "detail": f"{word} (Garmin)", "status": status,
                     "metric": None, "spark": _series(conn, source, "avg_stress", d)})

    if not rows:
        return None
    return {"headline": headline(rows), "rows": rows, "version": HEALTH_VERSION}


def headline(rows: list[dict]) -> str:
    by = {r["id"]: r for r in rows}
    sleep = by.get("sleep")
    if not sleep or sleep["status"] == "missing":
        first = "Last night isn't in yet"
    elif sleep["status"] == "watch":
        first = "A short night"
    elif "short of 7 h" in (sleep["detail"] or ""):
        first = "Sleep a bit short"
    else:
        first = "Slept well"
    rec = [by[k]["status"] for k in ("hrv", "resting_hr") if k in by and by[k]["status"] not in ("missing", "learning")]
    if not rec:
        second = "recovery still being learned" if any(by.get(k, {}).get("status") == "learning" for k in ("hrv", "resting_hr")) else None
    elif "watch" in rec:
        second = "recovery signals are off" if rec.count("watch") > 1 else "one recovery signal is off"
    elif "good" in rec:
        second = "well recovered"
    else:
        second = "recovered as usual"
    return f"{first}, {second}." if second else f"{first}."

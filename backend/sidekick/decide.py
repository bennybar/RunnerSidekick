"""The day's one decision: training readiness, whether intensity is held back, and the next run. Today, the race
week, the AI coach and the AI input on runs all read this, so they can't disagree. The older recommendation rules are
only safety inputs here: reported pain or illness, and several recovery signals pointing the same way."""

from __future__ import annotations

from datetime import date

from . import race
from . import readiness as rd

HOLD_BELOW = 60  # readiness under 60: nothing harder than easy


def hold_reason(rec: dict, ready: dict) -> str | None:
    """Why intensity is held back today, or None when it isn't."""
    score = ready.get("score")
    if rec["rule_id"] == "R0":
        return "you reported pain or illness"
    if rec["state"] == "consider_easier":
        return "several recovery signals point the same way"
    if score is None:
        return "readiness isn't known yet"
    if score < HOLD_BELOW:
        return "readiness is low for anything harder"
    return None


def decide(conn, source: str, d: date, morning: dict) -> dict:
    rec = morning["recommendation"]
    ready = rd.build(conn, source, d, morning)
    reason = hold_reason(rec, ready)
    rs = race.status(conn, d)
    if rs:
        rs["week"] = race.week_plan(conn, source, d, held=reason is not None)
    nxt = rd.next_run(conn, source, d, morning, ready, rs, hold=reason)
    today_kind = nxt["kind"] if nxt and nxt["date"] == d.isoformat() else None
    return {"readiness": ready, "next_run": nxt, "race": rs, "hold_reason": reason,
            # Today's run (if any) is easy or rest, or intensity is held back: no "harder" advice anywhere
            "hold_back": reason is not None or today_kind in ("rest", "easy"), "today_kind": today_kind}

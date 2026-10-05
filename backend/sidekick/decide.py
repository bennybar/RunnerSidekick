"""The day's one decision: training readiness, whether intensity is held back, and the next run. Today, the race
week, the AI coach and the AI input on runs all read this, so they can't disagree. The older recommendation rules are
only safety inputs here: reported pain or illness, and several recovery signals pointing the same way."""

from __future__ import annotations

from datetime import date

from . import race
from . import readiness as rd

HOLD_BELOW = 60  # readiness under 60: nothing harder than easy
STEADY_BELOW = 75  # readiness under 75 (Moderate): steady at most, no tempo or intervals
REST_BELOW = 40
# What today allows, in order, and the readiness headline each one gives: the card and the next run say the same thing
ALLOWS = ("rest", "easy", "steady", "hard")
HEADLINES = {"rest": "Take it easy or rest", "easy": "Fine for an easy run", "steady": "Good for a steady run", "hard": "Ready to train"}


def allows(rec: dict, ready: dict, reason: str | None) -> str:
    score = ready.get("score")
    if rec["rule_id"] == "R0" or (score is not None and score < REST_BELOW):
        return "rest"
    if reason is not None:
        return "easy"
    return "steady" if score < STEADY_BELOW else "hard"


def hold_reason(rec: dict, ready: dict) -> str | None:
    """Why intensity is held back today, or None when it isn't."""
    score = ready.get("score")
    if rec["rule_id"] == "R0":
        return "you said you're not feeling well"
    if rec["state"] == "consider_easier":
        return "several recovery signals point the same way"
    if score is None:
        return "readiness isn't known yet"
    if score < HOLD_BELOW:
        return "readiness is low for anything harder"
    g = ready.get("garmin") or {}
    if (g.get("recovery_hours") or 0) >= rd.GARMIN_HOLD_HOURS:
        return f"Garmin's recovery timer still shows about {g['recovery_hours']} h"
    return None


def decide(conn, source: str, d: date, morning: dict) -> dict:
    rec = morning["recommendation"]
    ready = rd.build(conn, source, d, morning)
    reason = hold_reason(rec, ready)
    allowed = allows(rec, ready, reason)
    if ready.get("status") == "ok":
        ready["headline"], ready["allows"], ready["hold_reason"] = HEADLINES[allowed], allowed, reason
    rs = race.status(conn, d)
    if rs:
        rs["week"] = race.week_plan(conn, source, d, held=reason is not None)
    nxt = rd.next_run(conn, source, d, morning, ready, rs, hold=reason, allowed=allowed)
    today_kind = nxt["kind"] if nxt and nxt["date"] == d.isoformat() else None
    return {"readiness": ready, "next_run": nxt, "race": rs, "hold_reason": reason, "allows": allowed,
            # Today's run (if any) is easy or rest, or intensity is held back: no "harder" advice anywhere
            "hold_back": reason is not None or today_kind in ("rest", "easy"), "today_kind": today_kind,
            # Reported pain or illness is already applied: the app needn't apply "not feeling well" itself
            "unwell_applied": rec["rule_id"] == "R0"}

"""What changed in today's call compared with yesterday's: the state and suggestion, readings that moved in or out
of your usual range, the plan, and a check-in. Computed when the briefing is read, from stored reports, so it never
affects report revisions."""

from __future__ import annotations

from datetime import date, timedelta

from . import reports as rp

STATE_LABELS = {"usual_plan": "Usual plan", "consider_easier": "Consider easier", "insufficient_data": "Not enough data"}
OUTSIDE = ("outside", "sustained")


def label(rec: dict) -> str:
    if rec["state"] == "usual_plan" and rec.get("suppress_intensity"):
        return "Go by feel"
    return STATE_LABELS.get(rec["state"], rec["state"])


def since_yesterday(conn, today_body: dict, d: date) -> list[str]:
    prev = rp.latest_body(conn, "morning", {"subject_key": (d - timedelta(days=1)).isoformat()})
    if prev is None:
        return []
    out = []
    a, b = label(prev["recommendation"]), label(today_body["recommendation"])
    if a != b:
        out.append(f"The call is now {b} (yesterday: {a}).")
    old = {f["metric"]: f for f in prev.get("findings", [])}
    for f in today_body.get("findings", []):
        o = old.get(f["metric"])
        if not o or f["metric"] not in rp.CORE_METRICS:
            continue
        if f["status"] in OUTSIDE and o["status"] not in OUTSIDE:
            out.append(f"{f['title']} moved outside your usual range.")
        elif o["status"] in OUTSIDE and f["status"] == "within":
            out.append(f"{f['title']} is back within your usual range.")
    pa, pb = (prev["recommendation"].get("plan") or {}).get("kind"), (today_body["recommendation"].get("plan") or {}).get("kind")
    if pb and pb != pa:
        out.append(f"Today's plan is set: {pb}.")
    if today_body.get("checkin") and not prev.get("checkin"):
        out.append("Your check-in is included.")
    return out

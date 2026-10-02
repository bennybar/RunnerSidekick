"""What changed since yesterday: training readiness (when it moved by 5 or more), readings that moved in or out of
your usual range, the plan, and a check-in. Computed when the briefing is read, from stored reports, so it never
affects report revisions."""

from __future__ import annotations

from datetime import date, timedelta

from . import reports as rp

OUTSIDE = ("outside", "sustained")
READINESS_STEP = 5


def since_yesterday(conn, today_body: dict, d: date, source: str | None = None) -> list[str]:
    prev = rp.latest_body(conn, "morning", {"subject_key": (d - timedelta(days=1)).isoformat()})
    if prev is None:
        return []
    out = []
    now = (today_body.get("readiness") or {}).get("score")
    if source and now is not None:
        from . import readiness
        before = readiness.build(conn, source, d - timedelta(days=1), prev).get("score")
        if before is not None and abs(now - before) >= READINESS_STEP:
            out.append(f"Readiness {'up' if now > before else 'down'} to {now} (yesterday {before}).")
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

"""Today as the app shows it: the morning report plus the day's decision (readiness, next run, race week), scores,
changes since yesterday, what stands out and reading notes. One place, used by the API and by the history replay, so the
replay checks exactly what the app would have said."""

from __future__ import annotations

from datetime import date


def enrich(conn, source: str, d: date, body: dict) -> dict:
    """Adds the live parts of Today to a morning report body (in place) and returns it."""
    from . import changes, compare, highlights, readings, scores
    from . import focus as fc
    from .decide import decide
    dec = decide(conn, source, d, body)
    body["race"], body["readiness"], body["next_run"] = dec["race"], dec["readiness"], dec["next_run"]
    body["decision"] = {"hold_back": dec["hold_back"], "hold_reason": dec["hold_reason"], "today_kind": dec["today_kind"],
                        "unwell_applied": dec["unwell_applied"]}
    body["scores"] = scores.build(conn, source, d, hold_back=dec["hold_back"])
    body["changes"] = changes.since_yesterday(conn, body, d, source)
    cmp = compare.build(conn, source, d)
    body["highlights"] = highlights.build(conn, source, d, cmp, fc.current(conn, source, d), body["race"])
    body["reading_notes"] = readings.notes(body["findings"], cmp)
    return body

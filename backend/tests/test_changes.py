from datetime import date, timedelta

from helpers import add_checkin, set_plan
from sidekick import changes
from sidekick import reports as rp
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


def test_changes_since_yesterday():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    rp.build_morning(conn, "fixture", ANCHOR - timedelta(days=1), True)
    set_plan(conn, ANCHOR.isoformat(), "easy", 40)
    add_checkin(conn, "c", ANCHOR.isoformat(), energy=2, pain=True)
    today = rp.build_morning(conn, "fixture", ANCHOR, True)
    ch = changes.since_yesterday(conn, today, ANCHOR)
    assert "Your check-in is included." in ch and "Today's plan is set: easy." in ch
    assert not any(c.startswith("The call is now") for c in ch)  # the old day's-call label is no longer shown
    assert changes.since_yesterday(conn, today, ANCHOR - timedelta(days=60)) == []  # no earlier briefing

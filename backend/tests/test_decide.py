from datetime import date

from helpers import add_checkin
from sidekick import coach as ch
from sidekick import reports as rp
from sidekick import run_ai
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, user_db_name
from sidekick.decide import decide
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


def test_one_decision_reaches_today_the_coach_and_run_ai():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    rp.regenerate(conn, "fixture", True, set(), [], ANCHOR)
    add_checkin(conn, "p", ANCHOR.isoformat(), pain=True)  # pain: rest, intensity held back everywhere
    m = rp.build_morning(conn, "fixture", ANCHOR, False)
    d = decide(conn, "fixture", ANCHOR, m)
    assert d["hold_back"] and d["hold_reason"] == "you reported pain or illness"
    assert d["readiness"]["status"] != "ok" or d["readiness"]["score"] <= 35
    coach_today = ch.build_bundle(conn, "fixture", ANCHOR).items["plan:today"]
    assert coach_today["intensity_held_back"] is True and coach_today["held_back_because"] == d["hold_reason"]
    sid = rp.activities(conn, "fixture", "2026-09-01", ANCHOR.isoformat())[-1]["source_id"]
    rp.build_post_run(conn, "fixture", sid, True)
    assert run_ai.bundle(conn, "fixture", sid, ANCHOR).items["today:advice"]["intensity_held_back"] is True

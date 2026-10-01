from datetime import date

from sidekick import focus as fc
from sidekick import reports as rp
from sidekick import weekly
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, first_weekday, set_setting, user_db_name, week_start
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)  # a Wednesday


def synced():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 60, 3, max_backfill_days=90)
    return conn


def test_week_start_precedence_and_arithmetic():
    conn = connect(user_db_name(1, "fixture"))
    assert first_weekday(conn) == 0  # nothing known: Monday
    set_setting(conn, "source_profile", {"first_day_of_week": "sunday"})
    assert first_weekday(conn) == 6  # Garmin's choice
    set_setting(conn, "week_start_day", "saturday")
    assert first_weekday(conn) == 5  # the runner's setting wins
    assert week_start(ANCHOR, 0) == date(2026, 9, 28) and week_start(ANCHOR, 6) == date(2026, 9, 27)
    assert week_start(date(2026, 9, 27), 6) == date(2026, 9, 27)


def test_weeks_follow_the_setting_and_history_is_kept():
    conn = synced()
    weekly.regenerate_weeklies(conn, "fixture", ANCHOR, True)
    monday_reviews = set(conn.report.distinct("subject_key", {"type": "weekly"}))
    assert all(date.fromisoformat(k).weekday() == 0 for k in monday_reviews)
    set_setting(conn, "week_start_day", "sunday")
    assert fc.current(conn, "fixture", ANCHOR)["week_start"] == "2026-09-27"  # this week's focus is for the new week
    w = weekly.build_weekly(conn, "fixture", date(2026, 9, 20), True)
    assert (w["week_start"], w["week_end"]) == ("2026-09-20", "2026-09-26")
    conn.report.delete_many({"type": "weekly", "subject_key": "2026-09-20"})
    weekly.regenerate_weeklies(conn, "fixture", ANCHOR, True)
    keys = set(conn.report.distinct("subject_key", {"type": "weekly"}))
    assert monday_reviews <= keys  # old reviews kept as they were
    assert not any(date.fromisoformat(k).weekday() == 6 for k in keys)  # every Sunday week overlaps a reviewed one
    r = rp.build_post_run(conn, "fixture", "fx-run-2026-09-28", True)
    assert r["calendar_week"]["start"] == "2026-09-27"  # the run's "this week" uses the new boundaries

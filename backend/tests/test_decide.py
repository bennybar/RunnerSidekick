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


def test_next_run_numbers_agree_and_follow_the_race_plan():
    from datetime import timedelta
    from sidekick import race
    from sidekick.db import set_setting
    from sidekick.readiness import next_day
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    rp.regenerate(conn, "fixture", True, set(), [], ANCHOR)
    for days_out in (60, 20, 10):  # build, sharpen and taper weeks: easy, long and quality sessions
        set_setting(conn, "race_date", (ANCHOR + timedelta(days=days_out)).isoformat())
        set_setting(conn, "race_distance", "10k")
        n = decide(conn, "fixture", ANCHOR, rp.build_morning(conn, "fixture", ANCHOR, False))["next_run"]
        if n["distance_km"] and n["minutes"]:
            pace = n["minutes"] * 60 / n["distance_km"]
            assert 180 <= pace <= 540, (days_out, n)  # 3:00–9:00 /km: distance and time describe the same run
    set_setting(conn, "race_date", next_day(conn, "fixture", ANCHOR).isoformat())  # race on the next running day
    n = decide(conn, "fixture", ANCHOR, rp.build_morning(conn, "fixture", ANCHOR, False))["next_run"]
    assert n["kind"] == "race" and n["distance_km"] == 10.0 and race.status(conn, ANCHOR)["phase"] == "race_week"


def test_rest_days_stay_rest_and_an_off_schedule_race_comes_first():
    from datetime import timedelta
    from sidekick.db import set_setting
    from sidekick.readiness import next_day
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    rp.regenerate(conn, "fixture", True, set(), [], ANCHOR)
    set_setting(conn, "race_distance", "10k")
    # A race on a day you don't usually run (Sunday with Mon/Wed/Fri/Sat running days), before the next running day
    set_setting(conn, "running_days", [0])  # Mondays only: the next running day is after Sunday
    sunday = next(ANCHOR + timedelta(days=k) for k in range(1, 8) if (ANCHOR + timedelta(days=k)).weekday() == 6)
    assert sunday < next_day(conn, "fixture", ANCHOR)
    set_setting(conn, "race_date", sunday.isoformat())
    n = decide(conn, "fixture", ANCHOR, rp.build_morning(conn, "fixture", ANCHOR, False))["next_run"]
    assert n["kind"] == "race" and n["date"] == sunday.isoformat() and n["distance_km"] == 10.0
    set_setting(conn, "running_days", [0, 2, 4, 5])
    # Whatever the week plan marks as rest is never offered as the next run
    for days_out in (8, 20, 45):
        set_setting(conn, "race_date", (ANCHOR + timedelta(days=days_out)).isoformat())
        d = decide(conn, "fixture", ANCHOR, rp.build_morning(conn, "fixture", ANCHOR, False))
        rest_days = {s["date"] for s in d["race"]["week"]["sessions"] if s["kind"] == "rest"}
        assert d["next_run"]["date"] not in rest_days or d["next_run"]["kind"] == "rest"

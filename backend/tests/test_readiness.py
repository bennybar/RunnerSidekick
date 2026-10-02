from datetime import date, timedelta

from sidekick import readiness as rd

TODAY = date(2026, 10, 2)


def f(metric, value, median=None, spark=None):
    return {"metric": metric, "observed": {"value": value}, "comparison": {"median": median} if median else None,
            "sparkline": spark or [], "status": "within" if median else "learning"}


def test_usual_falls_back_to_recent_days_while_range_is_learned():
    spark = [{"date": f"2026-09-{d}", "value": v} for d, v in (("27", 40), ("28", 44), ("29", 42), ("30", 46))]
    assert rd.usual(f("hrv_overnight_avg", 30, spark=spark), TODAY) == (43.0, "your last 4 days (provisional)")
    assert rd.usual(f("hrv_overnight_avg", 30, spark=spark[:3]), TODAY)[0] is None
    assert rd.usual(f("resting_hr", 50, median=48), TODAY) == (48, "your usual")


def test_missing_today_uses_yesterday_only():
    m = {"observed": None, "last": {"date": "2026-10-01", "value": 7}}
    assert rd.current(m, TODAY) == (7, "yesterday's value")
    assert rd.current({"observed": None, "last": {"date": "2026-09-29", "value": 7}}, TODAY) == (None, None)


def test_labels():
    assert [rd.label(x) for x in (90, 75, 60, 49)] == ["High", "High", "Moderate", "Low"]


def test_training_load_fades_and_counts_recent_effort():
    from datetime import datetime, timezone
    from sidekick.connectors.fixture import FixtureConnector
    from sidekick.db import connect, user_db_name
    from sidekick.sync import run_sync
    from sidekick import reports as rp
    anchor = date(2026, 9, 30)
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(anchor), anchor, 45, 3, max_backfill_days=60)
    zones = rp.hr_zones(conn)
    last = rp.activities(conn, "fixture", "2026-01-01", anchor.isoformat())[-1]
    end = datetime.fromisoformat(last["start_utc"].replace("Z", "+00:00"))
    soon = rd.training_load(conn, "fixture", end + timedelta(hours=14), zones)
    later = rd.training_load(conn, "fixture", end + timedelta(hours=62), zones)
    assert soon and later and soon["fatigue"] > later["fatigue"] > 0  # recent effort fades over days
    assert soon["ratio"] > later["ratio"] and soon["typical"] > 0

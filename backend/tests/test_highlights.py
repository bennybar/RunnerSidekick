from datetime import date

from sidekick import compare, highlights
from sidekick import focus as fc
from sidekick import reports as rp
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, get_setting, set_setting, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


def synced():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    rp.regenerate(conn, "fixture", True, set(), [], ANCHOR)
    return conn


def build(conn):
    return highlights.build(conn, "fixture", ANCHOR, compare.build(conn, "fixture", ANCHOR), fc.current(conn, "fixture", ANCHOR))


def test_attention_first_bounded_and_linked():
    conn = synced()
    g = get_setting(conn, "garmin_fitness", {})
    g["training_status"].update(phrase="OVERREACHING_3", acute_load=600, chronic_max=520)
    set_setting(conn, "garmin_fitness", g)
    h = build(conn)
    assert 1 <= len(h) <= highlights.MAX_ITEMS
    assert h[0]["tone"] == "attention" and {"training_status", "load"} <= {x["id"] for x in h}
    tones = [highlights.TONE_ORDER[x["tone"]] for x in h]
    assert tones == sorted(tones) and all(x["target"]["type"] for x in h)


def test_quiet_day_shows_only_positive_or_nothing_alarming():
    conn = synced()
    h = build(conn)  # fixture: productive status, load inside the range
    assert all(x["tone"] != "attention" or x["id"] in ("vo2_change", "focus") for x in h)
    assert any(x["id"] == "training_status" and x["tone"] == "positive" for x in h)


def test_vo2_change_never_crosses_a_watch_change():
    conn = synced()
    conn.activity.update_many({"local_date": {"$lt": "2026-09-20"}}, {"$set": {"device_id": "old-watch"}})
    for d, v in (("2026-08-20", 60.0), ("2026-09-29", 49.0)):
        conn.daily_observation.update_one({"source": "fixture", "metric": "garmin_vo2max_running", "local_date": d},
                                          {"$set": {"value": v, "state": "measured", "unit": "ml/kg/min"}}, upsert=True)
    assert "vo2_change" not in {x["id"] for x in build(conn)}
    conn.activity.update_many({}, {"$set": {"device_id": "same-watch"}})
    assert "vo2_change" in {x["id"] for x in build(conn)}  # same watch throughout: the drop is shown

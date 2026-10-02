from datetime import date

from sidekick import scores
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


def synced():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 60, 3, max_backfill_days=90)
    return conn


def test_scores_are_bounded_fixed_weight_explained_and_trended():
    s = scores.build(synced(), "fixture", ANCHOR)
    assert s["status"] == "ok"
    for k, weights in (("fitness", scores.FITNESS_WEIGHTS), ("health", scores.HEALTH_WEIGHTS)):
        x = s[k]
        assert x["status"] in ("ok", "partial") and 0 <= x["score"] <= 100 and x["label"]
        counted = [c for c in x["components"] if not c.get("context")]
        assert [c["id"] for c in counted] == list(weights)  # fixed parts, in a fixed order
        assert sum(c["weight_pct"] for c in counted if c["points"] is not None) in (99, 100, 101)
        assert all(c["say"] and c["note"] for c in x["components"])
        if x["status"] == "partial":
            assert x["missing"] == [c["title"] for c in counted if c["points"] is None]
    ids = {c["id"] for k in ("fitness", "health") for c in s[k]["components"] if not c.get("context")}
    assert not ids & {"fitness_age", "hrv", "resting_hr", "age_grade", "regularity"}  # context only, never counted


def test_activity_follows_the_who_guideline():
    conn = synced()
    h = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["health"]["components"]}
    assert h["activity"]["points"] is not None and "WHO: 150–300" in h["activity"]["say"]
    conn.daily_observation.update_many({"metric": "intensity_minutes_vigorous"}, {"$set": {"value": 25.0}})
    h = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["health"]["components"]}
    assert h["activity"]["points"] == 100


def test_short_nights_count_and_long_nights_dont_hurt():
    conn = synced()
    days = sorted(conn.daily_observation.distinct("local_date", {"metric": "sleep_duration", "local_date": {"$lte": ANCHOR.isoformat()}}))[-14:]
    for i, d in enumerate(days):  # six 4-hour nights among eight 8-hour ones: the median alone would hide them
        conn.daily_observation.update_one({"metric": "sleep_duration", "local_date": d},
                                          {"$set": {"value": (4 if i < 6 else 8) * 3600.0, "state": "measured"}})
    sl = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["health"]["components"]}["sleep_length"]
    assert sl["points"] < 60 and "6 of 14 nights under 7 h" in sl["say"]
    conn.daily_observation.update_many({"metric": "sleep_duration", "local_date": {"$in": days}}, {"$set": {"value": 10 * 3600.0}})
    sl = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["health"]["components"]}["sleep_length"]
    assert sl["points"] == 100


def test_vo2_outside_the_table_is_not_given_an_invented_percentile():
    conn = synced()
    from sidekick.db import set_setting
    conn.daily_observation.update_many({"metric": "garmin_vo2max_running"}, {"$set": {"value": 30.0}})
    set_setting(conn, "garmin_fitness", {"vo2max": {"value": 30.0, "date": ANCHOR.isoformat()}})
    v = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["fitness"]["components"]}["vo2max"]
    assert "below the 40th percentile" in v["say"] and "better than" not in v["say"]


def test_consistency_counts_only_weeks_with_history():
    conn = synced()
    first = scores.history_start(conn, "fixture")
    f = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["fitness"]["components"]}["regularity"]
    assert f.get("context") and ("of the last" in f["say"] or "Needs" in f["say"]) and first


def test_vo2_points_follow_the_percentile_and_extend_beyond_the_table():
    assert round(scores.vo2_points("male", 43, 46.2)) == 79  # Good for men 40-49, between the 60th and 80th
    assert scores.vo2_points("male", 43, 70) == 100 and scores.vo2_points("male", 43, 20) == 0
    assert scores.vo2_points("male", 43, 52.5) == 95


def test_missing_profile_or_too_few_components_is_unavailable():
    conn = connect(user_db_name(1, "fixture"))
    empty = scores.build(conn, "fixture", ANCHOR)  # no data and no profile: neither score is shown
    assert empty["fitness"]["status"] == "unavailable" and empty["health"]["status"] == "unavailable"
    h = scores.score([{"id": "sleep_length", "title": "Sleep length", "points": 100}, {"id": "activity", "title": "Weekly activity", "points": None},
                      {"id": "steps", "title": "Daily steps", "points": None}], scores.HEALTH_WEIGHTS, scores.HEALTH_REQUIRED)
    assert h["status"] == "unavailable"  # sleep alone can't make a Health score


def test_improvement_steps_are_calculated_ranked_and_capped():
    s = scores.build(synced(), "fixture", ANCHOR)
    for k in ("fitness", "health"):
        steps = s[k]["improve"]
        assert len(steps) <= scores.IMPROVE_SHOWN and all(x["gain"] >= 1 and x["text"] for x in steps)
        assert [x["gain"] for x in steps] == sorted((x["gain"] for x in steps), reverse=True)
        parts = {c["title"]: c for c in s[k]["components"]}
        for x in steps:  # each step belongs to a part that isn't at full points yet
            assert parts[x["part"]]["points"] < 100


def test_missing_awake_time_is_unknown_not_perfect():
    conn = synced()
    conn.sleep_session.update_many({}, {"$set": {"awake_s": None}})
    se = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["health"]["components"]}["sleep_efficiency"]
    assert se["points"] is None and se.get("context")


def test_a_birthday_is_not_a_fitness_trend():
    from datetime import timedelta
    from sidekick.db import set_setting
    conn = synced()
    # Turning 50 between the two readings, with VO2 max unchanged: the trend must stay flat
    set_setting(conn, "profile_sex", "male")
    set_setting(conn, "profile_birth_date", (ANCHOR - timedelta(days=50 * 365 + 13)).isoformat())
    conn.daily_observation.update_many({"metric": "garmin_vo2max_running"}, {"$set": {"value": 42.4}})
    f = scores.build(conn, "fixture", ANCHOR)["fitness"]
    assert f.get("trend", {}).get("delta", 0) == 0


def test_old_vo2_is_marked_stale_then_dropped():
    from datetime import timedelta
    from sidekick.db import set_setting
    conn = synced()
    conn.daily_observation.delete_many({"metric": "garmin_vo2max_running"})
    set_setting(conn, "garmin_fitness", {"vo2max": {"value": 46.0, "date": (ANCHOR - timedelta(days=45)).isoformat()}})
    f = scores.build(conn, "fixture", ANCHOR)["fitness"]
    assert f["status"] == "ok" and f.get("stale") is True and "45 days ago" in f["components"][0]["say"]
    set_setting(conn, "garmin_fitness", {"vo2max": {"value": 46.0, "date": (ANCHOR - timedelta(days=120)).isoformat()}})
    assert scores.build(conn, "fixture", ANCHOR)["fitness"]["status"] == "unavailable"


def test_newest_vo2_wins_and_movement_skips_the_unfinished_day():
    from datetime import timedelta
    from sidekick.db import set_setting
    conn = synced()
    conn.daily_observation.delete_many({"metric": "garmin_vo2max_running"})
    conn.daily_observation.insert_one({"source": "fixture", "local_date": (ANCHOR - timedelta(days=60)).isoformat(),
                                       "metric": "garmin_vo2max_running", "value": 40.0, "state": "measured"})
    set_setting(conn, "garmin_fitness", {"vo2max": {"value": 48.0, "date": ANCHOR.isoformat()}})
    assert scores.vo2_on(conn, "fixture", ANCHOR, ANCHOR) == (48.0, ANCHOR)
    before = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["health"]["components"]}["steps"]["points"]
    conn.daily_observation.update_one({"metric": "steps", "local_date": ANCHOR.isoformat()}, {"$set": {"value": 0.0, "state": "measured"}},
                                      upsert=True)
    after = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["health"]["components"]}["steps"]["points"]
    assert before == after  # a near-empty today doesn't pull the average down


def test_carried_forward_vo2_is_stored_on_its_measurement_day():
    from sidekick.connectors.garmin import normalise_max_metrics
    obs = normalise_max_metrics("2026-10-02", [{"generic": {"vo2MaxPreciseValue": 46.2, "calendarDate": "2026-08-03"}}])
    assert [(o.local_date, o.value) for o in obs] == [("2026-08-03", 46.2), ("2026-10-02", None)]
    same = normalise_max_metrics("2026-10-02", [{"generic": {"vo2MaxPreciseValue": 46.2, "calendarDate": "2026-10-02"}}])
    assert [(o.local_date, o.value) for o in same] == [("2026-10-02", 46.2)]

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
        assert [c["id"] for c in x["components"]] == list(weights)  # fixed parts, in a fixed order
        used = [c for c in x["components"] if c["points"] is not None]
        assert sum(c["weight_pct"] for c in used) in (99, 100, 101)
        assert all(c["say"] and c["note"] and c["verdict"] in ("good", "ok", "low", "unknown") for c in x["components"])
        if x["status"] == "partial":
            assert x["missing"] == [c["title"] for c in x["components"] if c["points"] is None]
    # Nothing is counted twice: no fitness age, no HRV
    ids = {c["id"] for k in ("fitness", "health") for c in s[k]["components"]}
    assert not ids & {"fitness_age", "hrv"}
    assert "trend" not in s["fitness"] or isinstance(s["fitness"]["trend"]["delta"], int)


def test_activity_follows_the_who_guideline():
    conn = synced()
    h = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["health"]["components"]}
    assert h["activity"]["points"] is not None and "WHO: 150–300" in h["activity"]["say"]
    # 300+ moderate-equivalent minutes a week is the top of the guideline: full points
    conn.daily_observation.update_many({"metric": "intensity_minutes_vigorous"}, {"$set": {"value": 25.0}})
    h = {c["id"]: c for c in scores.build(conn, "fixture", ANCHOR)["health"]["components"]}
    assert h["activity"]["points"] == 100


def test_vo2_points_follow_the_percentile_and_extend_beyond_the_table():
    assert round(scores.vo2_points("male", 43, 46.2)) == 79  # Good for men 40-49, between the 60th and 80th
    assert scores.vo2_points("male", 43, 70) == 100 and scores.vo2_points("male", 43, 20) == 0
    assert scores.vo2_points("male", 43, 52.5) == 95


def test_missing_profile_or_too_few_components_is_unavailable():
    conn = connect(user_db_name(1, "fixture"))
    assert scores.build(conn, "fixture", ANCHOR)["status"] == "unavailable"
    parts = [{"id": "vo2max", "points": 80}, {"id": "age_grade", "points": None}, {"id": "regularity", "points": None}]
    assert scores.combine(parts, scores.FITNESS_WEIGHTS)["status"] == "unavailable"

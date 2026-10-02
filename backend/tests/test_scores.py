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


def test_scores_are_bounded_weighted_and_explained():
    s = scores.build(synced(), "fixture", ANCHOR)
    for k in ("fitness", "health"):
        x = s[k]
        assert x["status"] == "ok" and 0 <= x["score"] <= 100 and x["label"]
        used = [c for c in x["components"] if c["points"] is not None]
        assert sum(c["weight_pct"] for c in used) in (99, 100, 101)
        assert all(c["note"] for c in x["components"])


def test_vo2_points_follow_the_percentile_and_extend_beyond_the_table():
    assert round(scores.vo2_points("male", 43, 46.2)) == 79  # Good for men 40-49, between the 60th and 80th
    assert scores.vo2_points("male", 43, 70) == 100 and scores.vo2_points("male", 43, 20) == 0
    assert scores.vo2_points("male", 43, 52.5) == 95


def test_missing_profile_or_too_few_components_is_unavailable():
    conn = connect(user_db_name(1, "fixture"))
    assert scores.build(conn, "fixture", ANCHOR)["status"] == "unavailable"
    parts = [{"id": "vo2max", "points": 80}, {"id": "age_grade", "points": None}, {"id": "consistency", "points": None}]
    assert scores.combine(parts, scores.FITNESS_WEIGHTS)["status"] == "unavailable"

from datetime import date

from fastapi.testclient import TestClient

from sidekick import compare
from sidekick.analytics import norms as nm
from sidekick.api import create_app
from sidekick.auth import create_token
from sidekick.config import Config
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, set_setting, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


def synced():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    return conn


def test_percentiles_interpolate_and_never_extrapolate():
    pts, pcts = nm.VO2["male"][2], nm.VO2_PERCENTILES  # men 40–49: 38.5, 42.4, 46.4, 52.5
    assert nm.percentile_of(46.2, pts, pcts) == (60 + (46.2 - 42.4) / (46.4 - 42.4) * 20, "within")
    assert nm.percentile_of(30.0, pts, pcts) == (None, "below")
    assert nm.percentile_of(60.0, pts, pcts) == (None, "above")


def test_age_grade_against_published_standard():
    std = nm.age_standards()["standards"]["male"]["5k"]
    assert std["30"] == 769.0  # open-class 5 km standard, 12:49
    ag = compare.age_grade("male", 30, "5k", 1000)
    assert ag["age_grade_pct"] == 76.9 and ag["class"] == "regional class"
    older = compare.age_grade("male", 60, "5k", 1000)
    assert older["age_grade_pct"] > ag["age_grade_pct"] and older["age_graded_time_s"] < 1000


def test_profile_from_garmin_with_override_and_items():
    conn = synced()
    out = compare.build(conn, "fixture", ANCHOR)
    assert out["profile"]["sex"] == "male" and out["profile"]["age"] == 43 and not out["missing"]
    items = {i["id"]: i for i in out["items"]}
    v = items["vo2max"]
    assert v["rating"] == "Excellent" and v["percentile"] == round(80 + (49.0 - 46.4) / (52.5 - 46.4) * 15)
    assert items["fitness_age"]["fitness_age"] == 40.4 and "younger" in items["fitness_age"]["headline"]
    assert items["resting_hr"]["status"] == "ok" and items["resting_hr"]["caveats"]
    h = items["hrv"]
    assert h["status"] == "ok" and h["chart"]["band"] and h["chart"]["points"]  # own range, not a population norm
    assert any(w in h["headline"] for w in ("within", "below", "above"))
    assert any(r["kind"] == "prediction" for r in items["age_grade"]["rows"])
    set_setting(conn, "profile_sex", "female")
    assert compare.build(conn, "fixture", ANCHOR)["profile"]["source"] == "settings"


def test_missing_profile_asks_for_it_instead_of_guessing():
    conn = connect(user_db_name(1, "fixture"))
    out = compare.build(conn, "fixture", ANCHOR)
    assert out["missing"] == ["sex", "birth date"] and out["items"] == []


def test_compare_endpoint_and_clearing_override(tmp_path):
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    client = TestClient(create_app(c, connector=FixtureConnector(ANCHOR)))
    client.app.state.do_sync(c.__class__(**{**c.__dict__, "user_id": 1}), 1)
    assert client.get("/v1/compare", headers=h).json()["profile"]["sex"] == "male"
    client.put("/v1/settings", json={"profile_birth_date": "1990-01-01"}, headers=h)
    assert client.get("/v1/settings", headers=h).json()["profile_birth_date"] == "1990-01-01"
    client.put("/v1/settings", json={"profile_birth_date": None}, headers=h)
    assert client.get("/v1/settings", headers=h).json()["profile_birth_date"] is None


def test_hrv_range_restarts_after_a_watch_change():
    conn = synced()
    conn.activity.update_many({"local_date": {"$lt": "2026-09-25"}}, {"$set": {"device_id": "old-watch"}})
    conn.activity.update_many({"local_date": {"$gte": "2026-09-25"}}, {"$set": {"device_id": "new-watch"}})
    h = compare.hrv_item(conn, "fixture", ANCHOR)
    assert "learning" in h["headline"]  # only a few nights on the new watch
    assert any(p["new_watch"] for p in h["chart"]["points"])

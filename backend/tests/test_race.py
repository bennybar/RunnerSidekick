from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from sidekick import focus as fc
from sidekick import highlights, race
from sidekick.api import create_app
from sidekick.auth import create_token
from sidekick.config import Config
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, set_setting, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


@pytest.mark.parametrize("dist,days,expected", [
    ("half", 100, "base"), ("half", 60, "build"), ("half", 30, "sharpen"), ("half", 12, "taper"), ("half", 5, "race_week"),
    ("half", 0, "race_week"), ("half", -5, "recovery"), ("half", -30, None),
    ("marathon", 20, "taper"), ("5k", 10, "sharpen"), ("5k", 6, "race_week"),
])
def test_phases_by_weeks_to_go(dist, days, expected):
    assert race.phase(dist, days) == expected


def synced():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    return conn


def set_race(conn, days, dist="half", target=6000, name="City Half"):
    set_setting(conn, "race_date", (ANCHOR + timedelta(days=days)).isoformat())
    set_setting(conn, "race_distance", dist)
    set_setting(conn, "race_target_s", target)
    set_setting(conn, "race_name", name)


def test_status_compares_garmin_prediction_with_target():
    conn = synced()
    set_race(conn, 12)
    s = race.status(conn, ANCHOR)
    assert s["phase"] == "taper" and s["days_to_go"] == 12 and s["headline"] == "City Half in 12 days"
    assert s["garmin_prediction_s"] == 6700 and s["prediction_vs_target_s"] == 700  # fixture predicts 1:51:40
    assert "slower than your target of 1:40:00" in s["prediction_text"]
    assert s["target_pace_s_per_km"] == round(6000 / 21.0975, 1)


def test_race_leads_highlights_and_sets_focus_priorities():
    conn = synced()
    set_race(conn, 12)
    s = race.status(conn, ANCHOR)
    h = highlights.build(conn, "fixture", ANCHOR, None, None, s)
    assert h[0]["id"] == "race" and "Taper" in h[0]["title"] and len(h) <= highlights.MAX_ITEMS
    assert fc.options(conn, "fixture", ANCHOR)[0]["kind"] == "recovery"  # taper: recovery first
    set_race(conn, 100)
    assert fc.options(conn, "fixture", ANCHOR)[0]["kind"] == "easy_runs"  # base: easy running first


def test_finished_race_drops_out():
    conn = synced()
    set_race(conn, -40)
    assert race.status(conn, ANCHOR) is None


def test_race_settings_round_trip_and_clear(tmp_path):
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    client = TestClient(create_app(c, connector=FixtureConnector(ANCHOR)))
    client.put("/v1/settings", json={"race_date": "2026-11-20", "race_distance": "half", "race_target_s": 6000, "race_name": "City Half"}, headers=h)
    s = client.get("/v1/settings", headers=h).json()
    assert (s["race_date"], s["race_distance"], s["race_target_s"]) == ("2026-11-20", "half", 6000)
    client.put("/v1/settings", json={"race_date": None, "race_distance": None, "race_target_s": None, "race_name": None}, headers=h)
    assert client.get("/v1/settings", headers=h).json()["race_date"] is None
    assert client.put("/v1/settings", json={"race_distance": "ultra"}, headers=h).status_code == 422

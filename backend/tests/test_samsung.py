import time
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from sidekick import samsung
from sidekick.api import create_app
from sidekick.auth import create_token
from sidekick.config import Config
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, set_setting, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


def ms(day: date, h: int, m: int = 0, s: int = 0, offset_h: int = 3) -> int:
    """Epoch ms of a local time (UTC+3 by default)."""
    return int((datetime(day.year, day.month, day.day, h, m, s, tzinfo=timezone.utc) - timedelta(hours=offset_h)).timestamp() * 1000)


def run(day: date, uid: str = "r1", h: int = 7, seconds: int = 600, speed: float = 3.0) -> dict:
    """A run as the phone sends it: heart rate and speed/cadence in separate log entries, a route north at `speed`."""
    t0 = ms(day, h)
    log, route = [], []
    for s in range(seconds):
        log.append([t0 + s * 1000, 140 + s % 5, None, None, None])
        log.append([t0 + s * 1000 + 500, None, speed, 164, None])
        route.append([t0 + s * 1000, 32.0 + s * speed / 110_540, 34.8, 20 + s * 0.01])
    return {"uid": uid, "type": "RUNNING", "title": None, "start": t0, "end": t0 + seconds * 1000, "offset_s": 3 * 3600,
            "device": "watch-1", "duration_s": seconds, "distance_m": seconds * speed, "climb_m": 6, "avg_hr": 142,
            "max_hr": 150, "avg_cadence": 164, "log": log, "route": route}


def test_a_run_becomes_one_second_samples_with_distance_altitude_and_route():
    a = samsung.activity(run(ANCHOR))
    s = a.samples
    assert a.sport == "running" and a.local_date == ANCHOR.isoformat() and a.manufacturer == "Samsung"
    assert len(s.t) == 600 and s.hr[10] is not None and s.speed[10] == 3.0 and s.cad[10] == 164  # both entries, one second
    assert abs(s.dist[-1] - 1800) < 1 and s.elev[100] is not None and s.power is None
    assert a.shape and len(a.shape) >= 30  # ~1.8 km at a point every 50 m
    assert a.raw[0].payload["startLatitude"] == 32.0 and "log" not in a.raw[0].payload  # where it started, not the track


def test_resting_hr_is_the_lowest_half_hour_and_needs_enough_readings():
    day = ANCHOR
    readings = [[ms(day, 0) + i * 600_000, 70] for i in range(144)]  # every 10 minutes
    for i in range(18, 22):  # 03:00-03:30: 50 bpm
        readings[i][1] = 50
    assert samsung.resting_hr(readings, 3 * 3600) == {day.isoformat(): 50.0}
    assert samsung.resting_hr(readings[:10], 3 * 3600) == {}


def test_sleep_counts_only_time_asleep_and_spots_naps():
    d = ANCHOR
    night = samsung.sleep({"uid": "n", "start": ms(d, 23) - 86_400_000, "end": ms(d, 6), "offset_s": 3 * 3600, "stages": [
        [ms(d, 23) - 86_400_000, ms(d, 1), "LIGHT"], [ms(d, 1), ms(d, 3), "DEEP"], [ms(d, 3), ms(d, 3, 30), "AWAKE"],
        [ms(d, 3, 30), ms(d, 6), "REM"]]})
    assert night.wake_date == d.isoformat() and not night.is_nap and night.duration_s == 6.5 * 3600 and night.awake_s == 1800
    nap = samsung.sleep({"uid": "p", "start": ms(d, 14), "end": ms(d, 14, 40), "offset_s": 3 * 3600,
                         "stages": [[ms(d, 14), ms(d, 14, 40), "LIGHT"]]})
    assert nap.is_nap


def test_only_samsung_days_reach_the_analysis_and_a_run_on_both_watches_shows_once():
    conn = connect(user_db_name(1, "garmin"))
    switch_day = ANCHOR
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": switch_day.isoformat()}])
    # Garmin recorded the same run as the Samsung watch on the switch day
    conn.activity.insert_one({"source": "garmin", "source_id": "g1", "id": 999, "local_date": switch_day.isoformat(),
                              "start_utc": datetime.fromtimestamp(ms(switch_day, 7, 1) / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
                              "manufacturer": "Garmin", "sport": "running"})
    readings = [[ms(switch_day, 0) + i * 600_000, 60] for i in range(144)]
    dates, runs = samsung.ingest(conn, "garmin", {"activities": [run(switch_day - timedelta(days=1), "old"), run(switch_day, "new")],
                                                  "heart_rate": readings, "offset_s": 3 * 3600})
    sources = {r["source_id"]: r["source"] for r in conn.activity.find({})}
    assert sources == {"samsung-old": "samsung", "samsung-new": "garmin", "g1": "garmin_aside"}
    assert runs == ["samsung-new"] and switch_day.isoformat() in dates
    assert conn.daily_observation.find_one({"source": "garmin", "metric": "resting_hr"})["value"] == 60
    # Sending the same again changes nothing
    assert samsung.ingest(conn, "garmin", {"activities": [run(switch_day, "new")]}) == (set(), [])


def test_switching_keeps_dated_history():
    conn = connect(user_db_name(1, "garmin"))
    samsung.switch(conn, "samsung", ANCHOR)
    samsung.switch(conn, "garmin", ANCHOR)  # changed their mind the same day
    assert samsung.watch_history(conn) == []
    samsung.switch(conn, "samsung", ANCHOR)
    samsung.switch(conn, "garmin", ANCHOR + timedelta(days=10))
    assert samsung.watch_on(conn, (ANCHOR - timedelta(days=1)).isoformat()) == "garmin"
    assert samsung.watch_on(conn, (ANCHOR + timedelta(days=3)).isoformat()) == "samsung"
    assert samsung.watch_on(conn, (ANCHOR + timedelta(days=10)).isoformat()) == "garmin"


def test_garmin_sync_pauses_on_samsung_and_never_fills_a_samsung_day():
    conn = connect(user_db_name(1, "fixture"))
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": "2026-09-20"}])
    assert run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 30, 3).outcome == "paused"
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": "2026-09-20"}, {"watch": "garmin", "from": "2026-09-25"}])
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 30, 3, max_backfill_days=40)
    days = set(conn.daily_observation.distinct("local_date"))
    runs = set(conn.activity.distinct("local_date"))
    assert "2026-09-19" in days and "2026-09-26" in days
    assert not any("2026-09-20" <= d < "2026-09-25" for d in days | runs)


def test_upload_through_the_api(tmp_path):
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    client = TestClient(create_app(c, connector=FixtureConnector(ANCHOR)))
    assert client.put("/v1/settings", json={"watch": "samsung"}, headers=h).json()["watch"] == "samsung"
    today = date.fromisoformat(client.get("/v1/status", headers=h).json()["today"])
    r = client.post("/v1/samsung", json={"activities": [run(today, "api")], "offset_s": 3 * 3600}, headers=h)
    assert r.status_code == 200 and r.json()["changed_runs"] == ["samsung-api"]
    st = client.get("/v1/status", headers=h).json()
    assert st["watch"] == "samsung" and st["connection"]["state"] == "connected"
    assert client.get("/v1/samsung", headers=h).json()["newest_activity_start"]
    assert any(a["source_id"] == "samsung-api" for a in client.get("/v1/activities", headers=h).json())
    for _ in range(50):
        if not client.get("/v1/status", headers=h).json()["sync_running"]:
            break
        time.sleep(0.05)

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
    readings = [(ms(day, 0) + i * 600_000, 70, 3 * 3600) for i in range(144)]  # every 10 minutes
    readings = [(t, 50 if 18 <= i < 22 else b, o) for i, (t, b, o) in enumerate(readings)]  # 03:00-03:30: 50 bpm
    assert samsung.resting_hr(readings) == {day.isoformat(): 50.0}
    assert samsung.resting_hr(readings[:10]) == {}  # under 4 hours measured
    daytime = [r for r in readings if r[0] >= ms(day, 8)]  # a new watch put on in the morning: no night, no resting value
    assert samsung.resting_hr(daytime) == {}


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
    samsung.switch(conn, "garmin", "samsung", ANCHOR)
    samsung.switch(conn, "garmin", "garmin", ANCHOR)  # changed their mind the same day
    assert samsung.watch_history(conn) == []
    samsung.switch(conn, "garmin", "samsung", ANCHOR)
    samsung.switch(conn, "garmin", "garmin", ANCHOR + timedelta(days=10))
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


def test_km_splits_from_the_samples_and_samsungs_vo2_kept_apart():
    a = samsung.activity(run(ANCHOR, seconds=1000, speed=3.0))  # 3 km
    assert len(a.laps) == 3 and all(abs(l.distance_m - 1000) <= 5 for l in a.laps)
    assert abs(a.laps[0].elapsed_s - 333) <= 2 and a.laps[0].avg_hr and a.laps[0].avg_cadence_spm == 164
    conn = connect(user_db_name(1, "garmin"))
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": ANCHOR.isoformat()}])
    samsung.ingest(conn, "garmin", {"activities": [{**run(ANCHOR, "v"), "vo2max": 55.4}]})
    assert conn.daily_observation.find_one({"metric": "samsung_vo2max_running"})["value"] == 55.4
    assert conn.daily_observation.find_one({"metric": "garmin_vo2max_running"}) is None
    assert conn.activity_lap.count_documents({}) == 2  # 1.8 km: one full km and what's left


def test_switching_maker_blends_but_a_new_garmin_still_starts_an_era():
    from sidekick import reports as rp
    conn = connect(user_db_name(1, "garmin"))
    def add(i, d, device, maker):
        conn.activity.insert_one({"source": "garmin", "source_id": f"a{i}", "id": i, "local_date": d, "start_utc": d + "T06:00:00Z",
                                  "device_id": device, "manufacturer": maker})
    add(1, "2026-09-01", "g1", None)
    add(2, "2026-09-10", "g2", "GARMIN")
    add(3, "2026-09-20", "s1", "Samsung")
    assert rp.device_era_start(conn, "garmin", date(2026, 9, 15)) == date(2026, 9, 2)  # a new Garmin: baselines restart
    assert rp.device_era_start(conn, "garmin", date(2026, 9, 25)) == date(2026, 9, 2)  # Garmin → Samsung: the era carries on
    add(4, "2026-09-28", "s2", "Samsung")
    assert rp.device_era_start(conn, "garmin", date(2026, 9, 29)) == date(2026, 9, 21)  # a new Samsung watch: restart


def test_moving_time_follows_the_samples_spacing_and_a_summary_only_workout_keeps_its_duration():
    r = run(ANCHOR, seconds=600, speed=3.0)
    r["log"] = [e for e in r["log"] if (e[0] - r["start"]) % 5000 < 1000]  # one sample every 5 s
    a = samsung.activity(r)
    assert abs(a.moving_s - 595) <= 5 and abs(a.samples.dist[-1] - 1800) < 1
    bare = samsung.activity({**run(ANCHOR, "b"), "log": [], "route": []})
    assert bare.moving_s == 600 and bare.samples is None


def test_resting_hr_is_the_same_however_the_readings_are_sent():
    conn = connect(user_db_name(1, "garmin"))
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": "2026-01-01"}])
    readings = [[ms(ANCHOR, 0) + i * 600_000, 50 if 18 <= i < 22 else 70, 3 * 3600] for i in range(144)]
    for part in (readings[:50], readings[50:100], readings[100:], readings[40:60]):  # in parts, one part twice
        samsung.ingest(conn, "garmin", {"heart_rate": part})
    assert conn.daily_observation.find_one({"metric": "resting_hr"})["value"] == 50.0


def test_switching_back_after_an_import_files_the_data_again():
    conn = connect(user_db_name(1, "garmin"))
    samsung.switch(conn, "garmin", "samsung", ANCHOR)
    conn.activity.insert_one({"source": "garmin", "source_id": "g1", "id": 999, "local_date": ANCHOR.isoformat(),
                              "start_utc": datetime.fromtimestamp(ms(ANCHOR, 7, 1) / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
                              "manufacturer": "Garmin", "sport": "running"})
    samsung.ingest(conn, "garmin", {"activities": [run(ANCHOR, "x")], "sleep": [{"uid": "n", "start": ms(ANCHOR, 0), "end": ms(ANCHOR, 6),
                   "offset_s": 3 * 3600, "score": 81, "stages": [[ms(ANCHOR, 0), ms(ANCHOR, 6), "LIGHT"]]}]})
    assert {r["source_id"]: r["source"] for r in conn.activity.find({})} == {"g1": "garmin_aside", "samsung-x": "garmin"}
    assert conn.daily_observation.find_one({"metric": "samsung_sleep_score"})["source"] == "garmin"
    moved = samsung.switch(conn, "garmin", "garmin", ANCHOR)  # changed their mind the same day
    assert ANCHOR.isoformat() in moved
    assert {r["source_id"]: r["source"] for r in conn.activity.find({})} == {"g1": "garmin", "samsung-x": "samsung"}
    assert conn.sleep_session.find_one({"source_id": "samsung-n"})["source"] == "samsung"
    assert conn.daily_observation.count_documents({"source": "garmin", "method": {"$regex": "^samsung"}}) == 0


def test_fitness_vo2_follows_the_watch_and_isnt_compared_across_a_switch():
    from sidekick import scores
    conn = connect(user_db_name(1, "garmin"))
    set_setting(conn, "vo2_source", "watch")  # the watch's VO2 max (Settings › VO2 max for scores)
    conn.daily_observation.insert_one({"source": "garmin", "local_date": "2026-09-01", "metric": "garmin_vo2max_running",
                                       "value": 46.3, "state": "measured"})
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": "2026-09-20"}])
    assert scores.vo2_on(conn, "garmin", date(2026, 9, 15), ANCHOR)[0] == 46.3
    assert scores.vo2_on(conn, "garmin", ANCHOR, ANCHOR) is None  # Samsung's day: Garmin's old estimate doesn't count
    samsung.ingest(conn, "garmin", {"activities": [{**run(ANCHOR, "v"), "vo2max": 55.4}]})
    assert scores.vo2_on(conn, "garmin", ANCHOR, ANCHOR)[0] == 55.4
    from sidekick import progress
    assert progress.vo2_signal(conn, "garmin", ANCHOR)["direction"] is None


def test_last_night_measured_and_compared_with_the_nights_before():
    from sidekick import reports as rp
    conn = connect(user_db_name(1, "garmin"))
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": "2026-01-01"}])
    for k in range(7):  # six usual nights, then a warmer one with a higher heart rate
        d = ANCHOR - timedelta(days=6 - k)
        last = k == 6
        start, end = ms(d, 0) - 3_600_000, ms(d, 6)  # 23:00 to 06:00
        hr = [[t, 58 if last else 50, 3 * 3600] for t in range(start, end, 600_000)]
        skin = [[t, (34.2 if last else 33.6), 3 * 3600] for t in range(start, end, 1_800_000)]
        spo2 = [[t, 95, 3 * 3600] for t in range(start, end, 1_800_000)]
        samsung.ingest(conn, "garmin", {"sleep": [{"uid": f"n{k}", "start": start, "end": end, "offset_s": 3 * 3600,
                                                   "stages": [[start, end, "LIGHT"]]}],
                                        "heart_rate": hr, "skin_temp": skin, "spo2": spo2})
    o = rp.overnight(conn, "garmin", ANCHOR, rp.day_obs(conn, "garmin", ANCHOR.isoformat()))
    assert o["measured_s"] >= 6.5 * 3600 and o["asleep_s"] == 7 * 3600  # readings every 10 minutes cover the night
    assert o["sleep_hr"]["low"] == 58 and o["sleep_hr"]["delta"] == 8
    assert o["skin_temp"]["delta"] == 0.6 and o["spo2"]["usual"] == [95.0, 95.0]
    first = rp.overnight(conn, "garmin", ANCHOR - timedelta(days=6), rp.day_obs(conn, "garmin", (ANCHOR - timedelta(days=6)).isoformat()))
    assert first["skin_temp"]["delta"] is None  # no usual yet: the number alone


def test_hr_quality_flags_a_dropout_but_not_a_warm_up_or_a_climb():
    from sidekick.analytics.running import hr_quality
    from sidekick.connectors.base import Samples
    n = 2400
    t, sp, d = [float(i) for i in range(n)], [3.0] * n, [3.0 * i for i in range(n)]
    mk = lambda hr, speed=sp: Samples(t, hr, speed, d, [0] * n, [165] * n)  # noqa: E731
    assert hr_quality(mk([min(160.0, 110 + i * 0.08) for i in range(n)]))["grade"] == "good"
    drop = [128.0 if 1440 <= i < 1520 else 150.0 for i in range(n)]  # 80 s of lost contact at a steady pace
    q = hr_quality(mk(drop))
    assert q["grade"] == "questionable" and q["stretches"][0]["start_s"] == 1440 and "jumped -22 bpm" in q["stretches"][0]["reason"]
    climb_sp = [2.2 if 1200 <= i < 1500 else 3.0 for i in range(n)]
    assert hr_quality(mk([160.0 if 1200 <= i < 1500 else 150.0 for i in range(n)], climb_sp))["grade"] == "good"


def test_samsung_run_export_names_its_sources():
    from sidekick import run_export
    conn = connect(user_db_name(1, "garmin"))
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": "2026-01-01"}])
    samsung.ingest(conn, "garmin", {"activities": [{**run(ANCHOR, "e", seconds=1500), "vo2max": 55.4}]})
    from sidekick import reports as rp
    rp.build_post_run(conn, "garmin", "samsung-e", False)
    md = run_export.markdown(conn, "garmin", "samsung-e", fetch=lambda *a, **k: None)[1]
    assert "VO₂ max (Samsung estimate, device value): **55.4**" in md and "Garmin estimate" not in md
    assert "HR data quality: **Good**" in md and "VO₂ source: **Samsung (device estimate)**" in md
    assert "Running dynamics source: **Not accessible via the current Samsung integration**" in md


def test_a_gtii_fit_run_becomes_a_samsung_run_with_laps_and_wins_over_its_samsung_health_copy():
    import fitgen
    from sidekick import fit
    start = datetime.fromtimestamp(ms(ANCHOR, 7) / 1000, timezone.utc)
    act, summary = fit.parse(fitgen.run(start))
    assert act.sport == "running" and act.local_date == ANCHOR.isoformat() and act.utc_offset_s == 3 * 3600
    assert act.manufacturer == "Samsung" and act.device_id is None and abs(act.distance_m - 1440) < 1
    assert act.samples.cad[10] == 164 and act.samples.hr[10] == 145 and abs(act.samples.speed[10] - 3.0) < 0.01
    assert [l.intensity for l in act.laps] == ["ACTIVE", "REST"] and act.shape and summary["recorder"] == "FIT"
    conn = connect(user_db_name(1, "garmin"))
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": "2026-01-01"}])
    samsung.ingest(conn, "garmin", {"activities": [run(ANCHOR, "twin")]})  # Samsung Health's copy first
    dates, runs = fit.ingest(conn, "garmin", fitgen.run(start))
    assert runs == [act.source_id]
    assert {r["source_id"]: r["source"] for r in conn.activity.find({})} == {"samsung-twin": "samsung", act.source_id: "garmin"}
    samsung.ingest(conn, "garmin", {"activities": [{**run(ANCHOR, "twin"), "title": "again"}]})  # sent again: stays aside
    assert conn.activity.find_one({"source_id": "samsung-twin"})["source"] == "samsung"
    assert samsung.reconcile(conn, "garmin") == set()  # re-filing leaves it aside too
    assert fit.ingest(conn, "garmin", fitgen.run(start)) == (set(), [])  # the same file again changes nothing


def test_the_fit_endpoint_refuses_what_isnt_a_run(tmp_path):
    import base64
    import fitgen
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    client = TestClient(create_app(c, connector=FixtureConnector(ANCHOR)))
    client.put("/v1/settings", json={"watch": "samsung"}, headers=h)
    today = date.fromisoformat(client.get("/v1/status", headers=h).json()["today"])
    good = fitgen.run(datetime.fromtimestamp(ms(today, 7) / 1000, timezone.utc))
    r = client.post("/v1/fit", json={"name": "run.fit", "data": base64.b64encode(good).decode()}, headers=h)
    assert r.status_code == 200 and r.json()["changed_runs"][0].startswith("fit-")
    bad = client.post("/v1/fit", json={"name": "photo.jpg", "data": base64.b64encode(b"not a fit file").decode()}, headers=h)
    assert bad.status_code == 422 and "photo.jpg" in bad.json()["detail"]


def test_a_deleted_run_stays_deleted_and_test_recordings_are_never_runs(tmp_path):
    import base64
    import fitgen
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    client = TestClient(create_app(c, connector=FixtureConnector(ANCHOR)))
    client.put("/v1/settings", json={"watch": "samsung"}, headers=h)
    today = date.fromisoformat(client.get("/v1/status", headers=h).json()["today"])
    start = datetime.fromtimestamp(ms(today, 7) / 1000, timezone.utc)
    short = fitgen.run(start, seconds=25, rest_from=None)  # a 25-second test recording
    assert client.post("/v1/fit", json={"name": "t.fit", "data": base64.b64encode(short).decode()}, headers=h).json()["changed_runs"] == []
    assert client.post("/v1/samsung", json={"activities": [run(today, "tiny", seconds=25)]}, headers=h).json()["changed_runs"] == []
    good = fitgen.run(start)
    sid = client.post("/v1/fit", json={"name": "r.fit", "data": base64.b64encode(good).decode()}, headers=h).json()["changed_runs"][0]
    assert any(a["source_id"] == sid for a in client.get("/v1/activities", headers=h).json())
    assert client.delete(f"/v1/activities/{sid}", headers=h).json() == {"deleted": sid}
    assert not any(a["source_id"] == sid for a in client.get("/v1/activities", headers=h).json())
    conn = connect(user_db_name(1, "fixture"))
    conn.activity.delete_many({"source_id": sid})  # even with the old copy gone, sending it again doesn't bring it back
    client.post("/v1/fit", json={"name": "r.fit", "data": base64.b64encode(good + b"").decode()}, headers=h)
    assert not any(a["source_id"] == sid for a in client.get("/v1/activities", headers=h).json())
    assert client.delete(f"/v1/activities/{sid}", headers=h).status_code == 404


def test_climb_and_descent_from_altitude_when_samsung_leaves_them_out():
    r = run(ANCHOR, seconds=1200)
    r.pop("climb_m")
    for i, p in enumerate(r["route"]):  # up 20 m, then back down
        p[3] = 20 + (i if i < 600 else 1200 - i) * 20 / 600
    a = samsung.activity(r)
    assert abs(a.elevation_gain_m - 20) < 1 and abs(a.elevation_loss_m - 20) < 1
    assert samsung.activity({**run(ANCHOR), "climb_m": 6, "descent_m": 5}).elevation_loss_m == 5  # Samsung's own, when given


def test_a_run_says_which_watch_and_gives_our_vo2_or_why_not():
    from sidekick import reports as rp
    conn = connect(user_db_name(1, "garmin"))
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": "2026-01-01"}])
    samsung.ingest(conn, "garmin", {"activities": [{**run(ANCHOR, "o", seconds=1500), "vo2max": 55.4}]})
    r = rp.build_post_run(conn, "garmin", "samsung-o", False)
    assert r["watch"] == "Samsung" and r["vo2_ours"]["value"] is None and r["vo2_ours"]["why"]  # no weather or resting HR here
    from sidekick import run_export
    md = run_export.markdown(conn, "garmin", "samsung-o", fetch=lambda *x, **k: None)[1]
    assert "VO₂ max (Runner Sidekick, from this run): not calculated (" in md and "VO₂ max (Samsung estimate" in md

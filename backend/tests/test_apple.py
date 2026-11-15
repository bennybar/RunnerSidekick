"""Apple Watch as the account's watch: the iPhone app uploads Apple Health data (POST /v1/apple) and every screen is
built from it. Synthetic payloads in the shape the app sends, dated from the real today (the API's own day)."""
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from sidekick import reports as rp
from sidekick.api import create_app
from sidekick.auth import create_token
from sidekick.config import Config
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, user_db_name

TZ = ZoneInfo("Asia/Jerusalem")
ANCHOR = date(2026, 9, 30)
TODAY = datetime.now(TZ).date()


def app(tmp_path, backfill_days=40):
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=backfill_days, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    return TestClient(create_app(c, connector=FixtureConnector(ANCHOR))), h, c


def at(d: date, hh: int, mm: int = 0, ss: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=TZ)


def run(d: date, uid: str, km: float = 10.0, pace_s: float = 330.0, pause_at: int | None = 1500, pause_s: int = 60,
        hill: bool = True) -> dict:
    """A run at a steady pace northwards over a rolling hill, with one pause; series as the phone sends them."""
    moving = round(km * pace_s)
    start = at(d, 6, 30)
    elapsed = moving + (pause_s if pause_at else 0)
    v = 1000 / pace_s

    def moved(t):  # seconds of running by elapsed second t
        if pause_at is None or t < pause_at:
            return t
        return max(pause_at, t - pause_s)
    paused = lambda t: pause_at is not None and pause_at <= t < pause_at + pause_s  # noqa: E731
    hr = [[t, round(128 + 30 * moved(t) / moving + 6 * math.sin(t / 90), 1)] for t in range(0, elapsed + 1, 5) if not paused(t)]
    dist = [[t, round(v * moved(t), 1)] for t in range(0, elapsed + 1, 3)]
    alt = lambda m: 20 + (15 * math.sin(2 * math.pi * m / 2500) if hill else 0)  # noqa: E731 (a 30 m hill every 2.5 km)
    route = [[t, 32.07 + v * moved(t) / 111_320, 34.78, round(alt(v * moved(t)), 1), round(0 if paused(t) else v, 2)]
             for t in range(0, elapsed + 1, 2)]
    steps = [[t, round(172 / 60 * moved(t))] for t in range(0, elapsed + 1, 5)]
    power = [[t, 0 if paused(t) else 250] for t in range(0, elapsed + 1, 5)]
    ev = [{"type": "pause", "start": (start + timedelta(seconds=pause_at)).isoformat()},
          {"type": "resume", "start": (start + timedelta(seconds=pause_at + pause_s)).isoformat()}] if pause_at else []
    return {"uuid": uid, "start": start.isoformat(), "end": (start + timedelta(seconds=elapsed)).isoformat(), "sport": "running",
            "indoor": False, "distance_m": round(v * moving, 1), "moving_s": float(moving), "elapsed_s": float(elapsed),
            "energy_kcal": 700.0, "device": "Apple Watch Series 10", "events": ev,
            "series": {"hr": hr, "distance": dist, "route": route, "power": power, "steps": steps},
            "dynamics": {"stride_m": 1.05, "vertical_osc_cm": 8.9, "ground_contact_ms": 251}}


def night(wake: date, rmssd: bool = True) -> tuple[list[dict], list[dict]]:
    """Sleep stages from 23:00 to about 06:30 (cycles of core, deep, core, REM and a brief wake) plus time in bed, and
    three HRV readings inside it."""
    t = at(wake - timedelta(days=1), 23, 0)
    end = at(wake, 6, 30)
    stages = [{"start": (t - timedelta(minutes=10)).isoformat(), "end": (end + timedelta(minutes=5)).isoformat(), "stage": "in_bed"}]
    cycle = [("core", 30), ("deep", 40), ("core", 40), ("rem", 25), ("awake", 5)]
    k = 0
    while t < end:
        st, m = cycle[k % len(cycle)]
        nxt = min(end, t + timedelta(minutes=m))
        stages.append({"start": t.isoformat(), "end": nxt.isoformat(), "stage": st})
        t, k = nxt, k + 1
    j = wake.toordinal() % 5
    hrv = [{"time": at(wake, hh).isoformat(), "sdnn_ms": 50.0 + j + hh, "rmssd_ms": (40.0 + j + hh) if rmssd else None, "beats": 70}
           for hh in (1, 3, 5)]
    return stages, hrv


def day(d: date) -> dict:
    j = d.toordinal() % 7
    return {"date": d.isoformat(), "resting_hr": 50 + j % 3, "steps": 8000 + 300 * j, "exercise_min": 35 + 5 * j,
            "vo2max": 49.3 if d.toordinal() % 3 == 0 else None, "weight_kg": 72.4 if j == 0 else None}


def history(days: int = 30, runs_every: int = 3) -> list[dict]:
    """Bodies to post, oldest first, in bounded batches: the days, nights and HRV, then the runs five at a time."""
    dates = [TODAY - timedelta(days=k) for k in range(days - 1, -1, -1)]
    sleep, hrv = [], []
    for d in dates:
        s, h = night(d)
        sleep += s
        hrv += h
    bodies = [{"tz": "Asia/Jerusalem", "days": [day(d) for d in dates]}]
    bodies += [{"tz": "Asia/Jerusalem", "sleep": sleep[i:i + 400]} for i in range(0, len(sleep), 400)]
    bodies.append({"tz": "Asia/Jerusalem", "hrv": hrv})
    runs = [run(d, f"run-{d.isoformat()}") for d in dates[:-1] if d.toordinal() % runs_every == 0]
    bodies += [{"tz": "Asia/Jerusalem", "workouts": runs[i:i + 5]} for i in range(0, len(runs), 5)]
    return bodies


def apple_account(tmp_path, **kw):
    client, h, c = app(tmp_path)
    client.cfg = c
    r = client.put("/v1/settings", json={"watch": "apple", "profile_sex": "male", "profile_birth_date": "1983-06-02"}, headers=h)
    assert r.status_code == 200 and r.json()["watch"] == "apple"
    for b in history(**kw):
        r = client.post("/v1/apple", json=b, headers=h)
        assert r.status_code == 200, r.text
    return client, h, connect(user_db_name(1, "fixture"))


def test_refused_while_the_watch_is_garmin_and_over_bounds(tmp_path):
    client, h, _ = app(tmp_path)
    assert client.get("/v1/settings", headers=h).json()["watch"] == "garmin"
    assert client.post("/v1/apple", json={"days": [day(TODAY)]}, headers=h).status_code == 409
    client.put("/v1/settings", json={"watch": "apple"}, headers=h)
    r = client.post("/v1/apple", json={"workouts": [run(TODAY - timedelta(days=1), f"w{k}") for k in range(6)]}, headers=h)
    assert r.status_code == 413 and "workouts" in r.json()["detail"]
    bad = client.post("/v1/apple", json={"days": [day(TODAY), {"date": "2026-02-30"}]}, headers=h)
    assert bad.status_code == 422 and "days" in str(bad.json()["detail"])  # says which item
    assert client.get("/v1/apple", headers=h).json()["watch"] == "apple"


def test_a_run_becomes_an_activity_with_laps_samples_pauses_and_hills(tmp_path):
    client, h, _ = app(tmp_path)
    client.put("/v1/settings", json={"watch": "apple"}, headers=h)
    d = TODAY - timedelta(days=1)
    w = run(d, "ABC-123")
    r = client.post("/v1/apple", json={"tz": "Asia/Jerusalem", "workouts": [w]}, headers=h)
    assert r.status_code == 200 and r.json()["accepted"]["workouts"] == 1 and r.json()["changed_dates"] >= 1
    conn = connect(user_db_name(1, "fixture"))
    a = conn.activity.find_one({"source_id": "apple-ABC-123"})
    assert a["manufacturer"] == "Apple" and a["sport"] == "running" and a["local_date"] == d.isoformat()
    assert a["elapsed_s"] == w["elapsed_s"] and a["moving_s"] == w["elapsed_s"] - 60  # the paused minute isn't moving
    assert abs(a["distance_m"] - 10_000) < 1 and 138 < a["avg_hr"] < 150 and 160 < a["avg_cadence_spm"] < 185
    assert 100 < a["elevation_gain_m"] < 160 and 100 < a["elevation_loss_m"] < 160  # four 30 m hills, from the route altitude
    laps = list(conn.activity_lap.find({"activity_id": a["id"]}, sort=[("idx", 1)]))
    assert len(laps) == 10 and all(abs(l["distance_m"] - 1000) < 15 for l in laps)
    assert all(l["avg_hr"] and l["elevation_gain_m"] is not None for l in laps)
    s = conn.activity_samples.find_one({"activity_id": a["id"]})["samples"]
    assert len(s["t"]) == w["elapsed_s"] + 1 - 60  # one per second, the pause left out
    assert s["t"][1500] == 1560.0  # time keeps counting across the pause
    assert any(e is not None for e in s["elev"]) and s["power"] and abs(s["speed"][100] - 1000 / 330) < 0.05
    assert conn.route_shape.find_one({"source_id": "apple-ABC-123"})
    # The run report, as for a Garmin run
    body = client.get("/v1/activities/apple-ABC-123", headers=h).json()
    rep = body["report"] if "report" in body else body
    assert rep["watch"] == "Apple Watch" and rep["garmin_extra"] == []
    assert len(rep["splits"]) == 10
    md = client.get("/v1/activities/apple-ABC-123/export.md", headers=h)
    assert md.status_code == 200 and "Apple Health" in md.text and "Garmin Connect" not in md.text
    # Sent again: nothing changes (keyed by the HealthKit UUID)
    before = (a["updated_at"], conn.activity.count_documents({}), conn.activity_lap.count_documents({}))
    again = client.post("/v1/apple", json={"tz": "Asia/Jerusalem", "workouts": [w]}, headers=h).json()
    assert again["accepted"]["workouts"] == 1 and again["changed_dates"] == 0
    a2 = conn.activity.find_one({"source_id": "apple-ABC-123"})
    assert (a2["updated_at"], conn.activity.count_documents({}), conn.activity_lap.count_documents({})) == before
    # Too short to be a run: not imported
    tiny = run(d, "tiny", km=0.1)
    assert client.post("/v1/apple", json={"workouts": [tiny]}, headers=h).json()["accepted"]["workouts"] == 0


def test_a_night_with_stages_and_hrv(tmp_path):
    client, h, _ = app(tmp_path)
    client.put("/v1/settings", json={"watch": "apple"}, headers=h)
    wake = TODAY - timedelta(days=2)
    stages, hrv = night(wake)
    # A night split across two uploads comes out whole, whichever order the parts arrive in
    assert client.post("/v1/apple", json={"sleep": stages[8:]}, headers=h).status_code == 200
    assert client.post("/v1/apple", json={"sleep": stages[:8], "hrv": hrv}, headers=h).status_code == 200
    conn = connect(user_db_name(1, "fixture"))
    ss = list(conn.sleep_session.find({"wake_date": wake.isoformat()}))
    assert len(ss) == 1 and not ss[0]["is_nap"]
    n = ss[0]
    assert n["start_utc"].startswith((wake - timedelta(days=1)).isoformat()) and n["deep_s"] and n["light_s"] and n["rem_s"] and n["awake_s"]
    assert abs(n["duration_s"] - (7.5 * 3600 - n["awake_s"])) < 1  # asleep time: deep + core + REM, time in bed and awake left out
    obs = rp.day_obs(conn, "fixture", wake.isoformat())
    assert obs["sleep_duration"]["value"] == n["duration_s"] and obs["sleep_duration"]["method"] == "apple_sleep_stages"
    j = wake.toordinal() % 5
    assert obs["hrv_overnight_avg"]["method"] == "apple_rmssd" and obs["hrv_overnight_avg"]["value"] == 40 + j + 3  # mean of 1, 3, 5 h
    # Without RMSSD from the heartbeat series, the night's HRV is Apple's SDNN, under its own method
    wake2 = wake + timedelta(days=1)
    s2, h2 = night(wake2, rmssd=False)
    client.post("/v1/apple", json={"sleep": s2, "hrv": h2}, headers=h)
    o2 = rp.day_obs(conn, "fixture", wake2.isoformat())["hrv_overnight_avg"]
    assert o2["method"] == "apple_sdnn" and o2["value"] == 50 + wake2.toordinal() % 5 + 3
    # Resending changes nothing
    assert client.post("/v1/apple", json={"sleep": stages, "hrv": hrv}, headers=h).json()["changed_dates"] == 0
    assert conn.sleep_session.count_documents({}) == 2


def test_baselines_never_mix_hrv_methods():
    from sidekick.connectors.base import DayBundle, Observation
    from sidekick.store import save_day
    conn = connect(user_db_name(1, "fixture"))
    d = date(2026, 10, 30)
    for k in range(30, 0, -1):
        ds = (d - timedelta(days=k)).isoformat()
        save_day(conn, "fixture", DayBundle(ds, [Observation(ds, "hrv_overnight_avg", 80.0, method="apple_sdnn")]))
    save_day(conn, "fixture", DayBundle(d.isoformat(), [Observation(d.isoformat(), "hrv_overnight_avg", 40.0, method="apple_rmssd")]))
    f = rp.metric_finding(conn, "fixture", "hrv_overnight_avg", d, rp.day_obs(conn, "fixture", d.isoformat())["hrv_overnight_avg"])
    assert f["status"] == "learning" and f["sample_size"] == 0  # SDNN nights aren't RMSSD's usual
    assert set(rp.hrv_series(conn, "fixture", d.isoformat()).values()) == {40.0}


def test_apple_only_account_builds_every_screen(tmp_path):
    client, h, conn = apple_account(tmp_path)
    st = client.get("/v1/apple", headers=h).json()
    assert st["counts"]["workouts"] >= 8 and st["counts"]["nights"] == 30 and st["counts"]["days"] == 30
    assert st["latest"]["night"] == TODAY.isoformat() and st["last_upload_at"]
    # Garmin's sync is skipped while the watch is Apple's: nothing fetched, nothing deleted
    n_obs = conn.daily_observation.count_documents({})
    assert client.post("/v1/sync", headers=h).json()["started"] is False
    res = client.app.state.do_sync(client.cfg.__class__(**{**client.cfg.__dict__, "user_id": 1}), 1)
    assert res["outcome"] == "skipped" and res["days_fetched"] == 0
    assert conn.daily_observation.count_documents({"method": {"$regex": "^garmin"}}) == 0
    assert conn.daily_observation.count_documents({}) == n_obs
    # VO2 max: Apple's, named as Apple's
    fit = client.get("/v1/fitness", headers=h).json()
    assert fit["vo2_maker"] == "Apple" and fit["vo2max_series"] and fit["vo2max_series"][-1]["value"] == 49.3 and fit["garmin"] is None
    # Zones derived from the held maximum and resting heart rate (no Garmin zones)
    z = fit["zones"]
    assert z and z["source"] == "derived" and z["method"] == "HRR" and len(z["floors"]) == 5
    assert z["resting_hr"] in (50, 51, 52) and z["floors"][0] == round(z["resting_hr"] + 0.5 * (z["max_hr"] - z["resting_hr"]))
    assert all(a < b for a, b in zip(z["floors"], z["floors"][1:]))
    cardio = client.get("/v1/cardio", headers=h).json()
    assert cardio["garmin"]["maker"] == "Apple" and cardio["garmin"]["value"] == 49
    # Today: the morning report with Apple's readings, scores, readiness; Garmin-only parts simply absent
    t = client.get("/v1/today", headers=h)
    assert t.status_code == 200, t.text
    t = t.json()
    by = {f["metric"]: f for f in t["findings"]}
    assert by["hrv_overnight_avg"]["observed"]["method"] == "apple_rmssd" and by["hrv_overnight_avg"]["status"] != "missing"
    assert by["sleep_duration"]["status"] in ("within", "outside", "sustained") and by["resting_hr"]["comparison"]
    assert t["hrv_detail"] is None  # Garmin's 5-minute overnight readings: none from an Apple Watch
    fitness, health = t["scores"]["fitness"], t["scores"]["health"]
    vo2 = next(p for p in fitness["components"] if p["id"] == "vo2max")
    assert vo2["points"] is not None and "Apple's VO₂ max" in vo2["note"]
    act = next(p for p in health["components"] if p["id"] == "activity")
    assert act["points"] is not None and "Apple's exercise minutes" in act["note"]
    assert next(p for p in health["components"] if p["id"] == "steps")["points"] is not None
    assert next(p for p in health["components"] if p["id"] == "sleep_length")["points"] is not None
    assert t["readiness"]
    # Every other screen builds
    for path in ("/v1/numbers", "/v1/trophies", "/v1/trends?days=7", "/v1/trends?days=28", "/v1/trends?days=90", "/v1/compare",
                 "/v1/insights", "/v1/focus", "/v1/routes", "/v1/activities", "/v1/reports", "/v1/export", "/v1/status", "/v1/coach"):
        r = client.get(path, headers=h)
        assert r.status_code == 200, (path, r.text[:300])
    assert client.get("/v1/weekly/latest", headers=h).status_code in (200, 404)
    cmp = {i["id"]: i for i in client.get("/v1/compare", headers=h).json()["items"]}
    assert cmp["vo2max"]["status"] == "ok" and cmp["hrv"]["status"] == "ok" and "RMSSD" in cmp["hrv"].get("method", "RMSSD")
    assert cmp["fitness_age"]["status"] in ("ok", "unavailable") and "Garmin" not in cmp["fitness_age"].get("headline", "")
    assert client.get("/v1/status", headers=h).json()["watch"] == "apple"
    # Each run's report and export
    for a in conn.activity.find({}, {"source_id": 1}):
        r = client.get(f"/v1/activities/{a['source_id']}", headers=h)
        assert r.status_code == 200
        assert client.get(f"/v1/activities/{a['source_id']}/export.md", headers=h).status_code == 200



def test_switching_keeps_garmin_data_and_starts_new_baselines(tmp_path):
    from sidekick.sync import run_sync
    client, h, c = app(tmp_path, backfill_days=(TODAY - ANCHOR).days + 40)
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)  # Garmin's history, up to the fixture's day
    garmin_obs = conn.daily_observation.count_documents({"method": {"$regex": "^garmin"}})
    garmin_runs = conn.activity.count_documents({})
    assert garmin_obs and garmin_runs
    assert client.get("/v1/fitness", headers=h).json()["vo2_maker"] == "Garmin"
    # Garmin's last day (the fixture's anchor) overlaps nothing; an Apple night on a day Garmin recorded is left out
    s, hv = night(ANCHOR)
    client.put("/v1/settings", json={"watch": "apple"}, headers=h)
    assert client.post("/v1/apple", json={"sleep": s, "hrv": hv, "days": [day(ANCHOR)]}, headers=h).status_code == 200
    assert conn.daily_observation.count_documents({"method": {"$regex": "^garmin"}}) == garmin_obs  # nothing of Garmin's replaced
    assert not conn.sleep_session.find_one({"source_id": {"$regex": "^apple-"}, "wake_date": ANCHOR.isoformat()})
    # A new era from the day after Garmin's last data
    assert rp.device_era_start(conn, "fixture", TODAY) == ANCHOR + timedelta(days=1)
    assert rp.device_era_start(conn, "fixture", ANCHOR) != ANCHOR + timedelta(days=1)
    # A run Garmin also recorded (same start) isn't imported twice
    g = conn.activity.find_one({}, sort=[("start_utc", -1)])
    t0 = datetime.fromisoformat(g["start_utc"].replace("Z", "+00:00")).astimezone(TZ)
    dup = run(t0.date(), "dup")
    dup["start"] = t0.isoformat()
    dup["end"] = (t0 + timedelta(seconds=dup["elapsed_s"])).isoformat()
    assert client.post("/v1/apple", json={"workouts": [dup]}, headers=h).json()["accepted"]["workouts"] == 0
    # Garmin's sync is skipped; switching back resumes it
    assert client.post("/v1/sync", headers=h).json()["started"] is False
    client.put("/v1/settings", json={"watch": "garmin"}, headers=h)
    res = client.app.state.do_sync(c.__class__(**{**c.__dict__, "user_id": 1}), 1)
    assert res["outcome"] != "skipped"
    assert conn.activity.count_documents({}) == garmin_runs


def test_nightly_hrv_uses_every_reading_in_the_sleep(tmp_path):
    # Apple takes an SDNN reading every few minutes asleep; only a few carry the heartbeat series (RMSSD)
    client, h, _ = app(tmp_path)
    client.put("/v1/settings", json={"watch": "apple"}, headers=h)
    wake = TODAY - timedelta(days=1)
    stages, _ = night(wake)
    sd = [40.0, 44.0, 52.0, 38.0, 61.0, 47.0, 55.0, 43.0]
    hrv = [{"time": at(wake, 0, 10 + 5 * i).isoformat(), "sdnn_ms": v, "rmssd_ms": 20.0 if i in (0, 1) else None, "beats": 60}
           for i, v in enumerate(sd)]
    assert client.post("/v1/apple", json={"sleep": stages, "hrv": hrv}, headers=h).status_code == 200
    conn = connect(user_db_name(1, "fixture"))
    o = conn.daily_observation.find_one({"metric": "hrv_overnight_avg", "local_date": wake.isoformat()})
    assert o["method"] == "apple_sdnn" and o["value"] == round(sum(sd) / len(sd), 1) and o["label"] == "8 readings"


def test_running_minutes_count_as_vigorous(tmp_path):
    # 60 exercise minutes on a day with a 45-minute Apple run: 45 vigorous (counted double by the WHO part), 15 moderate
    client, h, _ = app(tmp_path)
    client.put("/v1/settings", json={"watch": "apple"}, headers=h)
    d = TODAY - timedelta(days=2)
    w = run(d, "vig", km=45 * 60 / 330, pace_s=330.0, pause_at=None)
    assert client.post("/v1/apple", json={"days": [{**day(d), "exercise_min": 60}]}, headers=h).status_code == 200
    assert client.post("/v1/apple", json={"workouts": [w]}, headers=h).status_code == 200  # the run after the day: still split
    conn = connect(user_db_name(1, "fixture"))
    get = lambda m: conn.daily_observation.find_one({"metric": m, "local_date": d.isoformat()})["value"]  # noqa: E731
    assert get("exercise_minutes") == 60 and get("intensity_minutes_vigorous") == 45 and get("intensity_minutes_moderate") == 15


def test_climb_descent_and_laps_agree(tmp_path):
    # Apple's own climb is kept; descent and the laps come from the same altitude readings, scaled alike
    client, h, _ = app(tmp_path)
    client.put("/v1/settings", json={"watch": "apple"}, headers=h)
    w = run(TODAY - timedelta(days=3), "hill", km=5.0, pause_at=None)
    w["elevation_gain_m"] = 50.0
    assert client.post("/v1/apple", json={"workouts": [w]}, headers=h).status_code == 200
    conn = connect(user_db_name(1, "fixture"))
    a = conn.activity.find_one({"source_id": "apple-hill"})
    laps = list(conn.activity_lap.find({"activity_id": a["id"]}))
    alts = [r[3] for r in w["series"]["route"]]
    assert a["elevation_gain_m"] == 50.0
    assert abs(sum(l["elevation_gain_m"] for l in laps) - 50.0) < 1.5
    assert abs((a["elevation_gain_m"] - a["elevation_loss_m"]) - (alts[-1] - alts[0])) < 3


def test_resting_heart_rate_never_mixes_watches():
    from sidekick import cardio
    conn = connect(user_db_name(1, "fixture"))
    for k in range(30, 2, -1):  # Garmin's: 50 bpm
        conn.daily_observation.insert_one({"source": "fixture", "metric": "resting_hr", "state": "measured", "value": 50.0,
                                           "method": "garmin_daily_rhr", "local_date": (TODAY - timedelta(days=k)).isoformat()})
    for k in (2, 1, 0):  # then Apple's, read about 6 bpm higher
        conn.daily_observation.insert_one({"source": "fixture", "metric": "resting_hr", "state": "measured", "value": 56.0,
                                           "method": "apple_daily", "local_date": (TODAY - timedelta(days=k)).isoformat()})
    t = TODAY.isoformat()
    assert set(rp.rhr_series(conn, "fixture", t).values()) == {56.0}
    assert len(rp.rhr_series(conn, "fixture", t, all_watches=True)) == 31
    # Under a week of Apple readings: the previous watch's stand in for absolute inputs, never mixed in a trend
    assert cardio.rest_on(conn, "fixture", t) == 50.0
    assert rp.rhr_series(conn, "fixture", (TODAY - timedelta(days=28)).isoformat()) == {}


def test_per_second_speed_matches_distance_over_moving_time(tmp_path):
    # Apple's running speed read about 1% fast against its own distance: scaled to it, as Garmin's samples agree
    client, h, _ = app(tmp_path)
    client.put("/v1/settings", json={"watch": "apple"}, headers=h)
    w = run(TODAY - timedelta(days=4), "spd", km=5.0, pace_s=330.0, pause_at=None, hill=False)
    w["series"]["speed"] = [[t, round(1000 / 330 * 1.012, 3)] for t in range(0, int(w["elapsed_s"]) + 1, 5)]
    assert client.post("/v1/apple", json={"workouts": [w]}, headers=h).status_code == 200
    conn = connect(user_db_name(1, "fixture"))
    a = conn.activity.find_one({"source_id": "apple-spd"})
    sp = [v for v in rp.samples_for(conn, a["id"]).speed if v]
    assert abs(sum(sp) / len(sp) - a["distance_m"] / a["moving_s"]) < 0.005

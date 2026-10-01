import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from helpers import add_checkin
from sidekick import reports as rp
from sidekick.__main__ import RedactFilter
from sidekick.api import create_app, downsample
from sidekick.auth import create_token
from sidekick.config import Config
from sidekick.connectors.base import AuthRequired, ConnectionState, RateLimited, Samples
from sidekick.connectors.fixture import FixtureConnector
from sidekick.connectors.garmin import normalise_activity, normalise_hrv, normalise_sleep, normalise_user_summary
from sidekick.db import connect, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


@pytest.fixture
def conn(tmp_path):
    return connect(user_db_name(1, "fixture"))


def counts(conn):
    return {t: conn[t].count_documents({})
            for t in ("daily_observation", "activity", "activity_lap", "sleep_session")}


# ---------------------------------------------------------------- sync

def test_sync_is_idempotent_and_resumable(conn):
    fx = FixtureConnector(ANCHOR)
    r1 = run_sync(conn, fx, ANCHOR, backfill_days=60, refetch_days=3, max_backfill_days=20)
    assert r1.outcome == "ok"
    def days_cp():
        return conn.sync_checkpoint.find_one({"stream": "days"})
    assert days_cp()["oldest_done"] > "2026-08-01"  # bounded: not finished in one run
    while days_cp()["oldest_done"] > days_cp()["backfill_target"]:
        run_sync(conn, fx, ANCHOR, backfill_days=60, refetch_days=3, max_backfill_days=20)
    full = counts(conn)
    r = run_sync(conn, fx, ANCHOR, backfill_days=60, refetch_days=3, max_backfill_days=20)
    assert r.activities_fetched == 0 and not r.changed_dates
    assert counts(conn) == full
    assert len(conn.daily_observation.distinct("local_date")) == 60


class FailingConnector(FixtureConnector):
    def __init__(self, exc):
        super().__init__(ANCHOR)
        self.exc = exc
        self.calls = 0

    def read_days(self, start, end):
        self.calls += 1
        raise self.exc


def test_auth_failure_blocks_retries_until_relogin(conn):
    c = FailingConnector(AuthRequired("expired"))
    assert run_sync(conn, c, ANCHOR, 30, 3).outcome == "auth_failed"
    assert run_sync(conn, c, ANCHOR, 30, 3).outcome == "auth_failed"
    assert c.calls == 1  # no retry storm
    assert conn.source_connection.find_one()["state"] == ConnectionState.REAUTH_REQUIRED.value


def test_rate_limit_backs_off(conn):
    c = FailingConnector(RateLimited("429"))
    now = datetime(2026, 9, 30, 6, 0, tzinfo=timezone.utc)
    assert run_sync(conn, c, ANCHOR, 30, 3, now=now).outcome == "rate_limited"
    assert run_sync(conn, c, ANCHOR, 30, 3, now=now).outcome == "deferred"
    assert c.calls == 1
    nb = conn.source_connection.find_one()["retry_not_before"]
    assert nb >= "2026-09-30T06:07"  # >= 7.5 min (15 min base with 50-100% jitter)


# ---------------------------------------------------------------- Garmin normalisation (synthetic Garmin-shaped payloads)

def ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp() * 1000)


def test_sleep_across_midnight_and_dst_is_attributed_to_wake_date():
    # Israel DST starts 2026-03-27 02:00 local. Bed 22:30 IST (UTC+2), wake 06:30 IDT (UTC+3).
    p = {"dailySleepDTO": {"id": 123, "calendarDate": "2026-03-27", "sleepTimeSeconds": 25200,
                           "sleepStartTimestampGMT": ms("2026-03-26T20:30:00"), "sleepEndTimestampGMT": ms("2026-03-27T03:30:00"),
                           "sleepEndTimestampLocal": ms("2026-03-27T06:30:00"), "deepSleepSeconds": 5000,
                           "sleepScores": {"overall": {"value": 81}}},
         "dailyNapDTOS": [{"napStartTimestampGMT": ms("2026-03-27T12:00:00"), "napEndTimestampGMT": ms("2026-03-27T12:30:00"), "napTimeSec": 1800}]}
    o, sessions = normalise_sleep("2026-03-27", p)
    main = [s for s in sessions if not s.is_nap][0]
    assert main.wake_date == "2026-03-27" and main.utc_offset_s == 10800
    assert main.start_utc == "2026-03-26T20:30:00Z"
    assert [s.is_nap for s in sessions] == [False, True]
    dur = [x for x in o if x.metric == "sleep_duration"][0]
    assert dur.value == 25200 and dur.local_date == "2026-03-27"


def test_absent_garmin_values_are_not_measured_not_zero():
    o = {x.metric: x for x in normalise_user_summary("2026-09-30", {"totalSteps": None, "restingHeartRate": 48, "averageStressLevel": -1})}
    assert o["steps"].state == "not_measured" and o["steps"].value is None
    assert o["resting_hr"].value == 48
    assert o["avg_stress"].state == "not_measured"  # Garmin -1 sentinel
    assert normalise_hrv("2026-09-30", None)[0].state == "not_measured"
    o2, s = normalise_sleep("2026-09-30", {"dailySleepDTO": {"sleepTimeSeconds": None}})
    assert not s and o2[0].state == "not_measured"


def test_activity_durations_and_hr_gaps():
    a = {"activityId": 9, "activityName": "Morning Run", "activityType": {"typeKey": "running"},
         "startTimeGMT": "2026-09-30 03:30:00", "startTimeLocal": "2026-09-30 06:30:00",
         "distance": 10000.0, "duration": 3100.0, "elapsedDuration": 3300.0, "movingDuration": 3000.0, "averageHR": 150}
    start = datetime(2026, 9, 30, 3, 30, tzinfo=timezone.utc).timestamp() * 1000
    details = {"metricDescriptors": [{"metricsIndex": 0, "key": "directTimestamp"}, {"metricsIndex": 1, "key": "directHeartRate"},
                                     {"metricsIndex": 2, "key": "directSpeed"}],
               "activityDetailMetrics": [{"metrics": [start, 140, 3.0]}, {"metrics": [start + 5000, None, 3.1]}]}
    act = normalise_activity(a, {"lapDTOs": []}, details)
    assert (act.timer_s, act.elapsed_s, act.moving_s) == (3100.0, 3300.0, 3000.0)
    assert act.utc_offset_s == 10800 and act.local_date == "2026-09-30"
    assert act.samples.hr == [140.0, None]  # missing HR stays a gap


# ---------------------------------------------------------------- reports

def test_reports_revision_on_input_change_and_keep_history(conn):
    fx = FixtureConnector(ANCHOR)
    run_sync(conn, fx, ANCHOR, 45, 3, max_backfill_days=60)
    r1 = rp.build_morning(conn, "fixture", ANCHOR, True)
    assert rp.build_morning(conn, "fixture", ANCHOR, True)["revision"] == r1["revision"]  # no change, no new revision
    add_checkin(conn, "c1", ANCHOR.isoformat(), energy=4, pain=True)
    r2 = rp.build_morning(conn, "fixture", ANCHOR, True)
    assert r2["revision"] == r1["revision"] + 1 and r2["recommendation"]["rule_id"] == "R0"
    # contract: embedded check-in flags are JSON booleans (the Android client decodes them strictly)
    assert r2["checkin"]["pain"] is True and r2["checkin"]["deleted"] is False
    assert conn.report.count_documents({"type": "morning", "subject_key": ANCHOR.isoformat()}) == 2


def test_every_top_finding_has_evidence(conn):
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    r = rp.build_morning(conn, "fixture", date(2026, 9, 21), True)  # inside the synthetic recovery episode
    assert r["recommendation"]["state"] in ("consider_easier", "usual_plan")
    assert r["recommendation"]["state"] == "consider_easier" or r["checkin_prompt"]["ask"]  # app asks when unsure
    assert r["recommendation"]["evidence_ids"]
    ids = {f["id"] for f in r["findings"]}
    assert set(r["recommendation"]["evidence_ids"]) - {"checkin"} <= ids
    for f in r["findings"]:
        if f["status"] in ("outside", "within", "sustained"):
            assert f["evidence"]["record_ids"] and f["algorithm_version"] and f["sample_size"]


def test_insufficient_history_suppresses_conclusions(conn):
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 5, 3)
    r = rp.build_morning(conn, "fixture", ANCHOR, True)
    assert r["recommendation"]["state"] == "insufficient_data"
    assert all(f["status"] in ("learning", "missing") for f in r["findings"] if f["metric"] != "running_moving_time_7d")


def test_device_era_inferred_from_runs(conn):
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    assert rp.device_era_start(conn, "fixture", ANCHOR) is None  # one device throughout
    conn.activity.update_many({"local_date": {"$lt": "2026-09-15"}}, {"$set": {"device_id": "old-watch"}})
    era = rp.device_era_start(conn, "fixture", ANCHOR)
    last_old = max(conn.activity.distinct("local_date", {"device_id": "old-watch"}))
    assert era == date.fromisoformat(last_old) + timedelta(days=1)
    f = rp.metric_finding(conn, "fixture", "resting_hr", ANCHOR, rp.day_obs(conn, "fixture", ANCHOR.isoformat())["resting_hr"])
    assert f["comparison"] is None or f["comparison"]["window"][0] >= era.isoformat()
    assert any("watch changed" in x for x in f["limitations"])


# ---------------------------------------------------------------- API

def make_client(tmp_path):
    cfg = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
                 raw_retention_days=120, request_spacing_s=0)
    token = create_token(tmp_path, "test")
    app = create_app(cfg, connector=FixtureConnector(ANCHOR))
    return TestClient(app), token, app


def test_api_requires_token(tmp_path):
    client, token, _ = make_client(tmp_path)
    assert client.get("/v1/status").status_code == 401
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404
    assert client.get("/v1/status", headers={"Authorization": "Bearer nope"}).status_code == 401
    r = client.get("/v1/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["synthetic"] is True


def test_checkin_last_writer_wins(tmp_path):
    client, token, _ = make_client(tmp_path)
    h = {"Authorization": f"Bearer {token}"}
    body = {"local_date": "2026-09-30", "energy": 2, "client_updated_at": "2026-09-30T06:00:00Z"}
    assert client.put("/v1/checkins/a", json=body, headers=h).json()["energy"] == 2
    stale = {**body, "energy": 5, "client_updated_at": "2026-09-30T05:00:00Z"}
    assert client.put("/v1/checkins/a", json=stale, headers=h).json()["energy"] == 2
    newer = {**body, "energy": 4, "client_updated_at": "2026-09-30T07:00:00Z"}
    assert client.put("/v1/checkins/a", json=newer, headers=h).json()["energy"] == 4
    assert client.put("/v1/checkins/b", json={**body, "energy": 9}, headers=h).status_code == 422


def test_downsample_preserves_gaps():
    t = [float(x) for x in range(0, 600, 5)] + [float(x) for x in range(1200, 1800, 5)]
    hr = [150.0] * len(t)
    hr[10] = None
    s = Samples(t, hr, [3.0] * len(t), [0.0] * len(t), [0.0] * len(t), [0.0] * len(t))
    d = downsample(s, max_points=60)
    assert None in d["hr"]  # the 600 s recording gap becomes an explicit null
    assert 0 not in d["hr"]


def test_redaction_filter_drops_secret_looking_logs():
    f = RedactFilter()
    assert not f.filter(logging.LogRecord("x", logging.INFO, "", 0, "Authorization: Bearer abc", None, None))
    assert f.filter(logging.LogRecord("x", logging.INFO, "", 0, "synced 3 days", None, None))



def test_defaults_need_no_environment(monkeypatch):
    from sidekick import config
    monkeypatch.delenv("RSK_SOURCE", raising=False)
    monkeypatch.delenv("RSK_DATA_DIR", raising=False)
    cfg = config.load_config()
    assert cfg.source == "garmin" and cfg.data_dir == config.REPO_DIR / "data"

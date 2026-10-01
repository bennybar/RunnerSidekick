from datetime import date, timedelta

from fastapi.testclient import TestClient

from sidekick import trends, weekly
from sidekick.api import create_app
from sidekick.auth import create_token
from sidekick.config import Config
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)  # a Wednesday


def synced(tmp_path, days=60):
    conn = connect(tmp_path / "t.db")
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, days, 3, max_backfill_days=90)
    return conn


def test_trends_keep_gaps_as_null_and_band_only_when_sufficient(tmp_path):
    conn = synced(tmp_path)
    t = trends.build_trends(conn, "fixture", ANCHOR, 90, True)
    sleep = next(m for m in t["metrics"] if m["metric"] == "sleep_duration")
    assert len(sleep["points"]) == 90
    worn_gap = {(ANCHOR + timedelta(days=d)).isoformat() for d in (-44, -43, -42)}  # fixture: watch not worn
    assert all(p["value"] is None for p in sleep["points"] if p["date"] in worn_gap)
    assert all(p["value"] is None or p["value"] > 0 for p in sleep["points"])  # never zero-filled
    assert "median" not in sleep["band"][0]  # the first days have no 14-day history yet
    assert "median" in sleep["band"][-1]


def test_trend_summary_needs_both_periods(tmp_path):
    conn = synced(tmp_path)
    s28 = next(m for m in trends.build_trends(conn, "fixture", ANCHOR, 28, True)["metrics"] if m["metric"] == "resting_hr")["summary"]
    assert s28["enough"] and s28["previous_n"] >= 9 and s28["change"] is not None
    s90 = next(m for m in trends.build_trends(conn, "fixture", ANCHOR, 90, True)["metrics"] if m["metric"] == "resting_hr")["summary"]
    assert not s90["enough"] and s90["change"] is None


def test_weekly_volume_matches_hand_count(tmp_path):
    conn = synced(tmp_path)
    ws = date(2026, 9, 21)
    r = weekly.build_weekly(conn, "fixture", ws, True)
    vol = next(f for f in r["findings"] if f["metric"] == "weekly_moving_time")
    rows = conn.execute("SELECT COUNT(*), SUM(moving_s) FROM activity WHERE local_date BETWEEN '2026-09-21' AND '2026-09-27'").fetchone()
    assert vol["observed"]["runs"] == rows[0] == 4  # fixture runs Mon, Wed, Fri, Sat
    assert vol["observed"]["value"] == rows[1]
    assert r["week_end"] == "2026-09-27" and r["next_week_focus"]["rule"].startswith("F")


def test_weekly_pain_takes_priority_and_old_weeks_are_frozen(tmp_path):
    conn = synced(tmp_path)
    conn.execute("INSERT INTO checkin (id, local_date, energy, pain, client_updated_at, received_at) VALUES ('p','2026-09-23',3,1,'x','x')")
    assert weekly.build_weekly(conn, "fixture", date(2026, 9, 21), True)["next_week_focus"]["rule"] == "F1"
    weekly.regenerate_weeklies(conn, "fixture", ANCHOR, True)
    old = conn.execute("SELECT MAX(revision) FROM report WHERE type='weekly' AND subject_key='2026-08-10'").fetchone()[0]
    conn.execute("INSERT INTO checkin (id, local_date, energy, pain, client_updated_at, received_at) VALUES ('q','2026-08-12',3,1,'x','x')")
    weekly.regenerate_weeklies(conn, "fixture", ANCHOR, True)
    assert conn.execute("SELECT MAX(revision) FROM report WHERE type='weekly' AND subject_key='2026-08-10'").fetchone()[0] == old


def test_revisions_endpoint_lists_history(tmp_path):
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    token = create_token(tmp_path, "t")
    client = TestClient(create_app(c, connector=FixtureConnector(ANCHOR)))
    h = {"Authorization": f"Bearer {token}"}
    r1 = client.get("/v1/today", params={"date": "2026-09-30"}, headers=h).json()
    client.put("/v1/checkins/a", json={"local_date": "2026-09-30", "energy": 1, "client_updated_at": "2026-09-30T06:00:00Z"}, headers=h)
    r2 = client.get("/v1/today", params={"date": "2026-09-30"}, headers=h).json()
    revs = client.get("/v1/reports/morning/2026-09-30/revisions", headers=h).json()
    assert [x["revision"] for x in revs] == [r2["revision"], r1["revision"]]
    assert client.get(f"/v1/reports/{revs[-1]['id']}", headers=h).json()["revision"] == r1["revision"]
    assert client.get("/v1/trends", params={"days": 13}, headers=h).status_code == 422
    for d in (7, 28, 90):  # valid ranges arrive as query strings and must be accepted
        r = client.get("/v1/trends", params={"days": d}, headers=h)
        assert r.status_code == 200 and len(r.json()["metrics"][0]["points"]) == d

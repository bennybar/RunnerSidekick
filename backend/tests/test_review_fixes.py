"""Regressions for the second external review (2026-10-01)."""
import json
from datetime import date, datetime, timedelta

from sidekick import focus as fc
from sidekick import reports as rp
from sidekick.analytics import insights as ins
from sidekick.connectors.base import Samples
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)
LAST_WEEK = fc.week_start(ANCHOR) - timedelta(days=7)


def synced(tmp_path):
    conn = connect(tmp_path / "t.db")
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 60, 3, max_backfill_days=90)
    return conn


def set_zones(conn, floors):
    with conn:
        conn.execute("INSERT INTO user_settings VALUES ('source_hr_zones', ?) ON CONFLICT (key) DO UPDATE SET value_json=excluded.value_json",
                     (json.dumps({"floors": floors, "method": "HR_MAX", "max_hr": 189}),))


def test_runs_without_heart_rate_do_not_crash_intensity():
    s = Samples(t=[float(i) for i in range(0, 1200, 5)], hr=[None] * 240, speed=[3.0] * 240, dist=[None] * 240, elev=[None] * 240,
                cad=[None] * 240)
    runs = [ins.RunData(f"r{k}", "2026-09-01", datetime.min, None, 4000, 1200, None, s, [], "steady") for k in range(8)]
    out = ins.intensity_distribution(runs, {"floors": [95, 113, 132, 151, 170]})
    assert out["verdict"] == "not_enough_data"


def test_recovery_focus_counts_only_zones_4_and_5(tmp_path):
    conn = synced(tmp_path)
    set_zones(conn, [95, 113, 132, 200, 210])  # every fixture sample sits in zone 3
    r = fc.evaluate(conn, "fixture", LAST_WEEK, "recovery", ANCHOR)
    assert r["runs"] and not any(x["value"] >= 50 for x in r["runs"])
    assert r["status"] == "achieved"


def test_recovery_without_zones_is_unavailable_not_achieved(tmp_path):
    conn = synced(tmp_path)
    with conn:
        conn.execute("DELETE FROM user_settings WHERE key='source_hr_zones'")
    r = fc.evaluate(conn, "fixture", LAST_WEEK, "recovery", ANCHOR)
    assert r["status"] == "unavailable"


def test_no_zones_preference_is_respected(tmp_path):
    conn = synced(tmp_path)
    set_zones(conn, [95, 113, 132, 151, 170])
    with conn:
        conn.execute("INSERT INTO user_settings VALUES ('hr_zone_source', '\"none\"')")
        conn.execute("INSERT INTO day_plan VALUES (?, 'easy', 40, 'x')", (ANCHOR.isoformat(),))
    m = rp.build_morning(conn, "fixture", ANCHOR, True)
    assert "bpm" not in m["recommendation"]["suggestion"]
    assert rp.hr_zones(conn) is None


def test_zone_change_revises_the_morning_target(tmp_path):
    conn = synced(tmp_path)
    with conn:
        conn.execute("INSERT INTO day_plan VALUES (?, 'easy', 40, 'x')", (ANCHOR.isoformat(),))
    set_zones(conn, [95, 113, 132, 151, 170])
    a = rp.build_morning(conn, "fixture", ANCHOR, True)
    set_zones(conn, [95, 113, 142, 160, 175])
    b = rp.build_morning(conn, "fixture", ANCHOR, True)
    assert "132 bpm" in a["recommendation"]["suggestion"]
    assert "142 bpm" in b["recommendation"]["suggestion"] and b["revision"] > a["revision"]


def test_low_recovery_without_readings_is_not_called_typical():
    rec = {"state": "consider_easier", "rule_id": "R4s", "reason": "You reported feeling less recovered."}
    assert "typical" not in rp.headline(rec, [], {"recovery": 2})

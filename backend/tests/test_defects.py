"""Reproductions of earlier review findings, kept as regression tests."""
import json
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from helpers import add_checkin
from sidekick import focus as fc
from sidekick import highlights
from sidekick import narrative as nv
from sidekick import reports as rp
from sidekick import summaries as sm
from sidekick.api import create_app
from sidekick.auth import create_token
from sidekick.coach import Bundle
from sidekick.config import Config
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


def synced():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    return conn


def client(tmp_path):
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    return TestClient(create_app(c, connector=FixtureConnector(ANCHOR))), {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}


def test_settings_clear_and_ai_switch_off(tmp_path):
    cl, h = client(tmp_path)
    cl.put("/v1/settings", json={"ai_enabled": True, "goal": "sub 25 5k", "race_date": "2026-12-01", "race_distance": "10k"}, headers=h)
    s = cl.put("/v1/settings", json={"ai_enabled": False, "goal": None, "race_date": None, "race_distance": None}, headers=h).json()
    assert s["ai_enabled"] is False and s["goal"] is None and s["race_date"] is None


def test_impossible_dates_are_rejected_and_never_break_today(tmp_path):
    cl, h = client(tmp_path)
    assert cl.put("/v1/settings", json={"race_date": "2026-02-30"}, headers=h).status_code == 422
    assert cl.put("/v1/settings", json={"profile_birth_date": "1983-13-01"}, headers=h).status_code == 422
    assert cl.get("/v1/today", params={"date": "2026-02-30"}, headers=h).status_code == 422
    conn = connect(user_db_name(1, "fixture"))  # an impossible date stored before validation existed
    conn.user_settings.update_one({"key": "race_date"}, {"$set": {"value": "2026-02-30"}}, upsert=True)
    conn.user_settings.update_one({"key": "race_distance"}, {"$set": {"value": "10k"}}, upsert=True)
    assert cl.get("/v1/today", headers=h).status_code == 200


class Fake:
    name, model = "fake", "m"

    def __init__(self):
        self.calls = 0

    def generate(self, *a):
        self.calls += 1
        return json.dumps({"sentences": [{"text": "Steady.", "evidence_ids": ["x"]}]})


def test_failed_summary_is_retried_after_half_an_hour():
    conn = synced()
    b = Bundle()
    b.item("x", "thing", v=1)
    h = sm.input_hash(b, "m")
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    from sidekick.db import next_id
    conn.section_summary.insert_one({"id": next_id(conn, "section_summary"), "kind": "compare", "local_date": ANCHOR.isoformat(), "input_hash": h, "model": "m",
                                     "prompt_version": sm.PROMPT_VERSION, "status": "failed", "detail": "Timeout", "output": None,
                                     "created_at": old})
    p = Fake()
    assert sm.generate(conn, "compare", b, ANCHOR, "m", "k", 25, provider=p)["status"] == "ok" and p.calls == 1


def test_budget_counter_never_lets_more_calls_through_than_the_limit():
    conn = synced()
    conn.ai_call.insert_one({"id": 999, "feature": "coach", "created_at": nv.utc_now(), "outcome": "ok"})  # made before the counter
    got = [nv.reserve_call(conn, "coach", 3) for _ in range(4)]
    assert sum(g is not None for g in got) == 2  # 1 already used + 2 = the limit of 3


def test_automatic_focus_switches_to_recovery_after_pain():
    conn = synced()
    first = fc.current(conn, "fixture", ANCHOR)["current"]
    assert first and first["auto"]
    add_checkin(conn, "p", ANCHOR.isoformat(), pain=True)
    assert fc.current(conn, "fixture", ANCHOR)["current"]["kind"] == "recovery"


def test_best_highlight_uses_only_the_latest_revision():
    conn = synced()
    sid = rp.activities(conn, "fixture", "2026-09-24", ANCHOR.isoformat())[-1]["source_id"]
    rp.build_post_run(conn, "fixture", sid, True)
    r = conn.report.find_one({"type": "post_run", "subject_key": sid}, sort=[("revision", -1)])
    best = {"label": "5 km", "elapsed_s": 1500, "previous_best_s": 1600}
    # Latest revision: no longer a best. An older revision of the same run still says it was.
    conn.report.update_one({"_id": r["_id"]}, {"$set": {"body.best_efforts": {"5k": {**best, "is_best": False}}}})
    from sidekick.db import next_id
    conn.report.insert_one({**{k: v for k, v in r.items() if k != "_id"}, "id": next_id(conn, "report"), "revision": r["revision"] - 1,
                            "body": {**r["body"], "best_efforts": {"5k": {**best, "is_best": True}}}})
    ids = [x["id"] for x in highlights.build(conn, "fixture", ANCHOR, {"items": [], "missing": ["sex"]}, None, None)]
    assert "best:5k" not in ids


def test_unchanged_get_is_an_empty_304(tmp_path):
    cl, h = client(tmp_path)
    first = cl.get("/v1/settings", headers=h)
    tag = first.headers["etag"]
    again = cl.get("/v1/settings", headers={**h, "If-None-Match": tag})
    assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == tag
    cl.put("/v1/settings", json={"goal": "new goal"}, headers=h)
    changed = cl.get("/v1/settings", headers={**h, "If-None-Match": tag})
    assert changed.status_code == 200 and changed.json()["goal"] == "new goal"


def test_run_caches_follow_the_database_and_the_run_revision():
    conn = synced()
    a = rp.activities(conn, "fixture", "2026-09-01", ANCHOR.isoformat())[-1]
    k = rp.run_key(conn, a)
    assert k != rp.run_key(conn, {**a, "updated_at": "2099-01-01T00:00:00Z"})  # corrected samples: recomputed
    other = connect(user_db_name(2, "fixture"))
    assert k != rp.run_key(other, a)  # another user's run with the same id: never shared

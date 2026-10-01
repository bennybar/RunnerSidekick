import json
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from sidekick import reports as rp
from sidekick import run_ai
from sidekick.api import create_app
from sidekick.auth import create_token
from sidekick.coach import CoachError
from sidekick.config import Config
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)
SID = "fx-run-2026-09-28"


class Fake:
    name = "fake"

    def __init__(self, make):
        self.make, self.calls = make, 0

    def generate(self, system, bundle, schema, timeout_s, max_output_tokens):
        self.calls += 1
        return json.dumps(self.make(bundle))


def good(bundle, direction="easier"):
    p = {"text": "Your pace held at {fact:pace} (run:this).", "evidence_ids": ["run:this"]}
    return {"summary": "A steady run for its purpose.", "summary_evidence_ids": ["run:this"], "went_well": [p],
            "to_work_on": [{"text": "Ease the opening.", "evidence_ids": ["run:this"]}],
            "next_time": {"text": "Keep the next one easy.", "evidence_ids": ["today:advice"], "direction": direction}}


@pytest.fixture
def conn():
    c = connect(user_db_name(1, "fixture"))
    run_sync(c, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    rp.regenerate(c, "fixture", True, set(), [], ANCHOR)
    rp.build_post_run(c, "fixture", SID, True)
    c.run_intent.insert_one({"activity_source_id": SID, "kind": "easy", "note": "PRIVATE NOTE knee felt odd", "source": "user",
                             "client_updated_at": "x"})
    rp.build_post_run(c, "fixture", SID, True)
    return c


def test_bundle_has_context_and_no_private_text(conn):
    b = run_ai.bundle(conn, "fixture", SID, ANCHOR)
    s = json.dumps(b.to_json())
    assert "PRIVATE NOTE" not in s and "[Synthetic]" not in s and SID not in s
    assert {"run:this", "week:of_run", "today:advice"} <= set(b.items) and "pace" in b.facts
    assert b.items["run:this"]["meant_to_be"] == "easy"


def test_renders_facts_caches_and_rejects_unsupported(conn):
    b = run_ai.bundle(conn, "fixture", SID, ANCHOR)
    p = Fake(good)
    v = run_ai.generate(conn, "fixture", SID, b, "m", "k", "server", 20, provider=p)
    assert v["status"] == "ok" and "{fact:" not in v["went_well"][0]["text"] and "run:this" not in v["went_well"][0]["text"]
    run_ai.generate(conn, "fixture", SID, b, "m", "k", "server", 20, provider=p)
    assert p.calls == 1
    b.items["today:advice"]["intensity_held_back"] = True
    with pytest.raises(CoachError, match="harder"):
        run_ai.validate(json.dumps(good(None, "harder")), b)
    with pytest.raises(CoachError, match="numbers"):
        run_ai.validate(json.dumps({**good(None), "summary": "You ran 8 km."}), b)


def test_endpoint_only_generates_on_request(tmp_path):
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    p = Fake(good)
    client = TestClient(create_app(c, connector=FixtureConnector(ANCHOR), run_ai_provider=p))
    client.app.state.do_sync(c.__class__(**{**c.__dict__, "user_id": 1}), 1)
    client.put("/v1/settings", json={"ai_enabled": True}, headers=h)
    sid = client.get("/v1/activities", headers=h).json()[0]["source_id"]
    client.get(f"/v1/activities/{sid}", headers=h)
    assert client.get(f"/v1/activities/{sid}/ai", headers=h).json()["status"] == "none" and p.calls == 0
    assert client.post(f"/v1/activities/{sid}/ai", headers=h).json()["status"] in ("pending", "ok")
    for _ in range(100):
        v = client.get(f"/v1/activities/{sid}/ai", headers=h).json()
        if v["status"] == "ok":
            break
        time.sleep(0.05)
    assert v["status"] == "ok" and v["next_time"]["direction"] in ("easier", "same", "harder") and p.calls == 1
    assert client.get("/v1/activities/nope/ai", headers=h).status_code == 404


def test_retry_reports_pending_not_the_old_failure(tmp_path):
    import threading
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    gate = threading.Event()
    calls = []

    class Slow:
        name = "slow"

        def generate(self, *a):
            calls.append(1)
            if len(calls) == 1:
                raise TimeoutError()
            gate.wait(5)
            return json.dumps(good(None))

    client = TestClient(create_app(c, connector=FixtureConnector(ANCHOR), run_ai_provider=Slow()))
    client.app.state.do_sync(c.__class__(**{**c.__dict__, "user_id": 1}), 1)
    client.put("/v1/settings", json={"ai_enabled": True}, headers=h)
    sid = client.get("/v1/activities", headers=h).json()[0]["source_id"]
    client.get(f"/v1/activities/{sid}", headers=h)
    client.post(f"/v1/activities/{sid}/ai", headers=h)
    for _ in range(100):
        if client.get(f"/v1/activities/{sid}/ai", headers=h).json()["status"] == "failed":
            break
        time.sleep(0.05)
    client.post(f"/v1/activities/{sid}/ai", headers=h)  # retry
    assert client.get(f"/v1/activities/{sid}/ai", headers=h).json()["status"] == "pending"
    gate.set()

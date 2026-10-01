import json
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from sidekick import compare
from sidekick import summaries as sm
from sidekick.api import create_app
from sidekick.auth import create_token
from sidekick.coach import CoachError
from sidekick.config import Config
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, user_db_name
from sidekick.sync import run_sync
from sidekick.trends import build_trends

ANCHOR = date(2026, 9, 30)


class Fake:
    name = "fake"

    def __init__(self, make):
        self.make, self.calls = make, 0

    def generate(self, system, bundle, schema, timeout_s, max_output_tokens):
        self.calls += 1
        return json.dumps(self.make(bundle))


def good(bundle):
    fid = next(iter(bundle["facts"]))
    eid = bundle["evidence"][0]["id"]
    return {"sentences": [{"text": f"The clearest point is {{fact:{fid}}} ({eid}).", "evidence_ids": [eid]}]}


@pytest.fixture
def conn():
    c = connect(user_db_name(1, "fixture"))
    run_sync(c, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    return c


def test_compare_and_trends_bundles_carry_facts_and_caveats(conn):
    b = sm.compare_bundle(compare.build(conn, "fixture", ANCHOR))
    assert "vo2max" in b.facts and "resting_hr" in b.facts and b.items["compare:resting_hr"]["caveats"]
    t = sm.trends_bundle(build_trends(conn, "fixture", ANCHOR, 28, True))
    assert "trend:resting_hr" in t.items and "days" in t.facts


def test_daily_summary_renders_facts_and_is_cached_per_day(conn):
    b = sm.trends_bundle(build_trends(conn, "fixture", ANCHOR, 28, True))
    p = Fake(good)
    v = sm.generate(conn, "trends:28", b, ANCHOR, "m", "k", 20, provider=p)
    assert v["status"] == "ok" and "{fact:" not in v["sentences"][0]["text"] and "window:days" not in v["sentences"][0]["text"]
    sm.generate(conn, "trends:28", b, ANCHOR, "m", "k", 20, provider=p)
    assert p.calls == 1
    sm.generate(conn, "trends:28", b, date(2026, 10, 1), "m", "k", 20, provider=p)
    assert p.calls == 2  # a new day gets a new summary


@pytest.mark.parametrize("bad,why", [
    ({"sentences": [{"text": "You ran 3 times.", "evidence_ids": ["window:days"]}]}, "numbers"),
    ({"sentences": [{"text": "Fine.", "evidence_ids": []}]}, "at least one"),
    ({"sentences": [{"text": "This causes fatigue.", "evidence_ids": ["window:days"]}]}, "disallowed"),
    ({"sentences": []}, "number of sentences"),
])
def test_unsupported_summaries_rejected(conn, bad, why):
    b = sm.trends_bundle(build_trends(conn, "fixture", ANCHOR, 28, True))
    with pytest.raises(CoachError, match=why):
        sm.validate(json.dumps(bad), b)


def test_endpoints_attach_summary_when_ai_enabled(tmp_path):
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    client = TestClient(create_app(c, connector=FixtureConnector(ANCHOR), summary_provider=Fake(good)))
    client.app.state.do_sync(c.__class__(**{**c.__dict__, "user_id": 1}), 1)
    assert client.get("/v1/compare", headers=h).json()["ai_summary"]["status"] == "disabled"
    client.put("/v1/settings", json={"ai_enabled": True}, headers=h)
    for path in ("/v1/compare", "/v1/trends?days=28"):
        for _ in range(100):
            s = client.get(path, headers=h).json()["ai_summary"]
            if s["status"] == "ok":
                break
            time.sleep(0.05)
        assert s["status"] == "ok" and s["sentences"]

"""Watchletic connection through its MCP endpoint: registration, PKCE sign-in finished by the app, rotating refresh
tokens, and MCP calls answered as JSON or as a server-sent event."""

import json
import os
import stat
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from sidekick import accounts
from sidekick import watchletic as wl
from sidekick.auth import create_token
from sidekick.db import connect, user_db_name
from test_multiuser import client


@pytest.fixture
def watchletic_mock():
    import fitgen
    calls, state = [], {"refresh": "r1", "n": 0, "start": datetime(2026, 9, 29, 5, tzinfo=timezone.utc)}

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        path = req.url.path
        if path == "/oauth/register":
            body = json.loads(req.content)
            return httpx.Response(201, json={"client_id": "rs-client", "redirect_uris": body["redirect_uris"]})
        if path == "/oauth/token":
            form = parse_qs(req.content.decode())
            if form["grant_type"] == ["authorization_code"]:
                assert form["code"] == ["good-code"] and form["resource"] == [wl.RESOURCE]
                return httpx.Response(200, json={"access_token": "a1", "refresh_token": "r1", "expires_in": 3600})
            if form["refresh_token"] != [state["refresh"]]:
                return httpx.Response(400, json={"error": "invalid_grant"})  # a reused refresh token
            state["n"] += 1
            state["refresh"] = f"r{state['n'] + 1}"
            return httpx.Response(200, json={"access_token": f"a{state['n'] + 1}", "refresh_token": state["refresh"], "expires_in": 3600})
        if path.startswith("/mcp/download/"):
            return httpx.Response(200, content=fitgen.run(state["start"]), headers={"content-type": "application/vnd.ant.fit"})
        if path == "/mcp":
            msg = json.loads(req.content)
            if "id" not in msg:
                return httpx.Response(202)
            if msg["method"] == "initialize":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": "2025-06-18"}},
                                      headers={"mcp-session-id": "s1"})
            assert req.headers["mcp-session-id"] == "s1"
            if msg["method"] == "tools/list":
                # As a server-sent event, which Streamable HTTP allows
                ev = json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [{"name": "get_training_context"}]}})
                return httpx.Response(200, text=f"event: message\ndata: {ev}\n\n", headers={"content-type": "text/event-stream"})
            name, args = msg["params"].get("name"), msg["params"].get("arguments", {})
            out = {}
            if name == "list_activities":
                out = {"data": [{"id": "w-run", "revision": "r1", "durationSeconds": 900, "distanceMeters": 1440},
                                {"id": "w-test", "revision": "r1", "durationSeconds": 33, "distanceMeters": 0}], "nextCursor": None}
            elif name == "export_activity_file":
                assert args == {"activityId": "w-run", "format": "fit"}  # the test recording isn't downloaded
                out = {"downloadUrl": "https://api.watchletic.com/mcp/download/wld_x"}
            elif name == "get_training_context":
                assert args["timeZone"] == "Asia/Jerusalem"
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"structuredContent": out}})
        return httpx.Response(404)

    wl.transport = httpx.MockTransport(handler)
    yield calls, state
    wl.transport = None


def test_watchletic_connect_flow(tmp_path, watchletic_mock):
    calls, state = watchletic_mock
    c = client(tmp_path)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 'o')}"}
    c.put("/v1/settings", json={"watch": "samsung"}, headers=h)
    assert c.get("/v1/watchletic", headers=h).json()["connected"] is False
    url = c.post("/v1/watchletic/start", headers=h).json()["authorize_url"]
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert q["client_id"] == "rs-client" and q["code_challenge_method"] == "S256" and q["scope"] == "watchletic.read"
    assert q["resource"] == wl.RESOURCE and q["redirect_uri"].endswith("/v1/watchletic/callback")
    # The callback page only hands the answer to the app
    page = c.get("/v1/watchletic/callback", params={"state": q["state"], "code": "good-code"})
    assert "runnersidekick://watchletic-callback?" in page.text
    assert c.post("/v1/watchletic/complete", json={"state": "nope", "code": "good-code"}, headers=h).status_code == 409
    assert c.post("/v1/watchletic/complete", json={"state": q["state"], "code": "good-code"}, headers=h).json() == {"connected": True}
    tok = tmp_path / "users" / "1" / "watchletic_oauth.json"
    assert stat.S_IMODE(os.stat(tok).st_mode) == 0o600
    for _ in range(100):  # the first look back runs on its own
        if json.loads(tok.read_text()).get("last_sync"):
            break
        time.sleep(0.05)
    # The run came in from its FIT file, filed on the Samsung watch; the 33 s test recording didn't
    conn = connect(user_db_name(1, "fixture"))
    assert [a["source_id"] for a in conn.activity.find({})] == [f"fit-{int(state['start'].timestamp())}"]
    assert {s["id"]: s["note"] for s in conn.watchletic_seen.find({})} == {"w-run": "imported", "w-test": "too short to be a run"}
    assert {r["kind"] for r in conn.watchletic_raw.find({})} >= {"readiness", "context", "fitness", "tools"}
    # Seen at the same revision: nothing new the next time
    assert c.post("/v1/watchletic/sync", headers=h).json()["new_runs"] == 0
    # The client is registered once and reused
    assert sum(1 for x in calls if x.url.path == "/oauth/register") == 1
    # An expired access token is refreshed, and the rotated refresh token is the one kept
    data = json.loads(tok.read_text())
    tok.write_text(json.dumps({**data, "expires_at": 0}))
    assert c.post("/v1/watchletic/sync", headers=h).json()["connected"] is True
    assert json.loads(tok.read_text())["refresh_token"] == state["refresh"] == "r2"
    # Disconnecting removes the tokens
    assert c.delete("/v1/watchletic", headers=h).json() == {"disconnected": True}
    assert not tok.exists() and c.get("/v1/watchletic", headers=h).json()["connected"] is False
    assert accounts.app_db().oauth_states.count_documents({"provider": "watchletic"}) == 0

"""Watchletic connection through its MCP endpoint: registration, PKCE sign-in finished by the app, rotating refresh
tokens, and MCP calls answered as JSON or as a server-sent event."""

import json
import os
import stat
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from sidekick import accounts
from sidekick import watchletic as wl
from sidekick.auth import create_token
from test_multiuser import client


@pytest.fixture
def watchletic_mock():
    calls, state = [], {"refresh": "r1", "n": 0}

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
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"structuredContent": {"recent": []}}})
        return httpx.Response(404)

    wl.transport = httpx.MockTransport(handler)
    yield calls, state
    wl.transport = None


def test_watchletic_connect_flow(tmp_path, watchletic_mock):
    calls, state = watchletic_mock
    c = client(tmp_path)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 'o')}"}
    assert c.get("/v1/watchletic", headers=h).json()["connected"] is False
    url = c.post("/v1/watchletic/start", headers=h).json()["authorize_url"]
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert q["client_id"] == "rs-client" and q["code_challenge_method"] == "S256" and q["scope"] == "watchletic.read"
    assert q["resource"] == wl.RESOURCE and q["redirect_uri"].endswith("/v1/watchletic/callback")
    # The callback page only hands the answer to the app
    page = c.get("/v1/watchletic/callback", params={"state": q["state"], "code": "good-code"})
    assert "runnersidekick://watchletic-callback?" in page.text
    assert c.post("/v1/watchletic/complete", json={"state": "nope", "code": "good-code"}, headers=h).status_code == 409
    done = c.post("/v1/watchletic/complete", json={"state": q["state"], "code": "good-code"}, headers=h).json()
    assert done["connected"] is True and done["tools"] == ["get_training_context"] and done["context"] is True
    tok = tmp_path / "users" / "1" / "watchletic_oauth.json"
    assert stat.S_IMODE(os.stat(tok).st_mode) == 0o600
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

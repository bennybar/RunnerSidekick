import base64
import hashlib
import json
import os
import stat
import time
from datetime import date
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from sidekick import accounts
from sidekick import garmin_oauth as goauth
from sidekick.api import create_app
from sidekick.auth import create_token
from sidekick.config import Config
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, user_db_name

ANCHOR = date(2026, 9, 30)


def cfg(tmp_path):
    return Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=30, refetch_days=3,
                  raw_retention_days=120, request_spacing_s=0)


def fake_google(claims_by_token):
    def verify(tok):
        from fastapi import HTTPException
        if tok not in claims_by_token:
            raise HTTPException(401, "bad")
        return claims_by_token[tok]
    return verify


GOOGLE = {
    "tok-friend-xxxxxxxxxxxxxxxx": {"sub": "g-friend", "email": "Friend@Example.com", "email_verified": True, "name": "Friend"},
    "tok-stranger-xxxxxxxxxxxxxx": {"sub": "g-stranger", "email": "stranger@example.com", "email_verified": True},
    "tok-unverified-xxxxxxxxxxxx": {"sub": "g-unv", "email": "friend2@example.com", "email_verified": False},
}


def client(tmp_path):
    return TestClient(create_app(cfg(tmp_path), connector=FixtureConnector(ANCHOR), google_verifier=fake_google(GOOGLE)))


def wait_sync(c, h):
    c.post("/v1/sync", headers=h)
    for _ in range(100):
        if not c.get("/v1/status", headers=h).json()["sync_running"]:
            return
        time.sleep(0.05)


def test_sqlite_data_imports_into_mongo_and_old_token_keeps_working(tmp_path):
    import sqlite3
    from sidekick.migrate_sqlite import NotEmpty, migrate_all
    app = sqlite3.connect(tmp_path / "app.db")
    app.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, google_sub TEXT, name TEXT, role TEXT, created_at TEXT, deleted_at TEXT);
        CREATE TABLE sessions (id INTEGER PRIMARY KEY, user_id INT, name TEXT, token_sha256 TEXT, created_at TEXT, last_used_at TEXT, revoked_at TEXT);
        INSERT INTO users VALUES (1, 'me@example.com', NULL, 'Owner', 'owner', 'x', NULL);""")
    app.execute("INSERT INTO sessions VALUES (7, 1, 'phone', ?, 'x', NULL, NULL)", (hashlib.sha256(b"rsk_legacy").hexdigest(),))
    app.commit(); app.close()
    (tmp_path / "users" / "1").mkdir(parents=True)
    u = sqlite3.connect(tmp_path / "users" / "1" / "garmin.db")
    u.executescript("""
        CREATE TABLE report (id INTEGER PRIMARY KEY, type TEXT, subject_key TEXT, local_date TEXT, revision INT, generated_at TEXT,
                             data_cutoff TEXT, input_hash TEXT, algorithm_version TEXT, body_json TEXT);
        CREATE TABLE checkin (id TEXT PRIMARY KEY, local_date TEXT, energy INT, soreness INT, recovery INT, pain INT, illness INT,
                              notes TEXT, tags_json TEXT, client_updated_at TEXT, received_at TEXT, deleted INT);
        CREATE TABLE user_settings (key TEXT PRIMARY KEY, value_json TEXT);
        INSERT INTO report VALUES (41, 'morning', '2026-09-30', '2026-09-30', 1, 'x', '', 'h', '{"report": "r"}', '{"id": 41, "headline": "Hi"}');
        INSERT INTO checkin VALUES ('c', '2026-09-30', 3, NULL, 2, 1, 0, NULL, '["a"]', 'x', 'x', 0);
        INSERT INTO user_settings VALUES ('goal_type', '"performance"');""")
    u.commit(); u.close()
    print(migrate_all(tmp_path))
    a = accounts.app_db()
    assert accounts.verify_session(a, "rsk_legacy")["role"] == "owner"
    d = connect(user_db_name(1, "garmin"))
    assert d.report.find_one({"id": 41})["body"]["headline"] == "Hi"
    c = d.checkin.find_one({"id": "c"})
    assert c["pain"] is True and c["illness"] is False and c["tags"] == ["a"]
    assert d.user_settings.find_one({"key": "goal_type"})["value"] == "performance"
    assert accounts.create_session(a, 1, "new") and a.sessions.find_one({"name": "new"})["id"] == 8  # ids continue
    with pytest.raises(NotEmpty):
        migrate_all(tmp_path)  # never silently overwrites
    assert (tmp_path / "users" / "1" / "garmin.db").exists()  # SQLite left in place as a backup


def test_invite_only_google_sign_in(tmp_path):
    c = client(tmp_path)
    assert c.post("/v1/auth/google", json={"id_token": "tok-stranger-xxxxxxxxxxxxxx"}).status_code == 403
    assert c.post("/v1/auth/google", json={"id_token": "tok-unverified-xxxxxxxxxxxx"}).status_code == 403
    assert c.post("/v1/auth/google", json={"id_token": "not-a-real-google-token-xx"}).status_code == 401
    a = accounts.app_db()
    accounts.add_invite(a, "friend@example.com")
    r = c.post("/v1/auth/google", json={"id_token": "tok-friend-xxxxxxxxxxxxxxxx"})
    assert r.status_code == 200 and r.json()["token"].startswith("rsk_") and r.json()["user"]["email"] == "friend@example.com"
    again = c.post("/v1/auth/google", json={"id_token": "tok-friend-xxxxxxxxxxxxxxxx"}).json()
    assert again["user"]["id"] == r.json()["user"]["id"]  # same account, new session
    me = c.get("/v1/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()
    assert me["role"] == "member"


def test_owner_can_link_google_by_email(tmp_path):
    c = client(tmp_path)
    a = accounts.app_db()
    accounts.set_owner_email(a, "friend@example.com")  # owner's address, no invite needed
    r = c.post("/v1/auth/google", json={"id_token": "tok-friend-xxxxxxxxxxxxxxxx"}).json()
    assert r["user"]["role"] == "owner"


def test_users_cannot_see_each_others_data(tmp_path):
    c = client(tmp_path)
    owner_h = {"Authorization": f"Bearer {create_token(tmp_path, 'owner-phone')}"}
    accounts.add_invite(accounts.app_db(), "friend@example.com")
    friend_h = {"Authorization": "Bearer " + c.post("/v1/auth/google", json={"id_token": "tok-friend-xxxxxxxxxxxxxxxx"}).json()["token"]}
    wait_sync(c, owner_h)
    assert len(c.get("/v1/activities", headers=owner_h).json()) > 0
    assert c.get("/v1/activities", headers=friend_h).json() == []
    c.put("/v1/checkins/x", json={"local_date": "2026-09-30", "energy": 2, "client_updated_at": "2026-09-30T06:00:00Z"}, headers=friend_h)
    assert c.get("/v1/checkins", headers=owner_h).json() == []
    from sidekick.db import client as mongo
    names = mongo().list_database_names()
    assert user_db_name(1, "fixture") in names and user_db_name(2, "fixture") in names


def test_account_deletion_removes_data_and_sessions(tmp_path):
    c = client(tmp_path)
    accounts.add_invite(accounts.app_db(), "friend@example.com")
    r = c.post("/v1/auth/google", json={"id_token": "tok-friend-xxxxxxxxxxxxxxxx"}).json()
    h = {"Authorization": f"Bearer {r['token']}"}
    from sidekick.db import client as mongo
    folder = tmp_path / "users" / str(r["user"]["id"])
    c.put("/v1/checkins/x", json={"local_date": "2026-09-30", "energy": 2, "client_updated_at": "2026-09-30T06:00:00Z"}, headers=h)
    assert folder.exists() and user_db_name(r["user"]["id"], "fixture") in mongo().list_database_names()
    assert c.delete("/v1/account", headers=h).json() == {"deleted": True}
    assert not folder.exists() and user_db_name(r["user"]["id"], "fixture") not in mongo().list_database_names()
    assert c.get("/v1/status", headers=h).status_code == 401
    owner_h = {"Authorization": f"Bearer {create_token(tmp_path, 'o')}"}
    assert c.delete("/v1/account", headers=owner_h).status_code == 409


def test_google_sign_in_unconfigured_is_503(tmp_path):
    c = TestClient(create_app(cfg(tmp_path), connector=FixtureConnector(ANCHOR)))
    assert c.post("/v1/auth/google", json={"id_token": "x" * 30}).status_code == 503


# ---------------------------------------------------------------- Garmin OAuth (PKCE), Garmin servers mocked

@pytest.fixture
def garmin_mock():
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        if req.url.host == "diauth.garmin.com":
            form = parse_qs(req.content.decode())
            grant = form["grant_type"][0]
            if grant == "authorization_code" and form.get("code") == ["good-code"]:
                return httpx.Response(200, json={"access_token": "AT1", "refresh_token": "RT1", "expires_in": 86400,
                                                 "token_type": "bearer", "refresh_token_expires_in": 7775998})
            if grant == "refresh_token" and form["refresh_token"] == ["RT1"]:
                return httpx.Response(200, json={"access_token": "AT2", "refresh_token": "RT2", "expires_in": 86400})
            return httpx.Response(400, json={"error": "invalid_grant"})
        if req.url.path.endswith("/user/id"):
            return httpx.Response(200, json={"userId": "garmin-123"})
        if req.url.path.endswith("/user/registration") and req.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404)

    goauth.transport = httpx.MockTransport(handler)
    yield calls
    goauth.transport = None


def test_garmin_connect_flow(tmp_path, garmin_mock):
    c = client(tmp_path)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 'o')}"}
    assert c.post("/v1/garmin/oauth/start", headers=h).status_code == 503  # not configured yet
    (tmp_path / "secrets.json").write_text(json.dumps({"garmin_client_id": "cid", "garmin_client_secret": "csecret"}))
    url = c.post("/v1/garmin/oauth/start", headers=h).json()["authorize_url"]
    u = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert f"{u.scheme}://{u.netloc}{u.path}" == "https://connect.garmin.com/oauth2Confirm"
    assert q["response_type"] == "code" and q["client_id"] == "cid" and q["code_challenge_method"] == "S256"
    verifier = accounts.app_db().oauth_states.find_one({"state": q["state"]})["code_verifier"]
    assert 43 <= len(verifier) <= 128
    assert q["code_challenge"] == base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    page = c.get("/v1/garmin/oauth/callback", params={"state": q["state"], "code": "good-code"})
    assert "Garmin connected" in page.text
    tok_file = tmp_path / "users" / "1" / "garmin_oauth.json"
    assert stat.S_IMODE(os.stat(tok_file).st_mode) == 0o600
    exchange = parse_qs(garmin_mock[0].content.decode())
    assert exchange["code_verifier"] == [verifier] and exchange["client_secret"] == ["csecret"]
    st = c.get("/v1/status", headers=h).json()["garmin_official"]
    assert st["connected"] and st["garmin_user_id"] == "garmin-123"
    # state is single-use
    assert "expired or was already used" in c.get("/v1/garmin/oauth/callback", params={"state": q["state"], "code": "good-code"}).text
    # refresh when close to expiry
    d = json.loads(tok_file.read_text()); d["expires_at"] = time.time() + 60; tok_file.write_text(json.dumps(d))
    assert goauth.access_token(tok_file.parent, "cid", "csecret") == "AT2"
    # disconnect deregisters with Garmin and forgets tokens
    assert c.delete("/v1/garmin/connection", headers=h).json() == {"disconnected": True}
    assert any(r.method == "DELETE" and r.url.path.endswith("/user/registration") for r in garmin_mock)
    assert not tok_file.exists()


def test_garmin_callback_rejects_unknown_state_and_cancel(tmp_path):
    c = client(tmp_path)
    assert "not connected" in c.get("/v1/garmin/oauth/callback", params={"state": "nope", "code": "x"}).text.lower()
    assert "cancelled" in c.get("/v1/garmin/oauth/callback", params={"error": "access_denied"}).text

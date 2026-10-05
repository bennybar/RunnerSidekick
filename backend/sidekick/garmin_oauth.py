"""Official Garmin Connect Developer Program sign-in (OAuth 2.0 with PKCE), per Garmin's
"OAuth2.0 PKCE Specification": authorize at connect.garmin.com/oauth2Confirm, exchange and refresh at
diauth.garmin.com/di-oauth2-service/oauth/token, user id at apis.garmin.com/wellness-api/rest/user/id, and
DELETE .../user/registration when a user disconnects or deletes their account (required by Garmin).

Data import via the Health/Activity API (push/ping) is not implemented yet: it needs program approval and the
partner documentation. Until then a connected user's status says so.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets as pysecrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .db import utc_now

AUTHORIZE_URL = "https://connect.garmin.com/oauth2Confirm"
TOKEN_URL = "https://diauth.garmin.com/di-oauth2-service/oauth/token"
USER_ID_URL = "https://apis.garmin.com/wellness-api/rest/user/id"
REGISTRATION_URL = "https://apis.garmin.com/wellness-api/rest/user/registration"
STATE_TTL_S = 600
REFRESH_MARGIN_S = 600  # Garmin recommends refreshing at least 600 s before expiry

# Tests replace this with an httpx.MockTransport.
transport: httpx.BaseTransport | None = None


class NotConfigured(Exception):
    pass


class OAuthError(Exception):
    pass


def _client() -> httpx.Client:
    return httpx.Client(timeout=20.0, transport=transport)


def code_verifier() -> str:
    """43–128 chars from the unreserved set; token_urlsafe(64) gives 86 chars of [A-Za-z0-9_-]."""
    return pysecrets.token_urlsafe(64)


def code_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


BEGIN_TTL_S = 120  # the one-time link the app opens must be used within two minutes


def start(app_conn, user_id: int, client_id: str | None, redirect_uri: str) -> str:
    """The link the app opens: our own one-time /begin page, which ties the flow to that browser (a cookie) and only
    then sends it on to Garmin. A link forwarded to someone else can't finish linking (no cookie in their browser, and
    the ticket is single use)."""
    if not client_id:
        raise NotConfigured("Garmin sign-in isn't available yet: the Garmin developer program access is pending.")
    state, verifier = pysecrets.token_urlsafe(24), code_verifier()
    app_conn.oauth_states.delete_many({"created_at": {"$lt": (datetime.now(timezone.utc) - timedelta(seconds=STATE_TTL_S)).isoformat()
                                                                 .replace("+00:00", "Z")}})
    ticket, nonce = pysecrets.token_urlsafe(24), pysecrets.token_urlsafe(24)
    app_conn.oauth_states.insert_one({"state": state, "user_id": user_id, "code_verifier": verifier, "created_at": utc_now(),
                                      "ticket": ticket, "nonce": nonce, "begun": False})
    return redirect_uri.rsplit("/", 1)[0] + "/begin?" + urlencode({"ticket": ticket})


def begin(app_conn, ticket: str, client_id: str, redirect_uri: str) -> tuple[str, str]:
    """(Garmin's authorize URL, the browser nonce to set as a cookie), once per ticket and within BEGIN_TTL_S."""
    row = app_conn.oauth_states.find_one_and_update({"ticket": ticket, "begun": False}, {"$set": {"begun": True}})
    if row is None:
        raise OAuthError("This link was already used. Please start again from the app.")
    if (datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))).total_seconds() > BEGIN_TTL_S:
        raise OAuthError("This link has expired. Please start again from the app.")
    return AUTHORIZE_URL + "?" + urlencode({
        "client_id": client_id, "response_type": "code", "code_challenge": code_challenge(row["code_verifier"]),
        "code_challenge_method": "S256", "redirect_uri": redirect_uri, "state": row["state"]}), row["nonce"]


def _token_file(user_dir: Path) -> Path:
    return user_dir / "garmin_oauth.json"


def _save(user_dir: Path, data: dict) -> None:
    p = _token_file(user_dir)
    fd = os.open(p.with_suffix(".tmp"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(p.with_suffix(".tmp"), p)


def _store_tokens(user_dir: Path, tok: dict, extra: dict | None = None) -> dict:
    now = time.time()
    data = {"access_token": tok["access_token"], "refresh_token": tok["refresh_token"],
            "expires_at": now + float(tok.get("expires_in", 0)),
            "refresh_expires_at": now + float(tok["refresh_token_expires_in"]) if tok.get("refresh_token_expires_in") else None,
            "updated_at": utc_now(), **(extra or {})}
    _save(user_dir, data)
    return data


def complete(app_conn, state: str, code: str, client_id: str, client_secret: str, redirect_uri: str, user_dir_for,
             nonce: str | None = None, linked_elsewhere=lambda garmin_user, user_id: False) -> int:
    """Callback: validate state and the browser that began it, exchange the code, refuse a Garmin account already linked
    to another user, store tokens in the user's folder. Returns the user id."""
    row = app_conn.oauth_states.find_one_and_delete({"state": state})  # single use
    if row is None:
        raise OAuthError("This sign-in link has expired or was already used. Please try again from the app.")
    if row.get("nonce") and not (nonce and pysecrets.compare_digest(nonce, row["nonce"])):
        raise OAuthError("This connection was started on another device or browser. Please start again from the app.")
    created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
    if (datetime.now(timezone.utc) - created).total_seconds() > STATE_TTL_S:
        raise OAuthError("This sign-in link has expired. Please try again from the app.")
    with _client() as c:
        r = c.post(TOKEN_URL, data={"grant_type": "authorization_code", "client_id": client_id, "client_secret": client_secret,
                                    "code": code, "code_verifier": row["code_verifier"], "redirect_uri": redirect_uri})
        if r.status_code != 200:
            raise OAuthError(f"Garmin rejected the sign-in (HTTP {r.status_code}).")
        tok = r.json()
        uid = c.get(USER_ID_URL, headers={"Authorization": f"Bearer {tok['access_token']}"})
        garmin_user = uid.json().get("userId") if uid.status_code == 200 else None
    if garmin_user and linked_elsewhere(garmin_user, row["user_id"]):
        raise OAuthError("This Garmin account is already linked to another Runner Sidekick account.")
    _store_tokens(user_dir_for(row["user_id"]), tok, {"garmin_user_id": garmin_user})
    return row["user_id"]


def status(user_dir: Path, configured: bool) -> dict:
    p = _token_file(user_dir)
    if not p.exists():
        return {"available": configured, "connected": False}
    d = json.loads(p.read_text())
    return {"available": configured, "connected": True, "garmin_user_id": d.get("garmin_user_id"),
            "data_import": "pending: needs Garmin developer program approval"}


def access_token(user_dir: Path, client_id: str, client_secret: str) -> str | None:
    """A valid access token, refreshed when within REFRESH_MARGIN_S of expiry. None if not connected."""
    p = _token_file(user_dir)
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    if d["expires_at"] - time.time() > REFRESH_MARGIN_S:
        return d["access_token"]
    with _client() as c:
        r = c.post(TOKEN_URL, data={"grant_type": "refresh_token", "refresh_token": d["refresh_token"],
                                    "client_id": client_id, "client_secret": client_secret})
    if r.status_code != 200:
        raise OAuthError(f"Garmin token refresh failed (HTTP {r.status_code}); the user must reconnect.")
    return _store_tokens(user_dir, r.json(), {"garmin_user_id": d.get("garmin_user_id")})["access_token"]


def disconnect(user_dir: Path, client_id: str | None, client_secret: str | None) -> bool:
    """Deregister with Garmin (required when the user disconnects or deletes their account), then forget tokens."""
    p = _token_file(user_dir)
    if not p.exists():
        return False
    try:
        tok = access_token(user_dir, client_id or "", client_secret or "")
        if tok:
            with _client() as c:
                c.delete(REGISTRATION_URL, headers={"Authorization": f"Bearer {tok}"})
    except (OAuthError, httpx.HTTPError):
        pass  # still forget locally; Garmin also lets users revoke from their account settings
    p.unlink(missing_ok=True)
    return True


def linked_users(users_root: Path, garmin_user) -> list[int]:
    """User ids whose stored Garmin connection is this Garmin account."""
    out = []
    for f in users_root.glob("*/garmin_oauth.json"):
        try:
            if json.loads(f.read_text()).get("garmin_user_id") == garmin_user:
                out.append(int(f.parent.name))
        except (ValueError, OSError):
            continue
    return out

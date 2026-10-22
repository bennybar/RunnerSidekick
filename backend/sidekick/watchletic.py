"""Watchletic (a Galaxy Watch / Apple Watch workout app) through its official MCP endpoint, the route Watchletic offers
third-party apps: OAuth 2.1 with S256 PKCE, the client registered dynamically (RFC 7591) with our HTTPS callback.
Read and write (watchletic.read, watchletic.write: write only so the runner can delete a run there too, each time
from the app's delete dialog). Access tokens last an hour; refresh tokens rotate on every use and live 180 days, and
reusing a rotated one revokes the connection, so each refresh is saved before it's used and refreshes never overlap.
Data access needs the user's Watchletic Club membership; without it the tools answer premium_required.
Docs: github.com/watchletic/api (docs/authentication.md, docs/mcp.md)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets as pysecrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .db import utc_now

BASE = "https://api.watchletic.com"
RESOURCE = BASE + "/mcp"
SCOPE = "watchletic.read watchletic.write"
STATE_TTL_S = 600
REFRESH_MARGIN_S = 120
APP_RETURN = "runnersidekick://watchletic-callback"  # the callback page hands the answer to the app

# Tests replace this with an httpx.MockTransport.
transport: httpx.BaseTransport | None = None
_refresh_locks: dict[str, threading.Lock] = {}


class WatchleticError(Exception):
    pass


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0, transport=transport)


def _write_private(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, p)


def client_id(data_dir: Path, redirect_uri: str) -> str:
    """Our registered client (one for the server, kept in its data folder); registered on first use."""
    p = data_dir / "watchletic_client.json"
    if p.exists():
        reg = json.loads(p.read_text())
        if redirect_uri in reg.get("redirect_uris", []) and set(SCOPE.split()) <= set((reg.get("scope") or "").split()):
            return reg["client_id"]
    with _client() as c:
        r = c.post(BASE + "/oauth/register", json={
            "client_name": "Runner Sidekick", "redirect_uris": [redirect_uri], "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"], "token_endpoint_auth_method": "none", "scope": SCOPE})
    if r.status_code >= 300:
        raise WatchleticError(f"Watchletic didn't register the app ({r.status_code}).")
    reg = r.json()
    _write_private(p, {**reg, "redirect_uris": reg.get("redirect_uris") or [redirect_uri], "scope": reg.get("scope") or SCOPE})
    return reg["client_id"]


def _verifier() -> str:
    return pysecrets.token_urlsafe(64)


def _challenge(v: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()


def start(app_conn, user_id: int, data_dir: Path, redirect_uri: str) -> str:
    """Watchletic's authorize URL. The app finishes the link signed in as this same user (complete(..., user_id)), so a
    link forwarded to someone else ends up under their account and is refused."""
    cid = client_id(data_dir, redirect_uri)
    state, verifier = pysecrets.token_urlsafe(24), _verifier()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STATE_TTL_S)).isoformat().replace("+00:00", "Z")
    app_conn.oauth_states.delete_many({"created_at": {"$lt": cutoff}})
    app_conn.oauth_states.insert_one({"state": state, "user_id": user_id, "code_verifier": verifier, "provider": "watchletic",
                                      "created_at": utc_now()})
    return BASE + "/oauth/authorize?" + urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": redirect_uri, "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256", "state": state, "scope": SCOPE, "resource": RESOURCE})


def _token_file(user_dir: Path) -> Path:
    return user_dir / "watchletic_oauth.json"


def _store(user_dir: Path, tok: dict) -> dict:
    data = {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
            "expires_at": time.time() + float(tok.get("expires_in") or 3600), "scope": tok.get("scope"), "linked_at": utc_now()}
    old = _load(user_dir)
    if old.get("linked_at"):
        data["linked_at"] = old["linked_at"]
    _write_private(_token_file(user_dir), data)
    return data


def _load(user_dir: Path) -> dict:
    p = _token_file(user_dir)
    return json.loads(p.read_text()) if p.exists() else {}


def complete(app_conn, state: str, code: str, data_dir: Path, redirect_uri: str, user_dir_of, user_id: int) -> None:
    row = app_conn.oauth_states.find_one_and_delete({"state": state, "provider": "watchletic"})
    if not row or row["user_id"] != user_id:
        raise WatchleticError("This sign-in link has expired or belongs to another account. Start again from Me.")
    with _client() as c:
        r = c.post(BASE + "/oauth/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "client_id": client_id(data_dir, redirect_uri),
            "code_verifier": row["code_verifier"], "resource": RESOURCE})
    if r.status_code >= 300:
        raise WatchleticError("Watchletic didn't accept the sign-in. Please try again.")
    _store(user_dir_of(user_id), r.json())


def status(user_dir: Path) -> dict:
    t = _load(user_dir)
    return {"connected": bool(t), "linked_at": t.get("linked_at"), "last_sync": t.get("last_sync"), "problem": t.get("problem"),
            "can_delete": "watchletic.write" in (t.get("scope") or "").split()}


def access_token(user_dir: Path, data_dir: Path, redirect_uri: str) -> str:
    """A valid access token, refreshing (and saving the rotated refresh token first) when it's about to expire. One
    refresh at a time per user: two would reuse the same refresh token, which Watchletic treats as theft."""
    lock = _refresh_locks.setdefault(str(user_dir), threading.Lock())
    with lock:
        t = _load(user_dir)
        if not t:
            raise WatchleticError("Watchletic isn't connected.")
        if t.get("expires_at", 0) - REFRESH_MARGIN_S > time.time():
            return t["access_token"]
        if not t.get("refresh_token"):
            raise WatchleticError("The Watchletic connection expired. Connect it again from Me.")
        with _client() as c:
            r = c.post(BASE + "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                                                    "client_id": client_id(data_dir, redirect_uri), "resource": RESOURCE})
        if r.status_code >= 300:
            _write_private(_token_file(user_dir), {**t, "problem": "The connection expired or was revoked. Connect it again from Me."})
            raise WatchleticError("The Watchletic connection expired or was revoked. Connect it again from Me.")
        return _store(user_dir, r.json())["access_token"]


def disconnect(user_dir: Path, data_dir: Path, redirect_uri: str) -> None:
    t = _load(user_dir)
    if t.get("refresh_token"):
        try:
            with _client() as c:
                c.post(BASE + "/oauth/revoke", data={"token": t["refresh_token"], "token_type_hint": "refresh_token",
                                                     "client_id": client_id(data_dir, redirect_uri)})
        except httpx.HTTPError:
            pass  # gone on our side either way; the user can also revoke it in Watchletic's API access settings
    _token_file(user_dir).unlink(missing_ok=True)


def mark(user_dir: Path, **kv) -> None:
    t = _load(user_dir)
    if t:
        _write_private(_token_file(user_dir), {**t, **kv})


class Mcp:
    """A minimal Streamable HTTP MCP client: JSON-RPC over POST, answers as JSON or as a server-sent event."""

    def __init__(self, token: str):
        self.token, self.session, self.n = token, None, 0
        self.http = _client()

    def _post(self, payload: dict) -> dict | None:
        h = {"Authorization": f"Bearer {self.token}", "Accept": "application/json, text/event-stream",
             "Content-Type": "application/json", "MCP-Protocol-Version": "2025-06-18"}
        if self.session:
            h["Mcp-Session-Id"] = self.session
        r = self.http.post(RESOURCE, headers=h, json=payload)
        if r.headers.get("mcp-session-id"):
            self.session = r.headers["mcp-session-id"]
        if r.status_code == 202 or "id" not in payload:
            return None
        if r.status_code >= 300:
            raise WatchleticError(f"Watchletic answered {r.status_code}.")
        if r.headers.get("content-type", "").startswith("text/event-stream"):
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    msg = json.loads(line[5:].strip())
                    if msg.get("id") == payload["id"]:
                        return msg
            raise WatchleticError("Watchletic's answer was empty.")
        return r.json()

    def call(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        msg = self._post({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})
        if msg is None or "error" in msg:
            raise WatchleticError(f"Watchletic: {(msg or {}).get('error', {}).get('message', 'no answer')}")
        return msg["result"]

    def __enter__(self):
        self.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "runner-sidekick", "version": "1"}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def __exit__(self, *_):
        self.http.close()

    def tool(self, name: str, args: dict | None = None):
        """A tool's answer: its structured content when given, else its text parsed as JSON when it is JSON."""
        res = self.call("tools/call", {"name": name, "arguments": args or {}})
        if res.get("isError"):
            raise WatchleticError("; ".join(c.get("text", "") for c in res.get("content", [])) or f"{name} failed")
        if res.get("structuredContent") is not None:
            return res["structuredContent"]
        text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        try:
            return json.loads(text)
        except ValueError:
            return text


BACKFILL_DAYS = 90


def _download(url: str) -> bytes:
    with _client() as c:
        r = c.get(url)
    if r.status_code >= 300:
        raise WatchleticError(f"Watchletic's file download failed ({r.status_code}).")
    return r.content


def sync(conn, stream: str, user_dir: Path, data_dir: Path, redirect_uri: str, tz: str) -> tuple[set[str], list[str], dict]:
    """What's new in Watchletic: each running workout not seen at its current revision comes in as its FIT file
    (fit.ingest: test recordings left out, the Samsung Health copy of the same run set aside). Everything else it gives
    (readiness, training context, fitness analytics, the tool catalog) is kept as it came in watchletic_raw, for later.
    Returns the changed dates and runs, and a summary."""
    from . import fit
    dates: set[str] = set()
    runs: list[str] = []
    got = {"new_runs": 0, "skipped": 0, "failed": 0}
    since = (datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)).isoformat().replace("+00:00", "Z")
    with Mcp(access_token(user_dir, data_dir, redirect_uri)) as m:
        devices: list | None = None  # Watchletic's paired sensors, read once when a run used one
        cursor = None
        while True:
            page = m.tool("list_activities", {"activityType": "running", "from": since, "limit": 100, **({"cursor": cursor} if cursor else {})})
            for a in page.get("data", []):
                seen = conn.watchletic_seen.find_one({"id": a["id"]})
                if seen and seen.get("revision") == a.get("revision"):
                    continue
                note, sid = "imported", None
                if (a.get("durationSeconds") or 0) < fit.MIN_RUN_S or (a.get("distanceMeters") or 0) < fit.MIN_RUN_M:
                    note = "too short to be a run"
                    got["skipped"] += 1
                else:
                    try:
                        f = m.tool("export_activity_file", {"activityId": a["id"], "format": "fit"})
                        data = _download(f["downloadUrl"])
                        ch, rs = fit.ingest(conn, stream, data)
                        sid = fit.parse(data)[0].source_id
                        dates |= ch
                        runs += rs
                        got["new_runs"] += len(rs)
                        # Which app recorded it, and the heart-rate sensor when it was an external one: the FIT file only
                        # says "Heart Rate Monitor", Watchletic's device list has its name (when it knows just one)
                        extra = {"recorded_with": "Watchletic"}
                        if "heartRateMonitor" in (a.get("bluetoothDevices") or []):
                            if devices is None:
                                devices = (m.tool("list_devices") or {}).get("data", [])
                            hrms = [d for d in devices if d.get("type") == "heartRateMonitor"]
                            extra["hr_sensor"] = {"name": hrms[0].get("name") if len(hrms) == 1 else None, "kind": "external"}
                        conn.activity.update_many({"source_id": sid}, {"$set": extra})
                    except Exception as e:  # one bad workout doesn't stop the rest; it's tried again next time
                        got["failed"] += 1
                        conn.watchletic_seen.update_one({"id": a["id"]}, {"$set": {"error": str(e)[:300], "at": utc_now()}}, upsert=True)
                        continue
                conn.watchletic_seen.replace_one({"id": a["id"]}, {"id": a["id"], "revision": a.get("revision"), "date": a.get("date"),
                                                                   "note": note, "at": utc_now(),
                                                                   **({"source_id": sid} if note == "imported" else {})}, upsert=True)
            cursor = page.get("nextCursor")
            if not cursor:
                break
        # Kept as they came, nothing derived from them yet
        for kind, name, args in (("readiness", "list_readiness", {"limit": 100}), ("context", "get_training_context", {"timeZone": tz}),
                                 ("fitness", "get_fitness_analytics", {"timeZone": tz})):
            try:
                conn.watchletic_raw.replace_one({"kind": kind}, {"kind": kind, "at": utc_now(), "data": m.tool(name, args)}, upsert=True)
            except WatchleticError as e:
                conn.watchletic_raw.replace_one({"kind": kind}, {"kind": kind, "at": utc_now(), "error": str(e)[:300]}, upsert=True)
        if not conn.watchletic_raw.find_one({"kind": "tools"}, {"_id": 1}):
            conn.watchletic_raw.insert_one({"kind": "tools", "at": utc_now(), "data": m.call("tools/list").get("tools", [])})
    mark(user_dir, last_sync=utc_now(), problem=None)
    return dates, runs, got


def workout_of(conn, source_id: str) -> dict | None:
    """The Watchletic workout a run of ours came from, if it did."""
    return conn.watchletic_seen.find_one({"source_id": source_id})


def delete_workout(conn, source_id: str, user_dir: Path, data_dir: Path, redirect_uri: str) -> bool:
    """Deletes in Watchletic the workout this run came from (the runner ticked it in the app's delete dialog, which is the
    explicit confirmation Watchletic asks for): its preview, then the apply with the preview's confirmation token."""
    w = workout_of(conn, source_id)
    if not w:
        return False
    args = {"id": w["id"], **({"revision": w["revision"]} if w.get("revision") else {})}  # preview/apply take id, not activityId
    with Mcp(access_token(user_dir, data_dir, redirect_uri)) as m:
        preview = m.tool("preview_activity_delete", args)
        token = _find(preview, "confirmationToken")
        if not token:
            raise WatchleticError("Watchletic didn't confirm the deletion.")
        m.tool("apply_activity_delete", {**args, "confirmationToken": token})
    conn.watchletic_seen.update_one({"id": w["id"]}, {"$set": {"deleted_there": utc_now()}})
    return True


def _find(x, key: str):
    """A key anywhere in a nested answer (where Watchletic puts the confirmation token)."""
    if isinstance(x, dict):
        if key in x:
            return x[key]
        return next((v for v in (_find(y, key) for y in x.values()) if v), None)
    if isinstance(x, list):
        return next((v for v in (_find(y, key) for y in x) if v), None)
    return None

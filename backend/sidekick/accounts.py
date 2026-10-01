"""Users, invites and app sessions (data/app.db). Each user's health data lives in its own folder
data/users/<id>/ (own SQLite database and Garmin tokens), so users can't see each other's data and an account
can be deleted by removing one folder.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import shutil
import sqlite3
from pathlib import Path

from .db import APP_MIGRATIONS_DIR, connect, utc_now

OWNER_ROLE = "owner"


def app_db(data_dir: Path) -> sqlite3.Connection:
    conn = connect(data_dir / "app.db", APP_MIGRATIONS_DIR)
    migrate_single_user_layout(conn, data_dir)
    return conn


def user_dir(data_dir: Path, user_id: int) -> Path:
    (data_dir / "users").mkdir(mode=0o700, parents=True, exist_ok=True)
    d = data_dir / "users" / str(user_id)
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


def owner(conn) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE role=? AND deleted_at IS NULL ORDER BY id LIMIT 1", (OWNER_ROLE,)).fetchone()


def ensure_owner(conn) -> sqlite3.Row:
    o = owner(conn)
    if o is None:
        with conn:
            conn.execute("INSERT INTO users (role, name, created_at) VALUES (?, 'Owner', ?)", (OWNER_ROLE, utc_now()))
        o = owner(conn)
    return o


def migrate_single_user_layout(conn, data_dir: Path) -> None:
    """One-time move from the single-user layout (data/garmin.db, data/garmin_tokens, data/device_tokens.json)
    into data/users/<owner>/. Existing app tokens keep working: their hashes become owner sessions."""
    legacy = [data_dir / n for n in ("garmin.db", "fixture.db", "garmin_tokens")]
    tokens_file = data_dir / "device_tokens.json"
    if not any(p.exists() for p in legacy) and not tokens_file.exists():
        return
    o = ensure_owner(conn)
    dest = user_dir(data_dir, o["id"])
    for p in legacy:
        for suffix in ("", "-wal", "-shm"):
            src = p.with_name(p.name + suffix)
            if src.exists() and not (dest / src.name).exists():
                shutil.move(str(src), str(dest / src.name))
    if tokens_file.exists():
        with conn:
            for t in json.loads(tokens_file.read_text()):
                conn.execute("INSERT OR IGNORE INTO sessions (user_id, name, token_sha256, created_at, revoked_at) VALUES (?,?,?,?,?)",
                             (o["id"], t["name"], t["sha256"], t["created_at"], t["revoked_at"]))
        tokens_file.rename(tokens_file.with_name("device_tokens.json.migrated"))


# ---------------------------------------------------------------- sessions

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user_id: int, name: str) -> str:
    token = "rsk_" + secrets.token_urlsafe(32)
    with conn:
        conn.execute("INSERT INTO sessions (user_id, name, token_sha256, created_at) VALUES (?,?,?,?)", (user_id, name, _hash(token), utc_now()))
    return token


def verify_session(conn, token: str) -> sqlite3.Row | None:
    digest = _hash(token)
    r = conn.execute("SELECT s.id AS session_id, s.token_sha256, u.* FROM sessions s JOIN users u ON u.id = s.user_id"
                     " WHERE s.token_sha256=? AND s.revoked_at IS NULL AND u.deleted_at IS NULL", (digest,)).fetchone()
    if r is None or not hmac.compare_digest(r["token_sha256"], digest):
        return None
    with conn:
        conn.execute("UPDATE sessions SET last_used_at=? WHERE id=?", (utc_now(), r["session_id"]))
    return r


def revoke_sessions(conn, user_id: int, name: str | None = None) -> int:
    q, args = "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", [utc_now(), user_id]
    if name:
        q += " AND name=?"
        args.append(name)
    with conn:
        return conn.execute(q, args).rowcount


# ---------------------------------------------------------------- invites and sign-in

def normalise_email(email: str) -> str:
    return email.strip().lower()


def add_invite(conn, email: str) -> None:
    with conn:
        conn.execute("INSERT OR IGNORE INTO invites (email, created_at) VALUES (?,?)", (normalise_email(email), utc_now()))


def remove_invite(conn, email: str) -> int:
    with conn:
        return conn.execute("DELETE FROM invites WHERE email=? AND used_at IS NULL", (normalise_email(email),)).rowcount


def set_owner_email(conn, email: str) -> None:
    o = ensure_owner(conn)
    with conn:
        conn.execute("UPDATE users SET email=? WHERE id=?", (normalise_email(email), o["id"]))


class NotInvited(Exception):
    pass


def sign_in_with_google(conn, claims: dict) -> sqlite3.Row:
    """claims: a verified Google ID token payload. Existing users (by Google subject or email) sign in; new users
    need an unused invite for their verified email."""
    if not claims.get("email_verified"):
        raise NotInvited("Google account email is not verified")
    email, sub = normalise_email(claims["email"]), claims["sub"]
    u = conn.execute("SELECT * FROM users WHERE (google_sub=? OR email=?) AND deleted_at IS NULL", (sub, email)).fetchone()
    with conn:
        if u is None:
            inv = conn.execute("SELECT * FROM invites WHERE email=? AND used_at IS NULL", (email,)).fetchone()
            if inv is None:
                raise NotInvited("This Google account hasn't been invited yet")
            conn.execute("INSERT INTO users (email, google_sub, name, created_at) VALUES (?,?,?,?)", (email, sub, claims.get("name"), utc_now()))
            conn.execute("UPDATE invites SET used_at=? WHERE email=?", (utc_now(), email))
        else:
            conn.execute("UPDATE users SET google_sub=?, name=COALESCE(name, ?) WHERE id=?", (sub, claims.get("name"), u["id"]))
    return conn.execute("SELECT * FROM users WHERE google_sub=? AND deleted_at IS NULL", (sub,)).fetchone()


def delete_user(conn, data_dir: Path, user_id: int) -> None:
    """Removes the user's data folder (health data, Garmin tokens) and sessions; keeps a tombstone row."""
    shutil.rmtree(data_dir / "users" / str(user_id), ignore_errors=True)
    with conn:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM oauth_states WHERE user_id=?", (user_id,))
        conn.execute("UPDATE users SET deleted_at=?, email=NULL, google_sub=NULL, name=NULL WHERE id=?", (utc_now(), user_id))


def list_users(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT u.id, u.email, u.name, u.role, u.created_at, COUNT(s.id) AS sessions FROM users u"
        " LEFT JOIN sessions s ON s.user_id=u.id AND s.revoked_at IS NULL WHERE u.deleted_at IS NULL GROUP BY u.id ORDER BY u.id")]

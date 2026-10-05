"""Users, invites and app sessions (the `<prefix>_app` MongoDB database). Each user's health data lives in its own
database (`<prefix>_u<id>_<source>`) and their Garmin tokens in data/users/<id>/, so users can't see each other's
data and an account is deleted by dropping one database and one folder.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import shutil
from pathlib import Path

from pymongo.database import Database

from .db import app_name, client, connect, db_prefix, many, next_id, one, utc_now

OWNER_ROLE = "owner"


def app_db(data_dir: Path | None = None) -> Database:
    return connect(app_name())


def user_dir(data_dir: Path, user_id: int) -> Path:
    (data_dir / "users").mkdir(mode=0o700, parents=True, exist_ok=True)
    d = data_dir / "users" / str(user_id)
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


def owner(conn: Database) -> dict | None:
    return one(conn.users, {"role": OWNER_ROLE, "deleted_at": None}, sort=[("id", 1)])


def ensure_owner(conn: Database) -> dict:
    o = owner(conn)
    if o is None:
        conn.users.insert_one({"id": next_id(conn, "users"), "email": None, "google_sub": None, "name": "Owner", "role": OWNER_ROLE,
                               "created_at": utc_now(), "deleted_at": None})
        o = owner(conn)
    return o


def user(conn: Database, user_id: int) -> dict | None:
    return one(conn.users, {"id": user_id})


# ---------------------------------------------------------------- sessions

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn: Database, user_id: int, name: str) -> str:
    token = "rsk_" + secrets.token_urlsafe(32)
    conn.sessions.insert_one({"id": next_id(conn, "sessions"), "user_id": user_id, "name": name, "token_sha256": _hash(token),
                              "created_at": utc_now(), "last_used_at": None, "revoked_at": None})
    return token


SESSION_IDLE_DAYS = 90  # a sign-in unused this long expires (the app and its background refresh keep yours alive)


def verify_session(conn: Database, token: str) -> dict | None:
    digest = _hash(token)
    s = one(conn.sessions, {"token_sha256": digest, "revoked_at": None})
    if s is None or not hmac.compare_digest(s["token_sha256"], digest):
        return None
    from datetime import datetime, timedelta, timezone
    seen = s.get("last_used_at") or s.get("created_at")
    try:
        last = datetime.fromisoformat(seen.replace("Z", "+00:00")) if seen else None
    except ValueError:
        last = None  # an unreadable stamp (e.g. migrated from SQLite) doesn't end a sign-in
    if last and last < datetime.now(timezone.utc) - timedelta(days=SESSION_IDLE_DAYS):
        conn.sessions.update_one({"id": s["id"]}, {"$set": {"revoked_at": utc_now()}})
        return None
    u = one(conn.users, {"id": s["user_id"], "deleted_at": None})
    if u is None:
        return None
    conn.sessions.update_one({"id": s["id"]}, {"$set": {"last_used_at": utc_now()}})
    return {**u, "session_id": s["id"]}


def revoke_sessions(conn: Database, user_id: int, name: str | None = None) -> int:
    q = {"user_id": user_id, "revoked_at": None, **({"name": name} if name else {})}
    return conn.sessions.update_many(q, {"$set": {"revoked_at": utc_now()}}).modified_count


# ---------------------------------------------------------------- invites and sign-in

def normalise_email(email: str) -> str:
    return email.strip().lower()


def add_invite(conn: Database, email: str) -> None:
    """Invites an email. An invite used by an account that's since been deleted is renewed, so they can come back."""
    e = normalise_email(email)
    conn.invites.update_one({"email": e}, {"$setOnInsert": {"created_at": utc_now(), "used_at": None}}, upsert=True)
    if one(conn.users, {"email": e, "deleted_at": None}) is None:
        conn.invites.update_one({"email": e}, {"$set": {"used_at": None}})


def remove_invite(conn: Database, email: str) -> int:
    return conn.invites.delete_one({"email": normalise_email(email), "used_at": None}).deleted_count


def set_owner_email(conn: Database, email: str) -> None:
    o = ensure_owner(conn)
    conn.users.update_one({"id": o["id"]}, {"$set": {"email": normalise_email(email)}})


class NotInvited(Exception):
    pass


def sign_in_with_google(conn: Database, claims: dict) -> dict:
    """claims: a verified Google ID token payload. Existing users (by Google subject or email) sign in; new users
    need an unused invite for their verified email."""
    if not claims.get("email_verified"):
        raise NotInvited("Google account email is not verified")
    email, sub = normalise_email(claims["email"]), claims["sub"]
    # A linked account is matched only by its Google subject. Email matches only a user with no Google account linked
    # yet (the owner's first sign-in), and never re-links one: another Google account with the same email can't take over.
    u = one(conn.users, {"google_sub": sub, "deleted_at": None}) or one(conn.users, {"email": email, "google_sub": None, "deleted_at": None})
    if u is None and one(conn.users, {"email": email, "deleted_at": None}):
        raise NotInvited("This email is already linked to a different Google account")
    if u is None:
        if one(conn.invites, {"email": email, "used_at": None}) is None:
            raise NotInvited("This Google account hasn't been invited yet")
        conn.users.insert_one({"id": next_id(conn, "users"), "email": email, "google_sub": sub, "name": claims.get("name"),
                               "role": "member", "created_at": utc_now(), "deleted_at": None})
        conn.invites.update_one({"email": email}, {"$set": {"used_at": utc_now()}})
    else:
        conn.users.update_one({"id": u["id"]}, {"$set": {"google_sub": sub, "name": u.get("name") or claims.get("name")}})
    return one(conn.users, {"google_sub": sub, "deleted_at": None})


def delete_user(conn: Database, data_dir: Path, user_id: int) -> None:
    """Drops the user's databases and token folder and their sessions; keeps a tombstone record."""
    prefix = f"{db_prefix()}_u{user_id}_"
    for name in client().list_database_names():
        if name.startswith(prefix):
            client().drop_database(name)
    shutil.rmtree(data_dir / "users" / str(user_id), ignore_errors=True)
    conn.sessions.delete_many({"user_id": user_id})
    conn.oauth_states.delete_many({"user_id": user_id})
    conn.users.update_one({"id": user_id}, {"$set": {"deleted_at": utc_now(), "email": None, "google_sub": None, "name": None}})


def list_users(conn: Database) -> list[dict]:
    out = []
    for u in many(conn.users, {"deleted_at": None}, sort=[("id", 1)]):
        out.append({k: u.get(k) for k in ("id", "email", "name", "role", "created_at")} |
                   {"sessions": conn.sessions.count_documents({"user_id": u["id"], "revoked_at": None})})
    return out

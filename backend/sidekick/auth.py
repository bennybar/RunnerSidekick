"""App bearer tokens (thin wrapper over accounts). Tokens created from the CLI belong to the owner unless a user
is given; signed-in users get theirs from POST /v1/auth/google."""

from __future__ import annotations

from pathlib import Path

from . import accounts


def create_token(data_dir: Path, name: str, user_id: int | None = None) -> str:
    conn = accounts.app_db(data_dir)
    try:
        uid = user_id if user_id is not None else accounts.ensure_owner(conn)["id"]
        return accounts.create_session(conn, uid, name)
    finally:
        conn.close()


def revoke_token(data_dir: Path, name: str, user_id: int | None = None) -> int:
    conn = accounts.app_db(data_dir)
    try:
        uid = user_id if user_id is not None else accounts.ensure_owner(conn)["id"]
        return accounts.revoke_sessions(conn, uid, name)
    finally:
        conn.close()

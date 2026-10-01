"""SQLite access and forward-only migrations (migrations/NNNN_name.sql, applied in order)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    newly = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if f.name in applied:
            continue
        with conn:
            conn.executescript(f.read_text())
            conn.execute("INSERT INTO schema_migrations VALUES (?, ?)", (f.name, utc_now()))
        newly.append(f.name)
    return newly

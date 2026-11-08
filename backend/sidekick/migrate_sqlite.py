"""One-time import of the SQLite data (data/app.db and data/users/<id>/<source>.db) into MongoDB.

The SQLite files are only read, never changed or deleted, so they stay as a backup. Refuses to write into databases
that already hold data unless `replace=True`, which empties those collections first. Counters are set past the
highest imported id so new records continue the same numbering (report and activity ids the app has cached stay valid).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .db import app_name, connect, user_db_name

JSON_COLUMNS = {"capabilities_json": "capabilities", "payload_json": "payload", "garmin_metrics_json": "garmin_metrics",
                "samples_json": "samples", "tags_json": "tags", "body_json": "body", "value_json": "value", "output_json": "output",
                "params_json": "params", "targets_json": "targets"}
BOOL_COLUMNS = {"sleep_session": ("is_nap",), "checkin": ("pain", "illness", "deleted")}
USER_TABLES = ["source_connection", "sync_checkpoint", "sync_job", "raw_payload", "daily_observation", "activity", "activity_lap",
               "activity_samples", "sleep_session", "checkin", "activity_effort", "report", "user_settings", "narrative", "day_plan",
               "run_intent", "weekly_focus", "insight_state", "coach_analysis", "ai_call"]
APP_TABLES = ["users", "invites", "sessions", "oauth_states"]
COUNTED = {"activity", "report", "sync_job", "coach_analysis", "ai_call", "users", "sessions"}


class NotEmpty(Exception):
    pass


def _doc(table: str, row: sqlite3.Row) -> dict:
    d = {}
    for k in row.keys():
        v = row[k]
        if k in JSON_COLUMNS:
            d[JSON_COLUMNS[k]] = json.loads(v) if v is not None else None
        elif table == "report" and k == "algorithm_version":
            d[k] = json.loads(v)
        elif k in BOOL_COLUMNS.get(table, ()):
            d[k] = bool(v)
        else:
            d[k] = v
    return d


def _tables(src: sqlite3.Connection) -> set[str]:
    return {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def copy_db(sqlite_path: Path, target_name: str, tables: list[str], replace: bool = False) -> dict[str, int]:
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = connect(target_name)
    present = _tables(src)
    if not replace and any(dst[t].estimated_document_count() for t in tables):
        raise NotEmpty(f"{target_name} already has data; re-run with --replace to overwrite it")
    counts = {}
    try:
        for t in tables:
            if t not in present:
                continue
            docs = [_doc(t, r) for r in src.execute(f"SELECT * FROM {t}")]
            dst[t].delete_many({})
            if docs:
                dst[t].insert_many(docs, ordered=False)
            counts[t] = len(docs)
            if t in COUNTED:
                top = max((d["id"] for d in docs if d.get("id") is not None), default=0)
                dst.counters.update_one({"_id": t}, {"$max": {"n": top}}, upsert=True)
    finally:
        src.close()
    return counts


def migrate_all(data_dir: Path, replace: bool = False) -> list[str]:
    """Imports the accounts database and every user's per-source database. Returns a line per database."""
    out = []
    app = data_dir / "app.db"
    if app.exists():
        c = copy_db(app, app_name(), APP_TABLES, replace)
        out.append(f"{app_name()}: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    for udir in sorted((data_dir / "users").glob("*")) if (data_dir / "users").exists() else []:
        if not udir.name.isdigit():
            continue
        for f in sorted(udir.glob("*.db")):
            name = user_db_name(int(udir.name), f.stem)
            c = copy_db(f, name, USER_TABLES, replace)
            out.append(f"{name}: " + ", ".join(f"{k} {v}" for k, v in c.items() if v))
    return out

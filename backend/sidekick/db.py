"""MongoDB access. Accounts live in the `<prefix>_app` database; each user's health data has its own database,
`<prefix>_u<user id>_<source>`, so users can't see each other's data and an account is deleted by dropping one database.

Documents are stored natively (no JSON-in-strings). Natural keys are enforced with unique indexes; integer ids that
the app uses (activities, reports, users, sessions…) come from a per-database counter."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

MONGO_URI = "mongodb://127.0.0.1:27017"  # the server's local MongoDB; RSK_MONGO_URI overrides (tests, demos)

U = True   # unique
N = False  # plain index

# collection -> [(fields, unique)]
USER_INDEXES = {
    "source_connection": [(("source",), U)],
    "sync_checkpoint": [(("source", "stream"), U)],
    "sync_job": [(("id",), U)],
    "raw_payload": [(("source", "kind", "source_key"), U), (("fetched_at",), N)],
    "daily_observation": [(("source", "local_date", "metric"), U), (("source", "metric", "local_date"), N)],
    "activity": [(("source", "source_id"), U), (("id",), U), (("source", "local_date"), N)],
    "activity_lap": [(("activity_id", "idx"), U)],
    "activity_samples": [(("activity_id",), U)],
    "sleep_session": [(("source", "source_id"), U), (("wake_date",), N)],
    "checkin": [(("id",), U), (("local_date",), N)],
    "activity_effort": [(("activity_source_id",), U)],
    "report": [(("type", "subject_key", "revision"), U), (("id",), U), (("type", "local_date"), N)],
    "user_settings": [(("key",), U)],
    "narrative": [(("report_type", "subject_key", "input_hash", "model", "prompt_version"), U)],
    "day_plan": [(("local_date",), U)],
    "run_intent": [(("activity_source_id",), U)],
    "weekly_focus": [(("week_start",), U)],
    "insight_state": [(("insight_id",), U)],
    "coach_analysis": [(("id",), U), (("input_hash",), N)],
    "ai_call": [(("id",), U), (("created_at",), N)],
    "section_summary": [(("id",), U), (("kind", "local_date", "input_hash"), N)],
}
APP_INDEXES = {
    "users": [(("id",), U)],
    "invites": [(("email",), U)],
    "sessions": [(("id",), U), (("token_sha256",), U), (("user_id",), N)],
    "oauth_states": [(("state",), U)],
}

_client: MongoClient | None = None
_lock = threading.Lock()
_indexed: set[str] = set()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def db_prefix() -> str:
    return os.getenv("RSK_DB_PREFIX", "rsk")


def client() -> MongoClient:
    global _client
    with _lock:
        if _client is None:
            _client = MongoClient(os.getenv("RSK_MONGO_URI", MONGO_URI), serverSelectionTimeoutMS=5000, tz_aware=False)
        return _client


def connect(name: str) -> Database:
    """A database handle with its indexes in place. Handles are cheap and thread-safe; nothing needs closing."""
    d = client()[name]
    if name not in _indexed:
        indexes = APP_INDEXES if name.endswith("_app") else USER_INDEXES
        for coll, specs in indexes.items():
            for fields, unique in specs:
                kw = {"unique": True} if unique else {}
                d[coll].create_index([(f, ASCENDING) for f in fields], **kw)
        if name.endswith("_app"):
            # Emails and Google subjects are unique when present (deleted users keep a tombstone without them)
            for f in ("email", "google_sub"):
                d.users.create_index([(f, ASCENDING)], unique=True, partialFilterExpression={f: {"$type": "string"}})
        _indexed.add(name)
    return d


def app_name() -> str:
    return f"{db_prefix()}_app"


def user_db_name(user_id: int, source: str) -> str:
    return f"{db_prefix()}_u{user_id}_{source}"


def next_id(d: Database, name: str) -> int:
    return d.counters.find_one_and_update({"_id": name}, {"$inc": {"n": 1}}, upsert=True, return_document=ReturnDocument.AFTER)["n"]


NO_ID = {"_id": 0}


def one(coll, filt: dict, sort: list | None = None) -> dict | None:
    return coll.find_one(filt, NO_ID, sort=sort)


def many(coll, filt: dict | None = None, sort: list | None = None, limit: int = 0) -> list[dict]:
    return list(coll.find(filt or {}, NO_ID, sort=sort, limit=limit))


def put(coll, key: dict, doc: dict) -> None:
    """Insert or replace the document with this natural key."""
    coll.replace_one(key, {**key, **doc}, upsert=True)


def put_if_newer(coll, key: dict, doc: dict, field: str = "client_updated_at") -> None:
    """Last writer wins on `field`: a write older than (or as old as) the stored one is ignored."""
    try:
        coll.update_one({**key, field: {"$lt": doc[field]}}, {"$set": {**key, **doc}}, upsert=True)
    except DuplicateKeyError:
        pass  # a newer version exists


def get_setting(d: Database, key: str, default):
    r = d.user_settings.find_one({"key": key})
    return r["value"] if r else default


def set_setting(d: Database, key: str, value) -> None:
    d.user_settings.replace_one({"key": key}, {"key": key, "value": value}, upsert=True)


def plain(x):
    """The JSON shape of a value (string keys, lists), exactly as the API returns it, ready to store as a document."""
    import json
    return json.loads(json.dumps(x, default=str))

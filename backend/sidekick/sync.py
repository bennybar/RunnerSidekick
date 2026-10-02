"""Synchronisation: bounded, resumable backfill plus an incremental window that re-fetches recent days.

Ordering within a run (newest first so Today is useful early):
  1. incremental: today back to (newest_done - refetch_days), catching late sleep and revised activities
  2. backfill: continues from (oldest_done - 1) towards backfill_target, at most `max_backfill_days` per run
Progress is committed per day, so an interrupted run resumes where it stopped.

Failure policy:
  * AuthRequired  -> state reauth_required; no automatic retries until `garmin-login` succeeds.
  * RateLimited   -> exponential backoff with jitter (15 min doubling, capped at 6 h), persisted.
  * SourceUnavailable -> the same backoff, starting at 2 min. The library has already retried 5xx 3 times.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .connectors.base import AuthRequired, Capability, Connector, ConnectionState, RateLimited, SourceUnavailable
from pymongo.database import Database

from .db import get_setting, next_id, one, set_setting, utc_now
from .store import activity_hash, purge_raw, save_activity, save_day

REFETCH_EVERY_H = 6  # recent activities (within refetch_days) are re-read at most this often, for late samples/laps

log = logging.getLogger(__name__)


@dataclass
class SyncResult:
    outcome: str
    detail: str | None = None
    changed_dates: set[str] = field(default_factory=set)
    changed_activities: list[str] = field(default_factory=list)
    days_fetched: int = 0
    activities_fetched: int = 0


def backoff_seconds(failures: int, base: float, cap: float = 6 * 3600, rng: random.Random | None = None) -> float:
    rng = rng or random.Random()
    return min(cap, base * (2 ** max(0, failures - 1))) * (0.5 + 0.5 * rng.random())


CONNECTION_DEFAULTS = {"state": "not_configured", "detail": None, "last_attempt_at": None, "last_success_at": None,
                       "retry_not_before": None, "consecutive_failures": 0, "capabilities": {}}


def get_connection_row(conn: Database, source: str) -> dict | None:
    return one(conn.source_connection, {"source": source})


def set_connection(conn: Database, source: str, **fields) -> None:
    conn.source_connection.update_one({"source": source}, {"$setOnInsert": {k: v for k, v in CONNECTION_DEFAULTS.items() if k not in fields},
                                                           "$set": fields} if fields else
                                      {"$setOnInsert": CONNECTION_DEFAULTS}, upsert=True)


def mark_reconnected(conn: Database, source: str) -> None:
    """Called after a successful interactive login: clears the auth block."""
    set_connection(conn, source, state=ConnectionState.CONNECTED.value, detail=None, consecutive_failures=0, retry_not_before=None)


def _checkpoint(conn, source, stream, target: str) -> dict:
    key = {"source": source, "stream": stream}
    conn.sync_checkpoint.update_one(key, {"$setOnInsert": {"backfill_target": target, "oldest_done": None, "newest_done": None,
                                                           "updated_at": utc_now()}}, upsert=True)
    # A larger backfill configured later extends the target further back
    conn.sync_checkpoint.update_one({**key, "backfill_target": {"$gt": target}}, {"$set": {"backfill_target": target}})
    return one(conn.sync_checkpoint, key)


def _update_checkpoint(conn, source, stream, **fields) -> None:
    conn.sync_checkpoint.update_one({"source": source, "stream": stream}, {"$set": {**fields, "updated_at": utc_now()}})


def run_sync(conn: Database, connector: Connector, today: date, backfill_days: int, refetch_days: int,
             raw_retention_days: int = 120, max_backfill_days: int = 30, max_activity_details: int = 60,
             force: bool = False, now: datetime | None = None) -> SyncResult:
    source = connector.source
    now = now or datetime.now(timezone.utc)
    set_connection(conn, source)
    row = get_connection_row(conn, source)
    if row["state"] == ConnectionState.REAUTH_REQUIRED.value and not force:
        return SyncResult("auth_failed", "Re-authentication required; run garmin-login")
    if row["retry_not_before"] and not force and row["retry_not_before"] > now.isoformat().replace("+00:00", "Z"):
        return SyncResult("deferred", f"Backing off until {row['retry_not_before']}")
    if connector.connection_state() == ConnectionState.NOT_CONFIGURED:
        set_connection(conn, source, state=ConnectionState.NOT_CONFIGURED.value, detail="No credentials configured")
        return SyncResult("auth_failed", "Source not configured")

    target = (today - timedelta(days=backfill_days - 1)).isoformat()
    job_id = next_id(conn, "sync_job")
    conn.sync_job.insert_one({"id": job_id, "source": source, "kind": "sync", "started_at": utc_now(), "finished_at": None, "outcome": None,
                              "detail": None, "days_fetched": 0, "activities_fetched": 0})
    set_connection(conn, source, last_attempt_at=utc_now())
    res = SyncResult("ok")
    try:
        _sync_days(conn, connector, today, target, refetch_days, max_backfill_days, res)
        _sync_activities(conn, connector, today, target, refetch_days, max_activity_details, res)
        if hasattr(connector, "fitness_snapshot"):
            snap = connector.fitness_snapshot(today)
            if snap:
                # Garmin sometimes leaves a part out (e.g. no VO2 max early in the day, or one call failing): keep the last
                # known value of anything not returned this time instead of wiping it
                prev = get_setting(conn, "garmin_fitness", None) or {}
                merged = {**prev, **{k: v for k, v in snap.items() if v not in (None, {}, [])}}
                merged["fetched_at"] = utc_now()
                set_setting(conn, "garmin_fitness", merged)
        if hasattr(connector, "hr_zones"):
            zones = connector.hr_zones()
            if zones:
                set_setting(conn, "source_hr_zones", zones)
        if hasattr(connector, "profile"):
            prof = connector.profile()
            if prof:
                set_setting(conn, "source_profile", prof)
        purge_raw(conn, raw_retention_days)
        _record_capabilities(conn, connector)
        set_connection(conn, source, state=ConnectionState.CONNECTED.value, detail=None, last_success_at=utc_now(),
                       consecutive_failures=0, retry_not_before=None)
    except AuthRequired as e:
        res.outcome, res.detail = "auth_failed", str(e)
        set_connection(conn, source, state=ConnectionState.REAUTH_REQUIRED.value, detail=str(e))
    except (RateLimited, SourceUnavailable) as e:
        limited = isinstance(e, RateLimited)
        res.outcome, res.detail = ("rate_limited" if limited else "error"), str(e)
        failures = (row["consecutive_failures"] or 0) + 1
        wait = backoff_seconds(failures, 900 if limited else 120)
        set_connection(conn, source, state=(ConnectionState.RATE_LIMITED if limited else ConnectionState.ERROR).value,
                       detail=str(e), consecutive_failures=failures,
                       retry_not_before=(now + timedelta(seconds=wait)).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    conn.sync_job.update_one({"id": job_id}, {"$set": {"finished_at": utc_now(), "outcome": res.outcome, "detail": res.detail,
                                                       "days_fetched": res.days_fetched, "activities_fetched": res.activities_fetched}})
    return res


def _sync_days(conn, connector, today: date, target: str, refetch_days: int, max_backfill: int, res: SyncResult) -> None:
    source = connector.source
    cp = _checkpoint(conn, source, "days", target)
    newest_done = date.fromisoformat(cp["newest_done"]) if cp["newest_done"] else None
    inc_start = max(date.fromisoformat(target), (newest_done or today) - timedelta(days=refetch_days))
    for b in connector.read_days(inc_start, today):
        res.changed_dates |= save_day(conn, source, b)
        oldest = min(b.local_date, cp["oldest_done"] or b.local_date)
        _update_checkpoint(conn, source, "days", oldest_done=oldest)
        cp = one(conn.sync_checkpoint, {"source": source, "stream": "days"})
        res.days_fetched += 1
    _update_checkpoint(conn, source, "days", newest_done=today.isoformat())
    if cp["oldest_done"] is None:
        return
    oldest_done = date.fromisoformat(cp["oldest_done"])
    bf_end = oldest_done - timedelta(days=1)
    bf_start = max(date.fromisoformat(target), bf_end - timedelta(days=max_backfill - 1))
    if bf_end >= bf_start:
        for b in connector.read_days(bf_start, bf_end):
            res.changed_dates |= save_day(conn, source, b)
            _update_checkpoint(conn, source, "days", oldest_done=b.local_date)
            res.days_fetched += 1


def _sync_activities(conn, connector, today: date, target: str, refetch_days: int, max_details: int, res: SyncResult) -> None:
    source = connector.source
    _checkpoint(conn, source, "activities", target)
    summaries = connector.list_activities(date.fromisoformat(target), today)
    # Newest first, so a bounded run covers recent activities before old ones
    summaries.sort(key=lambda s: s["start"], reverse=True)
    fetched = 0
    recent = (today - timedelta(days=refetch_days)).isoformat()
    stale_before = (datetime.now(timezone.utc) - timedelta(hours=REFETCH_EVERY_H)).isoformat().replace("+00:00", "Z")
    for s in summaries:
        if activity_hash(conn, source, s["source_id"]) == s["content_hash"]:
            # Samples and laps can arrive or be corrected after the summary; re-read recent runs now and then
            row = one(conn.activity, {"source": source, "source_id": s["source_id"]})
            if not (row and row["local_date"] >= recent and row["updated_at"] < stale_before):
                continue
        if fetched >= max_details:
            res.outcome = "partial"
            res.detail = "Activity detail limit reached for this run; next sync continues"
            break
        a = connector.read_activity(s)
        save_activity(conn, source, a, s["content_hash"])
        fetched += 1
        res.changed_activities.append(a.source_id)
        res.changed_dates.add(a.local_date)
    res.activities_fetched = fetched
    _update_checkpoint(conn, source, "activities", newest_done=today.isoformat())


def _record_capabilities(conn, connector) -> None:
    declared = connector.capabilities()
    observed = {r["_id"]: (r["measured"], r["total"]) for r in conn.daily_observation.aggregate([
        {"$match": {"source": connector.source}},
        {"$group": {"_id": "$metric", "measured": {"$sum": {"$cond": [{"$eq": ["$state", "measured"]}, 1, 0]}}, "total": {"$sum": 1}}}])}
    caps = {}
    for m, cap in declared.items():
        measured, total = observed.get(m, (0, 0))
        state = Capability.SUPPORTED.value if measured else (cap.value if cap != Capability.SUPPORTED else "supported_not_observed")
        if cap == Capability.UNKNOWN and total and not measured:
            state = "not_observed"
        caps[m] = {"state": state, "days_measured": measured, "days_fetched": total}
    set_connection(conn, connector.source, capabilities=caps)

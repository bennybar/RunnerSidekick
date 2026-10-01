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

import json
import logging
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .connectors.base import AuthRequired, Capability, Connector, ConnectionState, RateLimited, SourceUnavailable
from .db import utc_now
from .store import activity_hash, purge_raw, save_activity, save_day

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


def get_connection_row(conn: sqlite3.Connection, source: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM source_connection WHERE source=?", (source,)).fetchone()


def set_connection(conn: sqlite3.Connection, source: str, **fields) -> None:
    conn.execute("INSERT INTO source_connection (source, state) VALUES (?, 'not_configured') ON CONFLICT DO NOTHING", (source,))
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE source_connection SET {sets} WHERE source=?", (*fields.values(), source))


def mark_reconnected(conn: sqlite3.Connection, source: str) -> None:
    """Called after a successful interactive login: clears the auth block."""
    with conn:
        set_connection(conn, source, state=ConnectionState.CONNECTED.value, detail=None, consecutive_failures=0,
                       retry_not_before=None)


def _checkpoint(conn, source, stream, target: str) -> sqlite3.Row:
    conn.execute("INSERT INTO sync_checkpoint (source, stream, backfill_target, updated_at) VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                 (source, stream, target, utc_now()))
    # A larger backfill configured later extends the target further back
    conn.execute("UPDATE sync_checkpoint SET backfill_target=? WHERE source=? AND stream=? AND backfill_target > ?",
                 (target, source, stream, target))
    return conn.execute("SELECT * FROM sync_checkpoint WHERE source=? AND stream=?", (source, stream)).fetchone()


def _update_checkpoint(conn, source, stream, **fields) -> None:
    sets = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE sync_checkpoint SET {sets}, updated_at=? WHERE source=? AND stream=?",
                 (*fields.values(), utc_now(), source, stream))


def run_sync(conn: sqlite3.Connection, connector: Connector, today: date, backfill_days: int, refetch_days: int,
             raw_retention_days: int = 120, max_backfill_days: int = 30, max_activity_details: int = 60,
             force: bool = False, now: datetime | None = None) -> SyncResult:
    source = connector.source
    now = now or datetime.now(timezone.utc)
    with conn:
        set_connection(conn, source)
    row = get_connection_row(conn, source)
    if row["state"] == ConnectionState.REAUTH_REQUIRED.value and not force:
        return SyncResult("auth_failed", "Re-authentication required; run garmin-login")
    if row["retry_not_before"] and not force and row["retry_not_before"] > now.isoformat().replace("+00:00", "Z"):
        return SyncResult("deferred", f"Backing off until {row['retry_not_before']}")
    if connector.connection_state() == ConnectionState.NOT_CONFIGURED:
        with conn:
            set_connection(conn, source, state=ConnectionState.NOT_CONFIGURED.value, detail="No credentials configured")
        return SyncResult("auth_failed", "Source not configured")

    target = (today - timedelta(days=backfill_days - 1)).isoformat()
    with conn:
        cur = conn.execute("INSERT INTO sync_job (source, kind, started_at) VALUES (?,?,?)", (source, "sync", utc_now()))
        job_id = cur.lastrowid
        set_connection(conn, source, last_attempt_at=utc_now())
    res = SyncResult("ok")
    try:
        _sync_days(conn, connector, today, target, refetch_days, max_backfill_days, res)
        _sync_activities(conn, connector, today, target, refetch_days, max_activity_details, res)
        if hasattr(connector, "hr_zones"):
            zones = connector.hr_zones()
            if zones:
                with conn:
                    conn.execute("INSERT INTO user_settings VALUES ('source_hr_zones', ?) ON CONFLICT (key) DO UPDATE SET value_json=excluded.value_json",
                                 (json.dumps(zones),))
        with conn:
            purge_raw(conn, raw_retention_days)
            _record_capabilities(conn, connector)
            set_connection(conn, source, state=ConnectionState.CONNECTED.value, detail=None, last_success_at=utc_now(),
                           consecutive_failures=0, retry_not_before=None)
    except AuthRequired as e:
        res.outcome, res.detail = "auth_failed", str(e)
        with conn:
            set_connection(conn, source, state=ConnectionState.REAUTH_REQUIRED.value, detail=str(e))
    except (RateLimited, SourceUnavailable) as e:
        limited = isinstance(e, RateLimited)
        res.outcome, res.detail = ("rate_limited" if limited else "error"), str(e)
        failures = (row["consecutive_failures"] or 0) + 1
        wait = backoff_seconds(failures, 900 if limited else 120)
        with conn:
            set_connection(conn, source, state=(ConnectionState.RATE_LIMITED if limited else ConnectionState.ERROR).value,
                           detail=str(e), consecutive_failures=failures,
                           retry_not_before=(now + timedelta(seconds=wait)).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    with conn:
        conn.execute("UPDATE sync_job SET finished_at=?, outcome=?, detail=?, days_fetched=?, activities_fetched=? WHERE id=?",
                     (utc_now(), res.outcome, res.detail, res.days_fetched, res.activities_fetched, job_id))
    return res


def _sync_days(conn, connector, today: date, target: str, refetch_days: int, max_backfill: int, res: SyncResult) -> None:
    source = connector.source
    with conn:
        cp = _checkpoint(conn, source, "days", target)
    newest_done = date.fromisoformat(cp["newest_done"]) if cp["newest_done"] else None
    inc_start = max(date.fromisoformat(target), (newest_done or today) - timedelta(days=refetch_days))
    for b in connector.read_days(inc_start, today):
        with conn:
            res.changed_dates |= save_day(conn, source, b)
            oldest = min(b.local_date, cp["oldest_done"] or b.local_date)
            _update_checkpoint(conn, source, "days", oldest_done=oldest)
            cp = conn.execute("SELECT * FROM sync_checkpoint WHERE source=? AND stream='days'", (source,)).fetchone()
        res.days_fetched += 1
    with conn:
        _update_checkpoint(conn, source, "days", newest_done=today.isoformat())
    if cp["oldest_done"] is None:
        return
    oldest_done = date.fromisoformat(cp["oldest_done"])
    bf_end = oldest_done - timedelta(days=1)
    bf_start = max(date.fromisoformat(target), bf_end - timedelta(days=max_backfill - 1))
    if bf_end >= bf_start:
        for b in connector.read_days(bf_start, bf_end):
            with conn:
                res.changed_dates |= save_day(conn, source, b)
                _update_checkpoint(conn, source, "days", oldest_done=b.local_date)
            res.days_fetched += 1


def _sync_activities(conn, connector, today: date, target: str, refetch_days: int, max_details: int, res: SyncResult) -> None:
    source = connector.source
    with conn:
        _checkpoint(conn, source, "activities", target)
    summaries = connector.list_activities(date.fromisoformat(target), today)
    # Newest first, so a bounded run covers recent activities before old ones
    summaries.sort(key=lambda s: s["start"], reverse=True)
    fetched = 0
    for s in summaries:
        if activity_hash(conn, source, s["source_id"]) == s["content_hash"]:
            continue
        if fetched >= max_details:
            res.outcome = "partial"
            res.detail = "Activity detail limit reached for this run; next sync continues"
            break
        a = connector.read_activity(s)
        with conn:
            save_activity(conn, source, a, s["content_hash"])
        fetched += 1
        res.changed_activities.append(a.source_id)
        res.changed_dates.add(a.local_date)
    res.activities_fetched = fetched
    with conn:
        _update_checkpoint(conn, source, "activities", newest_done=today.isoformat())


def _record_capabilities(conn, connector) -> None:
    declared = connector.capabilities()
    observed = {r["metric"]: (r["measured"], r["total"]) for r in conn.execute(
        "SELECT metric, SUM(state='measured') AS measured, COUNT(*) AS total FROM daily_observation WHERE source=? GROUP BY metric",
        (connector.source,))}
    caps = {}
    for m, cap in declared.items():
        measured, total = observed.get(m, (0, 0))
        state = Capability.SUPPORTED.value if measured else (cap.value if cap != Capability.SUPPORTED else "supported_not_observed")
        if cap == Capability.UNKNOWN and total and not measured:
            state = "not_observed"
        caps[m] = {"state": state, "days_measured": measured, "days_fetched": total}
    set_connection(conn, connector.source, capabilities_json=json.dumps(caps))

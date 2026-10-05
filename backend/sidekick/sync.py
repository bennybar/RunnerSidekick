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
    job_id: int | None = None


def report_progress(conn, job_id: int | None, fraction: float, phase: str) -> None:
    """How far a sync has got (0–1) and what it's doing, for the app's progress bar."""
    if job_id is not None:
        conn.sync_job.update_one({"id": job_id}, {"$set": {"progress": round(min(max(fraction, 0.0), 1.0), 3), "phase": phase}})


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


FITNESS_EVERY_H = 3      # Garmin's fitness snapshot: after a new run, otherwise every 3 hours
META_EVERY_H = 24        # heart-rate zones and profile
FULL_LIST_EVERY_H = 24   # the full activity history listing
RECENT_LIST_DAYS = 7     # otherwise only this many days are listed
CORE_DAY_METRICS = ("sleep_duration", "resting_hr", "hrv_overnight_avg")


def _hours_ago(h: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat().replace("+00:00", "Z")


def day_complete(conn, source: str, d: date) -> bool:
    """All of a day's core readings are in: re-reading it can't add anything the advice uses."""
    return conn.daily_observation.count_documents({"source": source, "local_date": d.isoformat(), "metric": {"$in": list(CORE_DAY_METRICS)},
                                                   "state": "measured"}) == len(CORE_DAY_METRICS)


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
    res = SyncResult("ok", job_id=job_id)
    report_progress(conn, job_id, 0.02, "Connecting to Garmin")
    try:
        _sync_days(conn, connector, today, target, refetch_days, max_backfill_days, res)
        _sync_activities(conn, connector, today, target, refetch_days, max_activity_details, res)
        prev_fit = get_setting(conn, "garmin_fitness", None) or {}
        fit_due = bool(res.changed_activities) or (prev_fit.get("fetched_at") or "") < _hours_ago(FITNESS_EVERY_H)
        report_progress(conn, job_id, 0.85, "Reading Garmin's fitness numbers")
        if hasattr(connector, "fitness_snapshot") and fit_due:
            snap = connector.fitness_snapshot(today)
            if snap:
                # Garmin sometimes leaves a part out (e.g. no VO2 max early in the day, or one call failing): keep the last
                # known value of anything not returned this time instead of wiping it
                prev = get_setting(conn, "garmin_fitness", None) or {}
                merged = {**prev, **{k: v for k, v in snap.items() if v not in (None, {}, [])}}
                merged["fetched_at"] = utc_now()
                set_setting(conn, "garmin_fitness", merged)
        # Zones and the profile (sex, birth date, week start) rarely change: once a day
        meta_due = (get_setting(conn, "source_meta_at", None) or "") < _hours_ago(META_EVERY_H)
        if hasattr(connector, "hr_zones") and meta_due:
            zones = connector.hr_zones()
            if zones:
                set_setting(conn, "source_hr_zones", zones)
        if hasattr(connector, "profile") and meta_due:
            prof = connector.profile()
            if prof:
                set_setting(conn, "source_profile", prof)
        if meta_due:
            set_setting(conn, "source_meta_at", utc_now())
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
    # Today and yesterday are always re-read (sleep and summaries arrive late); older days of the window only while one
    # of their core readings is still missing. Each skipped day saves six Garmin calls.
    todo = [inc_start + timedelta(days=k) for k in range((today - inc_start).days + 1)]
    todo = [d for d in todo if not (d < today - timedelta(days=1) and day_complete(conn, source, d))]
    for i, d in enumerate(todo):
        report_progress(conn, res.job_id, 0.05 + 0.45 * i / len(todo), "Reading your days from Garmin")
        for b in connector.read_days(d, d):
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
        report_progress(conn, res.job_id, 0.5, "Reading earlier days from Garmin")
        for b in connector.read_days(bf_start, bf_end):
            res.changed_dates |= save_day(conn, source, b)
            _update_checkpoint(conn, source, "days", oldest_done=b.local_date)
            res.days_fetched += 1


def _sync_activities(conn, connector, today: date, target: str, refetch_days: int, max_details: int, res: SyncResult) -> None:
    source = connector.source
    cp = _checkpoint(conn, source, "activities", target)
    # The whole history is listed once a day, or until every activity has been read; otherwise only the last week
    # (Garmin pages the list, so the full history is several requests)
    day_ago = (datetime.now(timezone.utc) - timedelta(hours=FULL_LIST_EVERY_H)).isoformat().replace("+00:00", "Z")
    full = not cp.get("complete") or (cp.get("full_listed_at") or "") < day_ago
    start = date.fromisoformat(target) if full else max(date.fromisoformat(target), today - timedelta(days=max(refetch_days, RECENT_LIST_DAYS)))
    summaries = connector.list_activities(start, today)
    # Newest first, so a bounded run covers recent activities before old ones
    summaries.sort(key=lambda s: s["start"], reverse=True)
    fetched = 0
    recent = (today - timedelta(days=refetch_days)).isoformat()
    stale_before = (datetime.now(timezone.utc) - timedelta(hours=REFETCH_EVERY_H)).isoformat().replace("+00:00", "Z")
    todo = []
    for s in summaries:
        if activity_hash(conn, source, s["source_id"]) == s["content_hash"]:
            # Samples and laps can arrive or be corrected after the summary; re-read recent runs now and then
            row = one(conn.activity, {"source": source, "source_id": s["source_id"]})
            if not (row and row["local_date"] >= recent and row["updated_at"] < stale_before):
                continue
        todo.append(s)
    report_progress(conn, res.job_id, 0.55, "Checking your runs")
    for s in todo:
        report_progress(conn, res.job_id, 0.55 + 0.3 * fetched / min(len(todo), max_details), "Reading your runs")
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
    done = res.outcome != "partial"
    _update_checkpoint(conn, source, "activities", newest_done=today.isoformat(), complete=done or (bool(cp.get("complete")) and not full),
                       **({"full_listed_at": utc_now()} if full and done else {}))


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


# ---------------------------------------------------------------- manual sync cooldown

# Minutes before another manual sync may call Garmin, by how the last one (manual or the hourly job) ended: a
# successful one rests 15 minutes, a failure can be retried soon, Garmin asking us to slow down gets a longer pause
COOLDOWN_MIN = {"ok": 15, "partial": 15, "rate_limited": 30, "deferred": 30}
COOLDOWN_AFTER_FAILURE_MIN = 2


def next_manual_sync(conn: Database, source: str, now: datetime | None = None) -> datetime | None:
    """When a manual sync may next call Garmin, or None when it may now. Protects the Garmin account from bursts."""
    now = now or datetime.now(timezone.utc)
    job = one(conn.sync_job, {"source": source, "finished_at": {"$ne": None}}, sort=[("id", -1)])
    t = None
    if job:
        done = datetime.fromisoformat(job["finished_at"].replace("Z", "+00:00"))
        t = done + timedelta(minutes=COOLDOWN_MIN.get(job.get("outcome"), COOLDOWN_AFTER_FAILURE_MIN))
    row = get_connection_row(conn, source)
    if row and row.get("retry_not_before"):  # Garmin's own back-off, when it set one
        rb = datetime.fromisoformat(row["retry_not_before"].replace("Z", "+00:00"))
        t = max(t, rb) if t else rb
    return t if t and t > now else None

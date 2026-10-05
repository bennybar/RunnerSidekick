"""Idempotent persistence of normalised records. Upserts are keyed on source identifiers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pymongo import ReplaceOne, UpdateOne
from pymongo.database import Database

from .connectors.base import METRIC_UNITS, Activity, DayBundle, RawPayload
from .db import next_id, one, utc_now


def save_raw(conn: Database, source: str, raw: list[RawPayload]) -> None:
    now = utc_now()
    ops = [ReplaceOne({"source": source, "kind": r.kind, "source_key": r.source_key},
                      {"source": source, "kind": r.kind, "source_key": r.source_key, "fetched_at": now, "payload": r.payload}, upsert=True)
           for r in raw]
    if ops:
        conn.raw_payload.bulk_write(ops, ordered=False)


def save_day(conn: Database, source: str, b: DayBundle) -> set[str]:
    """Upsert a day's observations and sleep sessions; returns the local dates whose inputs changed.

    Policy: a `not_measured` row never overwrites a `measured` one, because a later fetch
    for an adjacent date can legitimately lack a value that an earlier fetch attributed here.
    """
    now = utc_now()
    changed: set[str] = set()
    save_raw(conn, source, b.raw)
    for o in b.observations:
        key = {"source": source, "local_date": o.local_date, "metric": o.metric}
        prev = one(conn.daily_observation, key)
        if prev is not None and prev["state"] == "measured" and o.state != "measured":
            continue
        if prev is not None and prev["value"] == o.value and prev["state"] == o.state and prev["label"] == o.label:
            continue
        conn.daily_observation.replace_one(key, {**key, "value": o.value, "unit": METRIC_UNITS[o.metric], "state": o.state, "method": o.method,
                                                 "label": o.label, "source_record_id": o.source_record_id, "observed_start": o.observed_start,
                                                 "observed_end": o.observed_end, "ingested_at": now}, upsert=True)
        changed.add(o.local_date)
    for s in b.sleep:
        key = {"source": source, "source_id": s.source_id}
        prev = one(conn.sleep_session, key)
        if prev and (prev["duration_s"], prev["end_utc"], prev["garmin_sleep_score"]) == (s.duration_s, s.end_utc, s.garmin_sleep_score):
            continue
        conn.sleep_session.replace_one(key, {**key, "wake_date": s.wake_date, "start_utc": s.start_utc, "end_utc": s.end_utc,
                                             "utc_offset_s": s.utc_offset_s, "is_nap": bool(s.is_nap), "duration_s": s.duration_s,
                                             "deep_s": s.deep_s, "light_s": s.light_s, "rem_s": s.rem_s, "awake_s": s.awake_s,
                                             "garmin_sleep_score": s.garmin_sleep_score, "ingested_at": now}, upsert=True)
        changed.add(s.wake_date)
    return changed


def activity_hash(conn: Database, source: str, source_id: str) -> str | None:
    r = one(conn.activity, {"source": source, "source_id": source_id})
    return r["content_hash"] if r else None


def save_activity(conn: Database, source: str, a: Activity, chash: str) -> int:
    now = utc_now()
    save_raw(conn, source, a.raw)
    key = {"source": source, "source_id": a.source_id}
    prev = one(conn.activity, key)
    aid = prev["id"] if prev else next_id(conn, "activity")
    conn.activity.replace_one(key, {
        **key, "id": aid, "sport": a.sport, "name": a.name, "start_utc": a.start_utc, "utc_offset_s": a.utc_offset_s,
        "local_date": a.local_date, "distance_m": a.distance_m, "elapsed_s": a.elapsed_s, "moving_s": a.moving_s, "timer_s": a.timer_s,
        "avg_hr": a.avg_hr, "max_hr": a.max_hr, "elevation_gain_m": a.elevation_gain_m, "elevation_loss_m": a.elevation_loss_m,
        "avg_cadence_spm": a.avg_cadence_spm, "garmin_metrics": a.garmin_metrics, "content_hash": chash,
        "ingested_at": prev["ingested_at"] if prev else now, "updated_at": now, "device_id": a.device_id, "manufacturer": a.manufacturer,
    }, upsert=True)
    conn.activity_lap.delete_many({"activity_id": aid})
    if a.laps:
        # Replace by (activity, lap) so two syncs writing the same run at once can't collide on the unique index
        conn.activity_lap.bulk_write([ReplaceOne({"activity_id": aid, "idx": l["idx"]}, l, upsert=True) for l in [{
            "activity_id": aid, "idx": l.idx, "start_utc": l.start_utc, "distance_m": l.distance_m, "elapsed_s": l.elapsed_s,
            "moving_s": l.moving_s, "avg_hr": l.avg_hr, "max_hr": l.max_hr, "elevation_gain_m": l.elevation_gain_m,
            "elevation_loss_m": l.elevation_loss_m, "avg_cadence_spm": l.avg_cadence_spm, "intensity": l.intensity} for l in a.laps]])
    if a.samples is not None:
        conn.activity_samples.replace_one({"activity_id": aid}, {"activity_id": aid, "samples": a.samples.to_json()}, upsert=True)
    return aid


def purge_raw(conn: Database, retention_days: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat().replace("+00:00", "Z")
    return conn.raw_payload.delete_many({"fetched_at": {"$lt": cutoff}}).deleted_count


__all__ = ["save_raw", "save_day", "activity_hash", "save_activity", "purge_raw", "UpdateOne"]

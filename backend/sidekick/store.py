"""Idempotent persistence of normalised records. Upserts are keyed on source identifiers."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from .connectors.base import METRIC_UNITS, Activity, DayBundle, RawPayload
from .db import utc_now


def save_raw(conn: sqlite3.Connection, source: str, raw: list[RawPayload]) -> None:
    now = utc_now()
    conn.executemany(
        "INSERT INTO raw_payload (source, kind, source_key, fetched_at, payload_json) VALUES (?,?,?,?,?) "
        "ON CONFLICT (source, kind, source_key) DO UPDATE SET fetched_at=excluded.fetched_at, payload_json=excluded.payload_json",
        [(source, r.kind, r.source_key, now, json.dumps(r.payload, default=str)) for r in raw],
    )


def save_day(conn: sqlite3.Connection, source: str, b: DayBundle) -> set[str]:
    """Upsert a day's observations and sleep sessions; returns the local dates whose inputs changed.

    Policy: a `not_measured` row never overwrites a `measured` one, because a later fetch
    for an adjacent date can legitimately lack a value that an earlier fetch attributed here.
    """
    now = utc_now()
    changed: set[str] = set()
    save_raw(conn, source, b.raw)
    for o in b.observations:
        prev = conn.execute("SELECT value, state, label FROM daily_observation WHERE source=? AND local_date=? AND metric=?",
                            (source, o.local_date, o.metric)).fetchone()
        if prev is not None and prev["state"] == "measured" and o.state != "measured":
            continue
        if prev is not None and prev["value"] == o.value and prev["state"] == o.state and prev["label"] == o.label:
            continue
        conn.execute(
            "INSERT INTO daily_observation (source, local_date, metric, value, unit, state, method, label, source_record_id,"
            " observed_start, observed_end, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT (source, local_date, metric) DO UPDATE SET value=excluded.value, state=excluded.state,"
            " method=excluded.method, label=excluded.label, source_record_id=excluded.source_record_id,"
            " observed_start=excluded.observed_start, observed_end=excluded.observed_end, ingested_at=excluded.ingested_at",
            (source, o.local_date, o.metric, o.value, METRIC_UNITS[o.metric], o.state, o.method, o.label,
             o.source_record_id, o.observed_start, o.observed_end, now),
        )
        changed.add(o.local_date)
    for s in b.sleep:
        cur = conn.execute(
            "INSERT INTO sleep_session (source, source_id, wake_date, start_utc, end_utc, utc_offset_s, is_nap, duration_s,"
            " deep_s, light_s, rem_s, awake_s, garmin_sleep_score, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT (source, source_id) DO UPDATE SET wake_date=excluded.wake_date, start_utc=excluded.start_utc,"
            " end_utc=excluded.end_utc, utc_offset_s=excluded.utc_offset_s, is_nap=excluded.is_nap,"
            " duration_s=excluded.duration_s, deep_s=excluded.deep_s, light_s=excluded.light_s, rem_s=excluded.rem_s,"
            " awake_s=excluded.awake_s, garmin_sleep_score=excluded.garmin_sleep_score, ingested_at=excluded.ingested_at"
            " WHERE sleep_session.duration_s IS NOT excluded.duration_s OR sleep_session.end_utc IS NOT excluded.end_utc"
            " OR sleep_session.garmin_sleep_score IS NOT excluded.garmin_sleep_score",
            (source, s.source_id, s.wake_date, s.start_utc, s.end_utc, s.utc_offset_s, int(s.is_nap), s.duration_s,
             s.deep_s, s.light_s, s.rem_s, s.awake_s, s.garmin_sleep_score, now),
        )
        if cur.rowcount:
            changed.add(s.wake_date)
    return changed


def activity_hash(conn: sqlite3.Connection, source: str, source_id: str) -> str | None:
    r = conn.execute("SELECT content_hash FROM activity WHERE source=? AND source_id=?", (source, source_id)).fetchone()
    return r["content_hash"] if r else None


def save_activity(conn: sqlite3.Connection, source: str, a: Activity, chash: str) -> int:
    now = utc_now()
    save_raw(conn, source, a.raw)
    conn.execute(
        "INSERT INTO activity (source, source_id, sport, name, start_utc, utc_offset_s, local_date, distance_m, elapsed_s,"
        " moving_s, timer_s, avg_hr, max_hr, elevation_gain_m, elevation_loss_m, avg_cadence_spm, garmin_metrics_json,"
        " content_hash, ingested_at, updated_at, device_id, manufacturer) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT (source, source_id) DO UPDATE SET sport=excluded.sport, name=excluded.name,"
        " start_utc=excluded.start_utc, utc_offset_s=excluded.utc_offset_s, local_date=excluded.local_date,"
        " distance_m=excluded.distance_m, elapsed_s=excluded.elapsed_s, moving_s=excluded.moving_s,"
        " timer_s=excluded.timer_s, avg_hr=excluded.avg_hr, max_hr=excluded.max_hr,"
        " elevation_gain_m=excluded.elevation_gain_m, elevation_loss_m=excluded.elevation_loss_m,"
        " avg_cadence_spm=excluded.avg_cadence_spm, garmin_metrics_json=excluded.garmin_metrics_json,"
        " content_hash=excluded.content_hash, updated_at=excluded.ingested_at, device_id=excluded.device_id,"
        " manufacturer=excluded.manufacturer",
        (source, a.source_id, a.sport, a.name, a.start_utc, a.utc_offset_s, a.local_date, a.distance_m, a.elapsed_s,
         a.moving_s, a.timer_s, a.avg_hr, a.max_hr, a.elevation_gain_m, a.elevation_loss_m, a.avg_cadence_spm,
         json.dumps(a.garmin_metrics), chash, now, now, a.device_id, a.manufacturer),
    )
    aid = conn.execute("SELECT id FROM activity WHERE source=? AND source_id=?", (source, a.source_id)).fetchone()["id"]
    conn.execute("DELETE FROM activity_lap WHERE activity_id=?", (aid,))
    conn.executemany(
        "INSERT INTO activity_lap VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(aid, l.idx, l.start_utc, l.distance_m, l.elapsed_s, l.moving_s, l.avg_hr, l.max_hr, l.elevation_gain_m,
          l.elevation_loss_m, l.avg_cadence_spm, l.intensity) for l in a.laps],
    )
    if a.samples is not None:
        conn.execute("INSERT INTO activity_samples VALUES (?,?) ON CONFLICT (activity_id) DO UPDATE SET samples_json=excluded.samples_json",
                     (aid, json.dumps(a.samples.to_json())))
    return aid


def purge_raw(conn: sqlite3.Connection, retention_days: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat().replace("+00:00", "Z")
    return conn.execute("DELETE FROM raw_payload WHERE fetched_at < ?", (cutoff,)).rowcount

-- Canonical units: metres, seconds, m/s, bpm, milliseconds (HRV), kilograms.
-- Instants are ISO-8601 UTC strings ("...Z"); offsets are seconds east of UTC at the source.

CREATE TABLE source_connection (
    source              TEXT PRIMARY KEY,
    state               TEXT NOT NULL,          -- connected | not_configured | reauth_required | rate_limited | error
    detail              TEXT,
    last_attempt_at     TEXT,
    last_success_at     TEXT,                   -- last successful fetch from the source (not watch-sync time)
    retry_not_before    TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    capabilities_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE sync_checkpoint (
    source          TEXT NOT NULL,
    stream          TEXT NOT NULL,              -- days | activities
    backfill_target TEXT,                       -- oldest local date the backfill aims for
    oldest_done     TEXT,                       -- backfill progress (walks backwards from the newest date)
    newest_done     TEXT,                       -- incremental cursor
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (source, stream)
);

CREATE TABLE sync_job (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    kind        TEXT NOT NULL,                  -- backfill | incremental
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    outcome     TEXT,                           -- ok | partial | auth_failed | rate_limited | error
    detail      TEXT,
    days_fetched INTEGER NOT NULL DEFAULT 0,
    activities_fetched INTEGER NOT NULL DEFAULT 0
);

-- Source payloads, kept for re-normalisation and audit; purged by retention policy.
CREATE TABLE raw_payload (
    source      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    source_key  TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (source, kind, source_key)
);

-- One row per (date, metric). state distinguishes a measured value from a fetched-but-absent one.
-- A date that was never fetched has no row at all.
CREATE TABLE daily_observation (
    source          TEXT NOT NULL,
    local_date      TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           REAL,
    unit            TEXT NOT NULL,
    state           TEXT NOT NULL,              -- measured | not_measured | invalid
    method          TEXT,                       -- measurement type, used to keep e.g. HRV comparable
    label           TEXT,                       -- source text status (e.g. Garmin HRV status), when supplied
    source_record_id TEXT,
    observed_start  TEXT,
    observed_end    TEXT,
    ingested_at     TEXT NOT NULL,
    PRIMARY KEY (source, local_date, metric)
);

CREATE TABLE activity (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    sport           TEXT NOT NULL,
    name            TEXT,
    start_utc       TEXT NOT NULL,
    utc_offset_s    INTEGER,
    local_date      TEXT NOT NULL,
    distance_m      REAL,
    elapsed_s       REAL,
    moving_s        REAL,
    timer_s         REAL,
    avg_hr          REAL,
    max_hr          REAL,
    elevation_gain_m REAL,
    elevation_loss_m REAL,
    avg_cadence_spm REAL,
    garmin_metrics_json TEXT NOT NULL DEFAULT '{}',  -- Garmin-generated values under their own names
    content_hash    TEXT NOT NULL,
    ingested_at     TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (source, source_id)
);
CREATE INDEX activity_local_date ON activity (local_date);

CREATE TABLE activity_lap (
    activity_id INTEGER NOT NULL REFERENCES activity(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    start_utc   TEXT,
    distance_m  REAL,
    elapsed_s   REAL,
    moving_s    REAL,
    avg_hr      REAL,
    max_hr      REAL,
    elevation_gain_m REAL,
    elevation_loss_m REAL,
    avg_cadence_spm REAL,
    intensity   TEXT,                           -- source lap intensity type when supplied (e.g. active, rest)
    PRIMARY KEY (activity_id, idx)
);

-- Time series stored as compact JSON columns: t (s since start), hr, speed, dist, elev, cad.
-- Null entries are gaps, never zeros.
CREATE TABLE activity_samples (
    activity_id INTEGER PRIMARY KEY REFERENCES activity(id) ON DELETE CASCADE,
    samples_json TEXT NOT NULL
);

CREATE TABLE sleep_session (
    source          TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    wake_date       TEXT NOT NULL,              -- reporting date: local date of wake-up
    start_utc       TEXT NOT NULL,
    end_utc         TEXT NOT NULL,
    utc_offset_s    INTEGER,
    is_nap          INTEGER NOT NULL DEFAULT 0,
    duration_s      REAL,
    deep_s          REAL,
    light_s         REAL,
    rem_s           REAL,
    awake_s         REAL,
    garmin_sleep_score REAL,
    ingested_at     TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX sleep_wake_date ON sleep_session (wake_date);

-- Check-ins are written offline on the phone; id is a client UUID. Conflict policy: last client_updated_at wins.
CREATE TABLE checkin (
    id              TEXT PRIMARY KEY,
    local_date      TEXT NOT NULL,
    energy          INTEGER,                    -- 1..5
    soreness        INTEGER,                    -- 1..5 (5 = very sore)
    recovery        INTEGER,                    -- 1..5
    pain            INTEGER NOT NULL DEFAULT 0,
    illness         INTEGER NOT NULL DEFAULT 0,
    notes           TEXT,
    tags_json       TEXT NOT NULL DEFAULT '[]',
    client_updated_at TEXT NOT NULL,
    received_at     TEXT NOT NULL,
    deleted         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX checkin_local_date ON checkin (local_date);

CREATE TABLE activity_effort (
    activity_source_id TEXT PRIMARY KEY,
    rpe             INTEGER NOT NULL,           -- 1..10 session RPE
    client_updated_at TEXT NOT NULL
);

CREATE TABLE report (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT NOT NULL,              -- morning | post_run | weekly
    subject_key     TEXT NOT NULL,              -- local date, or activity source_id
    local_date      TEXT NOT NULL,
    revision        INTEGER NOT NULL,
    generated_at    TEXT NOT NULL,
    data_cutoff     TEXT NOT NULL,
    input_hash      TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    body_json       TEXT NOT NULL,
    UNIQUE (type, subject_key, revision)
);

CREATE TABLE user_settings (
    key     TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

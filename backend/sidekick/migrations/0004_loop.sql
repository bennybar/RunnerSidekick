-- The intent → suggestion → outcome loop.

-- What the runner intends to do on a day. Last client write wins.
CREATE TABLE day_plan (
    local_date  TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,            -- rest | easy | long | tempo | intervals | race | other
    minutes     INTEGER,
    client_updated_at TEXT NOT NULL
);

-- What a run was meant to be (user-stated; may be pre-filled from the day's plan) and a private note.
CREATE TABLE run_intent (
    activity_source_id TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,            -- easy | long | tempo | intervals | race | recovery | other
    note        TEXT,                     -- private: never sent to AI providers
    source      TEXT NOT NULL,            -- user | plan
    client_updated_at TEXT NOT NULL
);

-- One chosen focus per calendar week, evaluated against that week's runs.
CREATE TABLE weekly_focus (
    week_start  TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,            -- even_pacing | easy_runs | steady_volume | consistency | recovery
    params_json TEXT NOT NULL DEFAULT '{}',
    chosen_at   TEXT NOT NULL
);

-- Insight dismissals / "working on it", keyed by insight id. Re-shown when the insight's verdict changes.
CREATE TABLE insight_state (
    insight_id  TEXT PRIMARY KEY,
    state       TEXT NOT NULL,            -- dismissed | working_on
    verdict_at_dismissal TEXT,
    updated_at  TEXT NOT NULL
);

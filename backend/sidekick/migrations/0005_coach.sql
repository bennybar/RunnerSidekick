-- Validated AI coach analyses, one per evidence input hash. Doubles as the AI cost ledger with `narrative`.
CREATE TABLE coach_analysis (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    input_hash    TEXT NOT NULL,
    model         TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    status        TEXT NOT NULL,          -- ok | rejected | failed
    detail        TEXT,
    output_json   TEXT,
    targets_json  TEXT,                   -- evidence id -> where it opens in the app
    key_source    TEXT NOT NULL,          -- server | user (a user's own key is never stored)
    created_at    TEXT NOT NULL
);
CREATE INDEX coach_hash ON coach_analysis (input_hash);

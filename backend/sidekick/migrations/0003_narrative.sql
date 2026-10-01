-- Cached AI narratives, one per (report revision input, model, prompt version). Doubles as the cost ledger.
CREATE TABLE narrative (
    report_type     TEXT NOT NULL,
    subject_key     TEXT NOT NULL,
    input_hash      TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    status          TEXT NOT NULL,      -- ok | rejected | failed
    detail          TEXT,
    output_json     TEXT,
    bundle_sha256   TEXT NOT NULL,      -- what was sent, without storing it again
    created_at      TEXT NOT NULL,
    PRIMARY KEY (report_type, subject_key, input_hash, model, prompt_version)
);

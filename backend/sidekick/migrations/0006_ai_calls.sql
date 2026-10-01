-- Append-only ledger of AI provider calls (narrative and coach), reserved before each call. The daily budget counts these.
CREATE TABLE ai_call (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    feature     TEXT NOT NULL,            -- narrative | coach
    created_at  TEXT NOT NULL,
    outcome     TEXT                      -- ok | rejected | failed (null while in flight)
);

-- Global account database (data/app.db). Health data stays in per-user folders: data/users/<id>/.
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT UNIQUE,
    google_sub  TEXT UNIQUE,
    name        TEXT,
    role        TEXT NOT NULL DEFAULT 'member',   -- owner | member
    created_at  TEXT NOT NULL,
    deleted_at  TEXT
);

-- Invite-only access: an email may sign up only if listed here (owner is always allowed).
CREATE TABLE invites (
    email       TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    used_at     TEXT
);

-- App sessions (bearer tokens). Only SHA-256 hashes are stored.
CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    token_sha256 TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at  TEXT
);
CREATE INDEX sessions_user ON sessions (user_id);

-- Pending Garmin OAuth flows (PKCE). Short-lived; consumed on callback.
CREATE TABLE oauth_states (
    state       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_verifier TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

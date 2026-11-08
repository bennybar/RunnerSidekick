"""Runtime configuration, read from environment variables (all optional; see .env.example at the repo root).

Records live in MongoDB (see db.py, RSK_MONGO_URI). Secrets and Garmin tokens live in the data folder (RSK_DATA_DIR,
default <repo>/data), which is gitignored and never committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SOURCE_GARMIN = "garmin"
SOURCE_FIXTURE = "fixture"


@dataclass(frozen=True)
class Config:
    data_dir: Path
    source: str  # "garmin" or "fixture"; each source gets its own database so demo data never mixes with live
    timezone: str
    backfill_days: int
    refetch_days: int  # recent window re-fetched on every sync for late sleep / revised activities
    raw_retention_days: int
    request_spacing_s: float  # pause between Garmin requests during sync
    user_id: int | None = None  # set per request/user; selects the user's own database

    @property
    def db_name(self) -> str:
        from .db import user_db_name
        if self.user_id is None:
            raise ValueError("no user selected")
        return user_db_name(self.user_id, self.source)

    @property
    def garmin_token_dir(self) -> Path:
        return self.data_dir / "garmin_tokens"


# The data folder sits next to the code (<repo>/data) unless RSK_DATA_DIR points elsewhere (e.g. /data in Docker).
REPO_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_DIR / "data"

# Google Sign-In (optional): the app's public OAuth client IDs (not secrets). Android sign-in requests ID tokens for the
# Web client; the iOS client's ID tokens carry its own ID as audience. Set RSK_GOOGLE_WEB_CLIENT_ID to an empty value to
# switch Google sign-in off; it is invite-only either way (`python -m sidekick invite add EMAIL`).
GOOGLE_WEB_CLIENT_ID = os.getenv("RSK_GOOGLE_WEB_CLIENT_ID", "162421419636-deds89pjaleairjrbj6brdn29ldkhvh9.apps.googleusercontent.com")
GOOGLE_IOS_CLIENT_ID = os.getenv("RSK_GOOGLE_IOS_CLIENT_ID", "162421419636-rj38evk6329k0es0r4oni08qa7ak0sm3.apps.googleusercontent.com")


def public_base_url() -> str | None:
    """The server's public https address (RSK_PUBLIC_BASE_URL), e.g. https://api.example.com; None when unset. Only
    Garmin's official OAuth needs it (its callback address)."""
    return os.getenv("RSK_PUBLIC_BASE_URL", "").strip().rstrip("/") or None


def garmin_redirect_uri() -> str | None:
    base = public_base_url()
    return f"{base}/v1/garmin/oauth/callback" if base else None


def secrets(data_dir: Path) -> dict:
    """Server-only secrets from <data>/secrets.json (gitignored), e.g.
    {"garmin_client_id": "...", "garmin_client_secret": "...", "openai_api_key": "..."}. Missing file = none."""
    import json

    p = data_dir / "secrets.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def server_openai_key(data_dir: Path) -> str | None:
    """The server's own OpenAI key (OPENAI_API_KEY, or "openai_api_key" in secrets.json), unless the owner switched
    server AI off ("server_ai_enabled": false in secrets.json): then AI runs only with a runner's own key or on their
    phone. None without a key: the app works without AI."""
    s = secrets(data_dir)
    if s.get("server_ai_enabled") is False:
        return None
    return os.getenv("OPENAI_API_KEY") or s.get("openai_api_key")


def load_config() -> Config:
    source = os.getenv("RSK_SOURCE", SOURCE_GARMIN)
    if source not in (SOURCE_GARMIN, SOURCE_FIXTURE):
        raise ValueError(f"RSK_SOURCE must be '{SOURCE_GARMIN}' or '{SOURCE_FIXTURE}', got {source!r}")
    data_dir = Path(os.getenv("RSK_DATA_DIR", str(DATA_DIR))).expanduser()
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    return Config(
        data_dir=data_dir,
        source=source,
        timezone=os.getenv("RSK_TIMEZONE", "Asia/Jerusalem"),
        backfill_days=int(os.getenv("RSK_BACKFILL_DAYS", "90")),
        refetch_days=int(os.getenv("RSK_REFETCH_DAYS", "3")),
        raw_retention_days=int(os.getenv("RSK_RAW_RETENTION_DAYS", "120")),
        request_spacing_s=float(os.getenv("RSK_REQUEST_SPACING_S", "0.3")),  # was 1 s: most of a sync was this wait
    )

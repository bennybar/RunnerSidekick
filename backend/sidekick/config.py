"""Runtime configuration, read from environment variables.

Records live in MongoDB (see db.py). Secrets and Garmin tokens live in <repo>/data, which is gitignored and never committed.
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


# Fixed locations: the data folder always sits next to the code (<repo>/data), e.g. /var/www/RunnerSidekick/data on
# the server. No environment setup is needed; RSK_* variables only exist as overrides for tests and demos.
REPO_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_DIR / "data"

# Google Sign-In: the *Web* OAuth client ID from Google Cloud (not a secret). Android sign-in requests ID tokens for it.
GOOGLE_WEB_CLIENT_ID = "162421419636-deds89pjaleairjrbj6brdn29ldkhvh9.apps.googleusercontent.com"  # Google Cloud OAuth Web client (the app's Android clients match by package + signing key)

PUBLIC_BASE_URL = "https://runnersidekick.ibarak.org"
GARMIN_REDIRECT_URI = f"{PUBLIC_BASE_URL}/v1/garmin/oauth/callback"


def secrets(data_dir: Path) -> dict:
    """Server-only secrets from <data>/secrets.json (gitignored), e.g.
    {"garmin_client_id": "...", "garmin_client_secret": "...", "openai_api_key": "..."}. Missing file = none."""
    import json

    p = data_dir / "secrets.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


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
        request_spacing_s=float(os.getenv("RSK_REQUEST_SPACING_S", "1.0")),
    )

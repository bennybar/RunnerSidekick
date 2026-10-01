"""Runtime configuration, read from environment variables.

Secrets (Garmin tokens, device-token hashes) live under the data directory, which
defaults to ~/.runner-sidekick and is never inside the repository.
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

    @property
    def db_path(self) -> Path:
        return self.data_dir / f"{self.source}.db"

    @property
    def garmin_token_dir(self) -> Path:
        return self.data_dir / "garmin_tokens"


def load_config() -> Config:
    source = os.getenv("RSK_SOURCE", SOURCE_FIXTURE)
    if source not in (SOURCE_GARMIN, SOURCE_FIXTURE):
        raise ValueError(f"RSK_SOURCE must be '{SOURCE_GARMIN}' or '{SOURCE_FIXTURE}', got {source!r}")
    data_dir = Path(os.getenv("RSK_DATA_DIR", "~/.runner-sidekick")).expanduser()
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

"""Provider-neutral connector contract and normalised record types.

A connector reads from one source and returns normalised records plus the raw
payloads they came from. It never writes to the source. Future official-Garmin or
Health Connect adapters implement the same interface with their own capability set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Iterable, Protocol


class Capability(str, Enum):
    SUPPORTED = "supported"            # the source can provide this metric
    UNSUPPORTED = "unsupported"        # the source/device cannot provide it
    NO_PERMISSION = "no_permission"    # possible, but access not granted
    UNKNOWN = "unknown"                # not yet observed either way


class ConnectionState(str, Enum):
    CONNECTED = "connected"
    NOT_CONFIGURED = "not_configured"
    REAUTH_REQUIRED = "reauth_required"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class AuthRequired(Exception):
    """Credentials are missing, expired or revoked. Never retried automatically."""


class RateLimited(Exception):
    """The source asked us to slow down."""


class SourceUnavailable(Exception):
    """Transient failure (network, 5xx) after the client's own bounded retries."""


# Metric keys for daily observations, with canonical units.
METRIC_UNITS: dict[str, str] = {
    "resting_hr": "bpm",
    "hrv_overnight_avg": "ms",
    "hrv_weekly_avg": "ms",
    "sleep_duration": "s",
    "steps": "count",
    "active_duration": "s",
    "intensity_minutes_moderate": "min",   # Garmin's moderate-intensity minutes for the day
    "intensity_minutes_vigorous": "min",   # Garmin's vigorous-intensity minutes for the day
    "avg_stress": "garmin_stress_0_100",
    "body_battery_high": "garmin_body_battery",
    "body_battery_low": "garmin_body_battery",
    "respiration_waking_avg": "breaths/min",
    "weight": "kg",
    "body_fat_pct": "%",                   # only from a Garmin scale (Index) when it reports it
    "garmin_training_readiness": "garmin_score_0_100",
    "garmin_vo2max_running": "ml/kg/min",
    "garmin_sleep_score": "garmin_score_0_100",
}

# Values Garmin computes itself. Shown under their own names; never fed into our recommendation rules.
GARMIN_PROPRIETARY = {
    "avg_stress", "body_battery_high", "body_battery_low",
    "garmin_training_readiness", "garmin_vo2max_running", "garmin_sleep_score",
}


@dataclass
class RawPayload:
    kind: str
    source_key: str
    payload: object


@dataclass
class Observation:
    local_date: str
    metric: str
    value: float | None
    state: str = "measured"          # measured | not_measured | invalid
    method: str | None = None
    source_record_id: str | None = None
    observed_start: str | None = None
    observed_end: str | None = None
    # Garmin text status (e.g. HRV "BALANCED") kept alongside numeric value when supplied
    label: str | None = None


@dataclass
class SleepSession:
    source_id: str
    wake_date: str
    start_utc: str
    end_utc: str
    utc_offset_s: int | None
    is_nap: bool
    duration_s: float | None
    deep_s: float | None = None
    light_s: float | None = None
    rem_s: float | None = None
    awake_s: float | None = None
    garmin_sleep_score: float | None = None


@dataclass
class DayBundle:
    local_date: str
    observations: list[Observation] = field(default_factory=list)
    sleep: list[SleepSession] = field(default_factory=list)
    raw: list[RawPayload] = field(default_factory=list)


@dataclass
class Lap:
    idx: int
    start_utc: str | None
    distance_m: float | None
    elapsed_s: float | None
    moving_s: float | None
    avg_hr: float | None
    max_hr: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    avg_cadence_spm: float | None = None
    intensity: str | None = None


@dataclass
class Samples:
    """Parallel arrays. None marks a gap; arrays share the index of `t`."""
    t: list[float]
    hr: list[float | None]
    speed: list[float | None]
    dist: list[float | None]
    elev: list[float | None]
    cad: list[float | None]

    def to_json(self) -> dict:
        return {"t": self.t, "hr": self.hr, "speed": self.speed, "dist": self.dist, "elev": self.elev, "cad": self.cad}

    @staticmethod
    def from_json(d: dict) -> "Samples":
        return Samples(d["t"], d["hr"], d["speed"], d["dist"], d["elev"], d["cad"])


@dataclass
class Activity:
    source_id: str
    sport: str                       # normalised: running | trail_running | treadmill_running | other
    name: str | None
    start_utc: str
    utc_offset_s: int | None
    local_date: str
    distance_m: float | None
    elapsed_s: float | None
    moving_s: float | None
    timer_s: float | None
    avg_hr: float | None
    max_hr: float | None
    elevation_gain_m: float | None
    elevation_loss_m: float | None
    avg_cadence_spm: float | None
    garmin_metrics: dict = field(default_factory=dict)
    device_id: str | None = None
    manufacturer: str | None = None
    laps: list[Lap] = field(default_factory=list)
    samples: Samples | None = None
    raw: list[RawPayload] = field(default_factory=list)


class Connector(Protocol):
    source: str
    synthetic: bool

    def connection_state(self) -> ConnectionState: ...

    def capabilities(self) -> dict[str, Capability]: ...

    def read_days(self, start: date, end: date) -> Iterable[DayBundle]:
        """Historical/incremental daily reads, newest first. Raises AuthRequired/RateLimited/SourceUnavailable."""
        ...

    def list_activities(self, start: date, end: date) -> list[dict]:
        """Lightweight summaries (must include 'source_id' and 'content_hash')."""
        ...

    def read_activity(self, summary: dict) -> Activity:
        """Full activity: laps and samples."""
        ...

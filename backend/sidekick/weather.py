"""Weather around a run, as an Open-Meteo estimate for the run's place and hour, never watch data. Only the start
position rounded to 0.01° (about 1 km) and the date go to Open-Meteo. Looked up when a run is exported, then kept with
the run; a failed lookup is tried again after a day. Indoor runs and runs without GPS get none."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from .db import one, utc_now

log = logging.getLogger(__name__)

FORECAST = "https://api.open-meteo.com/v1/forecast"        # recent days (its past data reaches back about three months)
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"  # older days (its reanalysis lags by a few days)
ARCHIVE_AFTER_DAYS = 30
HOURLY = ("temperature_2m", "relative_humidity_2m", "dew_point_2m", "apparent_temperature", "wind_speed_10m")
RETRY_AFTER = timedelta(days=1)


def lookup(lat: float, lon: float, hour: datetime, fetch=httpx.get) -> dict | None:
    """Hourly values at (lat, lon) for one UTC hour, or None."""
    url = ARCHIVE if (datetime.now(timezone.utc) - hour).days > ARCHIVE_AFTER_DAYS else FORECAST
    day = hour.date().isoformat()
    try:
        r = fetch(url, params={"latitude": lat, "longitude": lon, "hourly": ",".join(HOURLY), "timezone": "GMT",
                               "start_date": day, "end_date": day, "wind_speed_unit": "kmh"}, timeout=8.0)
        r.raise_for_status()
        h = r.json()["hourly"]
        i = h["time"].index(hour.strftime("%Y-%m-%dT%H:00"))
    except Exception as e:  # network, HTTP or shape: no weather rather than a failed export
        log.warning("weather lookup failed: %s", e)
        return None
    vals = {k: h[k][i] for k in HOURLY if h.get(k) and h[k][i] is not None}
    if "temperature_2m" not in vals:
        return None
    return {**vals, "hour_utc": hour.isoformat().replace("+00:00", "Z"), "lat": lat, "lon": lon,
            "source": "Open-Meteo " + ("historical weather (reanalysis)" if url == ARCHIVE else "forecast model, past hours")}


def for_run(conn, a: dict, fetch=httpx.get) -> dict | None:
    if a.get("sport") == "treadmill_running":
        return None
    kept = one(conn.run_weather, {"source_id": a["source_id"]})
    if kept and (kept["weather"] or kept["checked_at"] > (datetime.now(timezone.utc) - RETRY_AFTER).strftime("%Y-%m-%dT%H:%M:%SZ")):
        return kept["weather"]
    raw = one(conn.raw_payload, {"kind": "activity_summary", "source_key": a["source_id"]})
    p = (raw or {}).get("payload") or {}
    if p.get("startLatitude") is None or p.get("startLongitude") is None:
        return None
    start = datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00"))
    mid = start + timedelta(seconds=(a.get("elapsed_s") or 0) / 2 + 1800)  # the hour nearest the run's middle
    w = lookup(round(p["startLatitude"], 2), round(p["startLongitude"], 2), mid.replace(minute=0, second=0, microsecond=0), fetch)
    conn.run_weather.update_one({"source_id": a["source_id"]}, {"$set": {"weather": w, "checked_at": utc_now()}}, upsert=True)
    return w

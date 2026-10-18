"""Weather around a run, as an Open-Meteo estimate for the run's place and hour, never watch data. Only the start
position rounded to 0.01° (about 1 km) and the date go to Open-Meteo. Looked up for new runs during a sync (and on
export), then kept with the run; a failed lookup is tried again after a day. Indoor runs and runs without GPS get none.

Heat: a dew point of 18 °C or more, or a feels-like temperature of 27 °C or more, raises heart rate at the same effort
noticeably. Such runs are marked hot and their drift and fade verdicts say so. Trends compare like with like instead:
only runs both humid (dew point 18 °C or more) and clearly hotter than your own usual (3 °C above your median dew point)
are left out, so a runner in a humid
climate still has a trend."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from .db import one, utc_now

log = logging.getLogger(__name__)

FORECAST = "https://api.open-meteo.com/v1/forecast"        # recent days (its past data reaches back about three months)
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"  # older days (its reanalysis lags by a few days)
ARCHIVE_AFTER_DAYS = 30
HOURLY = ("temperature_2m", "relative_humidity_2m", "dew_point_2m", "apparent_temperature", "wind_speed_10m",
          "wind_direction_10m", "wind_gusts_10m")
WX_VERSION = 2  # 2: wind direction and gusts, the start and finish; estimates kept from before are looked up again
RETRY_AFTER = timedelta(days=1)


def lookup(lat: float, lon: float, start: datetime, end: datetime, fetch=httpx.get) -> dict | None:
    """Open-Meteo's hourly values at (lat, lon) for the hour nearest the run's middle (the summary, as before), and at the
    start and the finish, interpolated between the hours either side. None when the lookup fails."""
    mid = start + (end - start) / 2
    url = ARCHIVE if (datetime.now(timezone.utc) - start).days > ARCHIVE_AFTER_DAYS else FORECAST
    try:
        r = fetch(url, params={"latitude": lat, "longitude": lon, "hourly": ",".join(HOURLY), "timezone": "GMT",
                               "start_date": start.date().isoformat(), "end_date": (end + timedelta(hours=1)).date().isoformat(),
                               "wind_speed_unit": "kmh"}, timeout=8.0)
        r.raise_for_status()
        h = r.json()["hourly"]
        times = [datetime.fromisoformat(x).replace(tzinfo=timezone.utc) for x in h["time"]]
    except Exception as e:  # network, HTTP or shape: no weather rather than a failed export
        log.warning("weather lookup failed: %s", e)
        return None

    def at(when: datetime, interpolate: bool) -> dict:
        i = max((k for k, x in enumerate(times) if x <= when), default=None)
        if i is None:
            return {}
        j = min(i + 1, len(times) - 1)
        f = (when - times[i]).total_seconds() / 3600 if interpolate and j > i else 0.0
        out = {}
        for k in HOURLY:
            a, b = (h.get(k) or [None] * len(times))[i], (h.get(k) or [None] * len(times))[j]
            if a is None:
                continue
            if k == "wind_direction_10m":  # the short way round the compass
                d = ((b if b is not None else a) - a + 540) % 360 - 180
                out[k] = round((a + f * d) % 360)
            else:
                out[k] = round(a + f * ((b if b is not None else a) - a), 1)
        return out
    vals = at((mid + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0), False)  # the hour nearest the middle
    if "temperature_2m" not in vals:
        return None
    return {**vals, "hour_utc": (mid + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z"),
            "start": {**at(start, True), "at_utc": start.isoformat().replace("+00:00", "Z")},
            "end": {**at(end, True), "at_utc": end.isoformat().replace("+00:00", "Z")},
            "lat": lat, "lon": lon, "v": WX_VERSION,
            "source": "Open-Meteo " + ("historical weather (reanalysis)" if url == ARCHIVE else "forecast model, past hours")}


def enabled(conn) -> bool:
    from .reports import get_setting
    return get_setting(conn, "weather_enabled", True)


def for_run(conn, a: dict, fetch=httpx.get) -> dict | None:
    if a.get("sport") == "treadmill_running":
        return None
    kept = one(conn.run_weather, {"source_id": a["source_id"]})
    if not enabled(conn):  # switched off: nothing is sent; estimates kept from before stay with their runs
        return (kept or {}).get("weather")
    if kept and ((kept["weather"] or {}).get("v") == WX_VERSION
                 or not kept["weather"] and kept["checked_at"] > (datetime.now(timezone.utc) - RETRY_AFTER).strftime("%Y-%m-%dT%H:%M:%SZ")):
        return kept["weather"]
    raw = one(conn.raw_payload, {"kind": "activity_summary", "source_key": a["source_id"]})
    p = (raw or {}).get("payload") or {}
    if p.get("startLatitude") is None or p.get("startLongitude") is None:
        return None
    start = datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00"))
    w = lookup(round(p["startLatitude"], 2), round(p["startLongitude"], 2), start, start + timedelta(seconds=a.get("elapsed_s") or 0), fetch)
    if w is None and kept and kept["weather"]:  # an older estimate stays when a new lookup fails
        return kept["weather"]
    conn.run_weather.update_one({"source_id": a["source_id"]}, {"$set": {"weather": w, "checked_at": utc_now()}}, upsert=True)
    return w


HOT_DEW_POINT_C = 18.0
HOT_FEELS_LIKE_C = 27.0
SYNC_LOOKUPS = 30   # at most this many lookups per sync
CATCH_UP_DAYS = 30  # recent runs still without weather are tried too, after the sync's own


# Heat stress for running, from the hottest of the run's start, middle and finish: dew point (how humid the air feels, the
# best single guide to how much heat slows a runner) or the feels-like temperature, whichever is worse. The Hot step is
# the same bar as `hot` above. Running context, not a medical risk assessment.
STRESS = (("High heat stress", 24.0, 32.0), ("Hot", HOT_DEW_POINT_C, HOT_FEELS_LIKE_C), ("Warm", 13.0, 20.0))
STRESS_BASIS = ("dew point 13 °C or feels-like 20 °C: Warm; 18 °C or 27 °C: Hot; 24 °C or 32 °C: High heat stress "
                "(the hottest of start, middle and finish)")


def heat_stress(w: dict) -> str:
    points = [w] + [w.get(k) for k in ("start", "end") if w.get(k)]
    dew = max((p["dew_point_2m"] for p in points if p.get("dew_point_2m") is not None), default=None)
    feels = max((p["apparent_temperature"] for p in points if p.get("apparent_temperature") is not None), default=None)
    return next((label for label, d, f in STRESS if (dew is not None and dew >= d) or (feels is not None and feels >= f)), "Comfortable")


def compass(deg: float) -> str:
    return ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")[round(deg / 22.5) % 16]


def heat(w: dict | None) -> dict | None:
    """{"hot": bool, "say": "25°C, dew point 19°C", "stress": "Hot"} from a stored estimate, or None without one."""
    if not w or w.get("temperature_2m") is None:
        return None
    dew, feels = w.get("dew_point_2m"), w.get("apparent_temperature")
    hot = (dew is not None and dew >= HOT_DEW_POINT_C) or (feels is not None and feels >= HOT_FEELS_LIKE_C)
    say = f"{w['temperature_2m']:.0f}°C" + (f", dew point {dew:.0f}°C" if dew is not None else "")
    return {"hot": hot, "say": say, "temperature_c": w["temperature_2m"], "dew_point_c": dew, "stress": heat_stress(w)}


def stored(conn, source_id: str) -> dict | None:
    """The kept estimate for a run, without looking anything up."""
    r = one(conn.run_weather, {"source_id": source_id})
    return (r or {}).get("weather")


def for_new_runs(conn, source: str, sids: list[str], fetch=httpx.get) -> list[str]:
    """Looks up weather for a sync's new or changed runs, then recent runs still without it, before reports are built.
    Returns the runs that gained an estimate, so their reports are rebuilt with it."""
    from . import reports as rp
    if not enabled(conn):
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=CATCH_UP_DAYS)).strftime("%Y-%m-%d")
    have = {r["source_id"] for r in conn.run_weather.find({"weather": {"$ne": None}}, {"source_id": 1})}
    recent = [a["source_id"] for a in rp.activities(conn, source, since, "9999-12-31") if a["source_id"] not in have]
    got = []
    for sid in list(dict.fromkeys([s for s in sids if s not in have] + recent))[:SYNC_LOOKUPS]:
        a = rp.activity_by_source_id(conn, source, sid)
        if a:
            try:
                if for_run(conn, a, fetch):
                    got.append(sid)
            except Exception as e:  # weather is a nicety: never a failed sync
                log.warning("weather for %s: %s", sid, e)
    return got


UNUSUAL_DEW_ABOVE_C = 3.0


def unusually_hot(conn) -> set[str]:
    """Runs both humid enough to matter (dew point 18 °C or more) and 3 °C or more above this runner's median dew point:
    left out of trends (like with like). The absolute bar keeps a temperate runner's warmer summer days in."""
    rows = [(r["source_id"], r["weather"]["dew_point_2m"]) for r in conn.run_weather.find({"weather.dew_point_2m": {"$ne": None}},
                                                                                            {"source_id": 1, "weather.dew_point_2m": 1})]
    if len(rows) < 5:
        return set()
    from statistics import median
    usual = median(d for _, d in rows)
    return {sid for sid, d in rows if d >= max(usual + UNUSUAL_DEW_ABOVE_C, HOT_DEW_POINT_C)}

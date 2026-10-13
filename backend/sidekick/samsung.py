"""Galaxy Watch data, sent by the app from Samsung Health on the phone (Samsung Health Data SDK). Samsung has no cloud
API, so the phone reads and uploads; everything after that happens here, the same as for Garmin.

Which watch counts for a day: the runner picks their watch in Settings, and every switch is kept with its date
(`watch_history`). Samsung data for a day when Samsung was the watch goes into the stream the analysis reads (the
records Garmin fills on Garmin days). Samsung data from other days is kept under its own source, outside the analysis,
so nothing is lost. A run recorded by both watches shows once: the current watch's copy; the other is set aside.
Garmin's sync pauses while Samsung is the watch, and never fills a Samsung day."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone

from pymongo.database import Database

from .connectors.base import Activity, DayBundle, Lap, Observation, RawPayload, Samples, SleepSession, valid_hr
from .db import get_setting, many, set_setting
from .routes import shape_from_track
from .store import save_activity, save_day

SAMSUNG = "samsung"          # the source Samsung data is kept under when it's not in the analysis stream
GARMIN_ASIDE = "garmin_aside"  # a Garmin run set aside because the Samsung watch recorded it too, on a Samsung day
WATCHES = ("garmin", "samsung")
SAME_RUN_S = 300             # two runs starting within 5 minutes of each other are the same run on two watches
RHR_WINDOW_S = 30 * 60       # resting heart rate: the lowest 30-minute average of the day, as Garmin defines it
RHR_MIN_READINGS = 24        # ...from at least 24 readings (4 hours at Samsung's default of one every 10 minutes)
NAP_MAX_S = 3 * 3600
SPORTS = {"RUNNING": "running", "TRACK_RUNNING": "running", "TREADMILL": "treadmill_running"}
CONVERSION = 2  # raised when the way a run is converted changes, so runs sent again are converted again


# ---------------------------------------------------------------- which watch counts for a day

def watch_history(conn: Database) -> list[dict]:
    return get_setting(conn, "watch_history", []) or []


def watch_on(conn: Database, d: str) -> str:
    """The watch that counts for local date `d`: Garmin unless the runner had switched to Samsung by then."""
    current = "garmin"
    for h in watch_history(conn):
        if h["from"] <= d:
            current = h["watch"]
    return current


def switch(conn: Database, watch: str, today: date) -> None:
    """Make `watch` the runner's watch from today. A switch back on the same day replaces that day's switch."""
    hist = [h for h in watch_history(conn) if h["from"] < today.isoformat()]
    if (hist[-1]["watch"] if hist else "garmin") != watch:
        hist.append({"watch": watch, "from": today.isoformat()})
    set_setting(conn, "watch_history", hist)


# ---------------------------------------------------------------- converting what the phone sends

def _utc(ms: float) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _local_date(ms: float, offset_s: int | None) -> str:
    return (_utc(ms) + timedelta(seconds=offset_s or 0)).date().isoformat()


def _haversine(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def activity(a: dict) -> Activity:
    """One workout from the phone: the summary, the per-second log [ms, hr, speed m/s, cadence spm, power W] and the
    route [ms, lat, lon, altitude]. Samples go on a one-second grid (the watch logs heart rate and speed in separate
    entries); distance is the speed integrated and scaled to the watch's total; altitude comes from the route."""
    start_ms, offset = a["start"], a.get("offset_s")
    start = _utc(start_ms)
    by_s: dict[int, list] = {}
    for e in a.get("log") or []:
        s = int((e[0] - start_ms) // 1000)
        if s < 0:
            continue
        row = by_s.setdefault(s, [None, None, None, None])
        for i in range(4):
            v = _num(e[i + 1]) if len(e) > i + 1 else None
            if v is not None:
                row[i] = v
    route = [(int((p[0] - start_ms) // 1000), _num(p[1]), _num(p[2]), _num(p[3]) if len(p) > 3 else None) for p in a.get("route") or []]
    route = [p for p in route if p[1] is not None and p[2] is not None and (p[1], p[2]) != (0, 0)]
    alt = {p[0]: p[3] for p in route if p[3] is not None}
    secs = sorted(by_s)
    total = _num(a.get("distance_m"))
    samples, shape = None, None
    if secs:
        dist, run, prev = [], 0.0, secs[0]
        for s in secs:
            sp = by_s[s][1]
            if sp is not None:
                run += sp * min(s - prev, 5)  # a gap longer than 5 s (a pause) adds no distance
            prev = s
            dist.append(run)
        k = total / run if total and run > 0 else 1.0
        dist = [round(d * k, 1) for d in dist]
        elev = [next((alt[s + j] for j in (0, -1, 1, -2, 2) if s + j in alt), None) for s in secs]
        power = [by_s[s][3] for s in secs]
        samples = Samples(t=[float(s) for s in secs], hr=valid_hr([by_s[s][0] for s in secs]), speed=[by_s[s][1] for s in secs],
                          dist=dist, elev=elev, cad=[by_s[s][2] for s in secs], power=power if any(p is not None for p in power) else None)
    # Samsung keeps no laps: 1 km splits from the samples, like Garmin's automatic laps (the last one is what's left)
    laps: list[Lap] = []
    if samples:
        s, first = samples, 0
        for i in range(1, len(s.t)):
            if s.dist[i] < (len(laps) + 1) * 1000 and i < len(s.t) - 1:
                continue
            seg = range(first + 1, i + 1)
            hr = [s.hr[j] for j in seg if s.hr[j] is not None]
            cad = [s.cad[j] for j in seg if s.cad[j] is not None]
            el = [s.elev[j] for j in range(first, i + 1, 10) if s.elev[j] is not None]  # every 10 s: GPS altitude is noisy
            laps.append(Lap(idx=len(laps), start_utc=_iso(start + timedelta(seconds=s.t[first])),
                            distance_m=round(s.dist[i] - s.dist[first], 1), elapsed_s=s.t[i] - s.t[first],
                            moving_s=float(sum(min(s.t[j] - s.t[j - 1], 5) for j in seg if (s.speed[j] or 0) >= 0.5)),
                            avg_hr=round(sum(hr) / len(hr), 1) if hr else None, max_hr=max(hr) if hr else None,
                            elevation_gain_m=round(sum(max(0.0, b - a) for a, b in zip(el, el[1:])), 1) if len(el) > 1 else None,
                            avg_cadence_spm=round(sum(cad) / len(cad), 1) if cad else None))
            first = i
        laps = [l for l in laps if l.distance_m and l.distance_m > 0]
    if len(route) >= 10:
        along, run = [0.0], 0.0
        for p, q in zip(route, route[1:]):
            run += _haversine(p[1:3], q[1:3])
            along.append(run)
        shape = shape_from_track(along, [p[1] for p in route], [p[2] for p in route])
    moving = sum(1 for s in secs if (by_s[s][1] or 0) >= 0.5) if secs else None
    summary = {k: v for k, v in a.items() if k not in ("log", "route")}
    if route:  # where the run started, for its weather (rounded to ~1 km when looked up); the track itself isn't kept
        summary.update(startLatitude=route[0][1], startLongitude=route[0][2])
    sid = f"samsung-{a['uid']}"
    return Activity(
        source_id=sid, sport=SPORTS.get(str(a.get("type") or "").upper(), "other"), name=a.get("title") or None,
        start_utc=_iso(start), utc_offset_s=offset, local_date=_local_date(start_ms, offset),
        distance_m=total, elapsed_s=(a["end"] - start_ms) / 1000 if a.get("end") else _num(a.get("duration_s")),
        moving_s=float(moving) if moving else None, timer_s=_num(a.get("duration_s")),
        avg_hr=_num(a.get("avg_hr")), max_hr=_num(a.get("max_hr")), elevation_gain_m=_num(a.get("climb_m")),
        elevation_loss_m=_num(a.get("descent_m")), avg_cadence_spm=_num(a.get("avg_cadence")),
        device_id=a.get("device") or None, manufacturer="Samsung", laps=laps, samples=samples, shape=shape,
        raw=[RawPayload("activity_summary", sid, summary)])


def sleep(s: dict) -> SleepSession:
    """One night (or nap) from the phone: [start ms, end ms, stage] per stage. Sleep time leaves out time awake."""
    stage_s = {"DEEP": 0.0, "LIGHT": 0.0, "REM": 0.0, "AWAKE": 0.0}
    for st in s.get("stages") or []:
        name = str(st[2]).upper()
        if name in stage_s:
            stage_s[name] += max(0.0, (st[1] - st[0]) / 1000)
    asleep = stage_s["DEEP"] + stage_s["LIGHT"] + stage_s["REM"]
    duration = asleep if asleep > 0 else _num(s.get("duration_s"))
    start_local = _utc(s["start"]) + timedelta(seconds=s.get("offset_s") or 0)
    nap = (duration or 0) < NAP_MAX_S and 9 <= start_local.hour < 20
    return SleepSession(
        source_id=f"samsung-{s['uid']}", wake_date=_local_date(s["end"], s.get("offset_s")), start_utc=_iso(_utc(s["start"])),
        end_utc=_iso(_utc(s["end"])), utc_offset_s=s.get("offset_s"), is_nap=nap, duration_s=duration,
        deep_s=stage_s["DEEP"] or None, light_s=stage_s["LIGHT"] or None, rem_s=stage_s["REM"] or None, awake_s=stage_s["AWAKE"] or None)


def resting_hr(readings: list[list], offset_s: int | None) -> dict[str, float]:
    """Resting heart rate per local day: the lowest average over any 30 minutes (Garmin's definition), from the watch's
    all-day readings [ms, bpm]. Samsung doesn't share its own resting heart rate, so it's worked out here."""
    days: dict[str, list[tuple[float, float]]] = {}
    for r in readings:
        bpm = _num(r[1]) if len(r) > 1 else None
        if bpm is None or not 30 <= bpm <= 240:
            continue
        days.setdefault(_local_date(r[0], offset_s), []).append((r[0] / 1000, bpm))
    out = {}
    for d, rs in days.items():
        if len(rs) < RHR_MIN_READINGS:
            continue
        rs.sort()
        best, j, total = None, 0, 0.0
        for i, (t0, _) in enumerate(rs):  # a sliding window: rs[i..j) are the readings within 30 minutes of rs[i]
            while j < len(rs) and rs[j][0] - t0 < RHR_WINDOW_S:
                total += rs[j][1]
                j += 1
            n = j - i
            if n >= 3 and rs[j - 1][0] - t0 >= RHR_WINDOW_S / 2:  # at least 3 readings spread over 15 minutes or more
                best = total / n if best is None else min(best, total / n)
            total -= rs[i][1]
        if best is not None:
            out[d] = round(best, 1)
    return out


# ---------------------------------------------------------------- storing

def _hash(a: dict) -> str:
    return hashlib.sha256(json.dumps([CONVERSION, a], sort_keys=True, default=str).encode()).hexdigest()


def ingest(conn: Database, stream: str, body: dict) -> tuple[set[str], list[str]]:
    """Store what the phone sent. Returns the dates and runs (in the stream) whose inputs changed, for the reports."""
    changed_dates: set[str] = set()
    changed_runs: list[str] = []
    for a in body.get("activities") or []:
        act = activity(a)
        mine = watch_on(conn, act.local_date) == SAMSUNG
        source = stream if mine else SAMSUNG
        if mine:
            # The same run from the Garmin watch, on a Samsung day: shown once, as the Samsung watch recorded it
            t0 = datetime.fromisoformat(act.start_utc.replace("Z", "+00:00"))
            for other in many(conn.activity, {"source": stream, "local_date": act.local_date, "manufacturer": {"$ne": "Samsung"}}):
                t = datetime.fromisoformat(other["start_utc"].replace("Z", "+00:00"))
                if abs((t - t0).total_seconds()) <= SAME_RUN_S:
                    conn.activity.update_one({"source": stream, "source_id": other["source_id"]}, {"$set": {"source": GARMIN_ASIDE}})
                    changed_dates.add(other["local_date"])
        h = _hash(a)
        prev = conn.activity.find_one({"source": source, "source_id": act.source_id}, {"content_hash": 1})
        if prev and prev.get("content_hash") == h:
            continue
        save_activity(conn, source, act, h)
        if act.sport != "other" and _num(a.get("vo2max")):  # Samsung's VO2 max estimate from this run
            v = Observation(act.local_date, "samsung_vo2max_running", round(_num(a["vo2max"]), 1), method="samsung_run",
                            source_record_id=act.source_id)
            changed = save_day(conn, source, DayBundle(local_date=act.local_date, observations=[v]))
            if mine:
                changed_dates |= changed
        if mine:
            changed_runs.append(act.source_id)
            changed_dates.add(act.local_date)
    days: dict[str, DayBundle] = {}

    def bundle(d: str) -> DayBundle:
        return days.setdefault(d, DayBundle(local_date=d))
    for s in body.get("sleep") or []:
        ss = sleep(s)
        bundle(ss.wake_date).sleep.append(ss)
    for d, b in days.items():
        main = [s.duration_s for s in b.sleep if not s.is_nap and s.duration_s]
        if main:
            b.observations.append(Observation(d, "sleep_duration", float(sum(main)), method="samsung_sleep_stages"))
    for d, v in resting_hr(body.get("heart_rate") or [], body.get("offset_s")).items():
        bundle(d).observations.append(Observation(d, "resting_hr", v, method="samsung_lowest_30min_hr"))
    for d, b in days.items():
        mine = watch_on(conn, d) == SAMSUNG
        changed = save_day(conn, stream if mine else SAMSUNG, b)
        if mine:
            changed_dates |= changed
    return changed_dates, changed_runs


def status(conn: Database, today: date) -> dict:
    """What the server has from the Samsung watch, so the phone knows from when to read."""
    newest = conn.activity.find_one({"manufacturer": "Samsung"}, sort=[("start_utc", -1)])
    return {"watch": watch_on(conn, today.isoformat()), "newest_activity_start": (newest or {}).get("start_utc")}

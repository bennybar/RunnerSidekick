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
from statistics import median

from .db import get_setting, many, set_setting
from .routes import shape_from_track
from .store import save_activity, save_day

SAMSUNG = "samsung"          # the source Samsung data is kept under when it's not in the analysis stream
GARMIN_ASIDE = "garmin_aside"  # a Garmin run set aside because the Samsung watch recorded it too, on a Samsung day
WATCHES = ("garmin", "samsung")
SAME_RUN_S = 300             # two runs starting within 5 minutes of each other are the same run on two watches
RHR_WINDOW_S = 30 * 60       # resting heart rate: the lowest 30-minute average of the day, as Garmin defines it
RHR_MIN_WORN_S = 4 * 3600    # ...on a day the watch measured for at least 4 hours
RHR_NIGHT_WORN_S = 3600      # ...an hour of it between midnight and 6 am: worn overnight, so the lowest is a resting value
WORN_GAP_S = 15 * 60         # time between two readings counts as worn up to 15 minutes (Samsung's default is every 10)
NAP_MAX_S = 3 * 3600
NIGHT_MIN_READINGS = 3       # a night's skin temperature or blood oxygen needs at least 3 readings inside it
SPORTS = {"RUNNING": "running", "TRACK_RUNNING": "running", "TREADMILL": "treadmill_running"}
CONVERSION = 3  # raised when the way a run is converted changes, so runs sent again are converted again


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


def switch(conn: Database, stream: str, watch: str, today: date) -> set[str]:
    """Make `watch` the runner's watch from today. A switch back on the same day replaces that day's switch. Data already
    imported is then filed again by the new history (see reconcile); returns the dates whose analysis inputs changed."""
    hist = [h for h in watch_history(conn) if h["from"] < today.isoformat()]
    if (hist[-1]["watch"] if hist else "garmin") != watch:
        hist.append({"watch": watch, "from": today.isoformat()})
    set_setting(conn, "watch_history", hist)
    return reconcile(conn, stream)


def reconcile(conn: Database, stream: str) -> set[str]:
    """Files every record by the watch history: Samsung records into the analysis stream on Samsung days and out of it on
    Garmin days, and Garmin runs set aside back in on Garmin days. Garmin's own daily readings for a day that changes to
    Garmin come back with its next sync (which re-reads recent days). Returns the dates whose inputs changed."""
    changed: set[str] = set()
    is_samsung = lambda d: watch_on(conn, d) == SAMSUNG  # noqa: E731
    for coll, date_key in ((conn.activity, "local_date"), (conn.sleep_session, "wake_date")):
        for r in coll.find({"source": {"$in": [stream, SAMSUNG]}, "source_id": {"$regex": "^samsung-"}}, {"source": 1, "source_id": 1, date_key: 1}):
            want = stream if is_samsung(r[date_key]) else SAMSUNG
            if r["source"] != want:
                coll.delete_one({"source": want, "source_id": r["source_id"]})
                coll.update_one({"_id": r["_id"]}, {"$set": {"source": want}})
                changed.add(r[date_key])
    for r in conn.activity.find({"source": GARMIN_ASIDE}, {"source_id": 1, "local_date": 1}):
        if not is_samsung(r["local_date"]):
            conn.activity.update_one({"_id": r["_id"]}, {"$set": {"source": stream}})
            changed.add(r["local_date"])
    for r in conn.daily_observation.find({"source": {"$in": [stream, SAMSUNG]}, "method": {"$regex": "^samsung"}}):
        want = stream if is_samsung(r["local_date"]) else SAMSUNG
        if r["source"] != want:
            conn.daily_observation.replace_one({"source": want, "local_date": r["local_date"], "metric": r["metric"]},
                                               {**{k: v for k, v in r.items() if k != "_id"}, "source": want}, upsert=True)
            conn.daily_observation.delete_one({"_id": r["_id"]})
            changed.add(r["local_date"])
    return changed


# ---------------------------------------------------------------- converting what the phone sends

def _utc(ms: float) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _local_date(ms: float, offset_s: int | None) -> str:
    return (_utc(ms) + timedelta(seconds=offset_s or 0)).date().isoformat()


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


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
    # Time between samples counts up to a gap: 10 s, or three times the watch's usual spacing when it samples less often
    steps = [b - a for a, b in zip(secs, secs[1:]) if b > a]
    gap = max(10, 3 * median(steps)) if steps else 10
    dt = [0] + [b - a if b - a <= gap else 0 for a, b in zip(secs, secs[1:])]  # the time each sample closes
    moving = sum(d for d, s in zip(dt, secs) if (by_s[s][1] or 0) >= 0.5) if secs else 0
    if secs:
        dist, run = [], 0.0
        for d, s in zip(dt, secs):
            run += (by_s[s][1] or 0) * d
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
                            moving_s=float(sum(dt[j] for j in seg if (s.speed[j] or 0) >= 0.5)),
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
    summary = {k: v for k, v in a.items() if k not in ("log", "route")}
    if route:  # where the run started, for its weather (rounded to ~1 km when looked up); the track itself isn't kept
        summary.update(startLatitude=route[0][1], startLongitude=route[0][2])
    sid = f"samsung-{a['uid']}"
    return Activity(
        source_id=sid, sport=SPORTS.get(str(a.get("type") or "").upper(), "other"), name=a.get("title") or None,
        start_utc=_iso(start), utc_offset_s=offset, local_date=_local_date(start_ms, offset),
        distance_m=total, elapsed_s=(a["end"] - start_ms) / 1000 if a.get("end") else _num(a.get("duration_s")),
        # Without a log (a workout entered by hand, say), the session's own duration stands in for moving time
        moving_s=float(moving) if moving else _num(a.get("duration_s")), timer_s=_num(a.get("duration_s")),
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


def resting_hr(readings: list[tuple[float, float, int]]) -> dict[str, float]:
    """Sidekick's estimate of resting heart rate per local day (Samsung doesn't share its own): the lowest average over
    any 30 minutes (Garmin's definition), from the watch's all-day readings (ms, bpm, the reading's UTC offset), on days
    it measured for 4 hours or more, one of them between midnight and 6 am."""
    days: dict[str, list[tuple[float, float, int]]] = {}
    for ms, bpm, off in readings:
        if 30 <= bpm <= 240:
            days.setdefault(_local_date(ms, off), []).append((ms / 1000, bpm, off))
    out = {}
    for d, rs in days.items():
        rs.sort()
        worn = [min(b[0] - a[0], WORN_GAP_S) for a, b in zip(rs, rs[1:])]
        night = sum(w for w, a in zip(worn, rs) if (_utc(a[0] * 1000) + timedelta(seconds=a[2] or 0)).hour < 6)
        if sum(worn) < RHR_MIN_WORN_S or night < RHR_NIGHT_WORN_S:
            continue
        best = lowest_30min([(ts, b) for ts, b, _ in rs])
        if best is not None:
            out[d] = round(best, 1)
    return out


def lowest_30min(rs: list[tuple[float, float]]) -> float | None:
    """The lowest average over any 30 minutes of (seconds, bpm) readings in time order, from at least 3 readings spread
    over 15 minutes or more."""
    best, j, total = None, 0, 0.0
    for i, (t0, _) in enumerate(rs):  # a sliding window: rs[i..j) are the readings within 30 minutes of rs[i]
        while j < len(rs) and rs[j][0] - t0 < RHR_WINDOW_S:
            total += rs[j][1]
            j += 1
        n = j - i
        if n >= 3 and rs[j - 1][0] - t0 >= RHR_WINDOW_S / 2:
            best = total / n if best is None else min(best, total / n)
        total -= rs[i][1]
    return best


def nights(conn: Database, stream: str, wake_dates: set[str]) -> set[str]:
    """Each night's readings from the Samsung watch, as the day's observations (context only, in no score): sleeping
    heart rate (average and lowest 30 minutes), skin temperature, blood oxygen (average and lowest), and how much of
    the time asleep the watch measured (heart-rate readings, gaps counted up to 15 minutes). Returns changed dates."""
    changed: set[str] = set()
    for d in sorted(wake_dates):
        mine = watch_on(conn, d) == SAMSUNG
        source = stream if mine else SAMSUNG
        spans = [(_ms(n["start_utc"]), _ms(n["end_utc"])) for n in conn.sleep_session.find(
            {"source": source, "wake_date": d, "is_nap": False, "source_id": {"$regex": "^samsung-"}})]
        if not spans:
            continue

        def inside(coll) -> list[tuple[float, float]]:
            q = {"$or": [{"t": {"$gte": a, "$lte": b}} for a, b in spans]}
            return sorted((r["t"] / 1000, r["v"] if "v" in r else r["bpm"]) for r in coll.find(q, {"_id": 0}))
        hr, skin, spo2 = inside(conn.samsung_hr), inside(conn.samsung_skin), inside(conn.samsung_spo2)
        asleep = sum(b - a for a, b in spans) / 1000
        measured = sum(min(b[0] - a[0], WORN_GAP_S) for a, b in zip(hr, hr[1:]))
        obs = [Observation(d, "night_measured_s", round(min(measured, asleep)), method="samsung_night")]
        if len(hr) >= NIGHT_MIN_READINGS:
            obs.append(Observation(d, "night_hr_avg", round(sum(b for _, b in hr) / len(hr), 1), method="samsung_night"))
            low = lowest_30min(hr)
            if low is not None:
                obs.append(Observation(d, "night_hr_low", round(low, 1), method="samsung_night"))
        if len(skin) >= NIGHT_MIN_READINGS:
            obs.append(Observation(d, "night_skin_temp", round(sum(v for _, v in skin) / len(skin), 2), method="samsung_night"))
        if len(spo2) >= NIGHT_MIN_READINGS:
            obs.append(Observation(d, "night_spo2_avg", round(sum(v for _, v in spo2) / len(spo2), 1), method="samsung_night"))
            obs.append(Observation(d, "night_spo2_min", round(min(v for _, v in spo2), 1), method="samsung_night"))
        got = save_day(conn, source, DayBundle(local_date=d, observations=obs))
        if mine:
            changed |= got
    return changed


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
    night_dates: set[str] = set()
    # Sleep: each night stored, then the day's totals from every night stored for it (an upload in parts can't shorten it)
    for s in body.get("sleep") or []:
        ss = sleep(s)
        night_dates.add(ss.wake_date)
        mine = watch_on(conn, ss.wake_date) == SAMSUNG
        source = stream if mine else SAMSUNG
        save_day(conn, source, DayBundle(local_date=ss.wake_date, sleep=[ss]))
        stored = list(conn.sleep_session.find({"source": source, "wake_date": ss.wake_date, "is_nap": False,
                                                "source_id": {"$regex": "^samsung-"}}))
        obs = [Observation(ss.wake_date, "sleep_duration", float(sum(n["duration_s"] or 0 for n in stored)), method="samsung_sleep_stages")]
        score = _num(s.get("score"))
        if score is not None and not ss.is_nap:
            obs.append(Observation(ss.wake_date, "samsung_sleep_score", score, method="samsung_sleep_score"))
        changed = save_day(conn, source, DayBundle(local_date=ss.wake_date, observations=obs))
        if mine:
            changed_dates |= changed
    # All-day heart rate: every reading kept (by its time, so sending one twice changes nothing), then each day it touches
    # worked out again from all the readings stored for it, whatever parts they arrived in
    from pymongo import UpdateOne

    def readings(key: str) -> list[tuple[int, float, int]]:
        return [(int(r[0]), float(r[1]), int(r[2]) if len(r) > 2 and r[2] is not None else body.get("offset_s") or 0)
                for r in body.get(key) or [] if len(r) > 1 and _num(r[0]) is not None and _num(r[1]) is not None]
    # Overnight skin temperature and blood oxygen: kept per reading like heart rate; a night's values are worked out below
    for key, coll in (("skin_temp", conn.samsung_skin), ("spo2", conn.samsung_spo2)):
        got = readings(key)
        if got:
            coll.bulk_write([UpdateOne({"t": t}, {"$set": {"t": t, "v": v, "off": o}}, upsert=True) for t, v, o in got], ordered=False)
            night_dates |= {_local_date(t, o) for t, _, o in got} | {_local_date(t + 86_400_000, o) for t, _, o in got}
    rs = readings("heart_rate")
    if rs:
        conn.samsung_hr.bulk_write([UpdateOne({"t": t}, {"$set": {"t": t, "bpm": b, "off": o}}, upsert=True) for t, b, o in rs], ordered=False)
        night_dates |= {_local_date(t, o) for t, _, o in rs} | {_local_date(t + 86_400_000, o) for t, _, o in rs}
        touched = {_local_date(t, o) for t, _, o in rs}
        lo, hi = min(t for t, _, _ in rs) - 2 * 86_400_000, max(t for t, _, _ in rs) + 2 * 86_400_000
        stored = [(r["t"], r["bpm"], r["off"]) for r in conn.samsung_hr.find({"t": {"$gte": lo, "$lte": hi}}, {"_id": 0})]
        for d, v in resting_hr(stored).items():
            if d in touched:
                mine = watch_on(conn, d) == SAMSUNG
                obs = Observation(d, "resting_hr", v, method="samsung_lowest_30min_hr")
                changed = save_day(conn, stream if mine else SAMSUNG, DayBundle(local_date=d, observations=[obs]))
                if mine:
                    changed_dates |= changed
    changed_dates |= nights(conn, stream, night_dates)
    return changed_dates, changed_runs


def status(conn: Database, today: date) -> dict:
    """What the server has from the Samsung watch, so the phone knows from when to read."""
    newest = conn.activity.find_one({"manufacturer": "Samsung"}, sort=[("start_utc", -1)])
    return {"watch": watch_on(conn, today.isoformat()), "newest_activity_start": (newest or {}).get("start_utc")}

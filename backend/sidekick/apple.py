"""Apple Watch data, read by the iPhone app from Apple Health (HealthKit) and uploaded (POST /v1/apple). Apple has no
cloud API for it, so the phone reads and sends; everything after that happens here, as for Garmin.

One watch per account (the `watch` setting). While it's "apple", Garmin's sync skips the account and the analysis reads
what the phone sends, stored in the same records Garmin fills (runs, nights, daily readings), so every screen works the
same. Nothing Garmin fetched is deleted or overwritten: a day's reading, a night or a run Garmin already recorded is
kept, and Apple's copy of the same thing isn't stored (an Apple Health history uploaded after switching can overlap
Garmin's last days). Switching watches starts new baselines (reports.watch_switch_era).

Everything is idempotent: a workout is keyed by its HealthKit UUID, a day's readings by date, HRV readings by their time
and sleep stages by their span, so the phone can send anything again. Nights and their HRV are worked out from every
stage and reading stored around them, so a night split across two uploads comes out whole."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pymongo import UpdateOne
from pymongo.database import Database

from .connectors.base import Activity, DayBundle, Lap, Observation, RawPayload, Samples, SleepSession, valid_hr
from .db import get_setting, set_setting, utc_now
from .routes import shape_from_track
from .store import save_activity, save_day

MAKER = "Apple"
SPORTS = {"running": "running", "treadmill_running": "treadmill_running", "trail_running": "trail_running"}
MIN_RUN_S, MIN_RUN_M = 120, 200   # shorter than 2 minutes or 200 m isn't a run (a test recording, a mis-tap): not imported
SAME_RUN_S = 300                  # a run Garmin recorded starting within 5 minutes is the same run: Garmin's copy stays
MAX_WORKOUTS, MAX_ITEMS = 5, 400  # per upload (the phone sends bounded batches)
MAX_SERIES_ROWS = 50_000          # per series of one workout
HOLD_S = {"hr": 30, "power": 30, "speed": 30, "alt": 30, "distance": 120, "steps": 120}  # interpolated across gaps up to this
RATE_WINDOW_S = 5                 # speed and cadence from cumulative distance and steps: ± this many seconds
MOVING_SPEED = 0.5                # m/s; slower counts as standing in a lap's moving time
NIGHT_GAP_S = 90 * 60             # sleep stages further apart than this belong to different sleeps
NIGHT_MARGIN_S = 36 * 3600        # stored stages and readings this far around an upload are read to rebuild its nights
NAP_MAX_S = 3 * 3600              # a sleep under 3 hours starting between 9:00 and 20:00 is a nap
MIN_SDNN = 6                      # a night's HRV from Apple's SDNN readings needs 6 inside the sleep (half an hour)
ASLEEP = ("deep", "core", "rem", "asleep")
CONVERSION = 2                    # 2: climb, descent and laps from one method, matched to Apple's climb; raised when the way a workout is converted changes, so a workout sent again is redone


# ---------------------------------------------------------------- small helpers

def num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def aware(t: datetime, tz: ZoneInfo) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=tz)


def iso_utc(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def ms(t: datetime) -> int:
    return int(t.timestamp() * 1000)


def offset_s(t: datetime) -> int:
    return int(t.utcoffset().total_seconds()) if t.utcoffset() is not None else 0


def local_date(t_ms: float, off: int) -> str:
    return (datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc) + timedelta(seconds=off)).date().isoformat()


def haversine(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def interp(points: list[tuple[float, float]], n: int, hold: float) -> list[float | None]:
    """Values on a 1-second grid 0..n, linear between readings up to `hold` seconds apart, a gap (None) otherwise."""
    out: list[float | None] = [None] * (n + 1)
    pts = sorted(points)
    if not pts:
        return out
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t1 - t0 > hold:
            continue
        for s in range(max(0, math.ceil(t0)), min(n, math.floor(t1)) + 1):
            out[s] = v0 if t1 == t0 else v0 + (v1 - v0) * (s - t0) / (t1 - t0)
    for t, v in pts:  # lone readings (no neighbour close enough) still count at their own second
        s = round(t)
        if 0 <= s <= n and out[s] is None:
            out[s] = v
    return out


def column(rows, col: int) -> list[tuple[float, float]]:
    return [(float(r[0]), float(r[col])) for r in rows or [] if len(r) > col and num(r[0]) is not None and num(r[col]) is not None]


def rate(t: list[float], cum: list[float | None], per: float) -> list[float | None]:
    """The rate of a cumulative series (per second × per) over ± RATE_WINDOW_S, only across unbroken time."""
    out: list[float | None] = []
    n = len(t)
    for i in range(n):
        a, b = max(0, i - RATE_WINDOW_S), min(n - 1, i + RATE_WINDOW_S)
        while a < i and (cum[a] is None or t[i] - t[a] > i - a):
            a += 1
        while b > i and (cum[b] is None or t[b] - t[i] > b - i):
            b -= 1
        out.append(round((cum[b] - cum[a]) / (t[b] - t[a]) * per, 3) if b > a and cum[a] is not None and cum[b] is not None else None)
    return out


def climb(t: list[float], elev: list[float | None]) -> tuple[float, float] | None:
    """Total climb and descent (m) from altitude samples read every 10 s (GPS altitude jitters second to second)."""
    pts, last = [], None
    for ti, e in zip(t, elev):
        if e is not None and (last is None or ti - last >= 10):
            pts.append(e)
            last = ti
    if len(pts) < 10:
        return None
    return (round(sum(max(0.0, b - a) for a, b in zip(pts, pts[1:])), 1),
            round(sum(max(0.0, a - b) for a, b in zip(pts, pts[1:])), 1))


# ---------------------------------------------------------------- runs

def pauses(events: list[dict], start: datetime, end: datetime) -> list[tuple[float, float]]:
    """Paused spans, in seconds from the start: each pause until the next resume (or the end)."""
    out, since = [], None
    for e in sorted((e for e in events or [] if e.get("type") in ("pause", "resume") and e.get("start")), key=lambda e: e["start"]):
        t = (e["start"] - start).total_seconds()
        if e["type"] == "pause" and since is None:
            since = t
        elif e["type"] == "resume" and since is not None:
            out.append((since, t))
            since = None
    if since is not None:
        out.append((since, (end - start).total_seconds()))
    return [(max(0.0, a), b) for a, b in out if b > a]


def make_lap(s: Samples, dt: list[float], idx: int, i0: int, i1: int, start: datetime) -> Lap | None:
    """A lap over samples i0..i1 (i0 is where it starts: its own time doesn't count)."""
    if i1 <= i0:
        return None
    seg = range(i0 + 1, i1 + 1)
    hr = [s.hr[j] for j in seg if s.hr[j] is not None]
    cad = [s.cad[j] for j in seg if s.cad[j] is not None and (s.speed[j] or 0) >= MOVING_SPEED]
    el = [s.elev[j] for j in range(i0, i1 + 1, 10) if s.elev[j] is not None]  # every 10 s: GPS altitude is noisy
    dist = round(s.dist[i1] - s.dist[i0], 1) if s.dist[i1] is not None and s.dist[i0] is not None else None
    return Lap(idx=idx, start_utc=iso_utc(start + timedelta(seconds=s.t[i0])), distance_m=dist, elapsed_s=s.t[i1] - s.t[i0],
               moving_s=float(sum(dt[j] for j in seg if (s.speed[j] or 0) >= MOVING_SPEED)),
               avg_hr=round(sum(hr) / len(hr), 1) if hr else None, max_hr=max(hr) if hr else None,
               elevation_gain_m=round(sum(max(0.0, b - a) for a, b in zip(el, el[1:])), 1) if len(el) > 1 else None,
               elevation_loss_m=round(sum(max(0.0, a - b) for a, b in zip(el, el[1:])), 1) if len(el) > 1 else None,
               avg_cadence_spm=round(sum(cad) / len(cad), 1) if cad else None)


def km_laps(s: Samples, dt: list[float], start: datetime) -> list[Lap]:
    """1 km laps from the samples' distance (the last one is what's left), like Garmin's automatic laps."""
    have = [i for i, d in enumerate(s.dist) if d is not None]
    if not have:
        return []
    laps, first, last = [], have[0], have[-1]
    for i in have[1:]:
        if s.dist[i] - s.dist[have[0]] >= (len(laps) + 1) * 1000 or i == last:
            lap = make_lap(s, dt, len(laps), first, i, start)
            if lap and lap.distance_m:
                laps.append(lap)
            first = i
    return laps


def event_laps(s: Samples, dt: list[float], events: list[dict], start: datetime) -> list[Lap]:
    """Apple's own laps (lap events with their span), when the workout has two or more."""
    spans = sorted(((e["start"] - start).total_seconds(), (e["end"] - start).total_seconds())
                   for e in events or [] if e.get("type") == "lap" and e.get("start") and e.get("end") and e["end"] > e["start"])
    if len(spans) < 2:
        return []
    laps = []
    for a, b in spans:
        i0 = next((i for i, t in enumerate(s.t) if t >= a), None)
        i1 = next((i for i in range(len(s.t) - 1, -1, -1) if s.t[i] <= b), None)
        lap = make_lap(s, dt, len(laps), i0, i1, start) if i0 is not None and i1 is not None else None
        if lap:
            laps.append(lap)
    return laps


def consistent_climb(apple_gain: float | None, gained: tuple[float, float] | None, laps: list[Lap]) -> tuple[float | None, float | None]:
    """The run's climb and descent and its laps' from one method (altitude every 10 s), so laps add up to the total and
    climb minus descent matches where the run ended. When Apple sent its own climb (barometric, the better measure),
    everything is scaled to it: the same factor for climb and descent, since altitude noise inflates both alike."""
    if not gained or gained[0] <= 0:
        return apple_gain, None
    f = apple_gain / gained[0] if apple_gain is not None else 1.0
    for lap in laps:
        if lap.elevation_gain_m is not None:
            lap.elevation_gain_m = round(lap.elevation_gain_m * f, 1)
        if lap.elevation_loss_m is not None:
            lap.elevation_loss_m = round(lap.elevation_loss_m * f, 1)
    return round(gained[0] * f, 1), round(gained[1] * f, 1)


def workout(w: dict, tz: ZoneInfo) -> Activity:
    """One Apple Watch workout as a run: samples on a 1-second grid (paused seconds left out), laps, the route's shape."""
    start, end = aware(w["start"], tz), aware(w["end"], tz)
    events = [{**e, "start": aware(e["start"], tz) if e.get("start") else None, "end": aware(e["end"], tz) if e.get("end") else None}
              for e in w.get("events") or []]
    elapsed = max(0.0, (end - start).total_seconds())
    paused = pauses(events, start, end)
    n = int(elapsed)
    still = [False] * (n + 1)
    for a, b in paused:
        for k in range(max(0, math.ceil(a)), min(n + 1, math.ceil(b))):  # paused from a, moving again at b
            still[k] = True
    ser = w.get("series") or {}
    route = [r for r in ser.get("route") or [] if len(r) > 2 and num(r[0]) is not None and num(r[1]) is not None
             and num(r[2]) is not None and (r[1], r[2]) != (0, 0)]
    along = []
    if len(route) > 1:
        run = 0.0
        along = [(float(route[0][0]), 0.0)]
        for p, q in zip(route, route[1:]):
            run += haversine(p[1:3], q[1:3])
            along.append((float(q[0]), run))
    cum = column(ser.get("distance"), 1) or along
    # Speed: Apple's running speed when sent; without any distance, the route's GPS speed; else worked out from distance
    speed = column(ser.get("speed"), 1) or ([] if cum else column(route, 4))
    grid = {"hr": interp(column(ser.get("hr"), 1), n, HOLD_S["hr"]), "dist": interp(cum, n, HOLD_S["distance"]),
            "alt": interp(column(route, 3), n, HOLD_S["alt"]), "power": interp(column(ser.get("power"), 1), n, HOLD_S["power"]),
            "steps": interp(column(ser.get("steps"), 1), n, HOLD_S["steps"]), "speed": interp(speed, n, HOLD_S["speed"])}
    keep = [k for k in range(n + 1) if not still[k]]
    t = [float(k) for k in keep]
    total = num(w.get("distance_m"))
    samples = laps = None
    shape = None
    if keep and any(grid[x][k] is not None for x in ("hr", "dist", "speed") for k in keep):
        dist = [grid["dist"][k] for k in keep]
        last = next((d for d in reversed(dist) if d is not None), None)
        f = total / last if total and last else 1.0  # Apple's samples add up to its own total, near enough: scaled to it
        dist = [round(d * f, 1) if d is not None else None for d in dist]
        speed = [grid["speed"][k] for k in keep] if any(grid["speed"][k] is not None for k in keep) else rate(t, dist, 1.0)
        steps = [grid["steps"][k] for k in keep]
        power = [grid["power"][k] for k in keep]
        samples = Samples(t=t, hr=valid_hr([round(grid["hr"][k], 1) if grid["hr"][k] is not None else None for k in keep]),
                          speed=[round(v, 3) if v is not None else None for v in speed], dist=dist,
                          elev=[round(grid["alt"][k], 1) if grid["alt"][k] is not None else None for k in keep],
                          cad=rate(t, steps, 60.0) if any(x is not None for x in steps) else [None] * len(t),
                          power=[round(p) if p is not None else None for p in power] if any(p is not None for p in power) else None)
    dt = [0.0] + [b - a if b - a <= 1 else 0.0 for a, b in zip(t, t[1:])] if t else []
    if samples is not None:
        laps = event_laps(samples, dt, events, start) or km_laps(samples, dt, start)
    if len(route) >= 10:
        run, al = 0.0, [0.0]
        for p, q in zip(route, route[1:]):
            run += haversine(p[1:3], q[1:3])
            al.append(run)
        shape = shape_from_track(al, [float(p[1]) for p in route], [float(p[2]) for p in route])
    moving = elapsed - sum(b - a for a, b in paused) if paused else (num(w.get("moving_s")) or elapsed)
    hr = [h for h in (samples.hr if samples else []) if h is not None]
    cad = [c for c, v in zip(samples.cad, samples.speed) if c is not None and (v or 0) >= MOVING_SPEED] if samples else []
    gained = climb(samples.t, samples.elev) if samples else None
    gain = num(w.get("elevation_gain_m"))
    gain, loss = consistent_climb(gain, gained, laps or [])
    dyn = w.get("dynamics") or {}
    pw = [p for p in (samples.power or []) if p is not None] if samples else []
    metrics = {k: v for k, v in (("avgStrideLength", round(num(dyn.get("stride_m")) * 100, 1) if num(dyn.get("stride_m")) else None),
                                  ("avgVerticalOscillation", num(dyn.get("vertical_osc_cm"))),
                                  ("avgGroundContactTime", num(dyn.get("ground_contact_ms"))),
                                  ("avgPower", round(sum(pw) / len(pw)) if pw else None), ("maxPower", max(pw) if pw else None)) if v is not None}
    sport = SPORTS.get(str(w.get("sport") or ""), "other")
    if sport == "running" and w.get("indoor"):
        sport = "treadmill_running"
    sid = f"apple-{w['uuid']}"
    summary = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in w.items() if k not in ("series", "events")}
    if route:  # where the run started, for its weather (rounded to ~1 km when looked up); the track itself isn't kept
        summary.update(startLatitude=float(route[0][1]), startLongitude=float(route[0][2]))
    return Activity(
        source_id=sid, sport=sport, name=None, start_utc=iso_utc(start), utc_offset_s=offset_s(start), local_date=start.date().isoformat(),
        distance_m=total if total is not None else (samples.dist[-1] if samples and samples.dist and samples.dist[-1] else None),
        elapsed_s=elapsed, moving_s=round(moving, 1), timer_s=round(moving, 1),
        avg_hr=round(sum(hr) / len(hr), 1) if hr else None, max_hr=max(hr) if hr else None,
        elevation_gain_m=gain, elevation_loss_m=loss,
        avg_cadence_spm=round(sum(cad) / len(cad), 1) if cad else None, garmin_metrics=metrics,
        device_id=w.get("device") or "Apple Watch", manufacturer=MAKER, laps=laps or [], samples=samples, shape=shape,
        raw=[RawPayload("activity_summary", sid, summary)])


def garmin_twin(conn: Database, source: str, a: Activity) -> bool:
    """Garmin recorded the same run (started within 5 minutes): its copy is the one kept."""
    t0 = datetime.fromisoformat(a.start_utc.replace("Z", "+00:00"))
    day = date.fromisoformat(a.local_date)
    for r in conn.activity.find({"source": source, "manufacturer": {"$ne": MAKER},
                                 "local_date": {"$gte": (day - timedelta(days=1)).isoformat(), "$lte": (day + timedelta(days=1)).isoformat()}},
                                {"start_utc": 1}):
        if abs((datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00")) - t0).total_seconds()) <= SAME_RUN_S:
            return True
    return False


def content_hash(w: dict) -> str:
    return hashlib.sha256(json.dumps([CONVERSION, w], sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- days

def not_garmins(conn: Database, source: str, obs: list[Observation]) -> list[Observation]:
    """Leaves out readings for a day and metric Garmin already measured (kept as they are)."""
    out = []
    for o in obs:
        prev = conn.daily_observation.find_one({"source": source, "local_date": o.local_date, "metric": o.metric, "state": "measured"},
                                               {"method": 1})
        if prev is None or str(prev.get("method") or "").startswith("apple_"):
            out.append(o)
    return out


def day_readings(d: dict) -> list[Observation]:
    ds = d["date"].isoformat()
    out = []
    for key, metric, method in (("resting_hr", "resting_hr", "apple_daily"), ("steps", "steps", "apple_daily"),
                                # Apple's exercise minutes as they are; intensity() splits them into vigorous and moderate
                                ("exercise_min", "exercise_minutes", "apple_exercise_minutes"),
                                ("vo2max", "apple_vo2max_running", "apple_cardio_fitness"), ("weight_kg", "weight", "apple_health")):
        v = num(d.get(key))
        if v is not None:
            out.append(Observation(ds, metric, round(v, 1), method=method))
    return out


def intensity(conn: Database, source: str, dates: set[str]) -> set[str]:
    """WHO activity minutes for Apple days. Apple counts exercise minutes without saying how hard: running is vigorous
    (well over 6 METs), so the day's Apple-run minutes count as vigorous and the rest of its exercise minutes as moderate,
    as Garmin split them. A day Garmin measured keeps Garmin's."""
    changed: set[str] = set()
    for d in sorted(dates):
        ex = conn.daily_observation.find_one({"source": source, "metric": "exercise_minutes", "local_date": d, "state": "measured"})
        runs = list(conn.activity.find({"source": source, "manufacturer": MAKER, "local_date": d}, {"moving_s": 1}))
        if ex is None and not runs:
            continue
        run_min = sum((r.get("moving_s") or 0) for r in runs) / 60
        total = ex["value"] if ex is not None else run_min
        vig = min(total, run_min)
        obs = [Observation(d, "intensity_minutes_vigorous", round(vig), method="apple_runs"),
               Observation(d, "intensity_minutes_moderate", round(max(0.0, total - vig)), method="apple_exercise_minutes")]
        changed |= save_day(conn, source, DayBundle(local_date=d, observations=not_garmins(conn, source, obs)))
    return changed


# ---------------------------------------------------------------- nights

def sleeps(stages: list[dict]) -> list[list[dict]]:
    """Stored stage spans grouped into sleeps: spans less than 90 minutes apart belong to the same one. Time in bed alone
    isn't sleep."""
    out: list[list[dict]] = []
    end = None
    for st in sorted((s for s in stages if s["stage"] != "in_bed"), key=lambda s: s["s"]):
        if out and st["s"] <= end + NIGHT_GAP_S * 1000:
            out[-1].append(st)
            end = max(end, st["e"])
        else:
            out.append([st])
            end = st["e"]
    return out


def union_s(spans: list[tuple[int, int]]) -> float:
    """Seconds covered by possibly overlapping spans (two sources writing the same stage count once)."""
    total, cur = 0, None
    for a, b in sorted(spans):
        if cur is None or a > cur[1]:
            if cur:
                total += cur[1] - cur[0]
            cur = [a, b]
        else:
            cur[1] = max(cur[1], b)
    if cur:
        total += cur[1] - cur[0]
    return total / 1000


def session(group: list[dict]) -> SleepSession | None:
    by = {k: union_s([(s["s"], s["e"]) for s in group if s["stage"] == k]) for k in ("deep", "core", "rem", "awake")}
    asleep = union_s([(s["s"], s["e"]) for s in group if s["stage"] in ASLEEP])
    if asleep <= 0:
        return None
    s0, last = min(s["s"] for s in group), max(group, key=lambda s: s["e"])
    off0 = next(s["off"] for s in group if s["s"] == s0)
    start_local = datetime.fromtimestamp(s0 / 1000, tz=timezone.utc) + timedelta(seconds=off0)
    wake = local_date(last["e"], last["off"])
    return SleepSession(
        source_id=f"apple-{wake}-{s0 // 60000}", wake_date=wake, start_utc=iso_utc(datetime.fromtimestamp(s0 / 1000, tz=timezone.utc)),
        end_utc=iso_utc(datetime.fromtimestamp(last["e"] / 1000, tz=timezone.utc)), utc_offset_s=last["off"],
        is_nap=asleep < NAP_MAX_S and 9 <= start_local.hour < 20, duration_s=asleep,
        deep_s=by["deep"] or None, light_s=by["core"] or None, rem_s=by["rem"] or None, awake_s=by["awake"] or None)


def nights(conn: Database, source: str, lo: int, hi: int) -> set[str]:
    """Rebuilds every night touching lo..hi (ms) from the stored stages, then its sleep time and HRV. A night Garmin
    recorded (the same wake date) is kept and Apple's isn't stored. Returns the dates whose readings changed."""
    stored = list(conn.apple_sleep.find({"e": {"$gte": lo - NIGHT_MARGIN_S * 1000}, "s": {"$lte": hi + NIGHT_MARGIN_S * 1000}}, {"_id": 0}))
    found: dict[str, list[SleepSession]] = {}
    for g in sleeps(stored):
        if max(s["e"] for s in g) < lo or min(s["s"] for s in g) > hi:
            continue
        ss = session(g)
        if ss:
            found.setdefault(ss.wake_date, []).append(ss)
    changed: set[str] = set()
    for wake, ss in sorted(found.items()):
        if conn.sleep_session.find_one({"source": source, "wake_date": wake, "is_nap": False, "source_id": {"$not": {"$regex": "^apple-"}}}):
            continue  # Garmin's night
        keep = {s.source_id for s in ss}
        gone = conn.sleep_session.delete_many({"source": source, "wake_date": wake, "source_id": {"$regex": "^apple-", "$nin": list(keep)}})
        if gone.deleted_count:
            changed.add(wake)
        main = [s for s in ss if not s.is_nap]
        obs = []
        if main:
            obs.append(Observation(wake, "sleep_duration", float(sum(s.duration_s or 0 for s in main)), method="apple_sleep_stages",
                                   observed_start=min(s.start_utc for s in main), observed_end=max(s.end_utc for s in main)))
            obs += night_hrv(conn, wake, main)
        changed |= save_day(conn, source, DayBundle(local_date=wake, sleep=ss, observations=not_garmins(conn, source, obs)))
    return changed


def night_hrv(conn: Database, wake: str, main: list[SleepSession]) -> list[Observation]:
    """The night's HRV from Apple's readings inside its sleep: the mean SDNN of all of them (what Apple Health reports as
    HRV; the watch takes one every few minutes asleep) once there are 6. RMSSD is only on the few readings that carry a
    heartbeat series, too few for a stable night, so it's the fallback when SDNN is too sparse. Kept apart by method."""
    spans = [(ms(datetime.fromisoformat(s.start_utc.replace("Z", "+00:00"))), ms(datetime.fromisoformat(s.end_utc.replace("Z", "+00:00"))))
             for s in main]
    rs = list(conn.apple_hrv.find({"$or": [{"t": {"$gte": a, "$lte": b}} for a, b in spans]}, {"_id": 0}))
    rmssd = [r["rmssd"] for r in rs if r.get("rmssd")]
    sdnn = [r["sdnn"] for r in rs if r.get("sdnn")]
    if len(sdnn) >= MIN_SDNN:
        return [Observation(wake, "hrv_overnight_avg", round(sum(sdnn) / len(sdnn), 1), method="apple_sdnn", label=f"{len(sdnn)} readings")]
    if len(rmssd) >= 2:
        return [Observation(wake, "hrv_overnight_avg", round(sum(rmssd) / len(rmssd), 1), method="apple_rmssd", label=f"{len(rmssd)} readings")]
    if sdnn:
        return [Observation(wake, "hrv_overnight_avg", round(sum(sdnn) / len(sdnn), 1), method="apple_sdnn", label=f"{len(sdnn)} readings")]
    return []


# ---------------------------------------------------------------- storing

def ingest(conn: Database, source: str, body: dict, tz: ZoneInfo) -> tuple[set[str], list[str], dict[str, int]]:
    """Store what the phone sent. Returns the dates and runs whose inputs changed (for the reports) and how many items of
    each kind were taken (stored, or already there unchanged)."""
    changed_dates: set[str] = set()
    changed_runs: list[str] = []
    accepted = {"workouts": 0, "days": 0, "hrv": 0, "sleep": 0}
    for w in body.get("workouts") or []:
        a = workout(w, tz)
        if a.sport == "other" or (a.elapsed_s or 0) < MIN_RUN_S or (a.distance_m or 0) < MIN_RUN_M or garmin_twin(conn, source, a):
            continue
        h = content_hash(w)
        prev = conn.activity.find_one({"source": source, "source_id": a.source_id}, {"content_hash": 1})
        accepted["workouts"] += 1
        if prev and prev.get("content_hash") == h:
            continue
        if save_activity(conn, source, a, h) is not None:
            conn.activity.update_one({"source": source, "source_id": a.source_id}, {"$set": {"apple_conversion": CONVERSION}})
            changed_runs.append(a.source_id)
            changed_dates.add(a.local_date)
    for d in body.get("days") or []:
        accepted["days"] += 1
        changed_dates |= save_day(conn, source, DayBundle(local_date=d["date"].isoformat(),
                                                          observations=not_garmins(conn, source, day_readings(d))))
    changed_dates |= intensity(conn, source, {a for a in changed_dates} | {d["date"].isoformat() for d in body.get("days") or []})
    lo, hi = None, None
    hrv = [(aware(r["time"], tz), r) for r in body.get("hrv") or [] if num(r.get("sdnn_ms")) or num(r.get("rmssd_ms"))]
    if hrv:
        conn.apple_hrv.bulk_write([UpdateOne({"t": ms(t)}, {"$set": {"t": ms(t), "off": offset_s(t), "sdnn": num(r.get("sdnn_ms")),
                                                                      "rmssd": num(r.get("rmssd_ms")), "beats": r.get("beats")}}, upsert=True)
                                   for t, r in hrv], ordered=False)
        accepted["hrv"] = len(hrv)
        lo, hi = min(ms(t) for t, _ in hrv), max(ms(t) for t, _ in hrv)
    st = [(aware(s["start"], tz), aware(s["end"], tz), s["stage"]) for s in body.get("sleep") or []
          if s.get("stage") in ASLEEP + ("awake", "in_bed")]
    st = [x for x in st if x[1] > x[0]]
    if st:
        conn.apple_sleep.bulk_write([UpdateOne({"s": ms(a), "e": ms(b), "stage": k}, {"$set": {"s": ms(a), "e": ms(b), "stage": k, "off": offset_s(b)}},
                                               upsert=True) for a, b, k in st], ordered=False)
        accepted["sleep"] = len(st)
        lo = min([ms(a) for a, _, _ in st] + ([lo] if lo is not None else []))
        hi = max([ms(b) for _, b, _ in st] + ([hi] if hi is not None else []))
    if lo is not None:
        changed_dates |= nights(conn, source, lo, hi)
    set_setting(conn, "apple_last_upload_at", utc_now())
    return changed_dates, changed_runs, accepted


def status(conn: Database, source: str) -> dict:
    """What the server has from the Apple Watch, so the phone knows from when to read."""
    w = conn.activity.find_one({"source": source, "manufacturer": MAKER}, {"local_date": 1}, sort=[("start_utc", -1)])
    n = conn.sleep_session.find_one({"source": source, "source_id": {"$regex": "^apple-"}, "is_nap": False}, {"wake_date": 1},
                                    sort=[("wake_date", -1)])
    return {"watch": get_setting(conn, "watch", "garmin"), "last_upload_at": get_setting(conn, "apple_last_upload_at", None),
            "latest": {"workout": (w or {}).get("local_date"), "night": (n or {}).get("wake_date")},
            "counts": {"workouts": conn.activity.count_documents({"source": source, "manufacturer": MAKER}),
                       "nights": len(conn.sleep_session.distinct("wake_date", {"source": source, "source_id": {"$regex": "^apple-"}, "is_nap": False})),
                       "days": len(conn.daily_observation.distinct("local_date", {"source": source, "method": {"$regex": "^apple_"}}))}}

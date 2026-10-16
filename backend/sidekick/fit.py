"""Runs from FIT files: what GTII (Gear Tracker II) records on the Galaxy Watch, sent by the app from GTII's export
folder. FIT is the format Garmin watches use too, so a run arrives with its per-second record (heart rate, speed,
distance, altitude, GPS, cadence; power and running dynamics when a sensor such as a Stryd provides them) and its laps.
A run recorded by GTII counts as the Samsung watch's (it was recorded on it), filed by the watch history like the
Samsung Health data; when Samsung Health has the same run too, the FIT copy is kept (it has laps) and the other is set
aside, not deleted."""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timedelta, timezone
from statistics import median

from pymongo.database import Database

from .connectors.base import Activity, Lap, RawPayload, Samples, valid_hr
from .routes import shape_from_track
from .samsung import SAME_RUN_S, SAMSUNG, _iso, watch_on
from .store import save_activity

FIT_CONVERSION = 1          # raised when the conversion changes, so files sent again are converted again
SEMI = 180 / 2 ** 31        # FIT positions are semicircles
MOVING_SPEED, GAP_S = 0.5, 10.0
SPORTS = {("running", "treadmill"): "treadmill_running", ("running", "trail"): "trail_running", ("running", None): "running"}
LAP_INTENSITY = {"active": "ACTIVE", "rest": "REST", "recovery": "RECOVERY", "warmup": "WARMUP", "cooldown": "COOLDOWN",
                 "interval": "INTERVAL"}


def _v(x):
    """A FIT value as a number, with the 0 that FIT writes for 'not measured' as None."""
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x != 0 else None


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def parse(data: bytes) -> tuple[Activity, dict]:
    """The run in a FIT file, and a summary of what the file held (for the raw store)."""
    import fitdecode
    records, laps, session, activity_msg, device, rr = [], [], {}, {}, {}, []
    with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.DISABLED) as fr:
        for f in fr:
            if not isinstance(f, fitdecode.FitDataMessage):
                continue
            vals = {fl.name: fl.value for fl in f.fields}
            if f.name == "record":
                records.append(vals)
            elif f.name == "lap":
                laps.append(vals)
            elif f.name == "session" and not session:
                session = vals
            elif f.name == "activity":
                activity_msg = vals
            elif f.name == "device_info" and vals.get("device_index") == "creator":
                device = vals
            elif f.name == "hrv":  # beat-to-beat intervals from a chest strap, when there's one
                rr += [x for x in (vals.get("time") or ()) if isinstance(x, (int, float)) and 0.25 < x < 2.5]
    if not session.get("start_time"):
        raise ValueError("no session in the FIT file")
    start = _utc(session["start_time"])
    offset = None
    if activity_msg.get("local_timestamp") and activity_msg.get("timestamp"):
        offset = round((activity_msg["local_timestamp"].replace(tzinfo=timezone.utc) - _utc(activity_msg["timestamp"])).total_seconds() / 900) * 900

    recs = [r for r in records if r.get("timestamp")]
    cad_raw = [(_v(r.get("cadence")) or 0) + (r.get("fractional_cadence") or 0) for r in recs]
    # FIT keeps running cadence in strides a minute (one foot); steps are twice that, unless the file already has steps
    cad_steps = median([c for c in cad_raw if c]) > 120 if any(cad_raw) else False
    t, hr, sp, dist, elev, cad, pw, lat, lon = [], [], [], [], [], [], [], [], []
    dyn = {"gct": [], "vo": [], "stride": []}
    for r, c in zip(recs, cad_raw):
        t.append(round((_utc(r["timestamp"]) - start).total_seconds(), 1))
        hr.append(_v(r.get("heart_rate")))
        sp.append(_v(r.get("enhanced_speed")) or _v(r.get("speed")))
        dist.append(r.get("distance"))
        elev.append(r.get("enhanced_altitude") if r.get("enhanced_altitude") is not None else r.get("altitude"))
        cad.append((c if cad_steps else 2 * c) or None)
        pw.append(_v(r.get("power")))
        la, lo = r.get("position_lat"), r.get("position_long")
        lat.append(la * SEMI if isinstance(la, int) else None)
        lon.append(lo * SEMI if isinstance(lo, int) else None)
        dyn["gct"].append(_v(r.get("stance_time")))                                          # ms
        dyn["vo"].append(round(_v(r.get("vertical_oscillation")) / 10, 2) if _v(r.get("vertical_oscillation")) else None)  # mm → cm
        dyn["stride"].append(round(_v(r.get("step_length")) / 1000, 3) if _v(r.get("step_length")) else None)  # mm → m
    samples = Samples(t=t, hr=valid_hr(hr), speed=sp, dist=dist, elev=elev, cad=cad,
                      power=pw if any(p is not None for p in pw) else None,
                      dyn={k: v for k, v in dyn.items() if any(x is not None for x in v)} or None) if t else None
    moving = sum(b - a for a, b, s in zip(t, t[1:], sp[1:]) if 0 < b - a <= GAP_S and (s or 0) >= MOVING_SPEED) if t else 0
    shape = shape_from_track([d for d in dist], lat, lon) if t and any(lat) else None

    out_laps = []
    for i, l in enumerate(laps):
        ls = l.get("start_time")
        lc = _v(l.get("avg_running_cadence")) or _v(l.get("avg_cadence"))
        out_laps.append(Lap(idx=i, start_utc=_iso(_utc(ls)) if ls else None, distance_m=_v(l.get("total_distance")),
                            elapsed_s=_v(l.get("total_elapsed_time")), moving_s=_v(l.get("total_timer_time")),
                            avg_hr=_v(l.get("avg_heart_rate")), max_hr=_v(l.get("max_heart_rate")),
                            elevation_gain_m=_v(l.get("total_ascent")), elevation_loss_m=_v(l.get("total_descent")),
                            avg_cadence_spm=(lc if cad_steps else 2 * lc) if lc else None,
                            intensity=LAP_INTENSITY.get(str(l.get("intensity") or "").lower())))
    sport = str(session.get("sport") or "")
    sub = str(session.get("sub_sport") or "")
    kind = SPORTS.get((sport, sub)) or SPORTS.get((sport, None)) or "other"
    sid = f"fit-{int(start.timestamp())}"
    sc = _v(session.get("avg_running_cadence")) or _v(session.get("avg_cadence"))
    first = next(((a, b) for a, b in zip(lat, lon) if a is not None and b is not None), None)
    summary = {"recorder": device.get("product_name") or "FIT", "records": len(recs), "laps": len(laps), "rr_intervals": len(rr),
               **({"startLatitude": first[0], "startLongitude": first[1]} if first else {}),
               "fields": sorted({k for r in recs for k, v in r.items() if v not in (None, 0, 0.0)})}
    act = Activity(
        source_id=sid, sport=kind, name=None, start_utc=_iso(start), utc_offset_s=offset,
        local_date=(start + timedelta(seconds=offset or 0)).date().isoformat(), distance_m=_v(session.get("total_distance")),
        elapsed_s=_v(session.get("total_elapsed_time")), moving_s=float(moving) or _v(session.get("total_timer_time")),
        timer_s=_v(session.get("total_timer_time")), avg_hr=_v(session.get("avg_heart_rate")), max_hr=_v(session.get("max_heart_rate")),
        elevation_gain_m=_v(session.get("total_ascent")), elevation_loss_m=_v(session.get("total_descent")),
        avg_cadence_spm=(sc if cad_steps else 2 * sc) if sc else None,
        device_id=None, manufacturer="Samsung",  # recorded on the Galaxy Watch; no device ID, so it never starts a device era
        laps=out_laps, samples=samples, shape=shape, raw=[RawPayload("activity_summary", sid, summary)])
    return act, summary


def ingest(conn: Database, stream: str, data: bytes) -> tuple[set[str], list[str]]:
    """Store one FIT file's run. Returns the dates and runs (in the analysis stream) that changed."""
    act, _ = parse(data)
    h = hashlib.sha256(bytes([FIT_CONVERSION]) + data).hexdigest()
    mine = watch_on(conn, act.local_date) == SAMSUNG
    source = stream if mine else SAMSUNG
    prev = conn.activity.find_one({"source_id": act.source_id}, {"content_hash": 1, "source": 1})
    if prev and prev.get("content_hash") == h:
        return set(), []
    if prev and prev["source"] != source:  # filed elsewhere before: one copy only
        conn.activity.delete_one({"_id": prev["_id"]})
    changed: set[str] = set()
    if mine:  # the same run from Samsung Health: the FIT copy stays, the other is set aside
        t0 = datetime.fromisoformat(act.start_utc.replace("Z", "+00:00"))
        for other in conn.activity.find({"source": stream, "local_date": act.local_date, "source_id": {"$regex": "^samsung-"}}):
            if abs((datetime.fromisoformat(other["start_utc"].replace("Z", "+00:00")) - t0).total_seconds()) <= SAME_RUN_S:
                conn.activity.delete_one({"source": SAMSUNG, "source_id": other["source_id"]})
                conn.activity.update_one({"_id": other["_id"]}, {"$set": {"source": SAMSUNG}})
                changed.add(other["local_date"])
    save_activity(conn, source, act, h)
    if mine:
        changed.add(act.local_date)
        return changed, [act.source_id]
    return changed, []

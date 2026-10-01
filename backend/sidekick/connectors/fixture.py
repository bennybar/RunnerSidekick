"""Deterministic synthetic connector for demo mode and tests.

Every value is derived from (seed, date), so any date range returns identical
records regardless of how a sync is chunked or resumed. Data is clearly synthetic:
the source is "fixture" and the API marks the mode as synthetic.

Built-in scenarios (relative to the anchor date):
  * days -44..-42: watch not worn (no daily data, no runs)
  * days -10..-8 : elevated resting HR and lower HRV episode
  * Wednesdays   : interval sessions (ineligible for drift analysis)
  * Saturdays    : long steady run
  * day -5       : run with a heart-rate sensor dropout
  * Sundays      : afternoon nap
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date, datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from .base import (
    METRIC_UNITS,
    Activity,
    Capability,
    ConnectionState,
    DayBundle,
    Lap,
    Observation,
    RawPayload,
    Samples,
    SleepSession,
)
from .garmin import content_hash, iso_utc

FIXTURE_METRICS = {"resting_hr", "hrv_overnight_avg", "sleep_duration", "steps", "active_duration", "avg_stress",
                   "body_battery_high", "body_battery_low", "garmin_training_readiness", "garmin_sleep_score"}


class FixtureConnector:
    source = "fixture"
    synthetic = True

    def __init__(self, anchor: date, tz: str = "Asia/Jerusalem", seed: int = 7):
        self.anchor = anchor
        self.tz = ZoneInfo(tz)
        self.seed = seed

    def _rng(self, d: date, salt: str) -> random.Random:
        h = hashlib.sha256(f"{self.seed}:{d.isoformat()}:{salt}".encode()).digest()
        return random.Random(int.from_bytes(h[:8], "big"))

    def _offset(self, d: date) -> int:
        return int(self.tz.utcoffset(datetime.combine(d, time(12))).total_seconds())

    def _rel(self, d: date) -> int:
        return (d - self.anchor).days

    def _not_worn(self, d: date) -> bool:
        return -44 <= self._rel(d) <= -42

    def connection_state(self) -> ConnectionState:
        return ConnectionState.CONNECTED

    def capabilities(self) -> dict[str, Capability]:
        return {m: (Capability.SUPPORTED if m in FIXTURE_METRICS else Capability.UNSUPPORTED) for m in METRIC_UNITS}

    # ------------------------------------------------------------ days

    def read_days(self, start: date, end: date) -> Iterable[DayBundle]:
        d = min(end, self.anchor)
        while d >= start:
            yield self._day(d)
            d -= timedelta(days=1)

    def _day(self, d: date) -> DayBundle:
        ds = d.isoformat()
        b = DayBundle(local_date=ds)
        if self._not_worn(d):
            for m in FIXTURE_METRICS:
                b.observations.append(Observation(ds, m, None, state="not_measured"))
            b.raw.append(RawPayload("fixture_day", ds, {"worn": False}))
            return b
        r = self._rng(d, "day")
        rel = self._rel(d)
        episode = -10 <= rel <= -8
        trend = rel / 120.0  # gentle fitness improvement towards the anchor
        rhr = round(52 - 1.5 * trend + r.gauss(0, 1.2) + (6 if episode else 0))
        hrv = round(60 + 4 * trend + r.gauss(0, 5) - (16 if episode else 0))
        sleep_s = round((7.1 + r.gauss(0, 0.6) - (0.8 if episode else 0)) * 3600 / 60) * 60
        off = self._offset(d)
        wake_local = datetime.combine(d, time(6, 30)) + timedelta(minutes=r.randint(-40, 40))
        end_utc = wake_local - timedelta(seconds=off)
        start_utc = end_utc - timedelta(seconds=sleep_s + r.randint(10, 35) * 60)
        sid = f"fx-sleep-{ds}"
        deep = round(sleep_s * r.uniform(0.15, 0.22))
        rem = round(sleep_s * r.uniform(0.18, 0.25))
        score = max(30, min(95, round(78 + (sleep_s - 7 * 3600) / 360 + r.gauss(0, 4) - (10 if episode else 0))))
        b.sleep.append(SleepSession(sid, ds, iso_utc(start_utc.replace(tzinfo=ZoneInfo("UTC"))),
                                    iso_utc(end_utc.replace(tzinfo=ZoneInfo("UTC"))), off, False, sleep_s,
                                    deep, sleep_s - deep - rem, rem, round(r.uniform(5, 25)) * 60, score))
        if d.weekday() == 6:  # Sunday nap
            ns = datetime.combine(d, time(15, 0)) - timedelta(seconds=off)
            b.sleep.append(SleepSession(f"fx-nap-{ds}", ds, iso_utc(ns.replace(tzinfo=ZoneInfo("UTC"))),
                                        iso_utc((ns + timedelta(minutes=35)).replace(tzinfo=ZoneInfo("UTC"))),
                                        off, True, 35 * 60))
        b.observations += [
            Observation(ds, "resting_hr", rhr, method="garmin_daily_rhr"),
            Observation(ds, "hrv_overnight_avg", hrv, method="garmin_overnight_hrv",
                        label="UNBALANCED" if episode else "BALANCED"),
            Observation(ds, "sleep_duration", sleep_s, method="garmin_main_sleep", source_record_id=sid,
                        observed_start=b.sleep[0].start_utc, observed_end=b.sleep[0].end_utc),
            Observation(ds, "garmin_sleep_score", score, method="garmin_sleep_score", source_record_id=sid),
            Observation(ds, "steps", round(r.gauss(9500, 2500)), method="garmin_daily_total"),
            Observation(ds, "active_duration", round(r.uniform(40, 110)) * 60, method="garmin_active_plus_highly_active"),
            Observation(ds, "avg_stress", round(r.uniform(22, 38) + (10 if episode else 0)), method="garmin_stress"),
            Observation(ds, "body_battery_high", round(min(100, r.uniform(70, 95) - (20 if episode else 0))), method="garmin_body_battery"),
            Observation(ds, "body_battery_low", round(r.uniform(10, 30)), method="garmin_body_battery"),
            Observation(ds, "garmin_training_readiness", round(max(5, r.uniform(50, 85) - (30 if episode else 0))),
                        method="garmin_morning_readiness"),
        ]
        b.raw.append(RawPayload("fixture_day", ds, {"worn": True}))
        return b

    # ------------------------------------------------------------ activities

    def _run_kind(self, d: date) -> str | None:
        if self._not_worn(d) or d > self.anchor:
            return None
        return {0: "easy", 2: "intervals", 4: "easy", 5: "long"}.get(d.weekday())

    def hr_zones(self) -> dict | None:
        return {"floors": [95, 113, 132, 151, 170], "method": "HR_MAX", "max_hr": 189, "lthr": 168, "profile": "DEFAULT", "source": "fixture"}

    def list_activities(self, start: date, end: date) -> list[dict]:
        out = []
        d = start
        while d <= min(end, self.anchor):
            kind = self._run_kind(d)
            if kind:
                sid = f"fx-run-{d.isoformat()}"
                out.append({"source_id": sid, "sport": "running", "start": d.isoformat(), "content_hash": content_hash([self.seed, sid, kind]),
                            "payload": {"date": d.isoformat(), "kind": kind}})
            d += timedelta(days=1)
        return out

    def read_activity(self, summary: dict) -> Activity:
        d = date.fromisoformat(summary["payload"]["date"])
        kind = summary["payload"]["kind"]
        r = self._rng(d, "run")
        off = self._offset(d)
        start_local = datetime.combine(d, time(6, 45)) + timedelta(minutes=r.randint(-20, 30))
        if d.weekday() == 4:
            start_local = datetime.combine(d, time(18, 30))  # Friday evening run
        start_utc = (start_local - timedelta(seconds=off)).replace(tzinfo=ZoneInfo("UTC"))
        fitness = self._rel(d) / 120.0  # -1 .. 0
        base_speed = 2.95 + 0.12 * (fitness + 1)  # m/s, ~5:39 -> 5:16 /km easy pace
        if kind == "long":
            plan = [("steady", 75 * 60, base_speed - 0.05)]
        elif kind == "intervals":
            plan = [("warmup", 12 * 60, base_speed - 0.1)]
            for _ in range(6):
                plan += [("interval", 3 * 60, base_speed + 1.0), ("recovery", 2 * 60, base_speed - 0.6)]
            plan += [("cooldown", 8 * 60, base_speed - 0.2)]
        else:
            plan = [("steady", r.randint(38, 50) * 60, base_speed)]

        dt = 5.0
        t = 0.0
        dist = 0.0
        elev_base = 40.0
        ts, hr, speed, dists, elev, cad = [], [], [], [], [], []
        total = sum(p[1] for p in plan)
        pause_at = total * 0.55 if kind == "easy" else None  # traffic light
        dropout = self._rel(d) == -5
        for seg, dur, v in plan:
            seg_t = 0.0
            while seg_t < dur:
                if pause_at is not None and abs(t - pause_at) < dt / 2:
                    # 60 s standing still: timer keeps running (no auto-pause) but the athlete is not moving
                    for _ in range(12):
                        ts.append(round(t, 1)); hr.append(round(118 + r.gauss(0, 2))); speed.append(0.0)
                        dists.append(round(dist, 1)); elev.append(round(elev_base, 1)); cad.append(0.0)
                        t += dt
                vs = max(0.5, v + r.gauss(0, 0.06))
                drift = 0.06 * (t / 60.0) if seg == "steady" else 0.0  # bpm per minute cardiac drift
                target = 92 + 22 * vs + drift - 3 * (fitness + 1)
                if seg in ("interval",):
                    target += min(18, seg_t / 6)
                h = round(target + r.gauss(0, 1.5))
                dist += vs * dt
                ts.append(round(t, 1))
                hr.append(None if dropout and 900 <= t < 1500 else h)
                speed.append(round(vs, 3))
                dists.append(round(dist, 1))
                elev.append(round(elev_base + 6 * math.sin(dist / 900.0), 1))
                cad.append(round(166 + 6 * (vs - 3) + r.gauss(0, 1.5)))
                t += dt
                seg_t += dt

        laps, lap_start_i, next_km = [], 0, 1000.0
        for i, dd in enumerate(dists):
            last = i == len(dists) - 1
            if dd >= next_km or last:
                laps.append(self._lap(len(laps), start_utc, ts, hr, speed, dists, elev, cad, lap_start_i, i))
                lap_start_i = i + 1
                next_km += 1000.0
        moving = sum(dt for s in speed if s and s > 0.5)
        hrs = [x for x in hr if x is not None]
        gain = sum(max(0.0, elev[i] - elev[i - 1]) for i in range(1, len(elev)))
        loss = sum(max(0.0, elev[i - 1] - elev[i]) for i in range(1, len(elev)))
        names = {"easy": "Easy run", "intervals": "6 × 3 min intervals", "long": "Long run"}
        return Activity(
            source_id=summary["source_id"], sport="running", name=f"[Synthetic] {names[kind]}",
            start_utc=iso_utc(start_utc), utc_offset_s=off, local_date=d.isoformat(),
            distance_m=round(dist, 1), elapsed_s=t, moving_s=moving, timer_s=t,
            avg_hr=round(sum(hrs) / len(hrs), 1), max_hr=max(hrs), elevation_gain_m=round(gain, 1),
            elevation_loss_m=round(loss, 1), avg_cadence_spm=round(sum(c for c in cad if c) / len([c for c in cad if c])),
            device_id="fixture-watch", manufacturer="FIXTURE",
            garmin_metrics={"aerobicTrainingEffect": round(2.5 + (1.0 if kind != "easy" else 0) + r.uniform(0, 0.5), 1)},
            laps=laps, samples=Samples(ts, hr, speed, dists, elev, cad),
            raw=[RawPayload("fixture_activity", summary["source_id"], summary["payload"])],
        )

    @staticmethod
    def _lap(idx, start_utc, ts, hr, speed, dists, elev, cad, a, b) -> Lap:
        prev_d = dists[a - 1] if a > 0 else 0.0
        prev_t = ts[a - 1] + 5.0 if a > 0 else 0.0
        hrs = [x for x in hr[a:b + 1] if x is not None]
        el = elev[max(0, a - 1):b + 1]
        return Lap(
            idx=idx, start_utc=iso_utc(start_utc + timedelta(seconds=prev_t)),
            distance_m=round(dists[b] - prev_d, 1), elapsed_s=round(ts[b] + 5.0 - prev_t, 1),
            moving_s=5.0 * sum(1 for s in speed[a:b + 1] if s and s > 0.5),
            avg_hr=round(sum(hrs) / len(hrs), 1) if hrs else None, max_hr=max(hrs) if hrs else None,
            elevation_gain_m=round(sum(max(0.0, el[i] - el[i - 1]) for i in range(1, len(el))), 1),
            elevation_loss_m=round(sum(max(0.0, el[i - 1] - el[i]) for i in range(1, len(el))), 1),
            avg_cadence_spm=round(sum(c for c in cad[a:b + 1] if c) / max(1, len([c for c in cad[a:b + 1] if c]))),
            intensity="ACTIVE",
        )

"""History replay: made-up but realistic runners, played forward one morning at a time through the real pipeline (sync,
reports, Today), recording what every part of the app says and checking it against what a sensible coach would say and
against itself (the card, the next run, the race week and the highlights must agree).

Each scenario is a function of the day (days relative to the last replayed morning, 0): whether the watch was worn,
the night's HRV, resting HR and sleep relative to the runner's normal, the day's run (kind, length, heat, hills,
heart-rate dropout) and check-ins. Runs happen in the evening, so each morning sees only the runs before it, like a real
morning; the morning's own sleep is already in. Weather for hot runs is stored as the sync would store it.

Run: python -m sidekick replay [SCENARIO ...]  (prints each morning and every failed check). Tests: tests/test_replay.py.
Checks are a sensible coach's expectations and the app's own consistency; passing them isn't physiological validation.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from .connectors.base import Activity, Lap, Observation, RawPayload, Samples, SleepSession, DayBundle
from .connectors.fixture import FixtureConnector, FIXTURE_METRICS
from .connectors.garmin import content_hash, iso_utc

TZ = "Asia/Jerusalem"
END = date(2026, 9, 27)  # the last replayed morning (a Sunday); fixed so replays are reproducible
HARD = {"tempo", "threshold", "intervals", "race_pace", "race"}


@dataclass
class Run:
    kind: str = "easy"          # easy | long | recovery | tempo | intervals | race
    minutes: int = 40
    hot: bool = False            # dew point 23 °C, heart rate ~8 bpm higher at the same pace
    hilly: bool = False          # out and back on a hill: up for the first half, down for the second
    dropout: float = 0.0         # share of the run with no heart rate (sensor dropout)


@dataclass
class Day:
    worn: bool = True
    rhr: float = 0.0             # resting HR above the runner's normal, bpm
    hrv: float = 0.0             # overnight HRV above normal, ms (negative = lower)
    sleep_h: float | None = None  # the night's sleep, hours (None: the runner's usual ~7.1 h)
    run: Run | None = None
    ill: bool = False            # a "not feeling well" check-in that morning


@dataclass
class Scenario:
    name: str
    about: str
    day: Callable[[int], Day]
    days: int = 84               # history length, up to and including END
    replay: int = 28             # mornings replayed one at a time (the earlier history is synced in one go)
    settings: dict = field(default_factory=dict)
    checks: list[Callable[["Scenario", list[dict]], list[str]]] = field(default_factory=list)


def routine(rel: int, long_minutes: int = 75) -> Run | None:
    """Four runs a week: easy Monday, Wednesday and Friday, a long run on Saturday."""
    wd = (END + timedelta(days=rel)).weekday()
    return {0: Run("easy", 40), 2: Run("easy", 45), 4: Run("easy", 40), 5: Run("long", long_minutes)}.get(wd)


# ---------------------------------------------------------------- the connector

class ScenarioConnector(FixtureConnector):
    """The fixture connector's shape, driven by a scenario. `anchor` is the morning being replayed: its night is in, its
    runs aren't yet (they happen that evening)."""

    def __init__(self, sc: Scenario, anchor: date):
        super().__init__(anchor, tz=TZ, seed=zlib.crc32(sc.name.encode()) % 1000)  # reproducible across runs
        self.sc = sc

    def spec(self, d: date) -> Day:
        rel = (d - END).days
        if rel < -self.sc.days:
            return Day(worn=False)
        return self.sc.day(rel)

    def _not_worn(self, d: date) -> bool:
        return not self.spec(d).worn

    def _day(self, d: date) -> DayBundle:
        ds, s = d.isoformat(), self.spec(d)
        b = DayBundle(local_date=ds)
        if not s.worn:
            for m in FIXTURE_METRICS:
                b.observations.append(Observation(ds, m, None, state="not_measured"))
            b.raw.append(RawPayload("fixture_day", ds, {"worn": False}))
            return b
        r = self._rng(d, "day")
        rhr = round(52 + r.gauss(0, 1.2) + s.rhr)
        hrv = round(60 + r.gauss(0, 4) + s.hrv)
        sleep_s = round(((s.sleep_h if s.sleep_h is not None else 7.1 + r.gauss(0, 0.4)) * 3600) / 60) * 60
        off = self._offset(d)
        end_utc = (datetime.combine(d, time(6, 30)) + timedelta(minutes=r.randint(-30, 30)) - timedelta(seconds=off)).replace(tzinfo=ZoneInfo("UTC"))
        start_utc = end_utc - timedelta(seconds=sleep_s + 20 * 60)
        sid = f"sc-sleep-{ds}"
        b.sleep.append(SleepSession(sid, ds, iso_utc(start_utc), iso_utc(end_utc), off, False, sleep_s,
                                    round(sleep_s * 0.18), round(sleep_s * 0.6), round(sleep_s * 0.22), 900, 75))
        b.observations += [
            Observation(ds, "resting_hr", rhr, method="garmin_daily_rhr"),
            Observation(ds, "hrv_overnight_avg", hrv, method="garmin_overnight_hrv", label="BALANCED" if s.hrv > -10 else "UNBALANCED"),
            Observation(ds, "sleep_duration", sleep_s, method="garmin_main_sleep", source_record_id=sid,
                        observed_start=iso_utc(start_utc), observed_end=iso_utc(end_utc)),
            Observation(ds, "garmin_sleep_score", 75, method="garmin_sleep_score", source_record_id=sid),
            Observation(ds, "steps", round(r.gauss(9000, 1500)), method="garmin_daily_total"),
            Observation(ds, "active_duration", round(r.uniform(40, 90)) * 60, method="garmin_active_plus_highly_active"),
            Observation(ds, "intensity_minutes_moderate", round(r.uniform(5, 30)), method="garmin_intensity_minutes"),
            Observation(ds, "intensity_minutes_vigorous", round(r.uniform(0, 15)), method="garmin_intensity_minutes"),
            Observation(ds, "avg_stress", round(r.uniform(22, 35)), method="garmin_stress"),
            Observation(ds, "body_battery_high", round(r.uniform(70, 95)), method="garmin_body_battery"),
            Observation(ds, "body_battery_low", round(r.uniform(10, 30)), method="garmin_body_battery"),
            Observation(ds, "garmin_training_readiness", round(r.uniform(55, 85)), method="garmin_morning_readiness"),
        ]
        b.raw.append(RawPayload("fixture_day", ds, {"worn": True}))
        return b

    def _run_kind(self, d: date) -> str | None:
        s = self.spec(d)
        return s.run.kind if s.worn and s.run and d < self.anchor else None  # today's run is this evening

    def fitness_snapshot(self, day: date) -> dict | None:
        snap = super().fitness_snapshot(day)
        snap["training_status"] = None  # Garmin's own verdict would mask what the app itself says
        return snap

    def list_activities(self, start: date, end: date) -> list[dict]:
        out = []
        d = start
        while d <= min(end, self.anchor - timedelta(days=1)):
            s = self.spec(d)
            if s.worn and s.run:
                sid = f"sc-run-{d.isoformat()}"
                out.append({"source_id": sid, "sport": "running", "start": d.isoformat(),
                            "content_hash": content_hash([self.seed, sid, s.run.kind, s.run.minutes, s.run.hot, s.run.hilly]),
                            "payload": {"date": d.isoformat(), "kind": s.run.kind}})
            d += timedelta(days=1)
        return out

    def read_activity(self, summary: dict) -> Activity:
        d = date.fromisoformat(summary["payload"]["date"])
        run = self.spec(d).run
        r = self._rng(d, "run")
        off = self._offset(d)
        start_utc = (datetime.combine(d, time(18, 0)) + timedelta(minutes=r.randint(-15, 15)) - timedelta(seconds=off)).replace(tzinfo=ZoneInfo("UTC"))
        v = 2.95  # m/s easy, about 5:39 /km
        mins = run.minutes * 60
        if run.kind == "intervals":
            plan = [("warmup", 12 * 60, v - 0.1)] + [("interval", 3 * 60, v + 1.0), ("recovery", 2 * 60, v - 0.6)] * 6 + [("cooldown", 8 * 60, v - 0.2)]
        elif run.kind == "tempo":
            plan = [("warmup", 10 * 60, v - 0.1), ("tempo", max(10, run.minutes - 20) * 60, v + 0.55), ("cooldown", 10 * 60, v - 0.2)]
        elif run.kind == "race":
            plan = [("race", mins, v + 0.45)]
        elif run.kind == "recovery":
            plan = [("steady", mins, v - 0.25)]
        else:
            plan = [("steady", mins, v - (0.05 if run.kind == "long" else 0.0))]
        dt, t, dist = 5.0, 0.0, 0.0
        ts, hr, speed, dists, elev, cad = [], [], [], [], [], []
        total = sum(p[1] for p in plan)
        for seg, dur, vv in plan:
            seg_t = 0.0
            while seg_t < dur:
                frac = t / total
                grade = (0.04 if frac < 0.5 else -0.04) if run.hilly else 0.0
                vs = max(0.5, vv * (1 - 3.0 * grade) + r.gauss(0, 0.05))  # slower up, faster down at the same effort
                target = 92 + 22 * vv + 0.05 * (t / 60.0) + (8 if run.hot else 0)
                if seg == "interval":
                    target += min(18, seg_t / 6)
                if seg in ("tempo", "race"):
                    target += 6
                dist += vs * dt
                ts.append(round(t, 1))
                gone = run.dropout and 0.2 * total <= t < (0.2 + run.dropout) * total
                hr.append(None if gone else round(target + r.gauss(0, 1.5)))
                speed.append(round(vs, 3))
                dists.append(round(dist, 1))
                elev.append(round(40 + 4 * math.sin(dist / 900.0), 1))  # gently rolling (a hilly run's profile is set below)
                cad.append(round(166 + 6 * (vs - 3) + r.gauss(0, 1.5)))
                t += dt
                seg_t += dt
        if run.hilly:  # a clean out-and-back profile: up 4% to the turn, back down
            half = dists[-1] / 2
            elev = [round(40 + 0.04 * (x if x <= half else 2 * half - x), 1) for x in dists]
        laps, a, next_km = [], 0, 1000.0
        for i, dd in enumerate(dists):
            if dd >= next_km or i == len(dists) - 1:
                laps.append(self._lap(len(laps), start_utc, ts, hr, speed, dists, elev, cad, a, i))
                a = i + 1
                next_km += 1000.0
        hrs = [x for x in hr if x is not None]
        gain = sum(max(0.0, elev[i] - elev[i - 1]) for i in range(1, len(elev)))
        loss = sum(max(0.0, elev[i - 1] - elev[i]) for i in range(1, len(elev)))
        return Activity(
            source_id=summary["source_id"], sport="running", name=f"[Replay] {run.kind}",
            start_utc=iso_utc(start_utc), utc_offset_s=off, local_date=d.isoformat(),
            distance_m=round(dist, 1), elapsed_s=t, moving_s=t, timer_s=t,
            avg_hr=round(sum(hrs) / len(hrs), 1), max_hr=max(hrs), elevation_gain_m=round(gain, 1), elevation_loss_m=round(loss, 1),
            avg_cadence_spm=round(sum(cad) / len(cad)), device_id="replay-watch", manufacturer="FIXTURE",
            garmin_metrics={"aerobicTrainingEffect": 3.6 if run.kind in HARD else 2.8},
            laps=laps, samples=Samples(ts, hr, speed, dists, elev, cad),
            raw=[RawPayload("fixture_activity", summary["source_id"], summary["payload"])],
        )


# ---------------------------------------------------------------- the replay

HOT = {"temperature_2m": 31.0, "dew_point_2m": 23.0, "apparent_temperature": 36.0, "relative_humidity_2m": 60}
MILD = {"temperature_2m": 21.0, "dew_point_2m": 13.0, "apparent_temperature": 21.0, "relative_humidity_2m": 55}


def replay(sc: Scenario, conn) -> list[dict]:
    """Plays the scenario forward and returns one snapshot per replayed morning."""
    from . import reports as rp
    from .db import set_setting, utc_now
    from .sync import run_sync
    for c in conn.list_collection_names():
        conn[c].drop()
    set_setting(conn, "timezone", TZ)
    for k, v in {"running_days": [0, 2, 4, 5], **sc.settings}.items():
        set_setting(conn, k, v)
    first = END - timedelta(days=sc.replay - 1)
    c = ScenarioConnector(sc, first - timedelta(days=1))

    def step(day: date, backfill: int):
        c.anchor = day
        s = c.spec(day)
        if s.ill:
            conn.checkin.replace_one({"id": f"ill-{day}"}, {"id": f"ill-{day}", "local_date": day.isoformat(), "energy": None, "soreness": None,
                                                           "recovery": None, "pain": False, "illness": True, "notes": None, "tags": [],
                                                           "client_updated_at": "x", "received_at": "x", "deleted": False}, upsert=True)
        res = run_sync(conn, c, day, backfill, 3, max_backfill_days=400)
        for sid in res.changed_activities:  # weather, as the sync stores it for outdoor runs
            run = c.spec(date.fromisoformat(sid[-10:])).run
            conn.run_weather.update_one({"source_id": sid}, {"$set": {"weather": HOT if run and run.hot else MILD, "checked_at": utc_now()}}, upsert=True)
        rp.regenerate(conn, c.source, True, set(res.changed_dates) | {day.isoformat()}, res.changed_activities, day)

    step(first - timedelta(days=1), sc.days)
    out = []
    for k in range(sc.replay):
        day = first + timedelta(days=k)
        step(day, 7)
        out.append(snapshot(conn, c, day))
    return out


def snapshot(conn, c: ScenarioConnector, day: date) -> dict:
    """What the app says this morning, in the parts the checks look at."""
    from . import progress, reports as rp, run_checks, strain, today_view
    from . import focus as fc
    body = rp.build_morning(conn, c.source, day, True)
    today_view.enrich(conn, c.source, day, body)
    ready = body.get("readiness") or {}
    nxt = body.get("next_run") or {}
    week = (body.get("race") or {}).get("week") or {}
    yesterday = (day - timedelta(days=1)).isoformat()
    checks = None
    rep = conn.report.find_one({"type": "post_run", "subject_key": f"sc-run-{yesterday}"}, sort=[("revision", -1)])
    if rep:
        checks = {x["id"]: (x["verdict"], x["say"]) for x in run_checks.build(conn, c.source, rep["body"])}
    sw = strain.build(conn, c.source, day)
    pg = progress.build(conn, c.source, day)
    return {
        "date": day.isoformat(), "weekday": day.strftime("%a"), "spec": c.spec(day),
        "yesterday": c.spec(day - timedelta(days=1)),
        "readiness": {k: ready.get(k) for k in ("status", "score", "label", "allows", "headline", "hold_reason", "capped_by", "floored_by")},
        "parts": {p["id"]: (p.get("points"), p["say"]) for p in ready.get("components", [])},
        "next_run": {k: nxt.get(k) for k in ("date", "kind", "title", "minutes", "optional", "caution", "hr")},
        "race": {k: (body.get("race") or {}).get(k) for k in ("phase", "days_to_go", "title")} if body.get("race") else None,
        "week": {"phase": week.get("phase"), "target": week.get("target_minutes"),
                 "sessions": {s["date"]: s["kind"] for s in week.get("sessions", [])}} if week else None,
        "decision": body.get("decision"),
        "highlights": [(h["id"], h["title"]) for h in body.get("highlights", [])],
        "strain": [s["id"] for s in sw["signals"]] if sw else None,
        "focus": (fc.current(conn, c.source, day) or {}).get("kind"),
        "progress": (pg.get("verdict"), [(s["id"], s.get("direction")) for s in pg.get("signals", [])]),
        "run_checks": checks,
    }


# ---------------------------------------------------------------- checks

ALLOWED = {"rest": {"rest"}, "easy": {"rest", "easy", "long", "recovery", "strides"},
           "steady": {"rest", "easy", "long", "recovery", "strides", "steady"}, "hard": None}
HEADLINES = {"rest": "Take it easy or rest", "easy": "Fine for an easy run", "steady": "Good for a steady run", "hard": "Ready to train"}


def consistency(sc: Scenario, snaps: list[dict]) -> list[str]:
    """Every morning, every scenario: the parts of Today agree with each other."""
    bad = []
    for s in snaps:
        r, n, d = s["readiness"], s["next_run"], s["date"]
        if r["status"] == "ok":
            if r["headline"] != HEADLINES.get(r["allows"]):
                bad.append(f"{d}: readiness says '{r['headline']}' but allows {r['allows']}")
            ok = ALLOWED.get(r["allows"])
            race_day = s["race"] and s["race"]["days_to_go"] == 0
            if n.get("date") == d and ok is not None and n.get("kind") not in ok and not (race_day and n.get("kind") == "race"):
                bad.append(f"{d}: today allows {r['allows']} but the next run is {n.get('kind')}")
        w = s["week"]
        if w and n.get("date") == d and d in w["sessions"]:
            planned = w["sessions"][d]
            if planned in HARD and n.get("kind") not in HARD and planned != "race" and not (s["decision"] or {}).get("hold_back"):
                bad.append(f"{d}: the week plans {planned} today but the next run is {n.get('kind')}")
        if s["race"] and w and s["race"]["phase"] != w["phase"] and any(t.lower().find(str(s["race"]["phase"]).replace("_", " ")) >= 0
                                                                      for i, t in s["highlights"] if i == "race"):
            bad.append(f"{d}: the race highlight says {s['race']['phase']} but this week's plan is {w['phase']}")
        hr = n.get("hr") or {}
        if hr.get("max") and hr.get("max") >= 195:
            bad.append(f"{d}: the next run's heart-rate target has no real upper limit ({hr.get('text')})")
        if s["strain"] and r.get("allows") == "hard":
            bad.append(f"{d}: strain is building ({', '.join(s['strain'])}) but today allows hard training")
    return bad


def never_rest_when_well(sc, snaps):
    """A healthy runner on their usual routine is never told to rest."""
    return [f"{s['date']} ({s['weekday']}): told to rest; parts {s['parts']}" for s in snaps
            if s["readiness"]["allows"] == "rest" and not s["spec"].ill]


def no_strain_warning(sc, snaps):
    return [f"{s['date']}: strain warning {s['strain']}" for s in snaps if s["strain"]]


def day_after_long_run(sc, snaps):
    """The morning after the weekly long run: easy at the least, never rest, and recovery called usual for the weekday."""
    bad = []
    for s in snaps:
        if s["yesterday"].run and s["yesterday"].run.kind == "long":
            if s["readiness"]["allows"] == "rest":
                bad.append(f"{s['date']}: rest the morning after the weekly long run")
            say = (s["parts"].get("recovery") or (None, ""))[1]
            if "more than usual" in say:
                bad.append(f"{s['date']}: the weekly long run's leftover called unusual: '{say}'")
    return bad


def rest_while_ill(sc, snaps):
    return [f"{s['date']}: ill but allows {s['readiness']['allows']}" for s in snaps if s["spec"].ill and s["readiness"]["allows"] != "rest"]


def easy_return_after_illness(sc, snaps):
    """The first days back from illness (decide.RETURN_EASY_DAYS): nothing harder than easy."""
    from .decide import RETURN_EASY_DAYS
    ill_days = [s["date"] for s in snaps if s["spec"].ill]
    if not ill_days:
        return []
    last = date.fromisoformat(max(ill_days))
    return [f"{s['date']}: {(date.fromisoformat(s['date']) - last).days} days after being ill, allows {s['readiness']['allows']}"
            for s in snaps if 0 < (date.fromisoformat(s["date"]) - last).days <= RETURN_EASY_DAYS and s["readiness"]["allows"] in ("steady", "hard")]


def no_load_alarm_on_return(sc, snaps):
    """Coming back from a break with a few easy runs isn't a dangerous load jump."""
    bad = []
    for s in snaps:
        load = s["parts"].get("load")
        if load and "Much heavier" in load[1]:
            bad.append(f"{s['date']}: '{load[1]}' after a break")
        if s["strain"] and "load" in s["strain"]:
            bad.append(f"{s['date']}: strain load jump after a break ({s['strain']})")
    return bad


def honest_when_not_worn(sc, snaps):
    """A night without the watch: no confident readiness from older readings."""
    bad = []
    for s in snaps:
        if not s["spec"].worn and s["readiness"]["status"] == "ok":
            known = [k for k, v in s["parts"].items() if k in ("hrv", "resting_hr", "sleep") and v[0] is not None]
            if known:
                bad.append(f"{s['date']}: watch not worn last night, yet readiness {s['readiness']['score']} uses {known}")
    return bad


def heat_isnt_lost_fitness(sc, snaps):
    """Hot, humid runs raise heart rate; that mustn't read as fitness going down or a poor run."""
    bad = []
    for s in snaps:
        verdict, signals = s["progress"]
        if verdict in ("declining", "down"):
            bad.append(f"{s['date']}: progress says {verdict} in a hot spell")
        for sid, direction in signals:
            if sid in ("efficiency", "drift") and direction in ("down", "worse", "declining"):
                bad.append(f"{s['date']}: {sid} trend {direction} in a hot spell")
        if s["strain"] and "heart_rate" in s["strain"]:
            bad.append(f"{s['date']}: strain reads hot runs' heart rate as strain")
        rc = s["run_checks"] or {}
        if s["yesterday"].run and s["yesterday"].run.hot and rc.get("drift", ("",))[0] == "low":
            bad.append(f"{s['date']}: yesterday's hot run's drift judged low: {rc['drift'][1]}")
    return bad


def hills_arent_a_fade(sc, snaps):
    bad = []
    for s in snaps:
        rc = s["run_checks"] or {}
        if s["yesterday"].run and s["yesterday"].run.hilly and rc.get("pacing", ("",))[0] == "low":
            bad.append(f"{s['date']}: an out-and-back hill run's pacing judged low: {rc['pacing'][1]}")
    return bad


def no_zones_from_dropouts(sc, snaps):
    bad = []
    for s in snaps:
        rc = s["run_checks"] or {}
        if s["yesterday"].run and s["yesterday"].run.dropout >= 0.3 and "effort" in rc:
            bad.append(f"{s['date']}: effort judged from a run with {s['yesterday'].run.dropout:.0%} heart rate missing: {rc['effort'][1]}")
    return bad


def taper_and_race_week(sc, snaps):
    """In the taper, volume comes down; in race week nothing hard but the race; on race day, the race."""
    bad, targets = [], {}
    for s in snaps:
        w = s["week"]
        if not w:
            continue
        targets.setdefault(w["phase"], []).append(w["target"] or 0)
        if w["phase"] == "race_week":
            hard = [k for dd, k in w["sessions"].items() if k in HARD - {"race", "race_pace"}]
            if hard:
                bad.append(f"{s['date']}: race week plans {hard}")
        if s["race"] and s["race"]["days_to_go"] == 0 and s["next_run"].get("kind") != "race":
            bad.append(f"{s['date']}: race day, but the next run is {s['next_run'].get('kind')}")
    build = max(targets.get("build", []) + targets.get("sharpen", []), default=None)
    taper = max(targets.get("taper", []), default=None)
    if build and taper and taper >= build:
        bad.append(f"taper volume {taper} min isn't below the build's {build} min")
    return bad


def after_the_race(sc, snaps):
    """The days after a race: easy running only."""
    return [f"{s['date']}: {s['race']['days_to_go']} days after the race, the next run is {s['next_run'].get('kind')}"
            for s in snaps if s["race"] and s["race"]["days_to_go"] is not None and -7 <= s["race"]["days_to_go"] < 0
            and s["next_run"].get("kind") in HARD]


# ---------------------------------------------------------------- the scenarios

def _ill(rel, a, b):
    return a <= rel <= b


SCENARIOS = [
    Scenario("routine", "Four easy runs a week with a Saturday long run, nothing unusual.",
             lambda rel: Day(run=routine(rel)), checks=[never_rest_when_well, no_strain_warning, day_after_long_run]),
    Scenario("long_run_growth", "The Saturday long run grows from 75 to 110 minutes over the replay.",
             lambda rel: Day(run=routine(rel, long_minutes=75 + max(0, (rel + 28)) * 35 // 28)),
             checks=[never_rest_when_well, day_after_long_run]),
    Scenario("illness", "A week ill (no runs, resting HR up, HRV down, short nights, 'not feeling well'), then back to running.",
             lambda rel: Day(rhr=7, hrv=-16, sleep_h=6.2, ill=True) if _ill(rel, -18, -12) else Day(run=routine(rel)),
             checks=[rest_while_ill, easy_return_after_illness]),
    Scenario("break", "Two weeks off running (well, watch on), then the routine again.",
             lambda rel: Day() if _ill(rel, -24, -11) else Day(run=routine(rel)), checks=[no_load_alarm_on_return, never_rest_when_well]),
    Scenario("missing_nights", "The watch is left off three nights, and one night with a run the evening before.",
             lambda rel: Day(worn=False) if _ill(rel, -12, -10) or rel == -4 else Day(run=routine(rel)),
             checks=[honest_when_not_worn, never_rest_when_well]),
    Scenario("hot_summer", "The last three weeks are hot and humid: the same runs at about 8 bpm higher heart rate.",
             lambda rel: Day(run=(lambda r: Run(r.kind, r.minutes, hot=rel >= -21) if r else None)(routine(rel))),
             checks=[heat_isnt_lost_fitness, never_rest_when_well]),
    Scenario("hilly", "The Wednesday run is an out-and-back on a 4% hill.",
             lambda rel: Day(run=(lambda r: Run(r.kind, r.minutes, hilly=(END + timedelta(days=rel)).weekday() == 2) if r else None)(routine(rel))),
             checks=[hills_arent_a_fade]),
    Scenario("hr_dropout", "Every Monday run loses heart rate for 40% of the run.",
             lambda rel: Day(run=(lambda r: Run(r.kind, r.minutes, dropout=0.4 if (END + timedelta(days=rel)).weekday() == 0 else 0.0) if r else None)(routine(rel))),
             checks=[no_zones_from_dropouts]),
    Scenario("race_build", "Building to a half marathon on the last Sunday of the replay; the race itself is run.",
             lambda rel: Day(run=Run("race", 115) if rel == 0 else routine(rel)),
             settings={"race_date": END.isoformat(), "race_distance": "half", "race_target_s": 6900, "race_name": "Replay Half"},
             checks=[taper_and_race_week]),
    Scenario("after_race", "A 10K race two weeks before the end, then the routine again.",
             lambda rel: Day(run=Run("race", 50) if rel == -14 else routine(rel)),
             settings={"race_date": (END - timedelta(days=14)).isoformat(), "race_distance": "10k", "race_target_s": 3000, "race_name": "Replay 10K"},
             checks=[after_the_race]),
]


def run(names: list[str] | None = None) -> dict[str, dict]:
    """Replays the scenarios (all, or those named) and returns {name: {"snaps": [...], "failures": [...]}}."""
    from .db import client, connect, db_prefix
    out = {}
    for sc in (s for s in SCENARIOS if not names or s.name in names):
        name = f"{db_prefix()}_replay_{sc.name}"  # a database of its own, dropped afterwards
        try:
            snaps = replay(sc, connect(name))
        finally:
            client().drop_database(name)
        fails = consistency(sc, snaps) + [f for chk in sc.checks for f in chk(sc, snaps)]
        out[sc.name] = {"snaps": snaps, "failures": fails}
    return out


def print_report(results: dict[str, dict]) -> int:
    worst = 0
    for name, r in results.items():
        sc = next(s for s in SCENARIOS if s.name == name)
        print(f"\n=== {name}: {sc.about}")
        for s in r["snaps"]:
            rd, n = s["readiness"], s["next_run"]
            print(f"  {s['date']} {s['weekday']}  readiness {rd['score']!s:>4} {str(rd['allows']):<6} next {n.get('date')} {n.get('kind')!s:<9}"
                  + (f" week {s['week']['phase']}" if s["week"] else "") + (f"  strain {s['strain']}" if s["strain"] else ""))
        print(f"  -- {len(r['failures'])} failed check(s)")
        for f in r["failures"]:
            print(f"     ✗ {f}")
        worst = max(worst, 1 if r["failures"] else 0)
    return worst

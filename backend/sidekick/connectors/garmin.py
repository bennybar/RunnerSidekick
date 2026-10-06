"""Garmin Connect adapter over the unofficial python-garminconnect library (read-only).

Payload field names below were taken from the library's endpoints as of 0.3.17 and
are parsed defensively: Garmin varies payloads by device and account, so any field
may be absent. Absent values become `not_measured`, never zero. The real coverage for
this account is recorded by `python -m sidekick audit` (docs/data-audit.md).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .base import (
    METRIC_UNITS,
    Activity,
    AuthRequired,
    Capability,
    ConnectionState,
    DayBundle,
    Lap,
    Observation,
    RateLimited,
    RawPayload,
    Samples,
    SleepSession,
    SourceUnavailable,
    valid_hr,
)

log = logging.getLogger(__name__)

RUNNING_TYPES = {"running", "trail_running", "treadmill_running", "track_running", "street_running", "indoor_running", "virtual_run", "ultra_run"}


# ---------------------------------------------------------------- parsing helpers

def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_garmin_ts(s: str | None) -> datetime | None:
    """Garmin 'YYYY-MM-DD HH:MM:SS[.f]' strings (no zone)."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def offset_seconds(local: datetime | None, gmt: datetime | None) -> int | None:
    """Source UTC offset from a local/GMT pair, rounded to 15 minutes."""
    if local is None or gmt is None:
        return None
    return int(round((local - gmt).total_seconds() / 900.0)) * 900


def ms_to_utc(ms: Any) -> datetime | None:
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def num(v: Any) -> float | None:
    """Numeric value or None. Garmin uses negative sentinels (-1/-2) for 'not enough data' in some fields."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def non_negative(v: Any) -> float | None:
    x = num(v)
    return x if x is not None and x >= 0 else None


def obs(d: str, metric: str, value: float | None, **kw) -> Observation:
    return Observation(local_date=d, metric=metric, value=value, state="measured" if value is not None else "not_measured", **kw)


def content_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def normalise_sport(type_key: str | None) -> str:
    if type_key in ("trail_running",):
        return "trail_running"
    if type_key in ("treadmill_running", "indoor_running"):
        return "treadmill_running"
    if type_key in RUNNING_TYPES:
        return "running"
    return "other"


# ---------------------------------------------------------------- daily normalisation

def normalise_user_summary(d: str, p: dict | None) -> list[Observation]:
    p = p or {}
    active = None
    if num(p.get("activeSeconds")) is not None or num(p.get("highlyActiveSeconds")) is not None:
        active = (num(p.get("activeSeconds")) or 0.0) + (num(p.get("highlyActiveSeconds")) or 0.0)
    return [
        obs(d, "steps", non_negative(p.get("totalSteps")), method="garmin_daily_total"),
        obs(d, "resting_hr", non_negative(p.get("restingHeartRate")), method="garmin_daily_rhr"),
        obs(d, "avg_stress", non_negative(p.get("averageStressLevel")), method="garmin_stress"),
        obs(d, "body_battery_high", non_negative(p.get("bodyBatteryHighestValue")), method="garmin_body_battery"),
        obs(d, "body_battery_low", non_negative(p.get("bodyBatteryLowestValue")), method="garmin_body_battery"),
        obs(d, "respiration_waking_avg", non_negative(p.get("avgWakingRespirationValue")), method="garmin_waking_avg"),
        obs(d, "active_duration", active, method="garmin_active_plus_highly_active"),
        obs(d, "intensity_minutes_moderate", non_negative(p.get("moderateIntensityMinutes")), method="garmin_intensity_minutes"),
        obs(d, "intensity_minutes_vigorous", non_negative(p.get("vigorousIntensityMinutes")), method="garmin_intensity_minutes"),
    ]


def normalise_sleep(d: str, p: dict | None) -> tuple[list[Observation], list[SleepSession]]:
    """Primary sleep is attributed to the local date of wake-up; the original interval is kept."""
    dto = (p or {}).get("dailySleepDTO") or {}
    sessions: list[SleepSession] = []
    start = ms_to_utc(dto.get("sleepStartTimestampGMT"))
    end = ms_to_utc(dto.get("sleepEndTimestampGMT"))
    duration = non_negative(dto.get("sleepTimeSeconds"))
    score = num(((dto.get("sleepScores") or {}).get("overall") or {}).get("value"))
    obs_list: list[Observation] = []
    if start and end and duration:
        local_end = ms_to_utc(dto.get("sleepEndTimestampLocal"))
        off = offset_seconds(local_end.replace(tzinfo=None) if local_end else None, end.replace(tzinfo=None))
        wake_date = (end + timedelta(seconds=off)).date().isoformat() if off is not None else d
        sid = str(dto.get("id") or f"sleep-{wake_date}")
        sessions.append(SleepSession(
            source_id=sid, wake_date=wake_date, start_utc=iso_utc(start), end_utc=iso_utc(end), utc_offset_s=off,
            is_nap=False, duration_s=duration,
            deep_s=non_negative(dto.get("deepSleepSeconds")), light_s=non_negative(dto.get("lightSleepSeconds")),
            rem_s=non_negative(dto.get("remSleepSeconds")), awake_s=non_negative(dto.get("awakeSleepSeconds")),
            garmin_sleep_score=score,
        ))
        obs_list.append(obs(wake_date, "sleep_duration", duration, method="garmin_main_sleep", source_record_id=sid,
                            observed_start=iso_utc(start), observed_end=iso_utc(end)))
        obs_list.append(obs(wake_date, "garmin_sleep_score", score, method="garmin_sleep_score", source_record_id=sid))
    else:
        obs_list.append(obs(d, "sleep_duration", None, method="garmin_main_sleep"))
        obs_list.append(obs(d, "garmin_sleep_score", None, method="garmin_sleep_score"))
    for nap in (p or {}).get("dailyNapDTOS") or []:
        ns, ne = ms_to_utc(nap.get("napStartTimestampGMT")), ms_to_utc(nap.get("napEndTimestampGMT"))
        if ns and ne:
            sessions.append(SleepSession(
                source_id=f"nap-{int(ns.timestamp())}", wake_date=d, start_utc=iso_utc(ns), end_utc=iso_utc(ne),
                utc_offset_s=None, is_nap=True, duration_s=non_negative(nap.get("napTimeSec")) or (ne - ns).total_seconds(),
            ))
    return obs_list, sessions


def normalise_hrv(d: str, p: dict | None) -> list[Observation]:
    s = (p or {}).get("hrvSummary") or {}
    label = s.get("status") if isinstance(s.get("status"), str) else None
    return [
        obs(d, "hrv_overnight_avg", non_negative(s.get("lastNightAvg")), method="garmin_overnight_hrv", label=label),
        obs(d, "hrv_weekly_avg", non_negative(s.get("weeklyAvg")), method="garmin_overnight_hrv_7d"),
    ]


def normalise_readiness(d: str, p: dict | None) -> list[Observation]:
    p = p or {}
    level = p.get("level") if isinstance(p.get("level"), str) else None
    return [obs(d, "garmin_training_readiness", non_negative(p.get("score")), method="garmin_morning_readiness", label=level)]


def normalise_max_metrics(d: str, p: Any) -> list[Observation]:
    entries = p if isinstance(p, list) else [p] if isinstance(p, dict) else []
    v, when = None, None
    for e in entries:
        g = (e or {}).get("generic") or {}
        v = non_negative(g.get("vo2MaxPreciseValue")) or non_negative(g.get("vo2MaxValue"))
        if v is not None:
            when = g.get("calendarDate")
            break
    # Stored under the day Garmin measured it: a value carried forward from an earlier day isn't a new measurement
    if v is not None and isinstance(when, str) and len(when) == 10 and when < d:
        return [obs(when, "garmin_vo2max_running", v, method="garmin_vo2max_generic"),
                obs(d, "garmin_vo2max_running", None, method="garmin_vo2max_generic")]
    return [obs(d, "garmin_vo2max_running", v, method="garmin_vo2max_generic")]


def normalise_weight(d: str, p: dict | None) -> list[Observation]:
    """Weight, and body fat when a scale reports it. The method says where the weight came from: a Garmin scale, or a
    value entered in Garmin Connect."""
    grams, fat, method = None, None, "garmin_weigh_in"
    for e in (p or {}).get("dateWeightList") or []:
        grams = non_negative(e.get("weight"))
        if grams is not None:
            fat = non_negative(e.get("bodyFat"))
            method = "garmin_scale" if "SCALE" in str(e.get("sourceType") or "").upper() else "garmin_entered"
            break
    return [obs(d, "weight", grams / 1000.0 if grams is not None else None, method=method),
            obs(d, "body_fat_pct", fat, method="garmin_scale")]


def normalise_fitness(race: dict, ts: dict) -> dict:
    out: dict = {"source": "garmin"}
    if race and any(race.get(k) for k in ("time5K", "time10K", "timeHalfMarathon", "timeMarathon")):
        out["race_predictions"] = {"date": race.get("calendarDate"), "5k": race.get("time5K"), "10k": race.get("time10K"),
                                   "half": race.get("timeHalfMarathon"), "marathon": race.get("timeMarathon")}
    vo2 = ((ts.get("mostRecentVO2Max") or {}).get("generic") or {})
    if vo2.get("vo2MaxPreciseValue") or vo2.get("vo2MaxValue"):
        out["vo2max"] = {"value": vo2.get("vo2MaxPreciseValue") or vo2.get("vo2MaxValue"), "date": vo2.get("calendarDate"),
                         "fitness_age": vo2.get("fitnessAge")}
    heat = (ts.get("mostRecentVO2Max") or {}).get("heatAltitudeAcclimation") or {}
    if heat.get("heatAcclimationPercentage") is not None:
        out["heat_acclimation_pct"] = heat.get("heatAcclimationPercentage")
    status_map = ((ts.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData") or {})
    st = next((v for v in status_map.values() if v.get("primaryTrainingDevice")), None) or next(iter(status_map.values()), None)
    if st:
        acute = st.get("acuteTrainingLoadDTO") or {}
        out["training_status"] = {
            "phrase": st.get("trainingStatusFeedbackPhrase"), "date": st.get("calendarDate"), "since": st.get("sinceDate"),
            "paused": st.get("trainingPaused"),
            # Garmin's acute load and its own chronic "optimal" range. The acute:chronic ratio is deliberately not shown.
            "acute_load": acute.get("dailyTrainingLoadAcute"),
            "chronic_min": acute.get("minTrainingLoadChronic"), "chronic_max": acute.get("maxTrainingLoadChronic"),
        }
    lb_map = ((ts.get("mostRecentTrainingLoadBalance") or {}).get("metricsTrainingLoadBalanceDTOMap") or {})
    lb = next((v for v in lb_map.values() if v.get("primaryTrainingDevice")), None) or next(iter(lb_map.values()), None)
    if lb:
        out["load_balance"] = {k: lb.get(k) for k in ("trainingBalanceFeedbackPhrase", "monthlyLoadAerobicLow", "monthlyLoadAerobicHigh",
                                                     "monthlyLoadAnaerobic", "monthlyLoadAerobicLowTargetMin", "monthlyLoadAerobicLowTargetMax",
                                                     "monthlyLoadAerobicHighTargetMin", "monthlyLoadAerobicHighTargetMax",
                                                     "monthlyLoadAnaerobicTargetMin", "monthlyLoadAnaerobicTargetMax")}
    return out


# ---------------------------------------------------------------- activity normalisation

def summarise_activity(a: dict) -> dict:
    """Light summary from the activity list, used to decide whether details need (re)fetching."""
    return {"source_id": str(a["activityId"]), "sport": normalise_sport((a.get("activityType") or {}).get("typeKey")),
            "start": a.get("startTimeGMT") or "", "content_hash": content_hash(a), "payload": a}


def normalise_activity(a: dict, splits: dict | None, details: dict | None) -> Activity:
    gmt = parse_garmin_ts(a.get("startTimeGMT"))
    local = parse_garmin_ts(a.get("startTimeLocal"))
    if gmt is None:
        raise ValueError(f"activity {a.get('activityId')} has no startTimeGMT")
    off = offset_seconds(local, gmt)
    start = gmt.replace(tzinfo=timezone.utc)
    local_date = (local or gmt).date().isoformat()
    garmin_metrics = {k: a[k] for k in (
        "aerobicTrainingEffect", "anaerobicTrainingEffect", "trainingEffectLabel", "activityTrainingLoad",
        "vO2MaxValue", "averageSpeed", "maxSpeed", "calories",
        # running dynamics, Garmin's per-run averages: W, cm, ms, %
        "avgPower", "maxPower", "normPower", "maxRunningCadenceInStepsPerMinute", "avgStrideLength", "avgVerticalOscillation",
        "avgGroundContactTime", "avgVerticalRatio") if a.get(k) is not None}
    laps = []
    for i, lap in enumerate((splits or {}).get("lapDTOs") or []):
        lg = parse_garmin_ts(lap.get("startTimeGMT"))
        laps.append(Lap(
            idx=i, start_utc=iso_utc(lg.replace(tzinfo=timezone.utc)) if lg else None,
            distance_m=non_negative(lap.get("distance")), elapsed_s=non_negative(lap.get("elapsedDuration")),
            moving_s=non_negative(lap.get("movingDuration")), avg_hr=non_negative(lap.get("averageHR")),
            max_hr=non_negative(lap.get("maxHR")), elevation_gain_m=non_negative(lap.get("elevationGain")),
            elevation_loss_m=non_negative(lap.get("elevationLoss")),
            avg_cadence_spm=non_negative(lap.get("averageRunCadence")),
            intensity=lap.get("intensityType") if isinstance(lap.get("intensityType"), str) else None,
        ))
    raw = [RawPayload("activity_summary", str(a["activityId"]), a)]
    if splits is not None:
        raw.append(RawPayload("activity_splits", str(a["activityId"]), splits))
    if details is not None:
        raw.append(RawPayload("activity_details", str(a["activityId"]), details))
    return Activity(
        source_id=str(a["activityId"]), sport=normalise_sport((a.get("activityType") or {}).get("typeKey")),
        name=a.get("activityName"), start_utc=iso_utc(start), utc_offset_s=off, local_date=local_date,
        distance_m=non_negative(a.get("distance")), elapsed_s=non_negative(a.get("elapsedDuration")),
        moving_s=non_negative(a.get("movingDuration")), timer_s=non_negative(a.get("duration")),
        avg_hr=non_negative(a.get("averageHR")), max_hr=non_negative(a.get("maxHR")),
        elevation_gain_m=non_negative(a.get("elevationGain")), elevation_loss_m=non_negative(a.get("elevationLoss")),
        avg_cadence_spm=non_negative(a.get("averageRunningCadenceInStepsPerMinute")),
        garmin_metrics=garmin_metrics, device_id=str(a["deviceId"]) if a.get("deviceId") is not None else None,
        manufacturer=a.get("manufacturer") if isinstance(a.get("manufacturer"), str) else None, laps=laps, samples=normalise_samples(details, start), raw=raw,
    )


def normalise_samples(details: dict | None, start: datetime) -> Samples | None:
    if not details:
        return None
    idx = {m.get("key"): m.get("metricsIndex") for m in details.get("metricDescriptors") or []}
    rows = [r.get("metrics") or [] for r in details.get("activityDetailMetrics") or []]
    if not rows:
        return None

    def col(key: str, parse=non_negative) -> list[float | None]:
        i = idx.get(key)
        if i is None:
            return [None] * len(rows)
        return [parse(r[i]) if i < len(r) else None for r in rows]

    ts = col("directTimestamp")
    if any(v is not None for v in ts):
        t = [(v / 1000.0 - start.timestamp()) if v is not None else None for v in ts]
    else:
        t = col("sumElapsedDuration")
    keep = [i for i, v in enumerate(t) if v is not None]
    if not keep:
        return None
    pick = lambda xs: [xs[i] for i in keep]  # noqa: E731
    cadence = col("directDoubleCadence") if "directDoubleCadence" in idx else [None] * len(rows)
    dyn = {}
    for key, name, scale in (("directGroundContactTime", "gct", 1), ("directStrideLength", "stride", 0.01),
                             ("directVerticalOscillation", "vo", 1), ("directVerticalRatio", "vr", 1), ("directBodyBattery", "bb", 1)):
        if key in idx:
            dyn[name] = [round(v * scale, 3) if v else None for v in pick(col(key))]  # 0 means not measured
    return Samples(t=[round(t[i], 1) for i in keep], hr=valid_hr(pick(col("directHeartRate"))), speed=pick(col("directSpeed")),
                   dist=pick(col("sumDistance")), elev=pick(col("directElevation", num)), cad=pick(cadence),
                   power=pick(col("directPower")) if "directPower" in idx else None, dyn=dyn or None)


# ---------------------------------------------------------------- connector

DETAIL_POINTS = 10000


class GarminConnector:
    source = "garmin"
    synthetic = False

    def __init__(self, token_dir: Path, request_spacing_s: float = 1.0, client_factory: Callable[[], Any] | None = None):
        self.token_dir = token_dir
        self.spacing = request_spacing_s
        self._client = None
        self._factory = client_factory

    # -- auth

    def _api(self):
        if self._client is not None:
            return self._client
        from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

        if self._factory is not None:
            self._client = self._factory()
            return self._client
        if not (self.token_dir / "garmin_tokens.json").exists():
            raise AuthRequired("Garmin isn't connected: connect it in the app (Settings → Garmin)")
        api = Garmin()
        try:
            api.login(tokenstore=str(self.token_dir))
        except GarminConnectAuthenticationError as e:
            raise AuthRequired("Garmin ended this connection: connect it again in the app (Settings → Garmin)") from e
        except GarminConnectTooManyRequestsError as e:
            raise RateLimited(str(e)) from e
        except Exception as e:  # network etc. Message only; never the token
            raise SourceUnavailable(f"Garmin login failed: {type(e).__name__}") from e
        self._client = api
        return api

    def _call(self, fn: str, *args):
        from garminconnect import (
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
            GarminConnectNotFoundError,
            GarminConnectTooManyRequestsError,
        )

        api = self._api()
        if self.spacing:
            time.sleep(self.spacing)
        try:
            return getattr(api, fn)(*args)
        except GarminConnectAuthenticationError as e:
            raise AuthRequired(f"{fn}: authentication failed") from e
        except GarminConnectTooManyRequestsError as e:
            raise RateLimited(f"{fn}: rate limited") from e
        except GarminConnectNotFoundError:
            return None
        except GarminConnectConnectionError as e:
            raise SourceUnavailable(f"{fn}: {type(e).__name__}") from e

    def connection_state(self) -> ConnectionState:
        if not (self.token_dir / "garmin_tokens.json").exists() and self._factory is None:
            return ConnectionState.NOT_CONFIGURED
        return ConnectionState.CONNECTED

    def capabilities(self) -> dict[str, Capability]:
        # Unknown until observed; the sync engine records observed coverage per metric.
        return {m: Capability.UNKNOWN for m in METRIC_UNITS}

    # -- reads

    def read_days(self, start: date, end: date) -> Iterable[DayBundle]:
        d = end
        while d >= start:
            ds = d.isoformat()
            b = DayBundle(local_date=ds)
            summary = self._call("get_user_summary", ds)
            b.raw.append(RawPayload("user_summary", ds, summary))
            b.observations += normalise_user_summary(ds, summary)
            sleep = self._call("get_sleep_data", ds)
            b.raw.append(RawPayload("sleep", ds, sleep))
            sleep_obs, sessions = normalise_sleep(ds, sleep)
            b.observations += sleep_obs
            b.sleep += sessions
            hrv = self._call("get_hrv_data", ds)
            b.raw.append(RawPayload("hrv", ds, hrv))
            b.observations += normalise_hrv(ds, hrv)
            ready = self._call("get_morning_training_readiness", ds)
            b.raw.append(RawPayload("training_readiness", ds, ready))
            b.observations += normalise_readiness(ds, ready)
            mm = self._call("get_max_metrics", ds)
            b.raw.append(RawPayload("max_metrics", ds, mm))
            b.observations += normalise_max_metrics(ds, mm)
            body = self._call("get_body_composition", ds, ds)
            b.raw.append(RawPayload("body_composition", ds, body))
            b.observations += normalise_weight(ds, body)
            yield b
            d -= timedelta(days=1)

    def hr_zones(self) -> dict | None:
        """User's Garmin HR zones (default/running profile) with provenance."""
        zs = self._call("get_heart_rate_zones") or []
        prof = next((z for z in zs if z.get("sport") == "RUNNING"), None) or next((z for z in zs if z.get("sport") == "DEFAULT"), None)
        if not prof:
            return None
        floors = [prof.get(f"zone{i}Floor") for i in range(1, 6)]
        if not all(isinstance(f, (int, float)) for f in floors):
            return None
        return {"floors": floors, "method": prof.get("trainingMethod"), "max_hr": prof.get("maxHeartRateUsed"),
                "lthr": prof.get("lactateThresholdHeartRateUsed"), "profile": prof.get("sport"), "source": "garmin"}

    def fitness_snapshot(self, day: date) -> dict | None:
        """Garmin's own fitness numbers, kept under Garmin's names: race predictions, VO2 max, training status,
        acute load vs Garmin's chronic range, load-balance feedback and heat acclimation."""
        rp_ = self._call("get_race_predictions") or {}
        ts = self._call("get_training_status", day.isoformat()) or {}
        out = normalise_fitness(rp_, ts)
        fa = self._call("get_fitnessage_data", day.isoformat()) or {}
        if fa.get("fitnessAge") is not None:
            # Garmin's own fitness age and the inputs it reports (resting HR, BMI, vigorous activity)
            out["fitness_age"] = {k: fa.get(k) for k in ("chronologicalAge", "fitnessAge", "achievableFitnessAge", "previousFitnessAge",
                                                         "lastUpdated")} | {
                "components": {k: (v.get("value") if isinstance(v, dict) else v) for k, v in (fa.get("components") or {}).items()}}
        return out

    def personal_records(self) -> list[dict] | None:
        """Garmin's own all-time personal records (fastest 1 km, mile, 5 km..., longest run, most steps, goal streaks), as
        {type, value, activity_id, date}. Garmin's type ids, kept as numbers; trophies.py names them."""
        rows = self._call("get_personal_record")
        if not isinstance(rows, list):
            return None
        out = []
        for r in rows:
            if r.get("typeId") is None or r.get("value") is None:
                continue
            when = r.get("prStartTimeLocalFormatted") or r.get("activityStartDateTimeLocalFormatted") or r.get("prStartTimeGmtFormatted")
            out.append({"type": int(r["typeId"]), "value": float(r["value"]),
                        "activity_id": str(r["activityId"]) if r.get("activityId") else None, "date": (when or "")[:10] or None})
        return out

    def profile(self) -> dict | None:
        """Sex, birth date, height and first day of week (comparisons, BMI, week boundaries). Nothing else from the profile."""
        ud = (self._call("get_user_profile") or {}).get("userData") or {}
        sex = {"MALE": "male", "FEMALE": "female"}.get((ud.get("gender") or "").upper())
        first = ((ud.get("firstDayOfWeek") or {}).get("dayName") or "").lower() or None
        if not sex and not ud.get("birthDate") and not first:
            return None
        h = num(ud.get("height"))
        wg = num(ud.get("weight"))  # grams in Garmin's profile
        return {"sex": sex, "birth_date": ud.get("birthDate"), "first_day_of_week": first,
                "height_cm": round(h, 1) if h and 100 <= h <= 250 else None,
                "weight_kg": round(wg / 1000, 1) if wg and 30_000 <= wg <= 250_000 else None, "source": "garmin"}

    def list_activities(self, start: date, end: date) -> list[dict]:
        acts = self._call("get_activities_by_date", start.isoformat(), end.isoformat()) or []
        out = []
        for a in acts:  # one entry Garmin sends in an odd shape (no activityId, say) is skipped, not fatal
            try:
                out.append(summarise_activity(a))
            except (KeyError, TypeError, ValueError) as e:
                log.warning("skipped an activity list entry: %s", e)
        return out

    def read_activity(self, summary: dict) -> Activity:
        a = summary["payload"]
        aid = summary["source_id"]
        splits = details = None
        if summary["sport"] != "other":
            splits = self._call("get_activity_splits", aid)
            # Up to 10,000 samples: Garmin's default (2,000) spaces a run over ~5.6 h more than 10 s apart, which the
            # analysis would read as pauses
            details = self._call("get_activity_details", aid, DETAIL_POINTS)
        return normalise_activity(a, splits, details)

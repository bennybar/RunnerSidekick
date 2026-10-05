"""HTTP API for the Android client. Every route requires a device bearer token."""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

import os

from . import narrative as nv
from . import reports as rp
from dataclasses import replace

from . import accounts
from . import garmin_oauth as goauth
from . import garmin_link
from .config import GARMIN_REDIRECT_URI, GOOGLE_WEB_CLIENT_ID, secrets
from fastapi.responses import HTMLResponse
from .config import SOURCE_FIXTURE, Config
from .connectors.base import Samples
from .connectors.fixture import FixtureConnector
from .connectors.garmin import GarminConnector
from .db import WEEKDAYS, connect, many, one, put, put_if_newer, set_setting, utc_now
from .sync import get_connection_row, next_manual_sync, run_sync

log = logging.getLogger(__name__)
MAX_CHART_POINTS = 240  # ~20 s buckets for a 75-min run: readable trend without hiding stops


class CheckinIn(BaseModel):
    local_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    energy: int | None = Field(default=None, ge=1, le=5)
    soreness: int | None = Field(default=None, ge=1, le=5)
    recovery: int | None = Field(default=None, ge=1, le=5)
    pain: bool = False
    illness: bool = False
    notes: str | None = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    client_updated_at: str
    deleted: bool = False


class EffortIn(BaseModel):
    rpe: int = Field(ge=1, le=10)
    client_updated_at: str


class PlanIn(BaseModel):
    kind: Literal["rest", "easy", "long", "tempo", "intervals", "race", "other"]
    minutes: int | None = Field(default=None, ge=5, le=600)
    client_updated_at: str


class IntentIn(BaseModel):
    """What the run was meant to be, and optionally how it went in the runner's words. Blank fields are left out."""
    kind: Literal["recovery", "easy", "steady", "long", "tempo", "threshold", "intervals", "race", "progression", "free", "other"]
    note: str | None = Field(default=None, max_length=500)
    target: str | None = Field(default=None, max_length=100)
    effort: Literal["very_easy", "easy", "easy_moderate", "moderate", "moderate_hard", "hard", "very_hard"] | None = None
    feel: Literal["great", "good", "okay", "poor", "very_poor"] | None = None
    limiter: Literal["none", "cardio", "breathing", "legs", "feet", "muscular_fatigue", "heat", "humidity", "hills", "illness",
                     "pain", "gi", "motivation", "other"] | None = None
    limiter2: Literal["none", "cardio", "breathing", "legs", "feet", "muscular_fatigue", "heat", "humidity", "hills", "illness",
                      "pain", "gi", "motivation", "other"] | None = None
    health: Literal["normal", "recovering", "mild_symptoms", "poor_sleep", "fatigued", "sore", "other"] | None = None
    client_updated_at: str


class GarminCompleteIn(BaseModel):
    state: str = Field(max_length=200)
    code: str = Field(max_length=2000)


class FocusIn(BaseModel):
    kind: Literal["even_pacing", "easy_runs", "steady_volume", "consistency", "recovery"]


class InsightStateIn(BaseModel):
    state: Literal["dismissed", "working_on"] | None


class GarminTicketIn(BaseModel):
    ticket: str = Field(pattern=r"^ST-[A-Za-z0-9._\-]{8,300}$")


class SettingsIn(BaseModel):
    timezone: str | None = None
    running_days: list[int] | None = Field(default=None, max_length=7)
    goal: str | None = Field(default=None, max_length=200)
    available_minutes: int | None = Field(default=None, ge=0, le=600)
    hr_zone_source: Literal["garmin", "none"] | None = None
    goal_type: Literal["consistency", "distance", "performance", "health"] | None = None
    ai_enabled: bool | None = None
    weather_enabled: bool | None = None
    ai_model: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:\-]{1,64}$")
    morning_window_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    morning_window_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    profile_sex: Literal["male", "female"] | None = None          # overrides Garmin's profile for comparisons
    profile_birth_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    race_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    race_distance: Literal["5k", "10k", "half", "marathon"] | None = None
    race_target_s: int | None = Field(default=None, ge=600, le=36000)
    race_name: str | None = Field(default=None, max_length=60)
    week_start_day: Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] | None = None


def downsample(s: Samples, max_points: int = MAX_CHART_POINTS) -> dict:
    """Time-bucket means for charting. A bucket with no valid value stays null; gaps are preserved."""
    if not s.t:
        return {"t": [], "hr": [], "speed": [], "elev": []}
    span = s.t[-1] - s.t[0]
    width = max(5.0, span / max_points)
    buckets: dict[int, list[int]] = {}
    for i, t in enumerate(s.t):
        buckets.setdefault(int((t - s.t[0]) // width), []).append(i)
    out = {"t": [], "hr": [], "speed": [], "elev": []}

    def mean(arr, idx):
        v = [arr[i] for i in idx if arr[i] is not None]
        return round(sum(v) / len(v), 3) if v else None

    prev = None
    for b in sorted(buckets):
        if prev is not None and b - prev > 1:  # explicit gap marker
            for k in out:
                out[k].append(round(s.t[0] + (prev + 1) * width, 1) if k == "t" else None)
        idx = buckets[b]
        out["t"].append(round(s.t[idx[0]], 1))
        out["hr"].append(mean(s.hr, idx))
        sp = [s.speed[i] for i in idx if s.speed[i] is not None and s.speed[i] >= 0.5]
        out["speed"].append(round(sum(sp) / len(sp), 3) if sp else None)
        out["elev"].append(mean(s.elev, idx))
        prev = b
    return out


class GoogleSignIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=4096)
    device_name: str = Field(default="android", max_length=60)


def verify_google_id_token(token: str) -> dict:
    """Signature, expiry, issuer and audience checks by Google's own library."""
    from google.auth.transport import requests as grequests
    from google.oauth2 import id_token

    if not GOOGLE_WEB_CLIENT_ID:
        raise HTTPException(503, "Google sign-in isn't configured on this server yet")
    try:
        return id_token.verify_oauth2_token(token, grequests.Request(), audience=GOOGLE_WEB_CLIENT_ID)
    except ValueError:
        raise HTTPException(401, "Google sign-in could not be verified")


def create_app(cfg: Config, connector=None, narrative_provider=None, google_verifier=verify_google_id_token,
               coach_provider=None, summary_provider=None, run_ai_provider=None) -> FastAPI:
    accounts.app_db()  # creates the accounts database's indexes
    synthetic = cfg.source == SOURCE_FIXTURE
    sync_locks: dict[int, threading.Lock] = {}
    running: set[int] = set()

    def current_user(authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="invalid or missing token")
        u = accounts.verify_session(accounts.app_db(), authorization[7:])
        if u is None:
            raise HTTPException(status_code=401, detail="invalid or missing token")
        return u

    def user_cfg(user) -> Config:
        """The same config, pointed at this user's own database and token folder."""
        return replace(cfg, data_dir=accounts.user_dir(cfg.data_dir, user["id"]), user_id=user["id"])

    def db(user=Depends(current_user)):
        return connect(user_cfg(user).db_name)

    def tz(conn) -> ZoneInfo:
        return ZoneInfo(rp.get_setting(conn, "timezone", cfg.timezone))

    def today(conn) -> date:
        return datetime.now(tz(conn)).date()

    def parse_day(day: str, conn) -> date:
        """A YYYY-MM-DD day within a sensible range (2000 to a year ahead), else ValueError with a plain message."""
        try:
            d = date.fromisoformat(day)
        except ValueError:
            raise ValueError("date must be YYYY-MM-DD")
        if not date(2000, 1, 1) <= d <= today(conn) + timedelta(days=366):
            raise ValueError("date is out of range")
        return d

    def make_connector(conn, ucfg: Config):
        if connector is not None:
            return connector
        if synthetic:
            return FixtureConnector(anchor=today(conn), tz=str(tz(conn)))
        return GarminConnector(ucfg.garmin_token_dir, ucfg.request_spacing_s)

    # No interactive docs or schema endpoint. Public routes live on `app`; everything with user data on `api`.
    app = FastAPI(title="Runner Sidekick", docs_url=None, redoc_url=None, openapi_url=None)
    api = APIRouter(dependencies=[Depends(current_user)])

    # Rate limit: per device token (or per address without one), a sliding minute. Generous for the app's polling;
    # stops a runaway client or someone hammering the server. RSK_RATE_LIMIT=0 turns it off.
    rate_hits: dict[str, list[float]] = {}
    rate_limit = int(os.getenv("RSK_RATE_LIMIT", "300"))

    @app.middleware("http")
    async def rate(request, call_next):
        import time as _time
        if not rate_limit:
            return await call_next(request)
        from fastapi.responses import JSONResponse
        ip = request.client.host if request.client else "?"
        now = _time.monotonic()

        def recent(key):
            return [h for h in rate_hits.get(key, []) if now - h < 60]
        # Per address, whatever the token says (junk tokens get no bucket of their own); requests turned away for a bad
        # or missing token fill a much smaller bucket, so guessing or hammering sign-in stops quickly
        if len(recent("ip:" + ip)) >= rate_limit or len(recent("bad:" + ip)) >= max(10, rate_limit // 10):
            return JSONResponse({"detail": "too many requests"}, status_code=429, headers={"Retry-After": "30"})
        rate_hits["ip:" + ip] = recent("ip:" + ip) + [now]
        resp = await call_next(request)
        if resp.status_code in (401, 403):
            rate_hits["bad:" + ip] = recent("bad:" + ip) + [now]
        if len(rate_hits) > 10000:  # forget idle clients
            for k in [k for k, v in rate_hits.items() if not v or now - v[-1] > 60]:
                rate_hits.pop(k, None)
        return resp

    @app.middleware("http")
    async def etag(request, call_next):
        """Every JSON GET carries an ETag; when the app already has that exact body it gets an empty 304 instead, so
        repeated refreshes and polls cost the phone almost nothing to download."""
        resp = await call_next(request)
        if request.method != "GET" or resp.status_code != 200 or not resp.headers.get("content-type", "").startswith("application/json"):
            return resp
        body = b"".join([chunk async for chunk in resp.body_iterator])
        tag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers={"ETag": tag})
        headers = {k: v for k, v in resp.headers.items() if k.lower() != "content-length"}
        return Response(content=body, status_code=200, headers={**headers, "ETag": tag}, media_type="application/json")

    def do_sync(ucfg: Config, user_id: int, force: bool = False) -> dict:
        with sync_locks.setdefault(user_id, threading.Lock()):
            running.add(user_id)
            conn = connect(ucfg.db_name)
            try:
                c = make_connector(conn, ucfg)
                res = run_sync(conn, c, today(conn), cfg.backfill_days, cfg.refetch_days, cfg.raw_retention_days, force=force)
                from .sync import report_progress
                if not synthetic:
                    from . import weather
                    res.changed_activities = list(dict.fromkeys(res.changed_activities + weather.for_new_runs(conn, c.source, res.changed_activities)))
                report_progress(conn, res.job_id, 0.92, "Updating your reports")
                with report_lock(conn):
                    rp.regenerate(conn, c.source, synthetic, res.changed_dates, res.changed_activities, today(conn))
                report_progress(conn, res.job_id, 1.0, "Done")
                auto_run_ai(conn, res.changed_activities)
                return {"outcome": res.outcome, "detail": res.detail, "days_fetched": res.days_fetched,
                        "activities_fetched": res.activities_fetched}
            except Exception:
                log.exception("sync failed")
                raise
            finally:
                running.discard(user_id)

    report_locks: dict[str, threading.RLock] = {}
    report_locks_guard = threading.Lock()

    def report_lock(conn) -> threading.RLock:
        """One lock per user's database: building one user's reports never waits on another's."""
        with report_locks_guard:
            return report_locks.setdefault(conn.name, threading.RLock())
    inflight: set[tuple] = set()

    def ai_config(conn, own_key: str | None = None) -> nv.AiConfig:
        """On the server's key only the allowed models run (RSK_AI_MODELS); with the runner's own key, any model they set."""
        model = rp.get_setting(conn, "ai_model", nv.DEFAULT_MODEL)
        if not (own_key or "").strip():
            model = nv.server_model(model)
        return nv.AiConfig(
            enabled=bool(rp.get_setting(conn, "ai_enabled", False)),
            model=model,
            api_key=os.getenv("OPENAI_API_KEY") or secrets(cfg.data_dir).get("openai_api_key"),
            max_calls_per_day=int(os.getenv("RSK_AI_MAX_CALLS_PER_DAY", "25")),
        )

    def generate_bg(body: dict, key: tuple, db_name: str) -> None:
        c = connect(db_name)
        try:
            nv.generate(c, body, ai_config(c), provider=narrative_provider)
        finally:
            inflight.discard(key)

    def with_narrative(conn, body: dict | None) -> dict | None:
        """Attach the cached narrative for this exact report revision; start generation in the background if missing."""
        if body is None:
            return None
        body = dict(body)
        ai = ai_config(conn)
        if not ai.enabled:
            body["narrative"] = {"status": "disabled"}
            return body
        if body["type"] in ("morning", "post_run"):
            # Today shows the coach's TL;DR and a run has its own AI input, so a narrative would be paid for and never read
            body["narrative"] = None
            return body
        hit = nv.cached(conn, body, ai.model)
        if hit:
            body["narrative"] = nv.view(hit)
        elif not ai.api_key and narrative_provider is None:
            body["narrative"] = {"status": "not_configured", "detail": "OPENAI_API_KEY is not set on the backend"}
        else:
            key = (conn.name, body["type"], body["id"], ai.model)
            if key not in inflight:
                inflight.add(key)
                threading.Thread(target=generate_bg, args=(body, key, conn.name), daemon=True).start()
            body["narrative"] = {"status": "pending"}
        return body

    @api.get("/v1/status")
    def status(conn=Depends(db), user=Depends(current_user)):
        row = get_connection_row(conn, cfg.source)
        lo = one(conn.daily_observation, {"source": cfg.source, "state": "measured"}, sort=[("local_date", -1)])
        la = one(conn.activity, {"source": cfg.source}, sort=[("start_utc", -1)])
        latest, latest_act = (lo or {}).get("local_date"), (la or {}).get("start_utc")
        cps = {r["stream"]: r for r in many(conn.sync_checkpoint, {"source": cfg.source})}
        job = one(conn.sync_job, {"source": cfg.source}, sort=[("id", -1)])
        return {
            "mode": cfg.source, "synthetic": synthetic, "today": today(conn).isoformat(), "timezone": str(tz(conn)),
            "week_start_day": WEEKDAYS[rp.first_weekday(conn)],
            "connection": {k: row[k] for k in ("state", "detail", "last_attempt_at", "last_success_at", "retry_not_before")} if row else
            {"state": make_connector(conn, user_cfg(user)).connection_state().value, "detail": None, "last_attempt_at": None, "last_success_at": None, "retry_not_before": None},
            "latest_observation_date": latest, "latest_activity_start": latest_act,
            "watch_sync_time": None,  # not exposed by the source; never guessed
            "backfill": cps.get("days"), "sync_running": user["id"] in running,
            "sync_progress": ({"percent": round(100 * (job or {}).get("progress", 0)), "phase": (job or {}).get("phase")}
                              if user["id"] in running else None),
            "last_job": job,
            "sync_next_allowed_at": (lambda w: w.isoformat().replace("+00:00", "Z") if w else None)(
                None if synthetic else next_manual_sync(conn, cfg.source)),
            "capabilities": row.get("capabilities", {}) if row else {},
            "garmin_linked": synthetic or garmin_link.linked(user_cfg(user).garmin_token_dir),
            "garmin_official": goauth.status(user_cfg(user).data_dir, bool(secrets(cfg.data_dir).get("garmin_client_id"))),
        }

    @api.post("/v1/sync", status_code=202)
    def sync_now(conn=Depends(db), user=Depends(current_user)):
        if user["id"] in running:
            return {"started": False, "detail": "sync already running"}
        # Not too often: Garmin can rate-limit or lock an account hit in bursts (demo data has no such limit)
        wait = None if synthetic else next_manual_sync(conn, cfg.source)
        if wait:
            return {"started": False, "detail": "synced recently", "next_allowed_at": wait.isoformat().replace("+00:00", "Z")}
        threading.Thread(target=do_sync, args=(user_cfg(user), user["id"]), daemon=True).start()
        return {"started": True}

    @api.get("/v1/today")
    def today_report(day: str | None = Query(default=None, alias="date"), conn=Depends(db)):
        try:
            d = parse_day(day, conn) if day else today(conn)
        except ValueError as e:
            raise HTTPException(422, str(e))
        with report_lock(conn):
            body = rp.build_morning(conn, cfg.source, d, synthetic)
        body = with_narrative(conn, body)
        if body is not None and d == today(conn):
            from . import compare, highlights
            from . import focus as fc
            from . import changes
            from .decide import decide
            dec = decide(conn, cfg.source, d, body)
            body["race"], body["readiness"], body["next_run"] = dec["race"], dec["readiness"], dec["next_run"]
            body["decision"] = {"hold_back": dec["hold_back"], "hold_reason": dec["hold_reason"], "today_kind": dec["today_kind"],
                                "unwell_applied": dec["unwell_applied"]}
            from . import scores
            body["scores"] = scores.build(conn, cfg.source, d, hold_back=dec["hold_back"])
            body["changes"] = changes.since_yesterday(conn, body, d, cfg.source)
            from . import readings
            cmp = compare.build(conn, cfg.source, d)
            body["highlights"] = highlights.build(conn, cfg.source, d, cmp, fc.current(conn, cfg.source, d), body["race"])
            body["reading_notes"] = readings.notes(body["findings"], cmp)
        return body

    @api.get("/v1/trends")
    def get_trends(days: int = 28, conn=Depends(db), x_openai_key: str | None = Header(default=None)):
        from . import summaries as sm
        from .trends import build_trends
        if days not in (7, 28, 90):
            raise HTTPException(422, "days must be 7, 28 or 90")
        out = build_trends(conn, cfg.source, today(conn), days, synthetic)
        out["ai_summary"] = ai_summary(conn, f"trends:{days}", sm.trends_bundle(out), x_openai_key)
        return out

    @api.get("/v1/weekly/latest")
    def latest_weekly(conn=Depends(db)):
        from .weekly import regenerate_weeklies
        with report_lock(conn):
            regenerate_weeklies(conn, cfg.source, today(conn), synthetic)
        r = one(conn.report, {"type": "weekly"}, sort=[("subject_key", -1), ("revision", -1)])
        if not r:
            raise HTTPException(404, "no completed week yet")
        return with_narrative(conn, r["body"])

    @api.get("/v1/reports/{rtype}/{key}/revisions")
    def revisions(rtype: str, key: str, conn=Depends(db)):
        """All stored revisions of one report, newest first, so earlier versions stay browsable."""
        return [{"id": r["id"], "revision": r["revision"], "generated_at": r["generated_at"], "data_cutoff": r["data_cutoff"],
                 "algorithm_version": r["algorithm_version"]}
                for r in conn.report.find({"type": rtype, "subject_key": key}, {"body": 0, "_id": 0}, sort=[("revision", -1)])]

    # ---------------------------------------------------------------- the intent → outcome loop

    @api.get("/v1/plan/{day}")
    def get_plan(day: str, conn=Depends(db)):
        return one(conn.day_plan, {"local_date": day})

    @api.put("/v1/plan/{day}")
    def put_plan(day: str, body: PlanIn, conn=Depends(db)):
        try:
            parse_day(day, conn)
        except ValueError as e:
            raise HTTPException(422, str(e))
        put_if_newer(conn.day_plan, {"local_date": day}, {"kind": body.kind, "minutes": body.minutes, "client_updated_at": body.client_updated_at})
        with report_lock(conn):
            return rp.build_morning(conn, cfg.source, date.fromisoformat(day), synthetic)

    @api.delete("/v1/plan/{day}")
    def delete_plan(day: str, conn=Depends(db)):
        try:
            parse_day(day, conn)  # checked before anything is deleted
        except ValueError as e:
            raise HTTPException(422, str(e))
        conn.day_plan.delete_one({"local_date": day})
        with report_lock(conn):
            return rp.build_morning(conn, cfg.source, date.fromisoformat(day), synthetic)

    @api.put("/v1/activities/{sid}/intent")
    def put_intent(sid: str, body: IntentIn, conn=Depends(db)):
        if not rp.activity_by_source_id(conn, cfg.source, sid):
            raise HTTPException(404)
        put_if_newer(conn.run_intent, {"activity_source_id": sid},
                     {"kind": body.kind, "note": body.note, "source": "user", "client_updated_at": body.client_updated_at,
                      **{k: (getattr(body, k) or "").strip() or None for k in rp.CONTEXT_FIELDS}})
        with report_lock(conn):
            return rp.build_post_run(conn, cfg.source, sid, synthetic)

    @api.get("/v1/focus")
    def get_focus(conn=Depends(db)):
        from . import focus as fc
        return fc.current(conn, cfg.source, today(conn))

    @api.put("/v1/focus")
    def put_focus(body: FocusIn, conn=Depends(db)):
        from . import focus as fc
        d = today(conn)
        fc.choose(conn, fc.week_start(d, rp.first_weekday(conn)), body.kind)
        return fc.current(conn, cfg.source, d)

    @api.put("/v1/insights/{insight_id}/state")
    def put_insight_state(insight_id: str, body: InsightStateIn, conn=Depends(db)):
        if body.state is None:
            conn.insight_state.delete_one({"insight_id": insight_id})
        else:
            cur = rp.latest_body(conn, "insights")
            verdict = next((i["verdict"] for i in cur["insights"] if i["id"] == insight_id), None) if cur else None
            put(conn.insight_state, {"insight_id": insight_id}, {"state": body.state, "verdict_at_dismissal": verdict, "updated_at": utc_now()})
        with report_lock(conn):
            return rp.build_insights(conn, cfg.source, today(conn), synthetic)

    # ---------------------------------------------------------------- AI coach

    coach_inflight: set[str] = set()

    def coach_bg(db_name: str, model: str, key: str, key_source: str, budget: int) -> None:
        from . import coach as ch
        c = connect(db_name)
        try:
            ch.run(c, cfg.source, today(c), model, key, key_source, provider=coach_provider, budget=budget)
        except Exception:
            log.exception("coach generation failed")
        finally:
            coach_inflight.discard(db_name)

    @api.get("/v1/coach")
    def get_coach(conn=Depends(db), x_openai_key: str | None = Header(default=None)):
        """Latest validated coach analysis for the current evidence; generates in the background when inputs changed.
        A user's own key (X-OpenAI-Key) is used for that call only and never stored or logged."""
        from . import coach as ch
        ai = ai_config(conn, x_openai_key)
        if not ai.enabled:
            return {"status": "disabled"}
        key = (x_openai_key or "").strip() or ai.api_key
        if not key and coach_provider is None:
            return {"status": "not_configured", "detail": "No OpenAI key: add one in Settings or on the server"}
        b = ch.build_bundle(conn, cfg.source, today(conn))
        h = ch.input_hash(b, ai.model)
        hit = one(conn.coach_analysis, {"input_hash": h, "status": "ok"}, sort=[("id", -1)])
        if hit:
            return ch.view(hit)
        db_path = conn.name
        last = ch.latest(conn)
        # The same evidence that just failed or hit the limit isn't retried for 30 minutes
        cooling = bool(last and last["status"] != "ok" and last["input_hash"] == h and
                       (datetime.now(timezone.utc) - datetime.fromisoformat(last["created_at"].replace("Z", "+00:00"))).total_seconds() < 1800)
        if db_path not in coach_inflight and not cooling:
            coach_inflight.add(db_path)
            threading.Thread(target=coach_bg, args=(db_path, ai.model, key, "user" if (x_openai_key or "").strip() else "server", ai.max_calls_per_day),
                             daemon=True).start()
        prev = ch.latest(conn, ok_only=True)
        out = {"status": "pending", "previous": ch.view(prev) if prev else None}
        if last and last["status"] != "ok" and last["input_hash"] == h:
            out = {"status": last["status"], "detail": last["detail"], "previous": out["previous"]}
        return out

    @api.get("/v1/fitness")
    def fitness(conn=Depends(db)):
        """Garmin's own fitness numbers (labelled as Garmin's) plus Runner Sidekick's records and easy pace."""
        d = today(conn)
        vo2 = [{"date": k, "value": v} for k, v in sorted(rp.series(conn, cfg.source, "garmin_vo2max_running", d.isoformat()).items())
               if k >= (d - timedelta(days=120)).isoformat()]
        report = rp.build_insights(conn, cfg.source, d, synthetic)
        easy = next((i for i in report["insights"] if i["id"] == "easy_pace"), None)
        return {"garmin": rp.get_setting(conn, "garmin_fitness", None), "vo2max_series": vo2, "records": rp.records(conn, cfg.source),
                "easy_pace": easy, "zones": rp.hr_zones(conn), "synthetic": synthetic}

    summary_inflight: set[tuple] = set()

    def summary_bg(db_name: str, kind: str, b, model: str, key: str, budget: int) -> None:
        from . import summaries as sm
        c = connect(db_name)
        try:
            sm.generate(c, kind, b, today(c), model, key, budget, provider=summary_provider)
        except Exception:
            log.exception("summary generation failed")
        finally:
            summary_inflight.discard((db_name, kind))

    def ai_summary(conn, kind: str, b, x_openai_key: str | None) -> dict:
        """Today's AI summary of a screen. Written in the background; meanwhile the newest earlier one is attached."""
        from . import summaries as sm
        ai = ai_config(conn, x_openai_key)
        if not ai.enabled:
            return {"status": "disabled"}
        key = (x_openai_key or "").strip() or ai.api_key
        if not key and summary_provider is None:
            return {"status": "not_configured"}
        d = today(conn)
        hit = sm.cached(conn, kind, d, sm.input_hash(b, ai.model))
        recent_failure = hit and hit["status"] != "ok" and \
            (datetime.now(timezone.utc) - datetime.fromisoformat(hit["created_at"].replace("Z", "+00:00"))).total_seconds() < 1800
        if hit and (hit["status"] == "ok" or recent_failure):
            return sm.view(hit)
        if (conn.name, kind) not in summary_inflight:
            summary_inflight.add((conn.name, kind))
            threading.Thread(target=summary_bg, args=(conn.name, kind, b, ai.model, key, ai.max_calls_per_day), daemon=True).start()
        prev = one(conn.section_summary, {"kind": kind, "status": "ok"}, sort=[("id", -1)])
        return {"status": "pending", "previous": sm.view(prev) if prev else None}

    @api.get("/v1/compare")
    def get_compare(conn=Depends(db), x_openai_key: str | None = Header(default=None)):
        """You against people of your sex and age: VO2 max, fitness age, resting heart rate, HRV and age-graded times."""
        from . import compare
        from . import summaries as sm
        out = compare.build(conn, cfg.source, today(conn))
        if not out["missing"]:
            out["ai_summary"] = ai_summary(conn, "compare", sm.compare_bundle(out), x_openai_key)
        return out

    @api.get("/v1/insights")
    def get_insights(conn=Depends(db)):
        from . import stats
        with report_lock(conn):
            body = dict(rp.build_insights(conn, cfg.source, today(conn), synthetic))
        body["stats"] = stats.four_weeks(conn, cfg.source, today(conn))
        return body

    @api.get("/v1/reports")
    def list_reports(type: str | None = None, start: str | None = Query(default=None, alias="from"),
                     end: str | None = Query(default=None, alias="to"), limit: int = Query(default=60, le=500), conn=Depends(db)):
        match: dict = {}
        if type:
            match["type"] = type
        if start or end:
            match["local_date"] = {**({"$gte": start} if start else {}), **({"$lte": end} if end else {})}
        # Newest revision of each report only
        rows = conn.report.aggregate([
            {"$match": match}, {"$sort": {"revision": -1}},
            {"$group": {"_id": {"t": "$type", "k": "$subject_key"}, "r": {"$first": "$$ROOT"}}}, {"$replaceRoot": {"newRoot": "$r"}},
            {"$sort": {"local_date": -1, "id": -1}}, {"$limit": limit}])
        out = []
        for r in rows:
            b = r["body"]
            title = b.get("headline")
            if r["type"] == "post_run":
                a = b.get("activity") or {}
                pace = b.get("pace_moving_s_per_km")
                name = a.get("name") if a.get("name") and a.get("name").lower() not in ("running", "run") else None
                title = " · ".join(x for x in (f"{(a.get('distance_m') or 0) / 1000:.1f} km",
                                                f"{int(pace) // 60}:{int(pace) % 60:02d} /km" if pace else None, name) if x)
            elif r["type"] == "insights":
                n = sum(1 for i in b.get("insights", []) if i["verdict"] == "pattern")
                title = f"{n} pattern{'s' if n != 1 else ''} found" if n else "No clear patterns"
            out.append({"id": r["id"], "type": r["type"], "subject_key": r["subject_key"], "local_date": r["local_date"],
                        "revision": r["revision"], "generated_at": r["generated_at"], "synthetic": b.get("synthetic", False),
                        "title": title,
                        "state": (b.get("recommendation") or {}).get("state")})
        return out

    @api.get("/v1/reports/{report_id}")
    def get_report(report_id: int, conn=Depends(db)):
        r = one(conn.report, {"id": report_id})
        if not r:
            raise HTTPException(404)
        return with_narrative(conn, r["body"])

    @api.post("/v1/reports/{report_id}/narrative")
    def regenerate_narrative(report_id: int, conn=Depends(db)):
        """Explicit request: regenerate the narrative for this revision (counts against the daily budget)."""
        r = one(conn.report, {"id": report_id})
        if not r:
            raise HTTPException(404)
        return nv.generate(conn, r["body"], ai_config(conn), provider=narrative_provider, force=True)

    @api.get("/v1/activities")
    def list_activities(start: str | None = Query(default=None, alias="from"), end: str | None = Query(default=None, alias="to"), conn=Depends(db)):
        try:
            for v in (start, end):
                if v:
                    parse_day(v, conn)
        except ValueError as e:
            raise HTTPException(422, str(e))
        end = end or today(conn).isoformat()
        start = start or (date.fromisoformat(end) - timedelta(days=cfg.backfill_days)).isoformat()
        rows = many(conn.activity, {"source": cfg.source, "local_date": {"$gte": start, "$lte": end}}, sort=[("start_utc", -1)])
        return [{k: r[k] for k in ("source_id", "sport", "name", "start_utc", "utc_offset_s", "local_date", "distance_m",
                                   "elapsed_s", "moving_s", "avg_hr", "elevation_gain_m")} |
                {"pace_moving_s_per_km": rp.rn.moving_pace(r["distance_m"], r["moving_s"]), "synthetic": synthetic} for r in rows]

    @api.get("/v1/activities/{sid}")
    def get_activity(sid: str, conn=Depends(db)):
        a = rp.activity_by_source_id(conn, cfg.source, sid)
        if not a:
            raise HTTPException(404)
        with report_lock(conn):
            report = rp.build_post_run(conn, cfg.source, sid, synthetic)
        s = rp.samples_for(conn, a["id"])
        from . import run_checks
        body = with_narrative(conn, report)
        if body is not None:
            body["checks"] = run_checks.build(conn, cfg.source, body)
        return {"report": body, "chart": downsample(s) if s else None}

    run_ai_inflight: set[tuple] = set()

    def auto_run_ai(conn, sids: list[str]) -> None:
        """New runs from the last 36 hours get AI input right after a sync, in the background, with the server's key."""
        from . import run_ai
        ai = ai_config(conn)
        if not sids or not ai.enabled or not (ai.api_key or run_ai_provider):
            return
        name = conn.name

        def work():
            c = connect(name)
            run_ai.auto(c, cfg.source, sids, today(c), ai.model, ai.api_key, ai.max_calls_per_day, provider=run_ai_provider,
                        on_start=lambda sid: run_ai_inflight.add((name, sid)), on_done=lambda sid: run_ai_inflight.discard((name, sid)))
        threading.Thread(target=work, daemon=True).start()

    def run_ai_bg(db_name: str, sid: str, b, model: str, key: str, key_source: str, budget: int) -> None:
        from . import run_ai
        c = connect(db_name)
        try:
            run_ai.generate(c, cfg.source, sid, b, model, key, key_source, budget, provider=run_ai_provider)
        except Exception:
            log.exception("run AI generation failed")
        finally:
            run_ai_inflight.discard((db_name, sid))

    def run_ai_state(conn, sid: str, x_openai_key: str | None, start: bool) -> dict:
        """AI input on one run. Generated only on request (start=True); afterwards served from the cache while the run's
        data is unchanged. A user's own key is used for that call only and never stored."""
        from . import run_ai
        ai = ai_config(conn, x_openai_key)
        if not ai.enabled:
            return {"status": "disabled"}
        key = (x_openai_key or "").strip() or ai.api_key
        if not key and run_ai_provider is None:
            return {"status": "not_configured"}
        try:
            b = run_ai.bundle(conn, cfg.source, sid, today(conn))
        except run_ai.NotFound:
            raise HTTPException(404)
        hit = run_ai.latest(conn, sid, run_ai.input_hash(b, ai.model))
        if hit and hit["status"] == "ok":
            return run_ai.view(hit)
        if (conn.name, sid) in run_ai_inflight:
            return {"status": "pending"}  # a retry in progress, not the earlier failure
        if hit and not start:
            return run_ai.view(hit)
        if not start:
            prev = run_ai.latest(conn, sid)
            # Stale only when you changed what the run was meant to be after the input was written (the bundle also
            # changes daily with today's advice, which isn't a reason to rewrite it)
            intent = one(conn.run_intent, {"activity_source_id": sid})
            stale = bool(prev and intent and (intent.get("client_updated_at") or "") > prev["created_at"])
            return {"status": "none", "previous": run_ai.view(prev) if prev and prev["status"] == "ok" else None, "stale": stale}
        run_ai_inflight.add((conn.name, sid))
        threading.Thread(target=run_ai_bg, args=(conn.name, sid, b, ai.model, key, "user" if (x_openai_key or "").strip() else "server", ai.max_calls_per_day),
                         daemon=True).start()
        return {"status": "pending"}

    @api.get("/v1/activities/{sid}/export.md")
    def export_run(sid: str, v: str | None = Query(default=None, max_length=20), conn=Depends(db)):
        """The run as one Markdown file for reading or for a language model (Runner Sidekick LLM Export v2). `v`: the app's
        version, written into the file."""
        from fastapi.responses import PlainTextResponse
        from . import run_export
        out = run_export.markdown(conn, cfg.source, sid, app_version=v, now=datetime.now(tz(conn)))
        if out is None:
            raise HTTPException(404)
        name, text = out
        return PlainTextResponse(text, media_type="text/markdown; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @api.get("/v1/activities/{sid}/ai")
    def get_run_ai(sid: str, conn=Depends(db), x_openai_key: str | None = Header(default=None)):
        return run_ai_state(conn, sid, x_openai_key, start=False)

    @api.post("/v1/activities/{sid}/ai")
    def post_run_ai(sid: str, conn=Depends(db), x_openai_key: str | None = Header(default=None)):
        return run_ai_state(conn, sid, x_openai_key, start=True)

    @api.put("/v1/activities/{sid}/effort")
    def put_effort(sid: str, body: EffortIn, conn=Depends(db)):
        put_if_newer(conn.activity_effort, {"activity_source_id": sid}, {"rpe": body.rpe, "client_updated_at": body.client_updated_at})
        return {"ok": True}

    @api.put("/v1/checkins/{cid}")
    def put_checkin(cid: str, body: CheckinIn, conn=Depends(db)):
        """Last-writer-wins on client_updated_at; a stale write is ignored and the stored version returned."""
        put_if_newer(conn.checkin, {"id": cid}, {"local_date": body.local_date, "energy": body.energy, "soreness": body.soreness,
                                                 "recovery": body.recovery, "pain": body.pain, "illness": body.illness, "notes": body.notes,
                                                 "tags": body.tags, "client_updated_at": body.client_updated_at, "received_at": utc_now(),
                                                 "deleted": body.deleted})
        return one(conn.checkin, {"id": cid})

    @api.get("/v1/checkins")
    def list_checkins(start: str | None = Query(default=None, alias="from"), end: str | None = Query(default=None, alias="to"), conn=Depends(db)):
        return many(conn.checkin, {"local_date": {"$gte": start or "0000", "$lte": end or "9999"}}, sort=[("local_date", -1)])

    @api.get("/v1/settings")
    def get_settings(conn=Depends(db)):
        return {"timezone": str(tz(conn)), "timezone_set": rp.get_setting(conn, "timezone", None) is not None, "running_days": rp.get_setting(conn, "running_days", [0, 2, 4, 5]),
                "goal": rp.get_setting(conn, "goal", None), "available_minutes": rp.get_setting(conn, "available_minutes", None),
                "hr_zone_source": rp.get_setting(conn, "hr_zone_source", "garmin"),
                "goal_type": rp.get_setting(conn, "goal_type", None),
                "ai_enabled": rp.get_setting(conn, "ai_enabled", False),
                "weather_enabled": rp.get_setting(conn, "weather_enabled", True),
                "ai_model": rp.get_setting(conn, "ai_model", nv.DEFAULT_MODEL),
                "ai_models": sorted(nv.server_models()),  # what the server's key may run; your own key may use any
                "ai_available": bool(os.getenv("OPENAI_API_KEY") or secrets(cfg.data_dir).get("openai_api_key")) or narrative_provider is not None,
                "morning_window_start": rp.get_setting(conn, "morning_window_start", "06:00"),
                "morning_window_end": rp.get_setting(conn, "morning_window_end", "10:00"),
                "profile_sex": rp.get_setting(conn, "profile_sex", None),
                "profile_birth_date": rp.get_setting(conn, "profile_birth_date", None),
                "profile_detected": rp.get_setting(conn, "source_profile", None),
                **{k: rp.get_setting(conn, k, None) for k in ("race_date", "race_distance", "race_target_s", "race_name", "week_start_day")},
                "week_start_effective": WEEKDAYS[rp.first_weekday(conn)]}

    @api.put("/v1/settings")
    def put_settings(body: SettingsIn, conn=Depends(db)):
        if body.timezone is not None:
            try:
                ZoneInfo(body.timezone)
            except Exception:
                raise HTTPException(422, "unknown timezone")
        if body.running_days is not None and any(not 0 <= d <= 6 for d in body.running_days):
            raise HTTPException(422, "running_days are 0 (Mon) .. 6 (Sun)")
        for k in ("profile_birth_date", "race_date"):
            v = getattr(body, k)
            try:
                if v is not None:
                    date.fromisoformat(v)  # the pattern alone lets 2026-02-30 through, which would break Today
            except ValueError:
                raise HTTPException(422, f"{k} is not a real date")
        for k, v in body.model_dump(exclude_unset=True).items():
            if v is None:
                # An explicit null clears an optional setting; it never clears required ones
                if k in ("goal", "available_minutes", "goal_type", "profile_sex", "profile_birth_date", "race_date", "race_distance",
                         "race_target_s", "race_name", "week_start_day"):
                    conn.user_settings.delete_one({"key": k})
                continue
            set_setting(conn, k, v)
        return get_settings(conn)

    @api.delete("/v1/data")
    def delete_data(scope: Literal["raw", "reports", "all"], conn=Depends(db)):
        """raw: source payloads. reports: generated reports. all: everything incl. normalised records, check-ins and settings.
        Garmin tokens are not touched (use `python -m sidekick garmin-logout`)."""
        tables = {"raw": ["raw_payload"], "reports": ["report", "narrative", "coach_analysis", "section_summary", "run_ai"],
                  "all": ["raw_payload", "report", "narrative", "coach_analysis", "section_summary", "run_ai", "run_weather", "ai_call", "day_plan", "run_intent", "weekly_focus", "insight_state", "activity_samples", "activity_lap", "activity", "daily_observation",
                          "sleep_session", "checkin", "activity_effort", "sync_checkpoint", "sync_job", "user_settings"]}[scope]
        for t in tables:
            conn[t].delete_many({})
        return {"deleted": tables}

    @api.get("/v1/export")
    def export(conn=Depends(db)):
        out = {}
        for t in ("daily_observation", "sleep_session", "activity", "activity_lap", "checkin", "activity_effort", "user_settings",
                  "day_plan", "run_intent", "weekly_focus", "insight_state", "narrative", "coach_analysis", "section_summary", "run_ai"):
            out[t] = many(conn[t])
        out["activity_samples"] = many(conn.activity_samples)
        out["reports"] = [r["body"] for r in many(conn.report)]
        return {"mode": cfg.source, "synthetic": synthetic, "exported_at": utc_now(), "data": out}

    # ---------------------------------------------------------------- sign-in (public)

    @app.post("/v1/auth/google")
    def auth_google(body: GoogleSignIn):
        """Exchange a Google ID token for an app token. Invite-only: new accounts need an invite for their email."""
        claims = google_verifier(body.id_token)
        a = accounts.app_db()
        try:
            u = accounts.sign_in_with_google(a, claims)
        except accounts.NotInvited as e:
            raise HTTPException(403, str(e))
        token = accounts.create_session(a, u["id"], body.device_name)
        return {"token": token, "user": {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"]}}

    # ---------------------------------------------------------------- official Garmin connection

    @api.post("/v1/garmin/oauth/start")
    def garmin_start(user=Depends(current_user)):
        sec = secrets(cfg.data_dir)
        try:
            return {"authorize_url": goauth.start(accounts.app_db(), user["id"], sec.get("garmin_client_id"), GARMIN_REDIRECT_URI)}
        except goauth.NotConfigured as e:
            raise HTTPException(503, str(e))

    def oauth_page(title, msg):
        return HTMLResponse(f"<!doctype html><meta name=viewport content='width=device-width'><title>{title}</title>"
                            f"<body style='font-family:system-ui;padding:32px;max-width:520px;margin:auto'><h2>{title}</h2>"
                            f"<p>{msg}</p><p>You can close this page and return to Runner Sidekick.</p></body>")

    @app.get("/v1/garmin/oauth/callback", response_class=HTMLResponse)
    def garmin_callback(state: str = "", code: str = "", error: str = ""):
        """Garmin's redirect: nothing is linked here. The page hands the answer to the app, which finishes the linking
        signed in as the user who started it."""
        from html import escape
        from urllib.parse import urlencode
        if error or not code or not state:
            return oauth_page("Garmin not connected", "The connection was cancelled or Garmin returned an error.")
        link = escape(goauth.APP_RETURN + "?" + urlencode({"state": state, "code": code}))
        return HTMLResponse(f"<!doctype html><meta name=viewport content='width=device-width'><title>Finish in the app</title>"
                            f"<meta http-equiv=refresh content='0;url={link}'>"
                            f"<body style='font-family:system-ui;padding:32px;max-width:520px;margin:auto'><h2>Almost done</h2>"
                            f"<p><a href='{link}'>Open Runner Sidekick</a> to finish connecting Garmin.</p></body>")

    @api.post("/v1/garmin/oauth/complete")
    def garmin_complete(body: GarminCompleteIn, user=Depends(current_user)):
        sec = secrets(cfg.data_dir)
        try:
            goauth.complete(accounts.app_db(), body.state, body.code, sec.get("garmin_client_id", ""), sec.get("garmin_client_secret", ""),
                            GARMIN_REDIRECT_URI, lambda uid: accounts.user_dir(cfg.data_dir, uid), user_id=user["id"],
                            linked_elsewhere=lambda g, uid: any(u != uid for u in goauth.linked_users(cfg.data_dir / "users", g)))
        except goauth.OAuthError as e:
            raise HTTPException(409, str(e))
        return {"connected": True}

    @api.post("/v1/garmin/ticket")
    def garmin_ticket(body: GarminTicketIn, conn=Depends(db), user=Depends(current_user)):
        """Connects Garmin from the app's sign-in page: exchanges its one-time ticket, then starts the first sync."""
        if synthetic:
            raise HTTPException(409, "This server uses demo data; there's no Garmin to connect.")
        ucfg = user_cfg(user)
        # The Garmin account this user's data came from (kept with the data, so a disconnect doesn't forget it; deleting
        # everything does, which is how to switch accounts)
        expected = rp.get_setting(conn, "garmin_profile_id", None) or garmin_link.profile_of(ucfg.garmin_token_dir)
        try:
            got = garmin_link.link(ucfg.garmin_token_dir, body.ticket, cfg.data_dir / "users", user["id"], expected_profile=expected)
        except garmin_link.LinkError as e:
            raise HTTPException(409, str(e))
        set_setting(conn, "garmin_profile_id", got["profile_id"])
        from .sync import mark_reconnected
        mark_reconnected(conn, cfg.source)  # a "connect again" state would otherwise stop the sync before it tries the new tokens
        if user["id"] not in running:
            threading.Thread(target=do_sync, args=(ucfg, user["id"]), daemon=True).start()
        return {"connected": True}

    @api.delete("/v1/garmin/connection")
    def garmin_disconnect(user=Depends(current_user)):
        sec = secrets(cfg.data_dir)
        official = goauth.disconnect(user_cfg(user).data_dir, sec.get("garmin_client_id"), sec.get("garmin_client_secret"))
        return {"disconnected": garmin_link.unlink(user_cfg(user).garmin_token_dir) or official}

    @api.post("/v1/auth/logout")
    def logout(user=Depends(current_user)):
        """Ends this device's sign-in on the server (its token stops working)."""
        accounts.app_db().sessions.update_one({"id": user["session_id"]}, {"$set": {"revoked_at": utc_now()}})
        return {"signed_out": True}

    @api.get("/v1/me")
    def me(user=Depends(current_user)):
        return {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}

    @api.delete("/v1/account")
    def delete_account(user=Depends(current_user)):
        """Deletes all of this user's data and sessions. The owner account can't delete itself from the app."""
        if user["role"] == accounts.OWNER_ROLE:
            raise HTTPException(409, "the owner account can't be deleted from the app")
        sec = secrets(cfg.data_dir)
        goauth.disconnect(user_cfg(user).data_dir, sec.get("garmin_client_id"), sec.get("garmin_client_secret"))  # Garmin requires it
        accounts.delete_user(accounts.app_db(), cfg.data_dir, user["id"])
        return {"deleted": True}

    app.include_router(api)
    app.state.do_sync = do_sync
    return app

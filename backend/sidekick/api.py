"""HTTP API for the Android client. Every route requires a device bearer token."""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

import os

from . import narrative as nv
from . import reports as rp
from .auth import verify_token
from .config import SOURCE_FIXTURE, Config
from .connectors.base import Samples
from .connectors.fixture import FixtureConnector
from .connectors.garmin import GarminConnector
from .db import connect, utc_now
from .sync import get_connection_row, run_sync

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


class SettingsIn(BaseModel):
    timezone: str | None = None
    running_days: list[int] | None = Field(default=None, max_length=7)
    goal: str | None = Field(default=None, max_length=200)
    available_minutes: int | None = Field(default=None, ge=0, le=600)
    hr_zone_source: Literal["garmin", "none"] | None = None
    ai_enabled: bool | None = None
    ai_model: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:\-]{1,64}$")
    morning_window_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    morning_window_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


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


def create_app(cfg: Config, connector=None, narrative_provider=None) -> FastAPI:
    def db():
        c = connect(cfg.db_path)
        try:
            yield c
        finally:
            c.close()

    connect(cfg.db_path).close()  # apply migrations at startup
    lock = threading.Lock()
    synthetic = cfg.source == SOURCE_FIXTURE
    state = {"running": False}

    def tz(conn) -> ZoneInfo:
        return ZoneInfo(rp.get_setting(conn, "timezone", cfg.timezone))

    def today(conn) -> date:
        return datetime.now(tz(conn)).date()

    def make_connector(conn):
        if connector is not None:
            return connector
        if synthetic:
            return FixtureConnector(anchor=today(conn), tz=str(tz(conn)))
        return GarminConnector(cfg.garmin_token_dir, cfg.request_spacing_s)

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not authorization.startswith("Bearer ") or not verify_token(cfg.data_dir, authorization[7:]):
            raise HTTPException(status_code=401, detail="invalid or missing device token")

    # No interactive docs or schema endpoint: they'd be the only unauthenticated routes.
    app = FastAPI(title="Runner Sidekick", dependencies=[Depends(require_token)], docs_url=None, redoc_url=None, openapi_url=None)

    def do_sync(force: bool = False) -> dict:
        with lock:
            state["running"] = True
            conn = connect(cfg.db_path)
            try:
                c = make_connector(conn)
                res = run_sync(conn, c, today(conn), cfg.backfill_days, cfg.refetch_days, cfg.raw_retention_days, force=force)
                with lock_reports:
                    rp.regenerate(conn, c.source, synthetic, res.changed_dates, res.changed_activities, today(conn))
                return {"outcome": res.outcome, "detail": res.detail, "days_fetched": res.days_fetched,
                        "activities_fetched": res.activities_fetched}
            except Exception:
                log.exception("sync failed")
                raise
            finally:
                conn.close()
                state["running"] = False

    lock_reports = threading.RLock()
    inflight: set[tuple] = set()

    def ai_config(conn) -> nv.AiConfig:
        return nv.AiConfig(
            enabled=bool(rp.get_setting(conn, "ai_enabled", False)),
            model=rp.get_setting(conn, "ai_model", nv.DEFAULT_MODEL),
            api_key=os.getenv("OPENAI_API_KEY"),
            max_calls_per_day=int(os.getenv("RSK_AI_MAX_CALLS_PER_DAY", "20")),
        )

    def generate_bg(body: dict, key: tuple) -> None:
        c = connect(cfg.db_path)
        try:
            nv.generate(c, body, ai_config(c), provider=narrative_provider)
        finally:
            c.close()
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
        hit = nv.cached(conn, body, ai.model)
        if hit:
            body["narrative"] = nv.view(hit)
        elif not ai.api_key and narrative_provider is None:
            body["narrative"] = {"status": "not_configured", "detail": "OPENAI_API_KEY is not set on the backend"}
        else:
            key = (body["type"], body["id"], ai.model)
            if key not in inflight:
                inflight.add(key)
                threading.Thread(target=generate_bg, args=(body, key), daemon=True).start()
            body["narrative"] = {"status": "pending"}
        return body

    @app.get("/v1/status")
    def status(conn=Depends(db)):
        row = get_connection_row(conn, cfg.source)
        latest = conn.execute("SELECT MAX(local_date) d FROM daily_observation WHERE source=? AND state='measured'", (cfg.source,)).fetchone()["d"]
        latest_act = conn.execute("SELECT MAX(start_utc) s FROM activity WHERE source=?", (cfg.source,)).fetchone()["s"]
        cps = {r["stream"]: dict(r) for r in conn.execute("SELECT * FROM sync_checkpoint WHERE source=?", (cfg.source,))}
        job = conn.execute("SELECT * FROM sync_job WHERE source=? ORDER BY id DESC LIMIT 1", (cfg.source,)).fetchone()
        return {
            "mode": cfg.source, "synthetic": synthetic, "today": today(conn).isoformat(), "timezone": str(tz(conn)),
            "connection": {k: row[k] for k in ("state", "detail", "last_attempt_at", "last_success_at", "retry_not_before")} if row else
            {"state": make_connector(conn).connection_state().value, "detail": None, "last_attempt_at": None, "last_success_at": None, "retry_not_before": None},
            "latest_observation_date": latest, "latest_activity_start": latest_act,
            "watch_sync_time": None,  # not exposed by the source; never guessed
            "backfill": cps.get("days"), "sync_running": state["running"],
            "last_job": dict(job) if job else None,
            "capabilities": json.loads(row["capabilities_json"]) if row else {},
        }

    @app.post("/v1/sync", status_code=202)
    def sync_now(conn=Depends(db)):
        if state["running"]:
            return {"started": False, "detail": "sync already running"}
        threading.Thread(target=do_sync, daemon=True).start()
        return {"started": True}

    @app.get("/v1/today")
    def today_report(day: str | None = Query(default=None, alias="date"), conn=Depends(db)):
        d = date.fromisoformat(day) if day else today(conn)
        with lock_reports:
            body = rp.build_morning(conn, cfg.source, d, synthetic)
        return with_narrative(conn, body)

    @app.get("/v1/trends")
    def get_trends(days: Literal[7, 28, 90] = 28, conn=Depends(db)):
        from .trends import build_trends
        return build_trends(conn, cfg.source, today(conn), days, synthetic)

    @app.get("/v1/weekly/latest")
    def latest_weekly(conn=Depends(db)):
        from .weekly import regenerate_weeklies
        with lock_reports:
            regenerate_weeklies(conn, cfg.source, today(conn), synthetic)
        r = conn.execute("SELECT body_json FROM report WHERE type='weekly' ORDER BY subject_key DESC, revision DESC LIMIT 1").fetchone()
        if not r:
            raise HTTPException(404, "no completed week yet")
        return with_narrative(conn, json.loads(r["body_json"]))

    @app.get("/v1/reports/{rtype}/{key}/revisions")
    def revisions(rtype: str, key: str, conn=Depends(db)):
        """All stored revisions of one report, newest first, so earlier versions stay browsable."""
        return [{"id": r["id"], "revision": r["revision"], "generated_at": r["generated_at"], "data_cutoff": r["data_cutoff"],
                 "algorithm_version": json.loads(r["algorithm_version"])}
                for r in conn.execute("SELECT id, revision, generated_at, data_cutoff, algorithm_version FROM report"
                                      " WHERE type=? AND subject_key=? ORDER BY revision DESC", (rtype, key))]

    @app.get("/v1/insights")
    def get_insights(conn=Depends(db)):
        with lock_reports:
            return rp.build_insights(conn, cfg.source, today(conn), synthetic)

    @app.get("/v1/reports")
    def list_reports(type: str | None = None, start: str | None = Query(default=None, alias="from"),
                     end: str | None = Query(default=None, alias="to"), limit: int = Query(default=60, le=500), conn=Depends(db)):
        q = ("SELECT r.id, r.type, r.subject_key, r.local_date, r.revision, r.generated_at, r.body_json FROM report r"
             " WHERE r.revision = (SELECT MAX(revision) FROM report x WHERE x.type=r.type AND x.subject_key=r.subject_key)")
        args: list = []
        if type:
            q += " AND r.type=?"; args.append(type)
        if start:
            q += " AND r.local_date>=?"; args.append(start)
        if end:
            q += " AND r.local_date<=?"; args.append(end)
        q += " ORDER BY r.local_date DESC, r.id DESC LIMIT ?"; args.append(limit)
        out = []
        for r in conn.execute(q, args):
            b = json.loads(r["body_json"])
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

    @app.get("/v1/reports/{report_id}")
    def get_report(report_id: int, conn=Depends(db)):
        r = conn.execute("SELECT body_json FROM report WHERE id=?", (report_id,)).fetchone()
        if not r:
            raise HTTPException(404)
        return with_narrative(conn, json.loads(r["body_json"]))

    @app.post("/v1/reports/{report_id}/narrative")
    def regenerate_narrative(report_id: int, conn=Depends(db)):
        """Explicit request: regenerate the narrative for this revision (counts against the daily budget)."""
        r = conn.execute("SELECT body_json FROM report WHERE id=?", (report_id,)).fetchone()
        if not r:
            raise HTTPException(404)
        return nv.generate(conn, json.loads(r["body_json"]), ai_config(conn), provider=narrative_provider, force=True)

    @app.get("/v1/activities")
    def list_activities(start: str | None = Query(default=None, alias="from"), end: str | None = Query(default=None, alias="to"), conn=Depends(db)):
        end = end or today(conn).isoformat()
        start = start or (date.fromisoformat(end) - timedelta(days=cfg.backfill_days)).isoformat()
        rows = conn.execute("SELECT * FROM activity WHERE source=? AND local_date BETWEEN ? AND ? ORDER BY start_utc DESC",
                            (cfg.source, start, end)).fetchall()
        return [{k: r[k] for k in ("source_id", "sport", "name", "start_utc", "utc_offset_s", "local_date", "distance_m",
                                   "elapsed_s", "moving_s", "avg_hr", "elevation_gain_m")} |
                {"pace_moving_s_per_km": rp.rn.moving_pace(r["distance_m"], r["moving_s"]), "synthetic": synthetic} for r in rows]

    @app.get("/v1/activities/{sid}")
    def get_activity(sid: str, conn=Depends(db)):
        a = rp.activity_by_source_id(conn, cfg.source, sid)
        if not a:
            raise HTTPException(404)
        with lock_reports:
            report = rp.build_post_run(conn, cfg.source, sid, synthetic)
        s = rp.samples_for(conn, a["id"])
        return {"report": with_narrative(conn, report), "chart": downsample(s) if s else None}

    @app.put("/v1/activities/{sid}/effort")
    def put_effort(sid: str, body: EffortIn, conn=Depends(db)):
        with conn:
            conn.execute("INSERT INTO activity_effort VALUES (?,?,?) ON CONFLICT (activity_source_id) DO UPDATE SET"
                         " rpe=excluded.rpe, client_updated_at=excluded.client_updated_at WHERE excluded.client_updated_at > activity_effort.client_updated_at",
                         (sid, body.rpe, body.client_updated_at))
        return {"ok": True}

    @app.put("/v1/checkins/{cid}")
    def put_checkin(cid: str, body: CheckinIn, conn=Depends(db)):
        """Last-writer-wins on client_updated_at; a stale write is ignored and the stored version returned."""
        with conn:
            conn.execute(
                "INSERT INTO checkin (id, local_date, energy, soreness, recovery, pain, illness, notes, tags_json, client_updated_at, received_at, deleted)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT (id) DO UPDATE SET local_date=excluded.local_date, energy=excluded.energy,"
                " soreness=excluded.soreness, recovery=excluded.recovery, pain=excluded.pain, illness=excluded.illness, notes=excluded.notes,"
                " tags_json=excluded.tags_json, client_updated_at=excluded.client_updated_at, received_at=excluded.received_at, deleted=excluded.deleted"
                " WHERE excluded.client_updated_at > checkin.client_updated_at",
                (cid, body.local_date, body.energy, body.soreness, body.recovery, int(body.pain), int(body.illness), body.notes,
                 json.dumps(body.tags), body.client_updated_at, utc_now(), int(body.deleted)))
        r = dict(conn.execute("SELECT * FROM checkin WHERE id=?", (cid,)).fetchone())
        r["tags"] = json.loads(r.pop("tags_json"))
        r["pain"], r["illness"], r["deleted"] = bool(r["pain"]), bool(r["illness"]), bool(r["deleted"])
        return r

    @app.get("/v1/checkins")
    def list_checkins(start: str | None = Query(default=None, alias="from"), end: str | None = Query(default=None, alias="to"), conn=Depends(db)):
        rows = conn.execute("SELECT * FROM checkin WHERE local_date BETWEEN ? AND ? ORDER BY local_date DESC",
                            (start or "0000", end or "9999")).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d.pop("tags_json"))
            d["pain"], d["illness"], d["deleted"] = bool(d["pain"]), bool(d["illness"]), bool(d["deleted"])
            out.append(d)
        return out

    @app.get("/v1/settings")
    def get_settings(conn=Depends(db)):
        return {"timezone": str(tz(conn)), "running_days": rp.get_setting(conn, "running_days", [0, 2, 4, 5]),
                "goal": rp.get_setting(conn, "goal", None), "available_minutes": rp.get_setting(conn, "available_minutes", None),
                "hr_zone_source": rp.get_setting(conn, "hr_zone_source", "garmin"),
                "ai_enabled": rp.get_setting(conn, "ai_enabled", False),
                "ai_model": rp.get_setting(conn, "ai_model", nv.DEFAULT_MODEL),
                "ai_available": bool(os.getenv("OPENAI_API_KEY")) or narrative_provider is not None,
                "morning_window_start": rp.get_setting(conn, "morning_window_start", "06:00"),
                "morning_window_end": rp.get_setting(conn, "morning_window_end", "10:00")}

    @app.put("/v1/settings")
    def put_settings(body: SettingsIn, conn=Depends(db)):
        if body.timezone is not None:
            try:
                ZoneInfo(body.timezone)
            except Exception:
                raise HTTPException(422, "unknown timezone")
        if body.running_days is not None and any(not 0 <= d <= 6 for d in body.running_days):
            raise HTTPException(422, "running_days are 0 (Mon) .. 6 (Sun)")
        with conn:
            for k, v in body.model_dump(exclude_none=True).items():
                conn.execute("INSERT INTO user_settings VALUES (?,?) ON CONFLICT (key) DO UPDATE SET value_json=excluded.value_json",
                             (k, json.dumps(v)))
        return get_settings(conn)

    @app.delete("/v1/data")
    def delete_data(scope: Literal["raw", "reports", "all"], conn=Depends(db)):
        """raw: source payloads. reports: generated reports. all: everything incl. normalised records, check-ins and settings.
        Garmin tokens are not touched (use `python -m sidekick garmin-logout`)."""
        tables = {"raw": ["raw_payload"], "reports": ["report", "narrative"],
                  "all": ["raw_payload", "report", "narrative", "activity_samples", "activity_lap", "activity", "daily_observation",
                          "sleep_session", "checkin", "activity_effort", "sync_checkpoint", "sync_job", "user_settings"]}[scope]
        with conn:
            for t in tables:
                conn.execute(f"DELETE FROM {t}")
        conn.execute("VACUUM")
        return {"deleted": tables}

    @app.get("/v1/export")
    def export(conn=Depends(db)):
        out = {}
        for t in ("daily_observation", "sleep_session", "activity", "activity_lap", "checkin", "activity_effort", "user_settings"):
            out[t] = [dict(r) for r in conn.execute(f"SELECT * FROM {t}")]
        out["reports"] = [json.loads(r["body_json"]) for r in conn.execute("SELECT body_json FROM report")]
        return {"mode": cfg.source, "synthetic": synthetic, "exported_at": utc_now(), "data": out}

    app.state.do_sync = do_sync
    return app

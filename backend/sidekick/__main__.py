"""Admin CLI. Run from backend/:  .venv/bin/python -m sidekick <command>

  garmin-login           interactive Garmin login (hidden password prompt); stores tokens, never the password
  garmin-logout          delete stored Garmin tokens
  create-token NAME      create an app token (printed once). Users who sign in with Google get theirs automatically
  revoke-token NAME
  sync [--loop]          sync every connected user (+ report regeneration); --loop repeats until backfill completes
  invite add|remove|list EMAIL   invite-only access: who may sign in with Google
  users [list]           list accounts
  users disable|enable EMAIL|ID   a disabled account's sign-ins end, it can't sign in and isn't synced; data kept
  users delete EMAIL|ID --yes     delete an account and all its data (can't be undone)
  set-owner-email EMAIL  let the owner sign in with Google as this address
  (most commands take --user ID; the default is the owner)
  rebuild-reports        regenerate reports after an algorithm change (new revisions; old ones kept)
  audit [--out PATH]     field-coverage audit of stored data (no values, no credentials)
  serve [--host --port]  run the API (default 127.0.0.1:8765)
  migrate-sqlite [--replace]  one-time import of the old SQLite files into MongoDB (the files are left untouched)

No configuration needed: records live in the local MongoDB, secrets and Garmin tokens in <repo>/data, and the source
is Garmin. (Overrides for tests/demo only: RSK_SOURCE=fixture, RSK_DATA_DIR=..., RSK_MONGO_URI=..., RSK_DB_PREFIX=...)
"""

from __future__ import annotations

import argparse
import getpass
import logging
import shutil
import sys
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from . import reports as rp
from dataclasses import replace

from . import accounts
from .auth import create_token, revoke_token
from .config import SOURCE_FIXTURE, SOURCE_GARMIN, load_config
from .connectors.fixture import FixtureConnector
from .connectors.garmin import GarminConnector
from .db import connect, many, one
from .sync import mark_reconnected, run_sync


class RedactFilter(logging.Filter):
    """Belt and braces: drop log records that look like they carry secrets."""
    MARKERS = ("password", "token", "authorization", "cookie", "ticket")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage().lower()
        return not any(m in msg for m in self.MARKERS)


def setup_logging() -> None:
    h = logging.StreamHandler()
    h.addFilter(RedactFilter())
    logging.basicConfig(level=logging.INFO, handlers=[h], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("garminconnect").setLevel(logging.WARNING)


def cmd_garmin_login(cfg) -> int:
    from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (hidden): ")
    api = Garmin(email=email, password=password, prompt_mfa=lambda: input("MFA code: ").strip())
    del password
    try:
        api.login(tokenstore=str(cfg.garmin_token_dir))
    except GarminConnectTooManyRequestsError:
        print("Garmin is rate-limiting logins. Wait a while before retrying; repeated attempts can lock the account.")
        return 2
    except GarminConnectAuthenticationError as e:
        print(f"Login failed: {str(e).splitlines()[0]}")
        return 1
    if not (cfg.garmin_token_dir / "garmin_tokens.json").exists():
        print("Login succeeded but tokens were not written; check permissions on", cfg.garmin_token_dir)
        return 1
    mark_reconnected(connect(replace(cfg, source=SOURCE_GARMIN).db_name), SOURCE_GARMIN)
    print(f"Connected as {api.get_full_name() or 'Garmin user'}. Tokens stored in {cfg.garmin_token_dir} (0600).")
    return 0


def make_connector(cfg, conn):
    tz = rp.get_setting(conn, "timezone", cfg.timezone)
    today = datetime.now(ZoneInfo(tz)).date()
    if cfg.source == SOURCE_FIXTURE:
        return FixtureConnector(anchor=today, tz=tz), today
    return GarminConnector(cfg.garmin_token_dir, cfg.request_spacing_s), today


def auto_run_ai(cfg, conn, source: str, sids: list[str], today) -> None:
    """AI input for new runs of the last 36 hours, with the server's key (see run_ai.auto)."""
    import os

    from . import narrative as nv
    from . import run_ai
    from .config import secrets
    key = os.getenv("OPENAI_API_KEY") or secrets(cfg.data_dir).get("openai_api_key")
    if sids and key and rp.get_setting(conn, "ai_enabled", False):
        wrote = run_ai.auto(conn, source, sids, today, nv.server_model(rp.get_setting(conn, "ai_model", nv.DEFAULT_MODEL)), key,
                            int(os.getenv("RSK_AI_MAX_CALLS_PER_DAY", "25")))
        if wrote:
            print(f"AI input written for {len(wrote)} new run(s)")


def cmd_sync(cfg, loop: bool) -> int:
    conn = connect(cfg.db_name)
    while True:
        c, today = make_connector(cfg, conn)
        res = run_sync(conn, c, today, cfg.backfill_days, cfg.refetch_days, cfg.raw_retention_days)
        if not c.synthetic:
            from . import weather
            res.changed_activities = list(dict.fromkeys(res.changed_activities + weather.for_new_runs(conn, c.source, res.changed_activities)))
        rp.regenerate(conn, c.source, c.synthetic, res.changed_dates, res.changed_activities, today)
        auto_run_ai(cfg, conn, c.source, res.changed_activities, today)
        cp = one(conn.sync_checkpoint, {"source": c.source, "stream": "days"})
        print(f"{res.outcome}: {res.days_fetched} days, {res.activities_fetched} activities fetched"
              + (f" — {res.detail}" if res.detail else "")
              + (f" | backfill at {cp['oldest_done']} (target {cp['backfill_target']})" if cp else ""))
        done = cp is not None and cp["oldest_done"] is not None and cp["oldest_done"] <= cp["backfill_target"]
        if not loop or res.outcome not in ("ok", "partial") or (done and res.outcome == "ok"):
            return 0 if res.outcome in ("ok", "partial") else 1


def cmd_audit(cfg, out: str | None) -> int:
    """Coverage matrix from stored normalised records plus key names seen in raw payloads (names only)."""
    conn = connect(cfg.db_name)
    src = {"source": cfg.source}
    lines = [f"# Data audit — source `{cfg.source}`" + (" (SYNTHETIC FIXTURE DATA)" if cfg.source == SOURCE_FIXTURE else ""), ""]
    days = sorted(conn.daily_observation.distinct("local_date", src))
    lines += [f"Generated {datetime.now().isoformat(timespec='minutes')}. Days fetched: {len(days)} "
              f"({days[0] if days else None} → {days[-1] if days else None}).", "",
              "## Daily metrics", "", "| Metric | Method | Measured days | Not measured | Coverage |", "|---|---|---|---|---|"]
    for r in conn.daily_observation.aggregate([{"$match": src}, {"$group": {
            "_id": "$metric", "methods": {"$addToSet": "$method"}, "n": {"$sum": 1},
            "m": {"$sum": {"$cond": [{"$eq": ["$state", "measured"]}, 1, 0]}}}}, {"$sort": {"_id": 1}}]):
        method = ",".join(sorted(x for x in r["methods"] if x)) or "—"
        lines.append(f"| {r['_id']} | {method} | {r['m']} | {r['n'] - r['m']} | {100 * r['m'] / r['n']:.0f}% |")
    acts = many(conn.activity, src)
    lines += ["", f"## Activities ({len(acts)})", "", "| Sport | Count |", "|---|---|"]
    for k, v in Counter(a["sport"] for a in acts).most_common():
        lines.append(f"| {k} | {v} |")
    runs = [a for a in acts if a["sport"] != "other"]
    if runs:
        ids = [a["id"] for a in runs]
        lines += ["", "### Run field presence", "", "| Field | Present |", "|---|---|"]
        for f in ("distance_m", "elapsed_s", "moving_s", "timer_s", "avg_hr", "max_hr", "elevation_gain_m", "avg_cadence_spm"):
            lines.append(f"| {f} | {sum(1 for a in runs if a[f] is not None)}/{len(runs)} |")
        lines.append(f"| laps | {len(conn.activity_lap.distinct('activity_id', {'activity_id': {'$in': ids}}))}/{len(runs)} |")
        sample_cov = Counter()
        n_s = 0
        for r in conn.activity_samples.find({"activity_id": {"$in": ids}}, {"_id": 0}):
            n_s += 1
            for k in ("hr", "speed", "dist", "elev", "cad"):
                if any(v is not None for v in r["samples"][k]):
                    sample_cov[k] += 1
        lines.append(f"| samples | {n_s}/{len(runs)} |")
        for k in ("hr", "speed", "dist", "elev", "cad"):
            lines.append(f"| samples.{k} | {sample_cov[k]}/{n_s} |")
        gm = Counter(k for a in runs for k in (a["garmin_metrics"] or {}))
        lines += ["", "### Garmin-generated activity metrics present", ""] + [f"- {k}: {v}/{len(runs)}" for k, v in gm.most_common()]
    lines += ["", "## Raw payload top-level keys (names only)", ""]
    for kind in sorted(conn.raw_payload.distinct("kind", src)):
        keys = Counter()
        n = 0
        for r in conn.raw_payload.find({**src, "kind": kind}, {"_id": 0, "payload": 1}, limit=30):
            p = r["payload"]
            n += 1
            if isinstance(p, dict):
                keys.update(p.keys())
            elif isinstance(p, list) and p and isinstance(p[0], dict):
                keys.update(p[0].keys())
        lines.append(f"- **{kind}** ({n} sampled): " + ", ".join(sorted(keys)) if keys else f"- **{kind}** ({n} sampled): empty/null")
    text = "\n".join(lines) + "\n"
    if out:
        with open(out, "w") as f:
            f.write(text)
        print(f"wrote {out}")
    else:
        print(text)
    return 0


def user_cfg(cfg, user_id: int | None):
    """Config pointed at one user's database and token folder (the owner when user_id is None)."""
    uid = user_id if user_id is not None else accounts.ensure_owner(accounts.app_db())["id"]
    return replace(cfg, data_dir=accounts.user_dir(cfg.data_dir, uid), user_id=uid), uid


def cmd_sync_all(cfg, loop: bool, only_user: int | None) -> int:
    users = [u["id"] for u in accounts.list_users(accounts.app_db()) if not u.get("disabled_at")] if only_user is None else [only_user]
    worst = 0
    for uid in users:
        ucfg, _ = user_cfg(cfg, uid)
        if cfg.source != SOURCE_FIXTURE and not (ucfg.garmin_token_dir / "garmin_tokens.json").exists():
            print(f"user {uid}: no Garmin connection, skipped")
            continue
        print(f"user {uid}:", end=" ")
        try:
            worst = max(worst, cmd_sync(ucfg, loop))
        except Exception as e:  # one user's failure never skips the users after them
            print(f"failed: {type(e).__name__}: {e}")
            worst = max(worst, 1)
    return worst


def main(argv=None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="sidekick")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def with_user(p):
        p.add_argument("--user", type=int, help="user id (default: the owner)")
        return p

    with_user(sub.add_parser("garmin-login"))
    with_user(sub.add_parser("garmin-logout"))
    with_user(sub.add_parser("create-token")).add_argument("name")
    with_user(sub.add_parser("revoke-token")).add_argument("name")
    p = with_user(sub.add_parser("sync", help="sync every connected user (or --user)")); p.add_argument("--loop", action="store_true")
    with_user(sub.add_parser("rebuild-reports"))
    with_user(sub.add_parser("backfill-intensity", help="intensity minutes from stored Garmin day summaries"))
    with_user(sub.add_parser("backfill-weather", help="Open-Meteo weather estimates for recent runs that have none"))
    with_user(sub.add_parser("backfill-samples", help="re-read run samples (e.g. running power) from stored Garmin details"))
    with_user(sub.add_parser("audit")).add_argument("--out")
    p = sub.add_parser("invite", help="invite-only access by Google email")
    p.add_argument("action", choices=["add", "remove", "list"]); p.add_argument("email", nargs="?")
    p = sub.add_parser("users", help="list, disable, enable or delete accounts")
    p.add_argument("action", nargs="?", default="list", choices=["list", "disable", "enable", "delete"])
    p.add_argument("who", nargs="?", help="email or user id"); p.add_argument("--yes", action="store_true")
    sub.add_parser("set-owner-email").add_argument("email")
    p = sub.add_parser("serve"); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8765)
    sub.add_parser("migrate-sqlite").add_argument("--replace", action="store_true", help="overwrite data already in MongoDB")
    args = ap.parse_args(argv)
    cfg = load_config()

    if args.cmd == "migrate-sqlite":
        from .migrate_sqlite import NotEmpty, migrate_all
        try:
            lines = migrate_all(cfg.data_dir, replace=args.replace)
        except NotEmpty as e:
            print(e); return 1
        print("\n".join(lines) or "No SQLite files found in " + str(cfg.data_dir))
        return 0
    if args.cmd in ("invite", "users", "set-owner-email"):
        a = accounts.app_db()
        if args.cmd == "users" and args.action == "list":
            for u in accounts.list_users(a):
                print(f"{u['id']:>3}  {u['role']:<6}  {u['email'] or '(no email yet)':<32}  {u['sessions']} active token(s)"
                      + ("  DISABLED" if u.get("disabled_at") else ""))
        elif args.cmd == "users":
            u = accounts.find_user(a, args.who or "")
            if u is None:
                print(f"no account {args.who!r} (see: users list)"); return 2
            label = f"user {u['id']} ({u['email'] or 'no email'})"
            try:
                if args.action == "delete":
                    if u["role"] == accounts.OWNER_ROLE:
                        print("the owner account can't be deleted"); return 2
                    if not args.yes:
                        print(f"This deletes {label} and all their data for good. Run again with --yes to do it."); return 2
                    accounts.delete_user(a, cfg.data_dir, u["id"])
                    print(f"Deleted {label}.")
                else:
                    accounts.set_disabled(a, u["id"], args.action == "disable")
                    print(f"{'Disabled' if args.action == 'disable' else 'Enabled'} {label}."
                          + (" Their sign-ins ended; their data is kept." if args.action == "disable" else " They can sign in again."))
            except ValueError as e:
                print(e); return 2
        elif args.cmd == "set-owner-email":
            accounts.set_owner_email(a, args.email)
            print(f"Owner can now sign in with Google as {accounts.normalise_email(args.email)}.")
        elif args.action == "list":
            for r in many(a.invites, sort=[("created_at", 1)]):
                print(f"{r['email']:<32}  {'used ' + r['used_at'] if r['used_at'] else 'not used yet'}")
        elif not args.email:
            print("email required"); return 2
        elif args.action == "add":
            accounts.add_invite(a, args.email)
            print(f"Invited {accounts.normalise_email(args.email)}. They can now sign in with Google in the app.")
        else:
            print(f"removed {accounts.remove_invite(a, args.email)} unused invite(s)")
        return 0
    if args.cmd == "sync":
        return cmd_sync_all(cfg, args.loop, args.user)
    if args.cmd == "serve":
        import uvicorn

        from .api import create_app
        if args.host not in ("127.0.0.1", "localhost", "::1"):
            print("Refusing to bind beyond loopback without TLS. See docs/SETUP.md for physical-device options.")
            return 2
        uvicorn.run(create_app(cfg), host=args.host, port=args.port, log_level="info")
        return 0

    ucfg, uid = user_cfg(cfg, args.user)
    if args.cmd == "garmin-login":
        return cmd_garmin_login(ucfg)
    if args.cmd == "garmin-logout":
        shutil.rmtree(ucfg.garmin_token_dir, ignore_errors=True)
        print("Garmin tokens deleted.")
        return 0
    if args.cmd == "create-token":
        token = create_token(cfg.data_dir, args.name, uid)
        print(f"\nDevice token for '{args.name}':\n\n    {token}\n\n"
              "Paste it into the app: Settings → Connection → Device token. It is shown only this once.")
        return 0
    if args.cmd == "revoke-token":
        print(f"revoked {revoke_token(cfg.data_dir, args.name, uid)} token(s) named {args.name!r}")
        return 0
    if args.cmd == "backfill-intensity":
        # Garmin's daily summaries are kept as raw payloads; the intensity minutes in them were not stored before
        from .connectors.base import DayBundle
        from .connectors.garmin import normalise_user_summary
        from .store import save_day
        conn = connect(ucfg.db_name)
        days = 0
        for r in conn.raw_payload.find({"kind": "user_summary"}):
            obs = [o for o in normalise_user_summary(r["source_key"], r["payload"]) if o.metric.startswith("intensity_minutes_")]
            if obs:
                save_day(conn, r["source"], DayBundle(local_date=r["source_key"], observations=obs))
                days += 1
        print(f"intensity minutes stored for {days} days")
        return 0
    if args.cmd == "backfill-samples":
        # Runs' sample streams from the stored raw details, and Garmin's per-run numbers from the stored summaries, with
        # fields added since they were first read (power, running dynamics)
        from datetime import datetime
        from .connectors.garmin import normalise_activity, normalise_samples
        from .db import utc_now
        conn = connect(ucfg.db_name)
        n = 0
        for raw in conn.raw_payload.find({"kind": "activity_details"}):
            a = conn.activity.find_one({"source_id": raw["source_key"]})
            if not a or not a.get("start_utc"):
                continue
            s = normalise_samples(raw["payload"], datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00")))
            if s is None:
                continue
            conn.activity_samples.update_one({"activity_id": a["id"]}, {"$set": {"samples": s.to_json()}}, upsert=True)
            summ = conn.raw_payload.find_one({"kind": "activity_summary", "source_key": raw["source_key"]})
            gm = normalise_activity(summ["payload"], None, None).garmin_metrics if summ else a.get("garmin_metrics")
            conn.activity.update_one({"id": a["id"]}, {"$set": {"updated_at": utc_now(), "garmin_metrics": gm}})  # cached analyses recompute
            n += 1
        print(f"samples re-read for {n} runs")
        return 0
    if args.cmd == "backfill-weather":
        # Weather estimates for runs of the last 120 days that don't have one yet (one Open-Meteo call each)
        from datetime import date, timedelta
        from . import weather
        conn = connect(ucfg.db_name)
        since = (date.today() - timedelta(days=120)).isoformat()
        have = set(conn.run_weather.distinct("source_id", {"weather": {"$ne": None}}))
        n = 0
        for a in conn.activity.find({"local_date": {"$gte": since}}):
            if a["source_id"] not in have:
                n += bool(weather.for_run(conn, a))
        print(f"weather looked up for {n} runs")
        return 0
    if args.cmd == "rebuild-reports":
        conn = connect(ucfg.db_name)
        c, today = make_connector(ucfg, conn)
        sids = [r["source_id"] for r in many(conn.activity, {"source": c.source}, sort=[("start_utc", 1)])]
        rp.regenerate(conn, c.source, c.synthetic, set(), sids, today)
        print(f"rebuilt {len(sids)} run reports and recent morning reports (unchanged inputs keep their revision)")
        return 0
    if args.cmd == "audit":
        return cmd_audit(ucfg, args.out)
    return 1


if __name__ == "__main__":
    sys.exit(main())

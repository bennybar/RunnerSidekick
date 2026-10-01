"""Admin CLI. Run from backend/:  .venv/bin/python -m sidekick <command>

  garmin-login           interactive Garmin login (hidden password prompt); stores tokens, never the password
  garmin-logout          delete stored Garmin tokens
  create-token NAME      create an app token (printed once). Users who sign in with Google get theirs automatically
  revoke-token NAME
  sync [--loop]          sync every connected user (+ report regeneration); --loop repeats until backfill completes
  invite add|remove|list EMAIL   invite-only access: who may sign in with Google
  users                  list accounts
  set-owner-email EMAIL  let the owner sign in with Google as this address
  (most commands take --user ID; the default is the owner)
  rebuild-reports        regenerate reports after an algorithm change (new revisions; old ones kept)
  audit [--out PATH]     field-coverage audit of stored data (no values, no credentials)
  serve [--host --port]  run the API (default 127.0.0.1:8765)

No configuration needed: data lives in <repo>/data and the source is Garmin. (Overrides for tests/demo only:
RSK_SOURCE=fixture, RSK_DATA_DIR=...)
"""

from __future__ import annotations

import argparse
import getpass
import json
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
from .db import connect
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
    conn = connect(cfg.data_dir / f"{SOURCE_GARMIN}.db")
    mark_reconnected(conn, SOURCE_GARMIN)
    print(f"Connected as {api.get_full_name() or 'Garmin user'}. Tokens stored in {cfg.garmin_token_dir} (0600).")
    return 0


def make_connector(cfg, conn):
    tz = rp.get_setting(conn, "timezone", cfg.timezone)
    today = datetime.now(ZoneInfo(tz)).date()
    if cfg.source == SOURCE_FIXTURE:
        return FixtureConnector(anchor=today, tz=tz), today
    return GarminConnector(cfg.garmin_token_dir, cfg.request_spacing_s), today


def cmd_sync(cfg, loop: bool) -> int:
    conn = connect(cfg.db_path)
    while True:
        c, today = make_connector(cfg, conn)
        res = run_sync(conn, c, today, cfg.backfill_days, cfg.refetch_days, cfg.raw_retention_days)
        rp.regenerate(conn, c.source, c.synthetic, res.changed_dates, res.changed_activities, today)
        cp = conn.execute("SELECT oldest_done, backfill_target FROM sync_checkpoint WHERE source=? AND stream='days'", (c.source,)).fetchone()
        print(f"{res.outcome}: {res.days_fetched} days, {res.activities_fetched} activities fetched"
              + (f" — {res.detail}" if res.detail else "")
              + (f" | backfill at {cp['oldest_done']} (target {cp['backfill_target']})" if cp else ""))
        done = cp is not None and cp["oldest_done"] is not None and cp["oldest_done"] <= cp["backfill_target"]
        if not loop or res.outcome not in ("ok", "partial") or (done and res.outcome == "ok"):
            return 0 if res.outcome in ("ok", "partial") else 1


def cmd_audit(cfg, out: str | None) -> int:
    """Coverage matrix from stored normalised records plus key names seen in raw payloads (names only)."""
    conn = connect(cfg.db_path)
    lines = [f"# Data audit — source `{cfg.source}`" + (" (SYNTHETIC FIXTURE DATA)" if cfg.source == SOURCE_FIXTURE else ""), ""]
    rng = conn.execute("SELECT MIN(local_date) a, MAX(local_date) b, COUNT(DISTINCT local_date) n FROM daily_observation WHERE source=?", (cfg.source,)).fetchone()
    lines += [f"Generated {datetime.now().isoformat(timespec='minutes')}. Days fetched: {rng['n']} ({rng['a']} → {rng['b']}).", "",
              "## Daily metrics", "", "| Metric | Method | Measured days | Not measured | Coverage |", "|---|---|---|---|---|"]
    for r in conn.execute("SELECT metric, GROUP_CONCAT(DISTINCT method) method, SUM(state='measured') m, SUM(state!='measured') x,"
                          " COUNT(*) n FROM daily_observation WHERE source=? GROUP BY metric ORDER BY metric", (cfg.source,)):
        lines.append(f"| {r['metric']} | {r['method'] or '—'} | {r['m']} | {r['x']} | {100 * r['m'] / r['n']:.0f}% |")
    acts = conn.execute("SELECT * FROM activity WHERE source=?", (cfg.source,)).fetchall()
    lines += ["", f"## Activities ({len(acts)})", "", "| Sport | Count |", "|---|---|"]
    for k, v in Counter(a["sport"] for a in acts).most_common():
        lines.append(f"| {k} | {v} |")
    runs = [a for a in acts if a["sport"] != "other"]
    if runs:
        lines += ["", "### Run field presence", "", "| Field | Present |", "|---|---|"]
        for f in ("distance_m", "elapsed_s", "moving_s", "timer_s", "avg_hr", "max_hr", "elevation_gain_m", "avg_cadence_spm"):
            lines.append(f"| {f} | {sum(1 for a in runs if a[f] is not None)}/{len(runs)} |")
        with_laps = conn.execute("SELECT COUNT(DISTINCT activity_id) n FROM activity_lap l JOIN activity a ON a.id=l.activity_id WHERE a.source=?", (cfg.source,)).fetchone()["n"]
        lines.append(f"| laps | {with_laps}/{len(runs)} |")
        sample_cov = Counter()
        n_s = 0
        for r in conn.execute("SELECT s.samples_json FROM activity_samples s JOIN activity a ON a.id=s.activity_id WHERE a.source=?", (cfg.source,)):
            d = json.loads(r["samples_json"])
            n_s += 1
            for k in ("hr", "speed", "dist", "elev", "cad"):
                if any(v is not None for v in d[k]):
                    sample_cov[k] += 1
        lines.append(f"| samples | {n_s}/{len(runs)} |")
        for k in ("hr", "speed", "dist", "elev", "cad"):
            lines.append(f"| samples.{k} | {sample_cov[k]}/{n_s} |")
        gm = Counter(k for a in runs for k in json.loads(a["garmin_metrics_json"]))
        lines += ["", "### Garmin-generated activity metrics present", ""] + [f"- {k}: {v}/{len(runs)}" for k, v in gm.most_common()]
    lines += ["", "## Raw payload top-level keys (names only)", ""]
    for kind, in conn.execute("SELECT DISTINCT kind FROM raw_payload WHERE source=?", (cfg.source,)).fetchall():
        keys = Counter()
        n = 0
        for r in conn.execute("SELECT payload_json FROM raw_payload WHERE source=? AND kind=? LIMIT 30", (cfg.source, kind)):
            p = json.loads(r["payload_json"])
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
    """Config pointed at one user's data folder (the owner when user_id is None)."""
    a = accounts.app_db(cfg.data_dir)
    try:
        uid = user_id if user_id is not None else accounts.ensure_owner(a)["id"]
    finally:
        a.close()
    return replace(cfg, data_dir=accounts.user_dir(cfg.data_dir, uid)), uid


def cmd_sync_all(cfg, loop: bool, only_user: int | None) -> int:
    a = accounts.app_db(cfg.data_dir)
    try:
        users = [u["id"] for u in accounts.list_users(a)] if only_user is None else [only_user]
    finally:
        a.close()
    worst = 0
    for uid in users:
        ucfg, _ = user_cfg(cfg, uid)
        if cfg.source != SOURCE_FIXTURE and not (ucfg.garmin_token_dir / "garmin_tokens.json").exists():
            print(f"user {uid}: no Garmin connection, skipped")
            continue
        print(f"user {uid}:", end=" ")
        worst = max(worst, cmd_sync(ucfg, loop))
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
    with_user(sub.add_parser("audit")).add_argument("--out")
    p = sub.add_parser("invite", help="invite-only access by Google email")
    p.add_argument("action", choices=["add", "remove", "list"]); p.add_argument("email", nargs="?")
    sub.add_parser("users")
    sub.add_parser("set-owner-email").add_argument("email")
    p = sub.add_parser("serve"); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    cfg = load_config()

    if args.cmd in ("invite", "users", "set-owner-email"):
        a = accounts.app_db(cfg.data_dir)
        try:
            if args.cmd == "users":
                for u in accounts.list_users(a):
                    print(f"{u['id']:>3}  {u['role']:<6}  {u['email'] or '(no email yet)':<32}  {u['sessions']} active token(s)")
            elif args.cmd == "set-owner-email":
                accounts.set_owner_email(a, args.email)
                print(f"Owner can now sign in with Google as {accounts.normalise_email(args.email)}.")
            elif args.action == "list":
                for r in a.execute("SELECT * FROM invites ORDER BY created_at"):
                    print(f"{r['email']:<32}  {'used ' + r['used_at'] if r['used_at'] else 'not used yet'}")
            elif not args.email:
                print("email required"); return 2
            elif args.action == "add":
                accounts.add_invite(a, args.email)
                print(f"Invited {accounts.normalise_email(args.email)}. They can now sign in with Google in the app.")
            else:
                print(f"removed {accounts.remove_invite(a, args.email)} unused invite(s)")
        finally:
            a.close()
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
    if args.cmd == "rebuild-reports":
        conn = connect(ucfg.db_path)
        c, today = make_connector(ucfg, conn)
        sids = [r[0] for r in conn.execute("SELECT source_id FROM activity WHERE source=? ORDER BY start_utc", (c.source,))]
        rp.regenerate(conn, c.source, c.synthetic, set(), sids, today)
        print(f"rebuilt {len(sids)} run reports and recent morning reports (unchanged inputs keep their revision)")
        return 0
    if args.cmd == "audit":
        return cmd_audit(ucfg, args.out)
    return 1


if __name__ == "__main__":
    sys.exit(main())

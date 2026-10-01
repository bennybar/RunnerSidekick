# Deploying the API — runnersidekick.ibarak.org

Everything lives in `/var/www/RunnerSidekick` and runs as root:

| Path | What |
|---|---|
| `/var/www/RunnerSidekick/backend` | code and `.venv` |
| `/var/www/RunnerSidekick/data` | `garmin.db`, `garmin_tokens/`, `device_tokens.json` (dir 0700, files 0600) |
| `/etc/runnersidekick.env` | optional, only for `OPENAI_API_KEY` (0600) |

No configuration is needed: the code always uses `<repo>/data` and Garmin.

The API listens on `127.0.0.1:8765`. nginx terminates TLS and proxies only `/v1/`, so nothing in
`/var/www/RunnerSidekick` is served as files.

## Install (on the server, as root)

```sh
cd /var/www/RunnerSidekick/backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
install -d -m 700 /var/www/RunnerSidekick/data
# optional, AI summaries only:  echo 'OPENAI_API_KEY=sk-...' > /etc/runnersidekick.env && chmod 600 /etc/runnersidekick.env
cp ../deploy/runnersidekick.service /etc/systemd/system/
systemctl daemon-reload
```

## Copy the Garmin session and history from the Mac

On the Mac:

```sh
sqlite3 ~/StudioProjects/RunnerSidekick/data/garmin.db "PRAGMA wal_checkpoint(TRUNCATE);"
scp -P 22238 -rp ~/StudioProjects/RunnerSidekick/data/garmin.db ~/StudioProjects/RunnerSidekick/data/garmin_tokens root@runnersidekick.ibarak.org:/var/www/RunnerSidekick/data/
```

On the server:

```sh
chmod 700 /var/www/RunnerSidekick/data /var/www/RunnerSidekick/data/garmin_tokens
chmod 600 /var/www/RunnerSidekick/data/garmin.db /var/www/RunnerSidekick/data/garmin_tokens/*
systemctl enable --now runnersidekick
```

Alternative to copying: log in on the server with
`.venv/bin/python -m sidekick garmin-login`.
Garmin often rate-limits logins from datacenter IPs, though.

## Device token for the phone (printed once)

```sh
cd /var/www/RunnerSidekick/backend && .venv/bin/python -m sidekick create-token phone
```

It prints a line starting with `rsk_`. Paste that into the app under Settings → Connection → Device token.

## Hourly sync (cron)

```sh
install -m 644 /var/www/RunnerSidekick/deploy/runnersidekick.cron /etc/cron.d/runnersidekick
```

It runs `python -m sidekick sync` at minute 17 of every hour and logs to `/var/log/runnersidekick-sync.log`.

## TLS and reverse proxy (DNS must already point at the server)

```sh
certbot certonly --nginx -d runnersidekick.ibarak.org
cp /var/www/RunnerSidekick/deploy/nginx-runnersidekick.conf /etc/nginx/sites-available/runnersidekick.conf
ln -s /etc/nginx/sites-available/runnersidekick.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

## Check

```sh
curl -s -o /dev/null -w '%{http_code}\n' https://runnersidekick.ibarak.org/v1/status                  # 401 without token
curl -s -H "Authorization: Bearer <token>" https://runnersidekick.ibarak.org/v1/status | head -c 200  # 200
journalctl -u runnersidekick -n 50; tail /var/log/runnersidekick-sync.log
```

Updating: `git pull`, then `.venv/bin/pip install -r requirements.txt` and `systemctl restart runnersidekick`.
Migrations apply on start. `/var/www/RunnerSidekick/data` holds health data and the Garmin session, so back it up as
private data and never commit it.

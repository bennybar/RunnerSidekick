# Manual install (systemd + nginx)

The easy way to run your own server is Docker Compose: see [SELF_HOSTING.md](SELF_HOSTING.md). This page is for a
plain Linux install instead. Replace `api.example.com` with your own domain.

Everything lives in `/var/www/RunnerSidekick`:

| Path | What |
|---|---|
| `/var/www/RunnerSidekick/backend` | code and `.venv` |
| `/var/www/RunnerSidekick/data` | `secrets.json`, `users/<id>/garmin_tokens/` (dir 0700, files 0600) |
| local MongoDB (`127.0.0.1:27017`) | all records: `rsk_app` (accounts) and `rsk_u<id>_garmin` (one database per user) |
| `/etc/runnersidekick.env` | optional environment settings (0600) |

MongoDB must listen on 127.0.0.1 only (the default `bindIp`). The API listens on `127.0.0.1:8765`; nginx terminates
TLS and proxies only `/v1/`, so nothing in `/var/www/RunnerSidekick` is served as files.

## Install (as root)

```sh
git clone <this repo> /var/www/RunnerSidekick
cd /var/www/RunnerSidekick/backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
install -d -m 700 /var/www/RunnerSidekick/data
cp ../deploy/runnersidekick.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now runnersidekick
```

## Connect Garmin

```sh
cd /var/www/RunnerSidekick/backend && .venv/bin/python -m sidekick garmin-login
```

It asks for your Garmin Connect email and password (and a code if you use two-step verification) and keeps only the
session tokens. Garmin sometimes rate-limits logins from datacenter IPs; try again later if it refuses.

## Device token for the app (printed once)

```sh
cd /var/www/RunnerSidekick/backend && .venv/bin/python -m sidekick create-token phone
```

It prints a line starting with `rsk_`. In the app, enter your server address (`https://api.example.com`) and paste
the token.

## Optional: Google sign-in and more users

```sh
.venv/bin/python -m sidekick set-owner-email you@example.com   # you can also sign in with Google
.venv/bin/python -m sidekick invite add friend@example.com      # invite-only: who may sign in with Google
.venv/bin/python -m sidekick users
```

Optional secrets go in `data/secrets.json` (mode 0600). Every key is optional:

```json
{"openai_api_key": "..."}
```

The OpenAI key turns on the AI summaries; without it everything else works.

## Hourly sync (cron)

```sh
install -m 644 /var/www/RunnerSidekick/deploy/runnersidekick.cron /etc/cron.d/runnersidekick
```

## TLS and reverse proxy (DNS must already point at the server)

```sh
certbot certonly --nginx -d api.example.com
sed 's/api.example.com/<your domain>/g' /var/www/RunnerSidekick/deploy/nginx-runnersidekick.conf > /etc/nginx/sites-available/runnersidekick.conf
ln -s /etc/nginx/sites-available/runnersidekick.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

## Check

```sh
curl -s -o /dev/null -w '%{http_code}\n' https://api.example.com/v1/status                  # 401 without a token
curl -s -H "Authorization: Bearer <token>" https://api.example.com/v1/status | head -c 200  # 200
journalctl -u runnersidekick -n 50; tail /var/log/runnersidekick-sync.log
```

Updating: `git pull`, `.venv/bin/pip install -r requirements.txt`, `systemctl restart runnersidekick`. Migrations
apply on start. `data/` and MongoDB hold your health data and Garmin session: back them up as private data and never
commit them.

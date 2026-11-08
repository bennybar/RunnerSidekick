# Self-hosting Runner Sidekick

Run your own Runner Sidekick server with Docker Compose: the API, MongoDB and an hourly Garmin sync. The server
works with nothing configured beyond this page: no Google setup, no OpenAI key and no Garmin developer account.

## Prerequisites

- A machine with Docker that stays on (a small Linux VPS is fine).
- Docker Engine with Compose v2.24 or newer (`docker compose version`).
- A domain name pointing at the machine and a reverse proxy for HTTPS (see below): the iOS app only connects to
  `https://` addresses, so give both apps the https one.
- MongoDB 8 (the image used) needs a CPU with AVX on x86 (any machine from the last decade) or ARMv8.2 on ARM: a
  Raspberry Pi 5 works, a Raspberry Pi 4 doesn't.

## Start

```sh
git clone <this repository> runnersidekick && cd runnersidekick
cp .env.example .env        # optional: time zone, OpenAI key, public address
docker compose up -d
docker compose ps           # mongo (healthy), api, sync
```

The API listens on `127.0.0.1:8765` on the host, for the reverse proxy only. `curl -i http://127.0.0.1:8765/v1/status`
answers `401` (no token yet): it's running.

## Sign in from the app

Create a device token for yourself (the owner account) and paste it in the app, with your server's https address:

```sh
docker compose exec api python -m sidekick create-token my-phone
```

The token is shown once. Make one per device; `revoke-token NAME` ends one.

Google sign-in is optional and invite-only. It uses the app's own Google client IDs, so it works with the published
apps once you allow someone: `docker compose exec api python -m sidekick invite add someone@example.com` (or
`set-owner-email you@example.com` to sign in as the owner with Google). To switch it off, set
`RSK_GOOGLE_WEB_CLIENT_ID=` (empty) in `.env`.

## Connect Garmin

Either:

- In the app: Settings → Garmin, sign in on Garmin's own page (the app sends the server a one-time ticket), or
- From the server: `docker compose exec api python -m sidekick garmin-login` asks for your Garmin email, password
  (hidden) and, if you use it, the two-factor code. Only Garmin's tokens are stored, in the data volume, never the
  password. `garmin-logout` removes them. Add `--user ID` for another account (`sidekick users`).

The `sync` service then syncs every connected user once an hour (the first run backfills 90 days, in steps). To sync
right away: `docker compose exec api python -m sidekick sync`.

## HTTPS

Put any reverse proxy with a certificate in front of `127.0.0.1:8765` and forward `/v1/` only. With Caddy, which
gets the certificate itself:

```
api.example.com {
    reverse_proxy /v1/* 127.0.0.1:8765
}
```

An nginx example is in `deploy/nginx-runnersidekick.conf` (it also keeps OAuth codes and query strings out of the
access log). Then use `https://api.example.com` in the app.

## Optional settings (`.env`)

| Variable | Default | What it does |
|---|---|---|
| `RSK_TIMEZONE` | `UTC` | Time zone for runners who haven't set theirs in the app |
| `OPENAI_API_KEY` | empty | AI summaries with the server's key; without it, runners can use their own key |
| `RSK_PUBLIC_BASE_URL` | empty | Your https address; only needed for Garmin's official OAuth (developer program) |
| `RSK_GOOGLE_WEB_CLIENT_ID`, `RSK_GOOGLE_IOS_CLIENT_ID` | the app's IDs | Google sign-in audiences; empty switches it off |

Run `docker compose up -d` again after changing `.env`. Server secrets can also go in `secrets.json` in the data
volume (`openai_api_key`, `garmin_client_id`, `garmin_client_secret`).

## Update

```sh
git pull
docker compose up -d --build
```

Reports are rebuilt by themselves when an algorithm changes.

## Backups

Two volumes hold everything: `mongo-data` (health data, accounts and device tokens) and `sidekick-data` (Garmin
tokens and `secrets.json`). A consistent MongoDB dump:

```sh
docker compose exec -T mongo mongodump --archive --gzip > runnersidekick-$(date +%F).archive.gz
# restore:
docker compose exec -T mongo mongorestore --archive --gzip --drop < runnersidekick-2026-01-01.archive.gz
```

And the data volume:

```sh
docker run --rm -v runnersidekick_sidekick-data:/data -v "$PWD":/backup alpine tar czf /backup/sidekick-data.tgz -C /data .
```

(The volume name is prefixed with the Compose project name, the folder's name by default: `docker volume ls`.)

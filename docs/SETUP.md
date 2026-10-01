# Setup

## Backend (macOS, Python 3.12)

```sh
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q                         # 33 tests
```

Configuration (environment variables):

| Name | Default | Meaning |
|---|---|---|
| `RSK_SOURCE` | `fixture` | `garmin` for live data, `fixture` for synthetic demo data (separate databases) |
| `RSK_DATA_DIR` | `~/.runner-sidekick` | databases, Garmin tokens, device-token hashes (0700) |
| `RSK_TIMEZONE` | `Asia/Jerusalem` | default local zone (editable in the app) |
| `RSK_BACKFILL_DAYS` | `90` | history to backfill |
| `RSK_REFETCH_DAYS` | `3` | recent window re-fetched every sync (late sleep, edited activities) |
| `RSK_RAW_RETENTION_DAYS` | `120` | raw Garmin payload retention |
| `RSK_REQUEST_SPACING_S` | `1.0` | pause between Garmin requests |

### Connect Garmin (live mode)

Run these in a real terminal (the password prompt needs a TTY):

```sh
export RSK_SOURCE=garmin
.venv/bin/python -m sidekick garmin-login     # email + hidden password; tokens saved, password never stored
.venv/bin/python -m sidekick sync --loop      # bounded, resumable ~90-day backfill (~6 requests/day, 1 s apart)
.venv/bin/python -m sidekick audit --out ../docs/data-audit.md   # coverage matrix (field names/counts only)
```

If Garmin later rejects the session, syncing stops (no retry storm) until `garmin-login` is run again.
Rate limiting backs off exponentially (15 min doubling, max 6 h, with jitter).

### Run the API

```sh
.venv/bin/python -m sidekick create-token emulator   # prints a token once
.venv/bin/python -m sidekick serve                   # 127.0.0.1:8765 only
```

## Android

Requirements: Android Studio (bundled JBR 21), SDK platform 37.

```sh
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
./gradlew assembleDebug testDebugUnitTest lintDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

In the app: **Settings → Connection**. The URL defaults to `http://10.0.2.2:8765` (the emulator's alias for the
host loopback). Paste the device token, then tap **Save and test**.

### Physical phone (not set up yet)

The backend refuses to bind beyond loopback without TLS. Options:
- USB: `adb reverse tcp:8765 tcp:8765`, then use `http://localhost:8765` (debug builds allow cleartext to localhost).
- LAN: put the API behind TLS (e.g. Caddy with a local CA installed on the phone) and use its `https://` URL.

## Data and deletion

- Backend: Settings → *Delete raw Garmin payloads* (`scope=raw`) or *Delete everything* (`scope=all`). Garmin
  tokens: `python -m sidekick garmin-logout`. Device tokens: `revoke-token NAME`.
- Phone: *Clear this phone's cache*. Android cloud backup and device transfer are disabled for the app.
- Backups: the app doesn't back anything up. Your computer's own backups (e.g. Time Machine) may include
  `~/.runner-sidekick`.

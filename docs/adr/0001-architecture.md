# ADR 0001 — Architecture of the personal MVP

Status: accepted for prototype · 2026-10-01

## Starting point (Phase 0 inspection)

- Fresh Android Studio template: single `:app` module, Views/AppCompat theme, no Activity, no Compose, no tests beyond
  template examples. `applicationId`/namespace `com.bennybar.runnersidekick`, minSdk 35, targetSdk 36.
- No `CLAUDE.md`, `AGENTS.md` or docs in the repo. No backend.
- **Baseline build failed:** template `androidx.core:core-ktx:1.19.0` requires AGP ≥ 9.1 and compileSdk 37,
  but the project used AGP 8.13.2 / compileSdk 36 (`checkDebugAarMetadata`).

## Decisions

1. **Toolchain.** Upgraded to AGP 9.4.1, Gradle 9.8.0, Kotlin 2.3.21 (Compose + serialization plugins), KSP 2.3.12,
   compileSdk 37. `targetSdk` (36), `minSdk` (35) and `applicationId` unchanged. The user chose this over pinning
   older libraries. AGP 9's built-in Kotlin support replaces the `kotlin-android` plugin.
2. **Client:** single-module Kotlin/Compose/Material 3 app, Google-app styling (dynamic colour, large top app bars,
   NavigationBar). Manual DI (`RunnerApp` holds one `Repository`); ViewModels per screen. A multi-module split would
   be premature for a single-user prototype.
3. **Backend:** Python 3.12 + FastAPI + SQLite, colocated in `backend/`. Plain numbered SQL migrations
   (`backend/sidekick/migrations`) applied on connect, so there's no Alembic dependency.
4. **One database per source** (`~/.runner-sidekick/garmin.db`, `fixture.db`). Synthetic and live records can't mix
   by construction. The API reports `mode`/`synthetic`; the app clears its cache on a mode change and shows a
   "Demo data" badge.
5. **Connector interface** (`connectors/base.py`): `connection_state`, `capabilities`, `read_days(start, end)`,
   `list_activities`, `read_activity`. Incremental reads are date-window reads driven by the sync engine's
   checkpoint, so the interface stays the same for future official-Garmin / Health Connect adapters with different
   capability sets.
6. **Auth.** Garmin: interactive `garmin-login` CLI (hidden prompt). The library stores tokens at 0600 in
   `~/.runner-sidekick/garmin_tokens/`, and the password is never written. App→backend: random device bearer token,
   stored as a SHA-256 hash on the backend and Keystore-encrypted (AES-GCM) on the phone. Every route requires it.
7. **Transport.** The backend binds to loopback only (it refuses other hosts). The emulator reaches it via
   `10.0.2.2`. Cleartext is allowed only in **debug** builds and only for `10.0.2.2`/localhost
   (`src/debug` network security config). Release builds have no cleartext allowance.
8. **Analytics are deterministic Python** with versioned constants (`baseline-1.0`, `running-1.0`, `rules-1.1`,
   `report-1.2`). The app renders numbers from structured findings. There is no LLM in v1. The narrative adapter is
   Phase 3, and reports carry `narrative: null`.
9. **Reports are revisioned by input hash.** Old revisions are kept. Morning reports older than 7 days aren't
   regenerated automatically, so the journal shows what was known at the time.
10. **Offline.** The app caches raw API JSON in Room (keyed per mode) plus report bodies. Check-ins are written to
    Room first and pushed later. The conflict policy is last-writer-wins on `client_updated_at`.

11. **Material 3 Expressive (2026-10-01).** At the user's request the UI uses M3 Expressive (MaterialExpressiveTheme,
    shape badges, ShortNavigationBar, LoadingIndicator, segmented groups). Those APIs are public only in
    `androidx.compose.material3` 1.5.0 alpha, so `material3` is pinned to `1.5.0-alpha29` over the Compose BOM (stable
    1.4.0). Revert the single version override once 1.5 is stable.
12. **Insight engine (2026-10-01).** A pre-registered question list answered from the user's data. See
    analysis-rules.md. Insights are stored as a revisioned `insights` report.
13. **Deployment.** a systemd unit for the API, an hourly cron sync, and nginx TLS for `runnersidekick.ibarak.org`. See
    docs/DEPLOY.md.

## Module / package layout

```
backend/sidekick/
  config.py  db.py  auth.py  store.py  sync.py  reports.py  api.py  __main__.py (CLI)
  connectors/{base,garmin,fixture}.py
  analytics/{baseline,running,recommend}.py
  migrations/0001_init.sql
app/src/main/java/com/bennybar/runnersidekick/
  RunnerApp.kt  MainActivity.kt
  data/{Repository.kt, remote/{ApiClient,Models}.kt, local/{Database,SettingsStore}.kt}
  ui/{theme, components, today, activities, journal, settings}, ui/Format.kt, ui/AppViewModels.kt
  work/RefreshWorker.kt
```

## Consequences / open questions

- The SQLite connection-per-request plus WAL is adequate for one user, but it isn't a multi-user design.
- Raw payloads are retained for 120 days (`RSK_RAW_RETENTION_DAYS`), separately from reports (kept until deleted).
- A physical phone needs TLS or `adb reverse`. That's documented, not implemented.

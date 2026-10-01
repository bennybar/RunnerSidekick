# Status — 2026-10-01

Spec: [docs/BRIEF.md](BRIEF.md) (unchanged copy of the build brief). Architecture: [adr/0001](adr/0001-architecture.md).
Rules: [analysis-rules.md](analysis-rules.md). Setup: [SETUP.md](SETUP.md).

## Done
- **Phase 0:** inspected the repo, fixed the broken baseline (toolchain upgrade, see ADR), recorded the architecture.
- **Phase 1 (pipeline, fixture-verified):** connector interface; deterministic fixture connector; Garmin adapter on
  `garminconnect` 0.3.17 (read-only); `garmin-login` CLI; SQLite schema with migrations; idempotent, resumable,
  bounded sync with a refetch window, auth-stop and rate-limit backoff; audit command.
- **Phase 2 (MVP):** baselines; run analysis (splits, classification, decoupling, similar runs, workload); rule table;
  revisioned morning and post-run reports with evidence; check-ins (offline-first, LWW); FastAPI with bearer auth.
- **Android:** Compose/M3 app with Today, Activities (list and detail), Journal, Settings; Room cache;
  Keystore-encrypted token; WorkManager best-effort refresh; offline and demo states.

## Verification (2026-10-01)
- `backend`: `pytest` → **56 passed** (was 33 at the first milestone).
- `./gradlew testDebugUnitTest lintDebug assembleDebug` → **7 unit tests passed; lint 0 errors**, 4 warnings
  (newer dependency versions available ×3, targetSdk 36 not latest).
- **Emulator** (Pixel 9 Pro XL, API 36, fixture backend): connect, Today, check-in → revised briefing, Show why,
  activities, run detail (HR dropout gap, partial split), journal revision, dark mode, offline cached view.
  Screenshots are in `docs/screenshots/` (synthetic data only).
- Found and fixed during emulator testing: a crash on a non-boolean check-in flag (backend contract), and decode
  errors not being caught in the app.

## Done since (2026-10-01, Phase 3 + insights)
- Device eras: baselines and HR comparisons never cross a watch change (3 devices detected in live data).
- Insight engine (7 pre-registered questions) with an Insights tab, a top insight on Today, and journal snapshots.
- Optional AI narrative (OpenAI, default `gpt-6.1-sol`, opt-in): schema-validated, finding-ID references, numbers
  resolved from deterministic findings, rejects digits, unknown IDs, causal or medical wording, template fallback,
  cached per revision, daily budget.
- Notifications: morning briefing (window, provisional handling, dedup) and new-run reports (dedup, no backfill spam).
- M3 Expressive redesign of all screens. Fixed top bars drawing under the status bar. Chart y-scale clamps
  start-up outliers. Main-thread JSON decoding moved off the main thread.
- Deployment files (`deploy/`, `docs/DEPLOY.md`). Pinned `requirements.txt`.

## Blockers
- None blocking. Live Garmin sync demonstrated 2026-10-01: 90-day backfill, 31 runs, 53 days of wellness data (see data-audit.md).

## Next
1. After login: live 90-day backfill, then `audit` → `docs/data-audit.md`, then fix the parsers against real payloads,
   then checkpoint 2.
2. AI narrative not yet exercised against the real OpenAI API (no key configured). Only fake-provider tests so far.
   TalkBack walkthrough not done (200 % font and dark mode checked).
3. Phase 4: Trends (7/28/90), weekly review, journal revision history browser.

## Known limitations
- Pace chart uses 20-s bucket means and is still noisy on real 1-s data. It may need smoothing.
- A brief "No briefing yet" frame shows before the Room cache emits on cold start.
- No Trends screen or weekly review yet (Phase 4).
- Notifications verified to build and wire up, but not yet observed firing on the emulator (WorkManager timing).
- Physical-device connectivity is documented but not set up (needs TLS or `adb reverse`).
- No Room migration tests yet (schema v1 exported to `app/schemas`).

## Process
- External review checkpoints (BRIEF §12, Codex Astra) are **waived by the user (2026-10-01)**. No review packets are
  kept, and progress isn't gated on review.

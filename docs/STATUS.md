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
- `backend`: `pytest` → **33 passed**.
- `./gradlew testDebugUnitTest lintDebug assembleDebug` → **7 unit tests passed; lint 0 errors**, 4 warnings
  (newer dependency versions available ×3, targetSdk 36 not latest).
- **Emulator** (Pixel 9 Pro XL, API 36, fixture backend): connect, Today, check-in → revised briefing, Show why,
  activities, run detail (HR dropout gap, partial split), journal revision, dark mode, offline cached view.
  Screenshots are in `docs/screenshots/` (synthetic data only).
- Found and fixed during emulator testing: a crash on a non-boolean check-in flag (backend contract), and decode
  errors not being caught in the app.

## Blockers
- None blocking. Live Garmin sync demonstrated 2026-10-01: 90-day backfill, 31 runs, 53 days of wellness data (see data-audit.md).

## Next
1. After login: live 90-day backfill, then `audit` → `docs/data-audit.md`, then fix the parsers against real payloads,
   then checkpoint 2.
2. Phase 3: optional LLM narrative adapter (schema-validated, finding-ID references, template fallback), report
   timing and notifications with dedup, accessibility pass (TalkBack, font scale 200 %).
3. Phase 4: Trends (7/28/90), weekly review, journal revision history browser.

## Known limitations
- Pace chart uses 20-s bucket means and is still noisy on real 1-s data. It may need smoothing.
- A brief "No briefing yet" frame shows before the Room cache emits on cold start.
- No notifications, AI opt-in, report-timing or Trends screens yet. They're not shown as placeholders.
- Physical-device connectivity is documented but not set up (needs TLS or `adb reverse`).
- No Room migration tests yet (schema v1 exported to `app/schemas`).

## Process
- External review checkpoints (BRIEF §12, Codex Astra) are **waived by the user (2026-10-01)**. No review packets are
  kept, and progress isn't gated on review.

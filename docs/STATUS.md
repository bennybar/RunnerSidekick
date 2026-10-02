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

## Phase 4 (2026-10-01)
- Trends (7/28/90 days): daily sleep, resting HR and comparable HRV with the personal-range band, explicit gaps and
  watch-change markers; period-vs-previous summary with sample sizes; weekly running volume; pace at the usual HR band
  per watch. Every point opens its day or run.
- Weekly review report (Mon–Sun, local): volume vs prior 4 weeks, intensity, pace at HR, recovery context,
  check-ins, next-week focus (rule table F1–F5). Revisioned; frozen after 14 days.
- Revision history: `/v1/reports/{type}/{key}/revisions`, "Versions" on every report.
- New launcher icon (concept A) with a themed layer and a notification glyph.
- Backend defaults hard-coded: data in `<repo>/data`, source Garmin. No env setup needed.

## Analysis additions (2026-10-01)
- Grade-adjusted pace; drift on GAP with 20-min segments (eligible runs 8 → 11 of 31 on live data); best efforts and
  PRs; run story; more specific next focus; easy pace (measured / unknown / estimated); Garmin fitness card (VO₂ max,
  race predictions, training status, load vs Garmin range, load balance, heat acclimation) with an agreement note.

## The loop (2026-10-01, v0.4.0)
- Today's plan (rest/easy/long/tempo/intervals/race plus minutes): the suggestion speaks to the planned session.
- Run intent ("what was this run meant to be?", pre-filled from the plan; private note never sent to AI). An easy
  intent that was mostly zone 3+ is flagged, and next focus says so.
- Weekly focus: three suggestions from the data, ordered by goal type; measured on that week's runs (fade, easy share,
  volume band, planned days, hard runs) with perceived effort; reported again in the weekly review.
- Insights: New/Changed/Continuing; "working on it"/dismiss (lapses when the verdict changes); Today prefers new or
  changed insights.
- Goal type (consistency / go longer / get faster / health); usual time shapes the suggestion.
- Fixed (from an external review): no "readings look typical" without overnight data or ranges (R1c/R1d/R1e);
  suggestion text respects suppressed intensity; local check-ins scoped per account (Room v2).
- New running icon (runner above a heart-rate line).

## AI coach and less interaction (2026-10-01)
- AI coach (`GET /v1/coach`): cross-domain insights and recommendations with evidence chips that open runs and
  insights; shown at the top of Insights with a one-line teaser on Today. Server key or the runner's own key (Settings).
  Verified live on real data (status ok, about 35 s, cached afterwards).
- Fewer questions: no FAB; the app asks for a one-tap check-in only when it would change the advice
  (`checkin_prompt`); the plan is an optional row; the weekly focus is picked automatically; run type is inferred.
- A little colour: soft category accents on icon badges (training, sleep, recovery, running, fitness, habits).
- Not exercised on the emulator: the check-in prompt card itself (today's report already had a check-in).

## Blockers
- None blocking. Live Garmin sync demonstrated 2026-10-01: 90-day backfill, 31 runs, 53 days of wellness data (audit in docs/data-audit.md, generated locally and not committed).

## Next
1. After login: live 90-day backfill, then `audit` → `docs/data-audit.md`, then fix the parsers against real payloads,
   then checkpoint 2.
2. AI narrative not yet exercised against the real OpenAI API (no key configured). Only fake-provider tests so far.
   TalkBack walkthrough not done (200 % font and dark mode checked).
3. Multi-user (see roadmap below).

## Review fixes, MongoDB, comparisons (2026-10-01)
- Second external review: the P1 and P2 findings fixed with regression tests (see the commit "Fix findings from the second
  external review"). Not done, by choice: an offline queue for plans and intent, race-specific planning, a redesign of
  Today's competing sections, and full semantic AI validation (replaced by structured constraints).
- Storage moved to the local MongoDB; one-time `migrate-sqlite`; every endpoint verified identical on real data.
- Compare tab: VO₂ max percentile, fitness age, resting HR percentile and age-graded times against published references
  for your sex and age, each with a chart and caveats. No HRV position: there's no comparable reference.

## Daily summaries and a sharper Today (2026-10-01, v0.7.0)
- Compare and Trends start with a daily AI summary (same checks as the coach). Verified live on real data.
- Today: a new "Stands out today" section (Garmin status, load, bests, VO₂ max movement, focus, comparisons, run intent)
  directly under the day's call, then readings; a single AI voice instead of two.

## Motion (2026-10-01, v0.8.0)
- Predictive back: opted in (`enableOnBackInvokedCallback`); the swipe drives Navigation's predictive-pop transitions
  (Navigation 2.10 has separate ones for the gesture; its default is a centred shrink). Cancelling snaps back.
- Material 3 motion: emphasized easing, fade-through between tabs, a horizontal shared axis for details; lists fade and
  reflow when tabs, ranges or cards change; expandable cards animate their height.

## Polish (2026-10-01, v0.10.0)
- Back (button or swipe, from any page) is iOS-style, as in FairEmail: the page slides off to the right with the
  finger at full size while the page below slides in from 48 dp left; forward is the mirror image. No scaling or cards.
- VO₂ max history: labelled dots on a zoomed scale with gridlines (position encodes the value, so a narrow 46–47 range
  isn't exaggerated as bar lengths would be); gaps break the line.

## Race goal, HRV trend, weekly digest (2026-10-01, v0.11.0)
- Race goal in Settings → phase (base, build, sharpen, taper, race week, recovery): leads Today's "Stands out" with
  prediction vs target, orders the weekly focus, and frames the coach (verified live: it plans from the build phase).
- Compare → HRV: this week against your own range on the current watch, with a 12-week chart split at watch changes.
- Monday weekly digest notification. Compiled; not yet seen firing (it needs a Monday morning).
- URL and token fields no longer autocorrect (it changed "http" to "https").

## Week start day (2026-10-01, v0.12.0)
- "Week starts on" in Settings (As in Garmin, Monday, Sunday, Saturday). The default comes from Garmin's profile
  (Sunday for the owner). Past reviews keep their weeks.

## AI input per run, manual sync (2026-10-01, v0.13.0)
- "Get AI input" on every run: summary, went well, to work on, next time. Verified live on real runs.
- Sync button on Activities: syncs with Garmin now and reports how many new runs arrived.

## Race week plan, what changed, TL;DR (2026-10-01, v0.14.0)
- With a race set, Today shows this week's sessions toward it: done, moved, missed or planned, against a minutes
  target with guardrails.
- The day's call shows when it was worked out and what changed since yesterday.
- From the second OpenAI review: done items 1 and 2. Not yet: focus outcomes across weeks (needs several weeks of
  focus history), an offline queue for plans and intent (low value for one user), official Garmin import (needs Garmin's
  developer approval).

## Refocus: data first, simple home (2026-10-02, v0.15.0)
- Goal: make Garmin's data more accessible, analyse it deterministically, and add AI on top. No manual inputs required.
- Today: Health and Fitness scores (0–100, age- and sex-based, with a breakdown), the day's call, the coach's TL;DR, up
  to 3 things that stand out, readings (with VO₂ max) and the latest run. Plan, check-in and focus are off Today; the
  focus and race week are now on Insights. The app no longer asks for check-ins.
- Fixed: a sync where Garmin left out VO₂ max (or another part of the fitness snapshot) wiped the stored value. It is
  now merged. Readings that aren't in yet show the last value with its date instead of "Not recorded".
- Transitions: one 120 ms crossfade everywhere, as in kitzi.

## Multi-user phase (in progress, 2026-10-01)
- Done (backend): `data/app.db` holding users, invites, sessions and OAuth state; per-user data folders
  `data/users/<id>/`; automatic migration of the single-user layout (owner = user 1, old tokens kept). Invite-only
  `POST /v1/auth/google` (Google ID token verified with `google-auth`). Garmin OAuth 2.0 PKCE start/callback/refresh/
  disconnect per Garmin's spec. Account deletion deregisters from Garmin. CLI: `invite`, `users`, `set-owner-email`,
  `--user`. 18 new tests, including cross-user isolation.
- Done (app): Google Sign-In screen (Credential Manager), device-token fallback, Account and Garmin sections in Settings.
- Waiting on the user: Google Cloud Web client ID; Garmin developer program approval.
- Not built yet: official Garmin data import (push/ping webhooks; partner docs needed after approval), per-user sync
  budgets beyond the hourly cron, privacy policy/consent screen.

## Roadmap: multi-user (original notes)
- Goal: other people sign in with Garmin and the backend issues their app token automatically.
- Use the **Garmin Connect Developer Program OAuth** (official; needs business approval, so apply early). Don't collect
  Garmin passwords via the unofficial library for other users: security liability, terms, and IP-level blocking.
- Backend: `users` table; every record, report, check-in and token scoped to a user; per-user sync scheduling and rate
  budgets; encrypted Garmin tokens; per-user export and deletion.
- App: a sign-in screen replacing manual URL/token entry.
- Compliance: privacy policy, explicit consent for health data (GDPR, Israeli privacy law).

## Known limitations
- Pace chart uses 20-s bucket means and is still noisy on real 1-s data. It may need smoothing.
- A brief "No briefing yet" frame shows before the Room cache emits on cold start.
- Notifications verified to build and wire up, but not yet observed firing on the emulator (WorkManager timing).
- Physical-device connectivity is documented but not set up (needs TLS or `adb reverse`).
- No Room migration tests yet (schema v1 exported to `app/schemas`).

## Process
- External review checkpoints (BRIEF §12, Codex Astra) are **waived by the user (2026-10-01)**. No review packets are
  kept, and progress isn't gated on review.

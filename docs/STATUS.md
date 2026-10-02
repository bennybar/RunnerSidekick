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

## Readings explained, a more numeric Insights (2026-10-02, v0.16.0)
- Tapping a reading on Today opens with one sentence on how good the value is (against your usual range, and people
  of your age and sex where a reference exists) and what the reading means.
- Insights starts with a "Last 4 weeks" grid (distance, runs, time, pace, heart rate, longest run, climb, share in
  zones 4–5), each against the 4 weeks before. Those numbers are calculated, not written by AI. The coach shows its
  TL;DR and the point titles, with the full analysis one tap away. Pattern cards are compact and keep their text
  under "Details". Patterns where nothing notable turned up are a short list.

## Training readiness, next run, leaner AI (2026-10-02, v0.17.0)
- Readings start with our own training readiness (0–100, calculated) and, below it, the next run in numbers: kind,
  distance, a heart-rate cap from Garmin's zones, easy pace and time when known, plus the reason in one line.
- AI efficiency: the morning narrative is no longer generated (Today shows the coach's TL;DR, so it was paid for and
  never read; it was about half of all calls). All calls use low reasoning effort (a real coach call went from 31 s
  to 18 s with fewer output tokens, same validated output). Each call's token use is now logged in `ai_call.usage`.

## Plainer Today, screen review (2026-10-02, v0.18.0)
- Today: the day's-call card ("Not enough data · train by feel") is gone. It contradicted readiness and the next run,
  which now sit right under the scores. The readiness breakdown shows a plain line and a Good / OK / Low verdict per
  part instead of points and formulas. "Since yesterday" now reports readiness moves of 5 or more, instead of the
  old call label.
- One freshness pill instead of three. Reading tiles say "Yesterday's" instead of "From … · today's not in yet".
- Insights: the coach card shows two findings and one thing to try (the rest under "Show full analysis"). The
  Garmin agreement card is one line. Compare no longer shows an ISO date.
- Journal: the Check-ins tab only appears for people who logged check-ins before.

## Readiness counts previous training (2026-10-02, v0.18.1)
- Readiness 1.1: the jumpy "minutes in the last 7 days" and the 2-day "last run" parts are replaced by a training
  load (heart-rate zones × minutes, fading over 7 vs 28 days) and a recovery part (recent effort fading over about
  2 days). Backtested against Garmin's readiness on real data: both now drop on the same mornings after runs.

## Plainer run screen (2026-10-02, v0.19.0)
- "How it went": plain checks with Good / OK / Low / Info instead of story sentences. The checks are pacing, effort
  against the run type, cadence, heart-rate drift (steady runs), hills and Garmin's training effect.
- The AI input card shows its TL;DR and the next-time tip, with went well / to work on one tap away.
- Removed:
  - the old per-run AI narrative (it often said nothing; the server no longer generates it, one AI call less per run);
  - the "drift not calculated" jargon row;
  - the perceived-effort input (no manual inputs).
- Garmin's numbers are rounded (training load 179, not 179.26…), and its training effect isn't repeated.

## Automatic AI input for new runs (2026-10-02, v0.20.0)
- After a sync (app-triggered or the hourly cron), new runs get AI input automatically with the server's key.
- Safeguards: only runs that started in the last 36 hours, so a first sync's or backfill's history never qualifies.
  Once per run, whatever the earlier outcome. At most 2 per sync. Never using the last 5 AI calls of the day.
- The card says "Written automatically for this new run"; Settings explains the rule. Older runs keep the
  Get AI input button.

## Insights trimmed, calculation fixes, battery (2026-10-02, v0.21.0)
- Insights:
  - Repeats removed: the "Garmin agrees" card, the hard-running and same-heart-rate pattern cards (covered by the
    stats grid, the coach and Trends), and VO₂ max from Garmin's card (now "Garmin training status").
  - Pattern cards have no buttons; "I'm working on it / Dismiss" sit in Details.
  - Compare cards show the verdict and chart, with the explanation on tap. The screen summaries show their first
    sentence (prompt summary-1.4: a takeaway first, at most 3 sentences).
  - Trends lists runs by date, distance and pace instead of raw ids. The weekly review card is its headline only.
- Calculation fixes from an external review:
  - The training-load cache is keyed per user database and run revision.
  - Readiness needs at least one overnight reading, and reported pain or illness caps it at 35 and makes the next run
    rest.
  - The fading load averages are bias-corrected for short history (22 vs 84 days of identical training now read the
    same).
  - Race-week sessions are scaled into one weekly budget.
  - No 3 km floor on the next run.
  - "Easy, as meant" requires 70% below zone 3.
  - The resting-HR sentence ranks your typical value, not today's reading, against the population.
  - "Update AI input" appears when a run's type was changed after its AI input was written.
- Battery:
  - The background worker no longer starts a Garmin sync and polls it (up to ~100 requests). It fetches only what
    notifications read; the server's hourly cron does the syncing.
  - The worker is scheduled only while signed in and needs the battery not to be low.
  - One coach poll at a time.
- Open: removing Health /100 (a product call). The rest was done in v0.22.0.

## One decision, defects closed, network diet (2026-10-02, v0.22.0)
- One decision (`decide.py`): readiness, whether intensity is held back, and the next run. Today, the race week, the
  morning notification, the AI coach (coach-1.6 explains it and can't contradict it) and the AI input on runs all read
  it. The older rules are only safety inputs: pain or illness, and several recovery signals at once. Missing or still-
  learning data no longer forces "easy" by itself; readiness handles it.
- Older defects fixed, each with a regression test:
  - Settings couldn't turn AI off or clear a field: the app left out values equal to their defaults.
  - Impossible dates (Feb 30) are rejected, and stored ones no longer break Today.
  - A failed summary is retried after 30 minutes.
  - The AI budget is one atomic counter per day.
  - An automatic weekly focus switches to recovery after pain.
  - Personal-best highlights read only each run's latest revision.
- Network and battery:
  - Polls pause while their screen is hidden and back off from 3 to 15 s; a new Trends range cancels the old poll.
  - Requests are cancellable, with a 45 s total timeout.
  - JSON GETs carry an ETag, and an unchanged answer is an empty 304.
  - Unchanged cache entries and journal rows aren't rewritten; the journal is saved in one transaction.

## Consistent plans, tidy polling, faster Garmin sync (2026-10-02, v0.23.0)
- Next run:
  - It picks one session first (safety, then the race week's session of any kind, including race day and quality,
    then the history rules) and derives distance, time and effort from it.
  - A planned duration converts to distance at your pace, so the numbers always describe the same run.
- Race week: a target too small for every session at 10 minutes gets fewer sessions (easy days drop first, the guard
  says so), then sessions are trimmed to fit.
- App:
  - Changing a run's type refreshes its AI state, so "Update AI input" shows right away.
  - Today runs one coach poll at a time. Compare and Trends each own one fetch-and-poll job, tied to their sub-tab.
    A new Trends range cancels the old one, including its first fetch.
  - The hourly worker runs only while notifications are on.
- Garmin sync:
  - Days older than yesterday are re-read only while a core reading is missing.
  - The activity history is listed in full once a day; otherwise only the last week.
  - Fitness numbers are fetched after a new run or every 3 hours; zones and profile once a day.
  - The 1 s pause between Garmin calls stays, because Garmin rate-limits hard.

## Background refresh setting (2026-10-02, v0.23.1)
- Settings → Notifications → Background refresh, off by default. With notifications off, it keeps the phone's copy
  (Today, runs, weekly review, focus) fresh about every 3 hours, with a network and the battery not low, and sends no
  notifications.
- With notifications on, the job stays hourly and the switch shows as already on. With both off, nothing is scheduled.

## Quieter loading indicator (2026-10-02, v0.23.2)
- Loading shows a thin progress line along the top edge of the content, not a spinner over the cards. The round
  pull-to-refresh indicator appears only while you're pulling. Shared `RefreshBox` on Today, Insights, Activities,
  run detail and Journal.

## Progress with percentage, plan-true next run (2026-10-02, v0.24.0)
- Loading shows a real progress line with what's happening and a percentage ("Reading your days from Garmin · 23%").
  - App refreshes count their steps.
  - "Sync Garmin" and "Get new runs" follow the server's own progress (`sync_job.progress` and `phase`, exposed as
    `/v1/status.sync_progress`): days, runs, Garmin's numbers, then updating reports. Then the app loads the results.
- Next run follows the week plan:
  - A planned rest day is skipped, never turned into a run; the next session still to do is chosen.
  - A race before the next running day comes first, even on a day you don't usually run.
- Trends: a new range cancels the previous range's first fetch as well (it runs inside the owning job).

## Health and fitness scores v2 (2026-10-02, v0.25.0)
- Fitness: VO₂ max for age and sex, recent age-graded running (90 days) and training regularity (2+ runs or 75+ min a
  week).
- Health: weekly activity against the WHO guideline (Garmin intensity minutes, now stored; `backfill-intensity` fills
  them from stored day summaries), resting HR for age and sex, sleep length and sleep regularity.
- Fitness age and HRV left the scores (no double counting). Fixed weights; missing parts are listed and marked
  partial; a 4-week trend.
- Today shows Health and Fitness as two tiles; each opens its own breakdown with a plain line and Good / OK / Low per
  part, plus "To improve": the two calculated steps that would add the most points (v0.25.1).

## Scores v3, review fixes (2026-10-02, v0.26.0)
- Fitness is VO₂ max for age and sex (no invented percentiles outside the table). Age grade and consistency are
  context only, with consistency over weeks of real history.
- Health is activity (WHO), daily steps (Paluch 2022), sleep length night by night, sleep regularity and sleep
  efficiency. Resting HR is a context line with its own 4-week trend. Health needs movement and sleep.
- "Potential score changes" with timeframes; no harder-session step while intensity is held back.
- Fixes:
  - The run caches (efforts, classification) are keyed per database and run revision.
  - An all-rest recovery week no longer yields a steady run.
  - Manual sync reports a real failure or "still syncing" instead of success; its polls back off (2–8 s).

## Scores 3.1 (2026-10-02, v0.26.1)
- Sleep efficiency is context only, and only from nights with a measured awake time (missing awake time no longer
  counts as perfect).
- Trends use today's reference group (no birthday jumps). The Fitness trend shows the VO₂ max change.
- VO₂ max freshness: shown with the date measured; stale after 30 days, no score after 90.
- Steps are worded as "our reference target"; the movement overlap is stated.
- The tiles say what each score covers. Each breakdown has "How it's calculated" (the rule and the share of the score
  for each part).

## Scores 3.2, aligned tiles (2026-10-02, v0.26.2)
- The newest VO₂ max from either source wins, and is stored under its measurement day.
- Movement counts completed days only.
- The Health and Fitness tiles are equal height with two-line subtitles, so the rings line up.

## Fitness progress (2026-10-02, v0.27.0)
- Fitness keeps its VO₂ max number and adds Progress: improving, stable, declining or not enough evidence. It's built
  from three separate signals: VO₂ max over 4 weeks, pace at the same heart rate, and heart-rate drift on steady runs.
  Each signal has its evidence and a confidence level. Shown on the tile and at the top of the Fitness breakdown.

## Home polish (2026-10-02, v0.27.1)
- Score rings (`ScoreGauge`): fill and count up when they appear, with a gradient sweep and a soft blurred glow.
- The score, readiness and next-run cards get tonal gradient washes; the next-run card gets a run badge and a larger
  title.
- Sparklines are smooth curves with a gradient fill, drawn left to right, with a haloed dot on today's value.

## BMI as context, centred gauges (2026-10-02, v0.28.0)
- The Garmin profile now also stores height (only sex, birth date, height and week start are kept). Weigh-ins keep
  their source (scale or entered) and body fat when a scale reports it.
- Health shows Body (BMI) as a context line, not counted: BMI from height and a weigh-in in the last 30 days, with
  the usual range and its limits.
- The Health and Fitness rings and their lines are centred in the tiles.

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

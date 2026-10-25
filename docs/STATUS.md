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

## Run export, power, decoupling for every run (2026-10-04, v0.29.0)
- Run screen: an Export button saves the run as one Markdown file in the phone's Downloads folder (MediaStore). It
  contains the summary, how it went, heart-rate zones, pace and splits, best efforts, decoupling, similar runs,
  Garmin's numbers, the week, next focus, a minute-by-minute table and the AI input at the end. Built by the backend
  (`/v1/activities/{id}/export.md`, `run_export.py`).
- Running power is now stored with each run's samples (Garmin `directPower`). `backfill-samples` re-reads stored runs
  from the raw details.
- Decoupling is calculated for every run with enough heart rate: pace:HR (hill-adjusted) and power:HR on the same
  halves. "eligible" still means steady and not too hilly, and only those feed the checks, durability and the coach;
  other runs show the numbers as indicative. Both are in each run's summary on the run screen (running-1.3).

## Hold a run out of our VO₂; altitude noise fixed (2026-10-19, v0.65.0)
- Run screen › VO₂ section › "Leave out of our VO₂ max" (`PUT /v1/activities/{sid}/vo2-hold`, setting `vo2_held_out`):
  the run's own estimate stays on it, marked held out; the Cardio page counts it as "held out by you".
- Gradients (running-1.11) from altitude smoothed over a symmetric ±15 s window, measured over 100 m, under 1% as flat:
  ±1 m of GPS altitude noise on flat ground had added 1.7% to the hill-adjusted pace (uphill counts more than downhill
  gives back); now about 0, and a real 3% hill keeps its adjustment. Affects flat-equivalent pace, decoupling and the
  VO₂ estimate. Every run in the VO₂ estimate needs altitude for 90% of its stretch (cardio-0.4).
- Wording: "Heart-rate recording quality" (a smooth trace can still read wrong) and a separate "unusual heart rate for
  this pace" flag; subgroup medians "don't isolate watch accuracy or the effect of heat"; sensitivity as an example
  ("if your actual maximum were 5 lower or higher"); the spread as the observed run range.

## VO₂ estimate, round 3 (2026-10-19, server only, cardio-0.3)
- Hill-adjusted pace on every run the VO₂ estimate takes (practically the recorded pace on the flat), so there's no
  switch of method at 10 m/km; "hill-adjusted" only names runs above it. A hilly run needs a gradient for 90% of its
  stretch (a missing one used to count as flat).
- One stable basis: the median of the last 8 qualifying runs whatever the weather (cool-first made the value jump when
  a third cool run arrived). Beside it, as descriptive subgroup medians: cool and warm runs, and each watch's runs when
  they're mixed; runs 5 or more from the median are flagged for review and kept. Sensitivity in both directions (±5 bpm
  maximum heart rate). Wording: "in the table's Excellent band", "around the 84th percentile (the reference group)".

## Hill-adjusted VO₂ estimate (2026-10-19, v0.64.0)
- Our VO₂ estimate (cardio-0.2) takes runs with more than 10 and up to 20 m of climb or descent per km on their
  hill-adjusted pace (the app's Minetti-based flat-equivalent, grades over ~50 m) instead of the recorded pace; flat
  runs as before; over 20 m/km "too hilly". Marked hill-adjusted per run (run screen, export) and counted on the Cardio
  page. Pace at your usual heart rate stays flat-only.

## Review fixes: VO₂ per watch, default to the watch's, honest wording; preferences on the server (2026-10-19, v0.63.0)
- VO₂ max for scores defaults to the watch's; ours is opt-in and labelled experimental (not a validated VO₂ max test).
- Ours per watch was tried and reverted the same day at the runner's request: runs (and resting heart rate) from every
  watch count together; the page says so when the estimate mixes watches.
  Cooler runs only when there are 3 of them; otherwise warm ones are included and the page says so (not corrected).
- Fitness score label in Compare's rating words; a note says the points are a percentile only within the published
  40th–95th range. "Health" is now "Healthy habits" (not a measure of heart health; activity and steps overlap); the step
  target eases from 8,000 at 55 to 6,000 at 65 instead of jumping on the 60th birthday.
- Resting heart rate on Compare: your 4-week median against the 4 weeks before, same watch; no population ranking (a
  watch's sleep-time value isn't a survey's seated pulse), the survey's middle for orientation only. Same in the Today
  note, the AI facts and the records page.
- HRV on Compare: "No overnight HRV since <date>" when there's none this week, instead of an old value as "this week".
- App preferences (units, theme, light/dark, notifications, background refresh) are kept with the account on the
  server and restored after sign-in on a reinstall; notifications only when Android grants the permission again.

## Our VO₂ max on each run; watch-named labels (2026-10-19, v0.62.0)
- Each run's report has `vo2_ours` (Runner Sidekick's estimate from this run, `cardio.estimate_for_run`, or why it gives
  none) and `watch` (the watch that recorded it). The header's VO₂ tile shows ours with the watch's beside it; the
  "From Garmin" section is now "VO₂ max and the watch's numbers", rows named by watch; the export has both lines.
- "Garmin HR zones" wording: "HR zones" on runs, "your HR zones (from your Garmin profile)" in insights (report-2.13).

## VO₂ max for scores: ours by default (2026-10-19, v0.61.0)
- Settings › About you › VO₂ max for scores: Ours (default) or Watch (`vo2_source`). With ours, the fitness score,
  VO₂ progress, Compare and the VO₂-based fitness age use Runner Sidekick's estimate from your runs (`cardio.own_vo2`:
  the median of the last 8 qualifying runs of 60 days, from 3), and show "not enough runs yet" rather than the watch's
  when there are fewer. The Cardio page's watch entry always shows the watch's (`scores.watch_vo2`).
- Qualifying runs: only those unusually hot for the runner are left out (humid and 3 °C above the usual dew point, as in
  trends), not every humid run; warm runs used are counted on the page (they read a little low).
- Samsung runs without a total descent (and GTII files without totals) get climb and descent from their altitude
  samples, read every 10 s (CONVERSION 5); the stored Samsung runs were filled in once from their samples.

## Weather in the export (2026-10-18, server only)
- Open-Meteo lookups (WX_VERSION 2) add wind direction and gusts, and the conditions at the run's start and finish,
  interpolated between the hourly values (wind direction the short way round). The summary stays the hour nearest the
  middle. Estimates kept from before are looked up again on export (the old one stays if that fails).
- Heat stress, from the hottest of start, middle and finish: dew point 13 °C or feels-like 20 °C Warm, 18/27 Hot (the
  existing hot bar), 24/32 High heat stress; running context, not a medical assessment.
- The run export's Conditions section has a start/finish table, wind direction and gusts and heat stress; the AI
  context line has wind and heat stress, marked as an Open-Meteo estimate. No app screen changes.

## Delete a run; test recordings skipped (2026-10-16, v0.60.0)
- Run screen › ⋮ › Delete run (confirmed): `DELETE /v1/activities/{sid}` moves the run to source `deleted` and records
  it in `deleted_run`; `save_activity` and Garmin's sync skip deleted runs, so no sync or upload (Garmin, Samsung Health,
  GTII) brings one back. Reports for its day are rebuilt.
- Samsung Health and GTII runs under 2 minutes or 200 m aren't imported (test recordings, mis-taps).

## GTII runs, step length, own race predictions (2026-10-16, v0.59.0)
- Runs recorded with GTII (Gear Tracker II) on the Galaxy Watch: Settings › GTII runs picks GTII's FIT export folder
  once (a persisted document tree); every refresh (and the background job, and Sync) sends FIT files not sent before
  (`POST /v1/fit`, base64). Server `fit.py` (fitdecode 0.10.0): per-second record (HR, speed, distance, altitude, GPS,
  cadence, power, and ground contact / vertical oscillation / step length when a sensor gives them), laps with their
  intensity, session, local offset; FIT running cadence in strides doubled to steps unless it already reads as steps.
  A GTII run counts as the Samsung watch's (no device ID, so no device era); with a Samsung Health copy of the same run
  (start within 5 min) the FIT copy counts and the other is set aside, also when it arrives later and on re-filing.
- Step length on each run (report-2.12): distance while moving ÷ steps (cadence × time), in the cadence check and export.
- Race predictions of our own when Garmin isn't the watch (or has none): Daniels' VDOT from the best 5 km, 10 km or
  half effort within a run in the 90 days before each date, weekly over six months, solved back into 5K/10K/half/marathon.
- Samsung's advanced running metrics (Myotest: contact/flight time, vertical, stiffness, regularity, asymmetry) aren't
  in the Samsung Health Data SDK; contact + flight time sums to step time, but the split can't be had without the IMU.

## How the run went (2026-10-15, v0.58.0)
- A verdict per run, not a score (`verdict.py`, verdict-1.0, report-2.11): against the runner's intent for the run, else
  the day's plan; never against a type inferred from the run itself (then "Not enough data"). Easy/recovery/long: at
  least half below zone 3 and at most 10% in zones 4–5; steady: at most 30% in zones 4–5; tempo/threshold: at least
  30% in zones 4–5, intervals 20% plus work laps within 5% of each other's pace when work and recovery laps exist;
  progression: a faster second half, hill-adjusted; a heart-rate cap in the target ("HR <= 150"): at most 10% above;
  shortened: under 80% of the plan's minutes. Questionable heart rate adds a caveat. Races: the age grade (USATF/Alan
  Jones) at 5 km, 10 km, half or marathon (within 2%), elapsed time; other distances aren't graded.
- Shown as a card under the run's header and as "How it went" in the export.

## AI back on the server, HR quality, export sources, own fitness age (2026-10-15, v0.57.0)
- AI input on the server's key again: each new run and the latest 3 runs until each has input that worked (a failed try
  waits 6 h), at most 3 per sync, keeping 5 calls of the day in reserve; also after Samsung uploads. No free-text chat.
  The runner's own key stays optional. Server key: `data/secrets.json` (`openai_api_key`, `server_ai_enabled`).
- Heart-rate data quality per run (`hr_quality`, hrq-1.1, report-2.10): after the first 6 min, a 20 bpm jump within 5 s, or 15 bpm from
  the median of the surrounding 5 minutes at a steady hill-adjusted pace (±15%); Good < 2% of running time, Questionable ≤ 8% or any
  stretch ≥ 1 min, else Poor. Readings unchanged; decoupling and the export carry a caveat when not Good.
- Samsung cadence: one method, time-weighted over moving samples (as the splits); Samsung's own average stays raw.
- Run export: VO₂ labelled by maker (device value), zone thresholds "Garmin-derived", recovery context by watch, a
  heart-rate quality section, provenance (device, HR source, running dynamics, VO₂, zone and recovery sources), and a
  cross-device note when similar runs came from another watch.
- Fitness age: Settings › About you › Fitness age, Garmin's or Runner Sidekick's (`fitness_age_source`). Ours is the
  "VO₂-based fitness age": the age at which the current watch's VO₂ max is typical for your sex (Cooper; typical = the
  midpoint of each group's 40th and 60th percentile values, not a published median), interpolated between group
  midpoints, in whole years ("around 45"). Only within the table (20–29 to 70–79): past it, "above the typical VO₂ max
  for men aged 20–29" with no age, a bound kept through the highlight and the AI facts.

## Last night (2026-10-13, v0.56.0)
- The app also reads the Samsung watch's skin temperature and blood oxygen (each its own permission; picking Samsung
  again in Your watch asks for what wasn't allowed) and uploads them with heart rate (`samsung_skin`, `samsung_spo2`).
- Each night (non-nap Samsung sleep for a wake date): how much was measured (heart-rate readings, gaps up to 15 min),
  sleeping heart rate (average, lowest 30 minutes), skin temperature (average) and blood oxygen (average, lowest), from
  at least 3 readings; observations `night_*`, method `samsung_night`.
- Today's "Last night" card (`overnight` in the morning report, report-2.8): each value against the previous 14 nights
  once there are 5 (sleeping HR and skin temperature as a difference from the median, blood oxygen as the 25th–75th
  percentile range), plus coverage. Context only: nothing feeds readiness or the suggestion.

## Samsung review fixes, wording (2026-10-13, v0.55.0)
- Moving time and distance from the actual time between samples (gap: 10 s or 3× the watch's spacing), so a watch that
  samples every 5 s isn't cut to a fifth; a workout without a log keeps its session duration.
- All-day heart rate kept per reading (`samsung_hr`, by time, with its own UTC offset); resting HR worked out again from
  everything stored for each day touched, so upload parts and retries give the same value. It needs 4 h measured
  (gaps count up to 15 min) and 1 h between midnight and 6 am; shown as "Resting heart rate (Sidekick's estimate)".
- Sleep totals from every Samsung night stored for the day; Samsung's sleep score kept (`samsung_sleep_score`) and
  shown with the watch's own scores on Today ("From Samsung").
- Switching watches files already-imported data again (`reconcile`): Samsung records out of the analysis on Garmin
  days and in on Samsung days, Garmin runs set aside come back; reports for those days rebuilt.
- The fitness score and VO2 progress use the current watch's VO2 max (Samsung's on Samsung days), and never trend
  across a switch. /v1/fitness gives Samsung's series (and none of Garmin's stale snapshot) on Samsung.
- App: each part of a multi-part workout keeps its own type; workouts, routes, heart rate and sleep each work with
  their own permission. Runs without Garmin's Training Effect show the app's training load; the power:HR tile only
  with power. Wording that named Garmin for data from either watch now follows the watch.
- HRV from Samsung: skipped for now (only via a watch app with the Sensor SDK).

## Galaxy Watch connector (2026-10-13, v0.54.0)
- Server fixes after the first real upload (same day, no new app): 1 km splits built from the samples (Samsung keeps
  no laps); Samsung's per-run VO2 max kept as `samsung_vo2max_running`, shown on Samsung runs and as "Samsung's VO₂ max"
  in Cardio while Samsung is the watch, never mixed into Garmin's series; resting HR only from days the watch was worn
  overnight (6+ readings midnight–6 am); switching between Garmin and Samsung no longer starts a device era (the era in
  force carries on; a new watch of the same maker still restarts it), and trends mark the switch date. A daytime-only
  Samsung resting HR (64) had replaced Garmin's 50 on 2026-10-13; restored from Garmin's raw record.
- Settings › Your watch: Garmin or Samsung Galaxy Watch, from today. Every switch is kept with its date
  (`watch_history`). A day's data comes from the watch that was current that day; earlier data stays.
- With the Samsung watch, the app reads Samsung Health (Samsung Health Data SDK) and uploads to `POST /v1/samsung`:
  on every refresh, from the background worker (when it runs), and on Sync. The first upload reads a year of runs and
  sleep and two months of all-day heart rate; after that, from 2 days before the last upload. One run per request.
- Server (`samsung.py`): runs become 1-second samples (heart rate, speed, cadence; distance from speed scaled to the
  watch's total; altitude from the route), the simplified route and the start point for weather; sleep from its
  stages (time awake left out; naps under 3 h in the daytime); resting heart rate as the day's lowest 30-minute
  average from at least 24 readings (Samsung doesn't share its own).
- Samsung data for a Samsung day goes into the stream the analysis reads; data from other days is kept under source
  `samsung`, outside it. A Garmin run starting within 5 minutes of a Samsung run on a Samsung day is set aside
  (`garmin_aside`), not deleted. Garmin's sync pauses while Samsung is the watch and never fills a Samsung day.
- A new watch starts a device era (by device ID), as a new Garmin watch did, so baselines rebuild from the switch.
- Not from Samsung: HRV, running dynamics, power, laps, Garmin's training scores. nginx body limit 1 MB → 16 MB.

## Samsung Health check (2026-10-13, v0.53.0)
- Galaxy Watch support starts with a check: Settings › Your data › Samsung Health check reads what Samsung Health on the
  phone shares through the Samsung Health Data SDK 1.1.0: the latest run in detail (log points and spacing; heart rate,
  speed, cadence and power; GPS route and altitude; climb, VO2 max), workouts over 30 days and a year, all-day heart rate
  spacing, sleep stages and score, skin temperature, blood oxygen and Energy Score. Read only; Copy report to share it.
- Samsung has no cloud API, so a Samsung connector has to read on the phone and upload. Until Samsung approves the app
  as a partner, Samsung Health needs developer mode ("Developer Mode for Data Read"). No HRV or resting HR from Samsung.
- The SDK AAR is Samsung's licensed download, not committed (public repo): put `samsung-health-data-api-*.aar` from
  developer.samsung.com in `app/libs` to build. The SDK doesn't run on emulators (it reports Samsung Health missing).
- Decided for switching watches: a setting picks Garmin or Samsung; history from both is kept; on a day both have data
  the watch current that day wins (a run recorded by both shows once); baselines blend, with the switch date marked.

## AI hidden when it's off (2026-10-12, v0.52.1)
- With "AI coach and summaries" off in Settings, nothing AI shows anywhere: no "Get AI input" button or AI card on a run,
  no coach on Today or Insights, no AI summary on Compare or Trends. The Settings section stays, to turn it on. The
  app keeps the server's settings in its cache (refreshed with everything else) and hides AI until it knows it's on.

## AI: your own key only (2026-10-11, v0.52.0)
- AI runs only with the runner's own OpenAI key (the server's key stays switched off), on gpt-6.1-sol only: no model
  choice (the setting and the allowed-models list are gone; `ai_config` always uses `narrative.DEFAULT_MODEL`).
- Gemini Nano (on-device AI input) removed: on the S26 Ultra the download/enable path kept failing. The ML Kit library,
  its keep rules, the setting and the server's prompt/local-answer endpoints are gone.
- Messages (snackbars) sit above the floating bottom bar on every screen; they were hidden behind it.

## Gemini Nano in release builds, server AI off (2026-10-11, v0.51.1)
- Release builds: R8 had broken ML Kit's setup (it finds classes by reflection), so the Gemini Nano status check threw a
  NullPointerException and the phone option stayed hidden even on supported phones (seen on a Galaxy S26 Ultra).
  Keep rules for ML Kit in proguard-rules.pro; the release build now answers like the unshrunk one.
- Settings always shows "Where AI input is written" with the AI coach on, with what the phone reports about Gemini Nano
  (and the error when asking failed), so "unsupported" can be told from "couldn't ask".
- Server AI switched off (`"server_ai_enabled": false` in data/secrets.json, read by `config.server_openai_key`): AI runs
  only with a runner's own key or on the phone. The server's key stays stored; set the flag to true to turn it back on.

## AI input on the phone, plain AI errors (2026-10-11, v0.51.0)
- Settings → AI coach → "Where AI input is written": on the server (OpenAI) or on this phone (Gemini Nano, through ML
  Kit's GenAI Prompt API, `com.google.mlkit:genai-prompt` 1.0.0-beta4). Offered only where the phone has Gemini Nano;
  choosing it downloads the model first when needed. On the phone, "Get AI input" fetches the run's prompt
  (`GET /v1/activities/{sid}/ai/prompt`: the same evidence bundle and instructions, with the output shape spelled out),
  runs it on the phone, and posts the answer (`POST …/ai/local`), which the server checks exactly like its own (format,
  evidence ids, numbers, wording; wrapped JSON is unwrapped) and keeps. In this mode the server never sends that run to
  OpenAI and skips the automatic input after a sync. The coach and summaries stay on the server.
- AI failures say why: a rejected key ("The server's OpenAI key was rejected …" or "Your OpenAI key …"), rate limits,
  connection problems (`ai_errors.py`), on the run card too (it used to say "didn't pass the app's checks" for every
  failure).
- Found: since 2026-10-11 the server's OpenAI key is rejected (HTTP 401) for every AI feature; it needs a new key.

## Route progress band search (2026-10-07, v0.50.3)
- The shared heart-rate band is searched over every whole-number centre across the route's runs, not only centres equal
  to a recorded average (runs at 137 and 143 bpm now share the 140 ± 3 band).

## Route progress compares like runs (2026-10-07, v0.50.2)
- A route's progress now compares individual runs within one shared heart-rate band (±3 bpm, the band holding the most
  runs), earliest two against latest two, at least 4 weeks apart; matching averages of different runs no longer count.
  The claim names the band and how many runs are in it. Live: Route 1, 9 runs at 155–161 bpm, 6:02 → 5:44 /km; Route 4's
  earlier claim no longer qualifies.
- Corrections saved in the first format (`not_route`) are still honoured (none existed on the server).

## Routes review fixes (2026-10-07, v0.50.1)
- Direction: following one route along another now advances with the distance travelled (150 m per 50-m step, plus the
  stretch spent in a detour, at most a third of a loop), so a short loop run the other way can't match by reaching round
  it. This also fixed a split: the old 1.5-km look-ahead jumped between an out-and-back's overlapping legs; on live data
  two groups of the same route (4 + 7 runs) are now one (12).
- Corrections are stored as pairs of runs that aren't the same route, so "different route" works for a route's first run
  too and survives regrouping.
- Unknown weather or run kind stays unknown and is left out of progress claims; the wording says what the filter is
  (hot with hot by the estimate's threshold), not "same conditions".
- The route sheet draws the route's outline (a shape in a unit box, no coordinates) with its start marked.
- App: route rows accept unknown weather and kind (a null there had made the routes list fail to load).

## Repeat routes, pace at your usual heart rate, endurance by length (2026-10-07, v0.50.0)
- Repeat routes (`routes.py`): each run's simplified route (a point every 50 m, rounded to ~11 m) in `route_shape`,
  kept as long as the run; the full GPS track is removed from the stored raw Garmin details as soon as it's made
  (`sidekick backfill-routes` did this for runs synced before). Matching is by geometry: distance and area only
  shortlist; two runs are the same route when each covers 95% of the other within 40 m and following one along the other
  goes forward (loops started elsewhere match, the opposite direction doesn't, an out-and-back matches itself, small
  detours fit). Only confident matches group; "This run is a different route" takes a run out for good. Progress is a
  separate step: same kind of run, same conditions (hot with hot), similar heart rate. On the run screen and in Your
  records. Live: 6 routes covering 20 of 31 runs.
- Training numbers: "Pace at your usual heart rate" (steady, level runs whose average was within 4 bpm of the reference;
  same watch; hot with hot; no extrapolation) and "Endurance by run length" (drift by duration group, 3+ runs each).
  Steady-stretch selection is shared with cardio fitness. A trend ("than on …") needs a point 4+ weeks earlier.

## Training numbers, review fixes (2026-10-07, v0.49.1)
- "Fitness, fatigue and form" is now "Training load balance": recent load against usual, bands named for what they
  measure and marked as the app's rules of thumb; no race-readiness or "building fitness" claims; after 10+ days
  without a run it says so ("Little recent training").
- Heart-rate recovery keeps every effort with continuous heart rate through the minute, whatever its drop; each session
  records whether recoveries were walked or jogged, and only like is compared with like.
- Climbing speed never spans a gap of more than 10 s in the recording; an older climb is labelled "best in the last
  year", and each climb shows its length and grade. Recovery and climbing appear in the app only once there's data.

## Training numbers (2026-10-07, v0.49.0)
- Insights → "Training numbers" (`GET /v1/numbers`, `numbers.py`), each with its history in a sheet (curve with better
  always up, recent values, runs open):
  - Lactate threshold: Garmin's heart rate and pace, weekly over the last year (Garmin's speed is in tenths of m/s).
  - Fitness, fatigue and form: the readiness load model's 28- and 7-day loads; form = (fitness − fatigue) / fitness,
    bands +20 / −10 / −30%.
  - Race predictions over time: Garmin's daily predictions, last 6 months.
  - Heart-rate recovery: the drop over 60 s after hard efforts (60+ s fast against the run's easier quarter, ending in
    zone 4+, followed by a slower minute), median of 2+ per session. Measured while moving; experimental.
  - Climbing speed (VAM): the run's best climb over 3–10 min at 3%+ and 20+ m (longer when about as fast). Also on the
    run screen's hills check and as a record ("Fastest climbing").
- Sync reads Garmin's threshold and prediction histories with the fitness numbers; failing on them doesn't fail a sync.

## Cardio fitness, experimental (2026-10-06, v0.48.0)
- Insights → Fitness → "Cardio fitness (experimental)" (`GET /v1/cardio`, `cardio.py`): the evidence about aerobic
  capacity side by side, never blended (they share inputs, so agreement wouldn't add certainty):
  - From your runs: ACSM running equation (flat, recorded speed) against heart-rate reserve (Swain's VO2-reserve form),
    per qualifying run: steady, outdoors, known and not hot weather, ≤10 m/km up and down with a level stretch,
    20+ min after a 10-min warm-up, 90%+ valid heart rate, 80% of the time within 50–90% of heart-rate reserve. The
    recent median, the run-to-run spread (variability, not accuracy), how much a 5-bpm-lower maximum moves the same
    runs, and every run left out with its reason.
  - Questionnaire-based: Jackson et al. 1990 BMI model with its own inputs: the NASA/JSC activity rating in its published
    wording (dated answer), height and weight (Garmin's or yours, dated), age and sex.
  - Running performance: Daniels' VDOT from the best 5 km+ stretch, never compared with the VO₂ estimates.
  - Garmin's VO₂ max (newest reading, via `scores.vo2_on`).
  - VO₂ estimates are placed among people of your sex and age (Cooper Institute ratings; FRIEND to come once its table
    is taken from the paper). Notes list possible reasons for disagreement without diagnosing one.
- Maximum heart rate: yours when set (dated), else the higher of Garmin's setting and the highest held over a full
  minute (time-weighted, continuous readings only).
- Heart rate: readings outside 30–240 bpm (a strap's 0 or 255) are gaps everywhere samples are read, not just here.
- Garmin's profile weight is now read (with height) for the questionnaire.

## New-record moments and record history (2026-10-06, v0.47.0)
- A run sets a record when it beats an earlier best (the first value in the history isn't a "new best"; for records
  Garmin also keeps, its older all-time record is the bar). `trophies.progressions` holds each record's improvements;
  `/v1/activities` gives each run the records it set.
- Activities: a run that set a record wears a trophy and says "New best: …". The new-run notification leads with it
  ("New record: Fastest 5 km 27:31").
- Your records: tapping a record opens its history: the value, its age comparison, a curve where better is always up,
  and each earlier best with its date, opening its run.

## Records, sync without cooldown (2026-10-06, v0.46.0)
- Activities → trophy icon → "Your records" (`GET /v1/trophies`, `trophies.py`): fastest 1 km, mile, 5 km, 10 km, half and
  marathon (the faster of Garmin's all-time personal record and the app's fastest stretch within a synced run), longest
  run, longest time running, most climbing, biggest week, highest VO₂ max, lowest resting heart rate, highest overnight
  HRV, and Garmin's step records and goal streaks. Each says where it comes from and opens its run when the app has
  it; age comparisons where a published reference exists (age grade for 5 km to the marathon, VO₂ max and usual
  resting heart rate against age and sex). Garmin's personal records are read with its fitness numbers (after new runs,
  else every 3 hours).
- Sync: no cooldown of the app's own for anyone (only Garmin's "please wait" holds a sync). A manual sync that finds
  another one running (the hourly job) waits for it, up to 4 minutes, then syncs, instead of ending with nothing.
- Run screen: when aerobic decoupling can't be measured (under 20 minutes after the warm-up, or too little heart rate),
  the card says why instead of not appearing.

## History replay (2026-10-05, v0.45.2)
- `sidekick/replay.py` (`sidekick replay [SCENARIO ...]`, and `tests/test_replay.py`): ten made-up runners played
  through the real pipeline one morning at a time (sync, reports, Today via `today_view.enrich`, the same code the API
  uses): a steady routine, a growing long run, a week ill, a two-week break, nights without the watch, a hot humid
  spell, out-and-back hills, heart-rate dropouts, a half-marathon build with taper and race, and the days after a
  10K. Runs happen in the evening, so each morning sees only what it would have. Every morning is checked for
  consistency (headline vs what's allowed, next run vs readiness, week plan vs next run, race phase, strain vs hard
  training) and each scenario for coach sense; the test also checks that every check actually met its case.
- What it found and fixed:
  - Back from illness, the next morning said "Ready to train": now the first 3 days after a "not feeling well" or pain
    check-in allow easy at most ("you were unwell in the last few days: ease back in").
  - A night without the watch reused the previous night's HRV, resting HR and sleep as last night's (readiness 93):
    now they're "Not measured last night" and readiness is unavailable when none were recorded (readiness-1.9).
  - The race highlight said one phase (by days to the race) while the week plan said another: Today now uses the
    week's phase throughout (recovery after the race excepted).
- Limits: checks are coach sense and internal consistency, not physiological validation; notifications (built in the
  app) and the AI coach aren't replayed.

## Review fixes and sync hint (2026-10-05, v0.45.1)
- Garmin: connecting again clears a "connect again" state before the first sync (it used to stop that sync without
  trying the new tokens). The Garmin account a user's data came from is kept with the data (`garmin_profile_id`), and
  connecting a different Garmin account is refused (switch = delete everything first), so two people's history never
  mixes.
- Readiness 1.8: one weak part alone is a real floor on the final score, also when other parts are missing (HRV 0 with
  sleep 60 and nothing else was 30 → rest; now 50 → easy).
- Heart-rate coverage: valid heart-rate time must cover 75% of the run's moving time in one step (two 75% checks in a
  row let about 56% through), in the intensity insight, run checks, weekly focus and strain.
- App: while "not feeling well" isn't in the server's briefing yet, the readiness sheet shows the same rest as the card,
  and the AI coach is held back on Today and Insights. The sync progress says it runs on the server (you can leave the
  app) and that a first download takes a few minutes.
- First live Garmin connection from the app (phone sign-in, ticket to the server): worked; the first sync took about
  5½ minutes for 34 days and 30 runs, the rest of the 90 days fills in through the hourly syncs.

## Connect Garmin from the app (2026-10-05, v0.45.0)
- Garmin is connected from the phone: Settings → Garmin → Connect (and by itself right after signing in when the
  account has no Garmin connection, with "Skip for now"). Garmin's own sign-in page opens in the app, so the password
  and any two-factor code go only to Garmin, from the phone's address (the server no longer signs in to Garmin and
  can't hit its sign-in limits). Garmin returns a one-time ticket; the app sends only that to `POST
  /v1/garmin/ticket`, and the server exchanges it for Garmin's renewable tokens, kept in the user's folder, then
  starts the first sync. One Garmin account per app user (by Garmin profile id); a failed relink never replaces a
  working connection. Status has `garmin_linked`.
- Settings → Garmin → Disconnect (with a confirmation) removes the connection; downloaded data stays. When Garmin ends
  a connection, the row offers Connect again. `sidekick garmin-login` still works on the server as a fallback.
- Still unofficial Garmin access (the official OAuth route waits for Garmin's approval).

## Google sign-in, account admin (2026-10-05, v0.44.0)
- Google sign-in is on: the Web OAuth client ID is in the app build and on the server (the Android clients, release
  and debug, match by package name and signing key). Invite-only as before.
- `sidekick users disable|enable EMAIL|ID`: a disabled account's sign-ins end at once, it can't sign in again and the
  hourly sync skips it; its data is kept. `sidekick users delete EMAIL|ID --yes` deletes an account and its data.
  Neither works on the owner. A refused Google sign-in shows the server's reason (not invited, or disabled).
- `/usr/local/bin/sidekick` on the server (`deploy/sidekick`) runs the admin CLI from anywhere.

## Android review round 4 (2026-10-05, v0.43.1)
- Server address: the saved token is never sent to a new address. A new server needs its own token (the sheet says
  so and Save waits for it), and it's checked there before anything is saved, so a wrong address can't sign you out.
- A save says "Saved" once the server has it; the refresh afterwards runs on its own, so its failure isn't reported
  as the save's and Save isn't held disabled by it. Which sheet is open, and its error, live in the view model: a save
  finishing after a rotation still closes its sheet, a slow save never closes a different one, and an old error
  never shows in a newly opened sheet. The model dialog shows its error too.
- Sign-in: too many tries reads "Wait a minute and try again". Garmin wording: members are told to tap Connect only
  when official Garmin sign-in is available (otherwise to ask the owner); "not configured" no longer says expired.
- "Not feeling well" follows the server's `decision.unwell_applied` instead of checking a rule ID in the app.
- Remaining big decodes run off the main thread; the ETag map is bounded (200) and cleared with the cache and on
  sign-out; sign-out waits at most 5 s for the server; a zero weekly target no longer makes a NaN progress bar.
- Still waiting on you: the Google Web client ID (GOOGLE_WEB_CLIENT_ID) for Google sign-in.

## Third review round (2026-10-05, v0.43.0)
- Weather: on by default with a Settings switch (Settings → Weather). Off means nothing is sent to Open-Meteo; estimates
  already kept stay. Each sync now looks up to 30 runs, the sync's own first and then recent runs (30 days) still
  without weather, and the runs that gain weather get their reports rebuilt.
- Heat loosens the bars instead of switching verdicts off: decoupling good ≤ 8% / ok ≤ 13% on a hot day (5 / 10
  otherwise), a second-half fade ok up to 25 s/km (15). Trends leave out a run only when it's both humid (dew point
  ≥ 18 °C) and 3 °C above your median, so a temperate runner's warm summer days stay in.
- Out-and-back on a hill: when one half descends by more than 1% and the halves' net grades differ by over 1.5 points,
  pacing says "halves not comparable" and neither the focus nor the run story calls it a fade (running-1.10).
- Readiness (1.7): recovery on its own floors at 55 when the leftover is what this weekday usually leaves (the
  morning after your weekly long run), 45 when it's more than that (still easy, not rest); the recovery line says
  which. HRV scores 100 down to 10% below usual (then 3 points per %), resting HR up to +3 bpm (then 10 per bpm).
  The basis text names the floors.
- Strain (1.1): runs meant to be hard don't count as "felt harder"; a week of identical daily loads counts as
  monotonous. Race: in the taper the long run comes down with the week instead of being held at your longest.
- Server: report building locks per user, not globally; an activity list entry in an odd shape is skipped, not fatal;
  activity date ranges are validated; a blank own-key header counts as the server's key. Rate limit: per address,
  with a small bucket for rejected tokens, so junk tokens don't get buckets of their own. Garmin linking refuses when
  Garmin doesn't say which account it is and turns network errors into a message. nginx no longer logs query strings.
- App: Settings sheets stay open with your edits until the save succeeds and show the error inside; their fields
  survive rotation; a new device token is checked before it replaces the working one. An expired session goes back
  to sign-in with a note; 429 reads "Too many requests"; the server's own reason is shown (e.g. why Garmin couldn't
  be linked). Members see a reconnect message for Garmin. The race strip shows the week's phase. Notification
  switches show before the server's settings load. Cached copies still in use aren't pruned as old; an older build
  installed over a newer cache starts it fresh.

## Open items closed (2026-10-05, v0.42.0)
- Sign-ins expire after 90 days unused; `POST /v1/auth/logout` ends this device's sign-in, and Sign out calls it.
- Rate limit: 300 requests a minute per device token, 30 per address without one (`RSK_RATE_LIMIT`, 0 = off).
- A deleted user can be invited again (their used invite is renewed).
- Very long runs: Garmin details are requested with up to 10,000 samples, and a gap is relative to the run's own
  sample spacing, so a run over ~5.6 h keeps its analysis (running-1.9).
- The training-load ratio is taken as of the end of the local day, so it no longer drifts through the day
  (readiness-1.6).
- App: release builds are shrunk with R8 and resource shrinking (57 MB → 6 MB; the release APK was signed into the
  live server on an emulator and Today, a run and the AI input all loaded), the cache drops per-run and per-day copies
  not opened for 30 days, "Get AI input" scrolls to the AI card. Signing in no longer starts a refresh that the closing
  screen cancelled (with refreshes coalesced, Today's own then waited on it and showed "No briefing yet").

## Heat and strain (2026-10-05, v0.41.0)
- Weather for every new run: looked up during sync (Open-Meteo estimate, start area to about 1 km), before the run's
  report; `backfill-weather` for runs of the last 120 days. Each run's checks show the conditions.
- Heat: a dew point of 18 °C+ or feels-like 27 °C+ marks a run hot. Its drift and fade verdicts say so and aren't read
  as poor durability; next focus says heat raises heart rate. Trends compare like with like: only runs clearly hotter
  than your usual (dew point 3 °C above your median) are left out of the durability trend, the durability insight and
  the strain check, so a humid climate (29 of 32 live runs have a dew point of 18 °C+) still has a trend (report-2.6).
  No numeric "heat correction": the models are rough, so the app says it instead.
- Strain warning (`strain.py`): two or more of a load jump (1.3×), the same load every day (monotony 2+ in a heavier
  week), cadence 3+ spm lower or heart rate 5+ bpm higher at your usual paces (hot runs left out), runs feeling hard
  while heart rate stayed easy. Shown first in "Stands out"; a nudge toward an easier day, never a diagnosis.

## Re-review fixes (2026-10-05, v0.40.1)
- Sync: a day Garmin can't read is skipped for real (days are read lazily, so the guard now covers the reading), and
  the backfill goes day by day past it instead of failing every hour. A sync only frees its own lease.
- Readiness: back to comparing leftover effort with the usual of all recent days, so the day after a weekly long run
  or a weekly hard session shows as still recovering; on its own that holds the day to easy (50+), never to rest
  (readiness-1.5).
- Hill adjustment: gentle linear rules on shallow grades (about 3.5% harder per 1% up, 2% easier per 1% down, at most
  15%), never more than Minetti; the weekly focus and the run's pacing finding use the one fade (running-1.8).
- Garmin linking is finished by the app, signed in: the callback page hands Garmin's answer to the app, and the server
  links it only to the user who started it, so a forwarded link is refused. The hourly AI job uses the allowed models.
- App: the device token is checked before it's saved; sign-in errors show a message instead of crashing; the time
  zone step can't block a refresh and resets for a new account; plain error messages; decoding off the main thread;
  clearer wording when the server's Garmin sign-in expires.
- Dates outside 2000 to a year ahead are refused (422) before anything changes.

## Settings redesign (2026-10-05, v0.40.0)
- Settings is a short list of sections (Account, Appearance, Training, Notifications, AI coach, Your data, About);
  only a Garmin problem shows at the top. Training, Race, About you, the morning window, the server and your own AI key
  each open a sheet with its own Save; closing one with unsaved edits asks "Discard changes?". Switches, units, theme
  and the AI on/off save at once.
- Proper pickers: race date and birth date (Material date picker), the morning window (time picker), the race target
  as h / min / s, the AI model from the server's allowed list (`ai_models` in /v1/settings; any model with your own
  key), and the time zone with "Use this phone's".

## Race week and focus on Today (2026-10-05, v0.39.0)
- Today: readiness, the next run, then (with a race goal) the race week as one row of the week's days (done, today,
  missed, planned, rest) with the minutes done against the target, and this week's focus as one line with its status.
  Each opens its full card in a sheet (sessions; focus details or choosing one). Then Health and Fitness.
- Insights no longer shows them: it's for looking back (stats, coach, fitness, weekly review, insights, Compare, Trends).

## Metric fixes (2026-10-05, v0.38.0)
From the full-code review, batch 2:
- Readiness: leftover effort is compared with the same weekday over the last 6 weeks (a regular Saturday long run makes
  Sunday normal for you); one weak overnight reading alone can hold the day to easy (50) but never to rest (readiness-1.4).
- Hill-adjusted pace: downhill credit is limited to 15% easier than flat (Minetti alone gave −10% at 4:00/km as
  6:41 flat); decoupling isn't valid when a half descends and the halves' net grades differ by over 1.5 points (an
  out-and-back hill) (running-1.7).
- Race week: the week after a race keeps its easy running days; taper and other phases count whole weeks before race
  week (a 5k taper had lasted one day); a week's plan uses the phase of its first day, so it doesn't change mid-week.
- One fade: every "faded", "negative split" and "even" uses the same halves (first and last half of complete splits)
  and ±5 s/km, on hill-adjusted pace where the samples allow it.
- Shared thresholds: the efficiency step (5 s/km a month), the evening cutoff (18:00), and coverage: 90% heart rate
  for decoupling, 75% for anything judged from time in zones.

## Robustness and security (2026-10-05, v0.37.0)
From the full-code review, batch 1:
- Sync: one day or activity Garmin sends in a shape we can't read is skipped and noted ("Skipped 1 record…"); any other
  error ends the job as a failure with a back-off instead of leaving it unfinished. The hourly job catches each user's
  failure so the users after them still sync. One sync per user at a time across processes (a lease in the user's
  database); reports and laps are written so two writers can't collide.
- Google sign-in: a linked account is matched only by its Google ID; another Google account with the same email can't
  take it over.
- Garmin linking (official OAuth, not live yet): the app opens a one-time /begin link (2 minutes) that ties the flow to
  that browser with a cookie; the callback needs it. A Garmin account already linked to another user is refused.
- AI: only allowed models run on the server's key (`RSK_AI_MODELS`, plus the default); your own key may use any. A
  daily cap across all users on the server's key (`RSK_AI_MAX_CALLS_ALL`, 300).
- App: any unexpected error shows a message instead of crashing; a response the app can't read is rejected before it's
  cached, so good saved data stays; chart data is read defensively.
- VO₂ highlight uses the same freshness rule as fitness progress and says the real span ("in 7 weeks"). A new
  account takes the phone's time zone. Messages no longer tell you to run backend commands. The race week title uses
  the race's name, not text cut from the headline.

## Manual sync cooldown (2026-10-05, v0.36.0)
- The server won't call Garmin for a manual sync within 15 minutes of the last sync that ended well (manual or the
  hourly job), 2 minutes after a failure, 30 minutes after Garmin rate-limited us, or before Garmin's own back-off
  ends (`sync.next_manual_sync`). It answers with `next_allowed_at`; `/v1/status` carries `sync_next_allowed_at`.
  Demo data is exempt. Pull-to-refresh only reloads from the server and isn't limited.
- App: "Sync Garmin" and "Get new runs" show "Next sync 14:32" and stay disabled until then; a refused sync says when.

## Follow-ups (2026-10-05, v0.35.3)
- The plan's duration also caps a session made easier when there's no easy-pace estimate: it becomes a time ("about
  10 min") with no guessed distance (a 10-minute plan had become 9 km).
- Race day with the easy-only caution: the target-pace instruction is dropped.

## Plan → readiness → next run, end to end (2026-10-05, v0.35.2)
From the v0.35.1 review, with tests that follow a session from the week plan to the next run:
- A session made easier (held back, or steady instead of tempo) keeps the plan's duration at most; it no longer falls
  back to a typical run's length (a 10-minute tempo had become a 60-minute steady run).
- Race day while today allows only easy or rest: the race stays the day's event, with a caution on the card and in the
  notification ("Readiness says easy only… run it easy or start well below your target pace").
- An optional session (the week's target met) is marked optional on the next run, with the reason, and in the
  notification.
- "Not feeling well": uses the phone's date, applies on the phone straight away (rest, no score shown) and says
  it's pending until the server has it; the AI coach is asked again. Wording matches the button everywhere.

## Run screen alignment (2026-10-05, v0.35.1)
- Run header: every tile label takes two lines, so all six tiles are the same height. Aerobic decoupling: one-line
  labels and equal-height tiles; the "power:HR on hills" note moved to the line below.

## One decision policy, coverage, race week, "Not feeling well" (2026-10-05, v0.35.0)
From the v0.34.1 review:
- One policy decides what today allows (rest, easy, steady, hard: `decide.allows`), and both the readiness headline
  and the next run follow it: Moderate (60–74) means steady at most, so a planned tempo or intervals becomes steady and
  the card says "Good for a steady run". The card shows the reason when intensity is held back (e.g. Garmin's timer).
- Intensity insight: the samples must cover 90% of the activity's moving time, and heart rate 90% of the samples.
- Race week: sessions still to run share what's left of the target; once it's reached, they become optional, short
  and easy.
- Fitness progress: one improving signal with the rest stable reads "Early signs of improvement"; the sheet shows
  signal agreement ("1 of 3 signals agree") instead of a confidence word (progress-1.3).
- Units: the next run's pace is sent as a number and shown in miles when set; the morning notification uses the
  runner's units.
- Today: readiness and the next run together at the top, then Health and Fitness, each with its time horizon.
- "Not feeling well?" on the readiness card: one tap marks the day (an illness check-in, the existing R0 rule: rest,
  readiness capped), tap again to undo. Never asked for.
- Trends (and its AI summary) load only when that tab is opened; a full refresh that's already running isn't started
  twice.

## "Aerobic decoupling" everywhere (2026-10-05, v0.34.1)
- The "How it went" check, the run's analysis item, the durability signal, the durability insight and the export now
  say "Aerobic decoupling" instead of "Heart-rate drift" / "Drift"; explanations keep "heart-rate drift" as the plain
  description (report-2.5).

## Readiness cap, Garmin cross-check, layout (2026-10-05, v0.34.0)
- Readiness 82 "High" the morning after a threshold run (Garmin: 1, 52 h recovery): the weakest part now caps the score
  25 points above it (was 40), giving 70 "Moderate". Garmin's own readiness and the time left on its recovery timer
  are shown in the readiness sheet; a timer of 24 h or more holds intensity back in the day's decision (readiness-1.3).
- Today: readiness, then Health and Fitness, then the next run.
- The navigation pill floats over the page with nothing behind it; tab lists scroll underneath it.

## Themes (2026-10-05, v0.33.0)
- Settings › Display › Theme: Forest (design B, hand-tuned), Ocean, Plum, Coral, Graphite, each expanded from its seed into
  a full Material 3 tonal scheme (MaterialKolor, a port of material-color-utilities; TonalSpot), and Dynamic (the phone's
  wallpaper colours, Material You). Appearance: System, Light or Dark. Stored on the phone.
- Every theme keeps B's layout: in light, white cards on the scheme's tinted ground; the hero cards take the primary
  colour (primary container in dark); Health and Fitness tiles take primary and tertiary containers (Forest keeps its
  blue and coral).

## Remaining review items (2026-10-05, v0.32.1)
- Compare uses the same dated VO₂ reading as the Fitness score (`scores.vo2_on`), not Garmin's raw snapshot.
- Race-week baseline: weeks before synced history are left out; a week with no running after that counts as a break.
- Time-weighted averages: the export's minute table (pace, cadence, power over moving time; HR and elevation over time)
  and split cadence (running-1.6).
- Insight confidence: "consistent" needs the earlier verdict to point the same way (`reports.pattern_key`).

## Redesign B, "Expressive Tonal" (2026-10-05, v0.32.0)
- Theme: a fixed deep-green and coral palette on a sage background with white cards (light and dark); dynamic
  wallpaper colours are off. Fonts: Unbounded for numbers and headlines, Plus Jakarta Sans for text (both bundled,
  OFL). Floating rounded navigation bar.
- Today: readiness first, in a green hero card with the number in a scalloped badge; then the next run as chips;
  Health and Fitness as tonal tiles with a bar; the latest run as one card.
- Run screen: green header with distance, moving pace in a white pill and six number tiles; aerobic decoupling in its
  own card; capsule split chart with the hilliest km and its flat-equivalent pace called out above the table.
- Removed the score rings (`ScoreGauge`, `ScoreRing`), no longer used.

## Calculation review fixes (2026-10-05, v0.31.0)
From the v0.30.2 review, each reproduced first (`tests/test_calc_review.py`, `test_readiness.py`):
- Readiness recovery counts only the effort left above what's usual for you at that time of day (the median of the last
  4 weeks), so a steady daily routine no longer pins readiness to Low. Load queries use the local calendar day, and runs
  end on elapsed time (readiness-1.2).
- Fitness progress: VO₂ needs two different dated readings (the newer within 2 weeks, 3+ weeks apart); efficiency
  follows the insight's rule that the trend and the half-by-half medians agree; durability looks at each run's newest
  report revision only (progress-1.2).
- Race week: two runs on one day both count toward the day and the weekly target.
- Intensity insight: only runs with heart rate over 90% of their moving time.
- Consistency insight: weeks before the first synced run are unknown, not zero.
- Four-week pace: only runs with both distance and moving time.
- Best efforts: end-anchored segments are tried too, so the fastest one is found (running-1.4).
- "Steady" runs: steady when either the recorded pace or the hill-adjusted pace is even (1-minute CV ≤ 0.08). Live runs
  had pace CV 0.04–0.06 but hill-adjusted CV 0.08–0.14 from elevation noise, so almost none counted for drift and
  durability (running-1.5). Hilly runs still have their own check.

## Wording: VO₂ estimate, aerobic decoupling (2026-10-04, v0.30.2)
- Garmin's VO₂ max is called a device estimate everywhere it trends: the progress signal is "Garmin VO₂ estimate", a
  dip shows as "Estimate dipped" (not "Declining"), and the Fitness trend says it's an estimate trend, not a measured
  decline. A VO₂ dip on its own can no longer make the progress verdict "declining" (progress-1.1).
- Run screen: "drift" is now "Aerobic decoupling" (pace:HR and power:HR) with an info tooltip: lower is better, under
  5% held steady, power:HR is the better read on hilly runs.

## Run header (2026-10-04, v0.30.1)
- Run screen: moving pace sits beside the distance; Garmin's aerobic training effect joins heart rate and VO₂ max;
  Garmin's training readiness on the morning of the run joins the drift row (report-2.4, `garmin_readiness_day`).

## LLM export v2, run context (2026-10-04, v0.30.0)
- Run screen: the "Run type" card opens an optional sheet: what the run was meant to be (recovery, easy, steady
  aerobic, long, tempo, threshold, intervals, race, progression, free run, other), a target, perceived effort, overall
  feel, primary and secondary limiter, health and private notes. Never asked for; blanks are left out.
- A stated intent wins everywhere: next focus (an HR cap in the target is checked against the run; steady kinds get
  no "start slower" advice; fade is hill-adjusted), the run checks (steady aerobic is judged on its own), the run AI
  (run-ai-1.2: judged against the intent; effort, feel, limiters and health go as fixed words, never target or notes)
  and the export. The data-based type is kept beside it with a confidence and the reason (report-2.3).
- Export (Runner Sidekick LLM Export v2): athlete context, data-based classification, not-moving time, Open-Meteo
  weather (start position rounded to about 1 km, labelled as an estimate), descent per km, hilliest km, the
  first/second-half table behind decoupling, running dynamics (Garmin averages plus halves from the samples), recovery
  context from that morning, similar runs with deltas against their median, the fitness trend, AI input as intent /
  subjective report / objective highlights / context / questions, the app's AI interpretation in its own section,
  minute-by-minute folded in `<details>`, data provenance, schema, app version and an ISO timestamp.
- Samples now keep ground contact time, stride length, vertical oscillation and ratio, and body battery; Garmin's
  per-run averages (power, normalized power, dynamics) are kept too. `backfill-samples` re-reads both.

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

## Fitness age from several VO₂ estimates; HUNT formula (2026-10-19, v0.66.0)
- A fifth piece of evidence on the Cardio page: the HUNT non-exercise VO₂ formula (Nes et al. 2011) from age, sex, waist,
  the watch's resting heart rate (4-week median, ≥ 7 days) and three activity questions (how often, how hard, how long).
  The points per answer of its activity index aren't verified against the original table (`HUNT_WEIGHTS_VERIFIED =
  False`); the page says the estimate is provisional. New dated settings: `profile_waist_cm`, `hunt_frequency`,
  `hunt_intensity`, `hunt_duration` (Cardio page › Your answers).
- `cardio.combined`: the median of the estimates present (ours from runs, the watch's, HUNT, the questionnaire), with
  each input and the spread. Runner Sidekick's fitness age now uses it instead of the single VO₂ value; the Fitness
  score still follows the VO₂ setting (cardio-0.5).

## HUNT fixed; fitness age back on the chosen source; no gradient jump at 1% (2026-10-19, v0.67.0)
After the round-4 review:
- HUNT's activity index now uses the model's own coding (frequency 0/0/1/2/3, duration 1/1/1.5/1.5, intensity 0/5/10,
  as reported by US DOT report 55934 applying Nes et al.); 0.66.0's points were about 4× too small.
- A seated resting pulse answer (`resting_pulse_seated`), as the study measured. Without it, HUNT uses the watch's
  overnight value and is labelled adapted (it reads high: 10 bpm ≈ +1.5) and stays out of the median.
- Fitness age goes back to the VO₂ source chosen in Settings; the median of the estimates stays on the Cardio page as a
  comparison only (cardio-0.6). Medians use unrounded per-run values.
- Gradients ease in from 0.5% to 1.5% instead of a hard cut at 1% (0.99% → 0, 1.01% → +3.5% speed before;
  running-1.12). ±1 m flat noise still about +0.03%; a 50 m rise over 300 m reads +1.55% against +1.88% exact.

## Round-5 corrections (2026-10-19, v0.68.0)
- Each VO₂ estimate is placed in its band and percentile by its unrounded value (46.45 had read as 46, below the
  Excellent band's 46.4); the ±5 bpm sensitivity recalculates from unrounded heart rate and cost (cardio-0.7).
- HUNT wording: "15 to under 30 minutes" (30 belongs to 30–60 only); a seated pulse is "measured as the study did",
  not "the formula as published" (the activity coding is still from a secondary report).
- Cardio page: the median of the estimates is a collapsed technical detail under the evidence.

## Round-6 wording; VO₂ tile follows the setting (2026-10-19, v0.68.1)
- Seated pulse: "a fresh heart-rate measurement on your watch (not its daily resting heart rate), or count your pulse for
  60 seconds"; named "self-measured", with "the study measured resting heart rate by ECG after 5 minutes of rest"
  (cardio-0.8). It still replaces the overnight value without the "adapted" label.
- Fitness age (ours) without a value names the chosen source ("Needs our VO₂ max estimate (3 qualifying runs)", or the
  watch's) instead of always "from your watch".
- Today's VO₂ max tile follows Settings › VO₂ max for scores: with Runner Sidekick's chosen, `/v1/fitness` sends its
  series (`cardio.own_vo2_series`: the median as it stood after each qualifying run, 120 days) and the tile shows it,
  where it used to show the watch's (Samsung's) even then.
- Wording: "Runner Sidekick" instead of "ours" in sentences, "Sidekick" on the chips and the run hero tile; Settings descriptions
  no longer say "this watch's runs" or "your watch's VO₂ max" for Runner Sidekick's options.
- The server address is built in (release: runnersidekick.ibarak.org; debug: the emulator's local backend) and no
  longer a setting: Settings' Server row and the sign-in screen's address field are gone (the device-token sign-in
  stays, against the built-in address).

## VO₂ max progress (2026-10-19, v0.69.0)
- Today › VO₂ max tile › sheet: a progress chart under the note, with chips for since 3 months, 6 months or a year
  ago, and the change over that period. It follows Settings › VO₂ max for scores (Runner Sidekick's estimate as it
  stood after each qualifying run, or the watch's readings). `/v1/fitness` now sends a year of VO₂ history (was 120
  days).

## Redesign: clean tiles, four tabs, full-page details (2026-10-20, v0.70.0)
- New look throughout: a neutral base (light grey / true black) with rounded tiles, each softly tinted for its kind of
  data (`Tint`, ui/theme/Theme.kt; `Tile`, ui/components/Tiles.kt): readiness green, next run orange, fitness blue,
  healthy habits purple, VO₂ teal, heart rate pink, sleep indigo, focus/race/records amber. Google Sans (OFL, bundled,
  subset to Latin + the symbols used; licence in assets/licenses). Colour themes removed (Light/Dark/System stay).
- Four tabs in a floating pill (as in Ilay for Reddit; slide along it to switch): Today, Runs (was Activities), Trends
  (was Insights: Summary / Compare / Charts), Me (was Settings, with Reports — the old Journal tab — as a page).
- Detail sheets are full pages with a back arrow (`DetailPage`): readiness, full briefing, scores, VO₂ max, race week,
  weekly focus, cardio fitness, training numbers, patterns, records, routes. "Show why", the run-type form and the
  settings edit forms stay bottom sheets.
- Nothing dropped: every data item, state and control in the pre-redesign inventory has a place (mockups:
  claude.ai/artifact/6uCRtx3eoHyYgj9F6ix7fD).
- Fixes found on the way: text outside a Surface was black in dark mode (sign-in title); status/navigation bar icons now
  follow the app's light/dark choice (they followed the phone's), also on detail pages; the refresh progress label sits
  above the tab bar instead of over the header buttons.

## Flat tile colours (2026-10-20, v0.70.1)
- Tiles are an even wash of their colour (no gradient fading to white); the readiness bar and the fill under sparklines
  are flat too. The fade behind the floating tab bar stays (it keeps the bar readable over tiles).

## Faster sync; no fade behind the tab bar (2026-10-20, v0.70.2)
- Today took ~14.5 s on the server with Runner Sidekick's VO₂ max chosen: the estimate (asked for 5 times per request)
  re-read 60 days of runs' samples each time, and the maximum heart rate a year of them. The parts computed from a run's
  samples alone (its steady stretch and the highest heart rate held for a minute) are now kept per revision of the run
  (`rp.run_key`, as the run analysis already was); weather, resting and maximum heart rate are still read each time.
- The floating tab bar no longer has a fade behind it.

## Screens load side by side (2026-10-20, v0.70.3)
- After the connection step (status, settings, the Samsung/GTII upload), the app asks for every screen at once instead
  of one after another; the progress label reads "Loading your data". The server's per-run caches tolerate two requests
  evicting at the same time.

## Watchletic connection (2026-10-20, v0.71.0)
- Me › Watch and data sources › Watchletic › Connect: Watchletic's official sign-in (OAuth 2.1 + PKCE, our server
  registered dynamically with its HTTPS callback; read-only scope) through its MCP endpoint, the route Watchletic offers
  third-party apps. As with Garmin, the callback page hands the answer to the app, which finishes the link signed in.
  Tokens per user (`watchletic_oauth.json`, 0600); refresh tokens rotate and are saved before use, one refresh at a
  time (reuse revokes the connection). Disconnect revokes; account deletion disconnects; "delete everything" includes it.
- First step only: on connect and on each refresh the server saves the tool catalog and the training context as they
  come (`watchletic_raw`), to build the importer on Watchletic's real answers. Runs aren't imported yet.
- (server, after 0.71.0) Watchletic runs come in on every refresh: each running workout not yet seen at its revision is
  exported as FIT and goes through `fit.ingest` (test recordings left out; the Samsung Health copy set aside), then
  weather, reports and AI input like any new run. First look back 90 days, in the background after connecting.
  Readiness, training context and fitness analytics are kept as they come (`watchletic_raw`). Seen workouts:
  `watchletic_seen`. Watchletic readiness has no HRV for this user (sleep and some resting HR only).

## Watchletic: full access, delete there too (2026-10-20, v0.72.0)
- The connection asks for read and write (`watchletic.write`), only so a run can be deleted in Watchletic: the run
  screen's delete dialog has "Also delete it in Watchletic" for runs that came from it, unticked by default, each time
  (preview_activity_delete, then apply with its confirmation token). If Watchletic refuses, nothing is deleted here
  either. An older read-only connection shows "Reconnect" in Me. Our client is re-registered when its scope grows.
- Imported runs remember their Watchletic workout (`watchletic_seen.source_id`); the run detail says `watchletic: true`.

## Watchletic runs: recording app and heart-rate sensor (2026-10-22, v0.73.0)
- A run from Watchletic says so ("recorded with Watchletic") and, when it used an external heart-rate sensor, names it
  ("Heart rate from HW9 17586 (external sensor)"): the FIT file only says "Heart Rate Monitor", so the name comes from
  Watchletic's device list (when it knows exactly one; else "an external sensor"). Stored on the activity
  (`recorded_with`, `hr_sensor`), in the run report (report-2.14) and in the Markdown export's data provenance.
- First real run checked: 5.04 km, 27:57, HR avg 158 / max 181 from the HW9 armband (1,674 samples), GPS, cadence 182
  spm (FIT strides doubled), 50 m climb. Beat-to-beat intervals weren't recorded (the sensor reports it supports them).
- (v0.73.1) The external sensor's connection log comes with each Watchletic run (from the diagnostics in Watchletic's
  JSON export: Bluetooth connects and dropouts, seconds into the run; the sensor's name as recorded). The run screen
  says "connected the whole run" or "dropped out at 15:00, back at 16:00". The 22 Oct run: connected throughout (no
  dropout logged); its 15–18 min dip (HR ~30 bpm down at the same pace, then back to 167) is the armband reading low,
  flagged "questionable" by the HR recording-quality check.
- Watchletic FIT audit (22 Oct run, against the original FIT and Watchletic's own JSON samples):
  cadence is right as steps (FIT 91 strides ×2 = 182 = Watchletic's figure), but Watchletic repeats the watch's last
  cadence reading in every record (two thirds of the records were over 5 s old, up to a minute), which made the
  203–221 spm minutes and the halves (184/187, above the 182 average). FIT conversion 2: in Watchletic files an
  unchanged cadence is kept for 5 s, then left out (matches the raw channel: 689 of 718 kept records within 5 s of a
  reading). Watchletic writes one lap for the whole run, so a FIT with one lap now gets 1 km splits from its distance
  samples (`samsung.km_laps`, shared with Samsung). The 15–18 min HR dip is in the original file (no gap, no zero, no
  sensor dropout logged): kept as recorded. Export: no "from Garmin" on a Watchletic run, halves say warm-up included
  and how they're weighted, a zone caveat and an HR sensitivity check when HR quality isn't good, provenance per field.
  Regression fixture: tests/data/watchletic_2026-10-22.fit (the real file without positions).

## Material 3 Expressive touches (2026-10-25, v0.74.0)
- One choice from a few is a connected button group (`ChoiceGroup`): the VO₂ progress range, Trends' Summary/Compare/
  Charts, the Runs filter, Journal's tabs, Appearance, Units, VO₂ and fitness-age source, week start, HR zones, sex.
- Options that turn on and off, or a choice that can be cleared, are toggle buttons that change shape when on
  (`ToggleRow`): running days, main goal, race distance, today's plan and its minutes. Unchosen buttons get a fill a
  step stronger than the card, or they vanish on a plain card.
- Loading: the Garmin sign-in uses the Expressive loading indicator; the sync's measured progress is a wavy bar; an
  unmeasured refresh shows the contained loading indicator; the pull-down shows the Expressive pull indicator.
- Shape badges: each reading tile on Today (sleep, resting HR, HRV, running time, VO₂ max), the latest run, and each run
  in Runs (a trophy on a sun shape for a run that set a record, replacing the trophy at the row's end). Still shapes only.
- Expressive APIs are opted into once in app/build.gradle.kts. Lint: the run day's name reads the locale from the
  configuration (the one lint error, from 0.70.0).

## Newest-run questions as a wizard; faster Garmin sync (2026-10-25, v0.75.0)
- Opening Runs asks about the newest run when nothing's been said about it yet: what it was meant to be (pre-set to
  the plan's or the data's guess), effort, how it went, what limited you, health, a note — one question per step,
  one tap moves on, every step skippable. Closing it keeps what was answered; a run is asked about once (the phone
  remembers it). Me → Notifications → "Ask about your newest run" turns it off. The run list carries `answered`.
- Garmin sync: 0.3 s between Garmin requests instead of 1 s (measured: a quiet sync 15.6 s → 6.3 s; the wait was most
  of it). The app checks a running sync every 1–2 s instead of backing off to 8 s.
- Garmin data coverage audit: ~/Downloads/garmin_data_coverage_audit_findings.md (findings only, nothing changed).

## Garmin's numbers with their context (2026-10-25, v0.76.0)
From the Garmin data coverage audit (~/Downloads/garmin_data_coverage_audit_findings.md), the top 5 plus its bug:
- What Garmin's readiness was built from: `garmin_readiness_inputs` (1 with a valid night; label = each input's
  feedback) and `garmin_recovery_time_min` (minutes, with Garmin's time). Export and briefing: "94 / 100 (high), at
  13:09, without sleep or HRV (no night on this watch), recovery time then 0 h". `asleep_measured_s` (0 kept: no
  overnight wear) qualifies resting HR as "daytime only".
- HRV against Garmin's own baseline band (`hrv_baseline_low/high`): "42 ms (balanced), within Garmin's baseline 35–47 ms".
- Garmin's training status, acute load vs its range and load focus kept per day (`garmin_status_history`), in a new
  export section "Training load and thresholds (Garmin)" with a count of the runs Garmin didn't record (other watch).
- In-run Performance Condition (0 kept; first → last, lowest) and stamina left at the end (`dyn.pc`, `dyn.stamina`),
  and the run's average HR as a share of Garmin's lactate threshold as of that day: `garmin_extra` rows on the run
  report (report-2.15), shown in the app's "watch's numbers" group and the export.
- Bug: the race goal and the AI coach read a stale Garmin prediction (10 Oct snapshot) while the Numbers sheet used the
  daily history; both now use `numbers.current_predictions` (the newer of the two).
- Backfilled from stored raw payloads (no Garmin calls): 62 days of readiness context, 59 nights of HRV band, 21 runs
  with performance condition/stamina. Export schema v2.1; every earlier line of the 25 Oct export kept, two qualified.
- Briefing: Garmin's labels show under the name (subtitle) instead of squeezed beside the number.
- Not done (need a decision): resting HR from a no-night day still enters the baseline comparison; switch-day nights.
- (v0.76.1) Garmin's resting HR from a day without a night on the watch (`asleep_measured_s` 0) is a daytime value:
  shown ("Daytime only · not compared", status `not_compared`), never compared with the usual nor part of it
  (`reports.rhr_series`, also used by readiness, fitness age and the comparison sheet). Readiness: "Not counted".
  No "switch days" exist (the user switches watches fully), so mixed-day handling isn't needed.

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

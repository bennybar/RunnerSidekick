# Analysis rules (v1)

Product heuristics, **not** validated clinical or coaching thresholds. Each constant lives in code with a
version string. Change the version whenever a value changes, so reports record which rules produced them.

## Personal baselines — `analytics/baseline.py` (`baseline-1.0`)

| Rule | Value | Rationale |
|---|---|---|
| Window | preceding 28 local days, **target day excluded** | avoids leakage of today's value into its own reference |
| Minimum history | 14 valid observations in window | below this: "learning", no comparison shown |
| Summary | median and IQR (q1–q3, linear interpolation) | robust to outliers; called *personal reference range* |
| HRV comparability | baseline uses only observations with the same `method` | doesn't mix measurement types |
| Missing days | absent rows, never zeros | |

Meaningful-change thresholds (direction of concern only):

| Metric | Concern | Threshold | Why this size |
|---|---|---|---|
| resting_hr | up | ≥ 5 bpm above median | larger than typical day-to-day noise of ~1–3 bpm |
| hrv_overnight_avg | down | ≥ 15 % below median | nightly HRV varies widely; % scales across individuals |
| sleep_duration | down | ≥ 60 min below median | one sleep cycle-ish; smaller gaps are common |

*Sustained* = beyond threshold on each of the last 3 days, each against its own baseline.
Percentages are omitted when the median is 0.

## Running — `analytics/running.py` (`running-1.1`)

- **Pace basis: moving time.** A sample counts as moving if speed ≥ 0.5 m/s. Elapsed (includes stops), moving and
  timer (Garmin `duration`) are stored separately and labelled in the UI.
- **Sample weighting:** each sample is weighted by the time to the next sample. Gaps > 10 s and stopped samples
  get weight 0. Missing HR stays `null`.
- **Splits:** source laps. A lap shorter than 95 % of the median lap distance is *incomplete* and excluded from
  split comparisons.
- **Classification:** 1-min moving-speed blocks, with the first and last 10 % trimmed. Coefficient of variation ≤ 0.08
  → steady. Source laps that include REST/RECOVERY → variable. (Uniform `INTERVAL` labels are ignored: Garmin
  labels every auto-lap that way on some devices, as observed in live data.)
- **Pace:HR decoupling:** `100 × (EF₁ − EF₂) / EF₁`. EF = time-weighted mean speed ÷ time-weighted mean HR, for
  each half (split by moving time) of the eligible segment. Positive = less efficient in the second half.
  Eligibility: steady; first 10 min of moving time excluded; ≥ 30 min remaining; valid-HR coverage ≥ 90 %
  (HR 60–220); elevation gain ≤ 15 m/km. Otherwise the reasons are shown and no number appears.
  The 5 % reference is a common coaching heuristic and is labelled as such.
  Hand-worked test: HR 150 → 156 at constant speed gives 3.846 % (`test_decoupling_hand_calculated`).
- **Similar runs:** same sport, distance ±20 %, elevation gain per km within ±8 m, both steady. Up to the 5 most
  recent earlier runs. A summary is shown only with ≥ 3 matches. Weather isn't considered.
- **Workload:** trailing 7 completed days vs the mean week of the prior 4 weeks (moving time). It's descriptive
  only. Calendar week is shown separately in run reports. There's no ACWR and no injury-risk number.
- **Session-RPE load** = RPE × moving minutes. It's a separate measure and is never combined with Garmin load.

## Recommendation rules — `analytics/recommend.py` (`rules-1.4`)

Signal groups (correlated inputs count once): `overnight_autonomic` (RHR high **or** HRV low), `sleep`,
`subjective` (check-in energy ≤ 2 or recovery ≤ 2 or soreness ≥ 4), `load` (7-day moving time > 1.5× prior weekly
mean), `sustained`. Garmin composite scores (readiness, Body Battery, sleep score) are shown but **not used**, to avoid
double counting.

| Rule | Prerequisite | State | Intensity suppressed |
|---|---|---|---|
| R0 | check-in reports pain or illness | consider_easier | yes |
| R1 | no overnight data and no check-in | insufficient_data | yes |
| R1b | no baseline yet and no check-in | insufficient_data | yes |
| R2 | ≥ 2 signal groups | consider_easier | yes |
| R4s | only `subjective` fired | consider_easier | yes |
| R3 | 1 group, no check-in | usual_plan ("go by feel") | yes |
| R4 | 1 group, check-in without concerns | usual_plan | no |
| R5 | no groups | usual_plan | only if overnight data missing |
| R1c | check-in but no overnight data | insufficient_data | yes |
| R1d | overnight data and check-in, no personal ranges, no signal | insufficient_data | yes |
| R1e | a signal (e.g. load) but no personal ranges | usual_plan ("go by feel") | yes |

"Readings look typical" is only said when overnight data and personal ranges exist (rules-1.3). With a day plan,
the suggestion names the planned session: swap it (consider_easier), keep its hard parts optional (suppressed
intensity), or go ahead.

There is no `check_in_needed` state (rules-1.4): advice never waits on the runner. Instead the morning report carries
`checkin_prompt {ask, reason}`, and the app asks one question ("how recovered do you feel?") only when no check-in
exists and the answer would change the advice: R3, R1e, R1, R1b, or any signal that hasn't already made the day easier.
The morning notification mentions the question only then. Checking in is otherwise an optional row.

A single low HRV never cancels a run by itself (R3/R4). A good score never overrides reported pain (R0).
There are no numeric pace or HR prescriptions in v1.

## Time and attribution

- Instants are stored in UTC, with the source offset kept (`utc_offset_s`).
- Activities are attributed to the **local date where they happened** (Garmin `startTimeLocal`). History isn't
  rewritten into the current zone.
- Primary sleep is attributed to the **local wake date**, and the original interval is kept. Naps are stored
  separately (`is_nap`) and excluded from `sleep_duration`.
- Daily Garmin metrics use Garmin's calendar date.

## Insights — `analytics/insights.py` (`insights-1.0`)

A fixed, pre-registered question list. The engine never searches many associations to surface the largest. Every
question is answered every time, with one of three verdicts: `pattern`, `no_clear_pattern` or `not_enough_data`.
Confidence starts at *emerging* and becomes *consistent* only if an insights report from at least 14 days earlier
reached the same verdict.

| ID | Question | Method | Minimum data | Pattern threshold |
|---|---|---|---|---|
| intensity | Time across HR zones | moving-time share per Garmin zone (zones fetched from Garmin, with provenance) | 8 runs with HR | ≥ 50 % of time in Z4–Z5 |
| efficiency | Faster at the same HR? | pace in the user's most common 10-bpm band, first 10 min excluded; Theil–Sen slope **per device** | 6 runs on one watch over ≥ 21 days | ≥ 5 s/km per 30 days and halves agree |
| pacing | Pacing habit | complete splits; positive = second half > 3 s/km slower | 8 steady runs with ≥ 4 splits | ≥ 60 % positive |
| evening_sleep | Evening runs vs sleep | nights after runs starting ≥ 18:00 vs other nights; medians | 8 nights per group | sleep ≥ 20 min or HRV ≥ 10 % difference |
| recovery | Morning after harder runs | HRV/RHR after upper-half Garmin load vs after no-run days | 8 mornings per group | HRV ≤ −10 % or RHR ≥ +2 bpm |
| consistency | Week-to-week volume | weekly moving time, last 8 weeks, coefficient of variation | 4 weeks with running | CV ≥ 0.4 |
| durability | Drift on steady runs | median decoupling over eligible runs | 4 eligible runs | median > 5 % |

Practical notes are options, never prescriptions. The only numbers they use are the user's own Garmin zone
boundaries. Confounders are listed with every insight. HR-based comparisons never cross a device change.

## Weekly review — `weekly.py` (`weekly-1.0`)

Covers a completed Monday–Sunday week in local time.
- **Volume:** moving time vs the mean of the previous 4 weeks. Flagged outside if > 1.5× or < 0.5×.
- **Intensity:** share of moving time in Garmin zones 4–5.
- **Pace at HR:** the week's median vs the previous 4 weeks, same watch only, ≥ 3 earlier runs.
- **Recovery:** the week's median vs the personal range ending the day before the week. Needs ≥ 4 measured nights.
- **Next-week focus, first match wins:** F1 pain/illness reported → F2 volume > 1.5× → F3 ≥ 70% hard (suggest one
  easy run below your zone-3 floor) → F4 light or empty week → F5 keep the rhythm.
- Reviews older than 14 days are not regenerated, so history keeps its original context.

## Trends — `trends.py` (`trends-1.0`)

Daily values are shown as measured; missing days are null, never zero. The band is the same 28-day personal range as
the morning report, restarted at watch changes. The period summary compares medians with the previous period of
equal length, and only when each has ≥ max(3, days/3) measured days. "Notable" uses the same thresholds as baselines.

## Grade-adjusted pace, best efforts, run story — `running.py` (`running-1.2`)

- **Grade-adjusted pace (GAP).** Uses the Minetti et al. (2002) energy-cost polynomial
  `C(i) = 155.4i⁵ − 30.4i⁴ − 43.3i³ + 46.3i² + 19.5i + 3.6` (J/kg/m, i = gradient). Gradient is measured over about
  50 m of distance and clamped to ±30 %. GAP speed = speed × C(i)/C(0). It's used for split "flat-equivalent" pace,
  for steady/variable classification, and for drift.
- **Drift** now uses GAP, needs a ≥ 20 min steady segment (20–30 min is flagged "short"), and excludes only runs
  above 40 m/km of climbing.
- **"Variable" vs intervals:** intervals need rest/recovery laps or a 1-min speed CV above 0.15. A run that's merely
  uneven (CV between 0.08 and 0.15) isn't called an interval session.
- **Best efforts:** the fastest continuous 1 km / 5 km / 10 km / half segment inside a run, by elapsed time, with
  boundaries interpolated. A sample gap over 30 s invalidates a segment. "New best" means faster than every earlier
  synced run.
- **Run story:** deterministic sentences from complete splits: fastest and slowest km, fade (> 5 s/km between
  halves), the km from which HR stayed in zone ≥ 4, cadence change (≥ 4 spm), and the most uphill km (pace minus GAP
  > 8 s/km).
- **Next focus** (first match wins): intervals → compare efforts; drift > 5 % → see if it repeats; fade > 8 s/km →
  start about 10 s/km slower; ≥ 80 % of splits in zone ≥ 4 → "if meant to be easy, it wasn't"; uneven → steadier
  effort enables comparisons; otherwise keep building comparable runs.

## Easy pace — `insights.py` (`insights-1.1`)

This is the pace below the zone-3 floor (top of zone 2), on the current watch, over the last 6 weeks, with the first
10 min of each run excluded. It's **measured** if there are at least 10 minutes of such running. If 90 % of minutes
are more than 10 bpm above zone 2, the app says it's **unknown** and explains how to measure it. Otherwise it's
**estimated** with a Theil–Sen pace–HR line (interquartile range of residuals as the band), labelled as an estimate.

## Garmin fitness

VO₂ max, race predictions, training status, acute load vs Garmin's chronic range, load-balance feedback and heat
acclimation are shown under Garmin's names, as supplied. Garmin's acute:chronic ratio is deliberately not shown or
used. When Garmin's status (Overreaching/Strained/Unproductive) or low-aerobic shortage coincides with our "mostly
hard" insight, the app says they agree. It also notes they come from the same runs, so the agreement isn't
independent confirmation.

## Weekly focus — `focus.py` (`focus-1.0`)

| Focus | Measured as | Target |
|---|---|---|
| even_pacing | second-half minus first-half pace on complete splits | ≤ 5 s/km on each run |
| easy_runs | share of moving time below the zone-3 floor | ≥ 1 run with ≥ 70 % |
| steady_volume | weekly moving time vs the previous week | within ±15 % |
| consistency | runs on the configured running days | all planned days |
| recovery | runs with ≥ 50 % of moving time in zones 4–5 | none |

Suggestions come from the latest insights (pacing, intensity), last week's volume jump (> 1.5× the prior 4-week mean)
and Garmin's training status. They're ordered by goal type. A week in progress is never scored as missed. If the runner hasn't chosen one, the top
suggestion is picked automatically (`auto: true`, shown as "picked for you"); they can change it.

## Run intent

User choice → today's plan → inferred (`source: "inferred"`): intervals if the run is structured or its lap-pace
coefficient of variation is > 0.15; long if moving time ≥ max(60 min, 1.3× the 6-week median); otherwise by share of
time below the zone-3 floor: easy (≥ 70 %), tempo (< 40 %), else other. An inferred intent never produces the
"meant to be easy" finding; the app shows it as one line ("Looks like: …") that can be corrected.

## AI coach — `coach.py` (`coach-1.5`)

Cross-domain insights (≤ 4) and recommendations (≤ 4; training, recovery, sleep, pacing, habits) written by the
selected OpenAI model from a bundle of deterministic outputs only: profile, today's plan and advice, today's readings,
Garmin fitness, insights, the last four weeks, weekly focus, the last 10 runs (no names, notes or IDs) and habit
summaries. Strict JSON schema. Accepted only if every item cites known evidence IDs, the text has no digits outside
`{fact:id}` placeholders (the server fills in the values), and no medical, causal or certainty words. The model is
told never to ask for more logging or check-ins. Cached by input hash; shares the daily AI budget with summaries.
Key: the server's, or the runner's own key sent per request as `X-OpenAI-Key` (Keystore-encrypted on the phone,
never stored by the server).
coach-1.3: the summary must cite evidence; numbers written in words are rejected; each recommendation carries a
direction (easier/same/harder), and "harder" is rejected while today's advice holds intensity back; confidence is capped by the
strongest cited evidence (consistent insight: high, emerging: medium, others: low). All AI calls (summaries and coach)
go through one append-only ledger reserved before each call; a spent budget is recorded, and the same failed input
is retried no sooner than 30 minutes later.

## Comparisons with your age and sex — `compare.py` (`compare-1.0`)

Profile: sex and birth date from Garmin's user profile (stored alone; weight and height aren't), overridable in
Settings. Missing values are asked for, never guessed. Positions are interpolated between published percentiles and
never extrapolated (outside the table: "below the 40th" or "above the 95th").

| Comparison | Reference | Notes |
|---|---|---|
| VO₂ max | Cooper Institute ratings as published by Garmin (40th/60th/80th/95th by decade, 20–79) | "Typical age" = age where the 40th–60th midpoint equals your value |
| Fitness age | Garmin's own fitness age, achievable age and previous value | shown next to the VO₂ max typical age |
| Resting HR | NHANES 1999–2008, CDC NHSR 41, Tables 2–3 (2.5th–97.5th) | Seated clinic pulse reads higher than Garmin's resting HR, so the comparison flatters; this is stated on the card |
| Age grade | USATF/Alan Jones 2025 road standards (5K, 10K, half, marathon; single ages 5–100) | grade = standard ÷ time; 60/70/80/90% = local/regional/national/world class; bests are segments, not races |
| HRV | your own nights | This week's median against your usual range (25th–75th percentile, last 28 days, current watch, ≥ 14 nights). Weekly medians for 12 weeks, split at watch changes. Population norms (e.g. Fitbit, 5-min windows at 6–7 am) aren't comparable with a whole-night average, so they aren't used |

## Daily AI summaries of Compare and Trends — `summaries.py` (`summary-1.3`)

Two to four sentences at the top of each screen (Trends: per 7/28/90-day window), written from that screen's
deterministic results only. The coach's checks apply: every sentence cites evidence, numbers are fact placeholders
rendered by the server, no medical, causal, certainty or spelled-out-number wording, and at most one caveat. One
summary per screen per day, plus a new one within the day only if the screen's data changed. Calls count against the
shared daily AI budget, and the user's own key works here too. While a new summary is being written, the previous one
is shown and labelled with its date.

## Stands out today — `highlights.py` (`highlights-1.0`)

At most four items, attention first, each linked to its detail:

| Item | Rule |
|---|---|
| Garmin training status | Overreaching, Strained, Unproductive, Detraining (attention); Productive, Peaking (positive) |
| Load | Garmin acute load above Garmin's chronic range maximum |
| New best | any best effort (1 km, 5 km, 10 km, half) set in the last 7 days |
| VO₂ max movement | change of 0.5 or more versus the reading at least 28 days earlier, current watch only |
| Weekly focus | off track (attention) or done (positive) |
| Comparison | fitness age at least 2 years below actual age, or else VO₂ max at or above the 75th percentile |
| Run intent | the latest run (within 2 days) was planned easy but mostly zone 3 or above |

Today's order is: the day's call, what stands out, the readings, the focus, then one AI voice (the coach summary,
or the report summary when there isn't one) and one insight.

## Race goal — `race.py` (`race-1.0`)

One race: date, distance (5K, 10K, half, marathon), optional target time and name. The phase comes from the weeks
left, using common periodisation rules of thumb rather than a personal plan:

| Phase | Weeks to race |
|---|---|
| race week | 0–6 days |
| taper | ≤ taper length (5K/10K 1 week, half 2, marathon 3) |
| sharpen | the 3 weeks before the taper |
| build | the 6 weeks before that |
| base | earlier |
| recovery | after the race: 5K 4 days, 10K 7, half 10, marathon 21 |

Effects: it leads "Stands out today", showing Garmin's predicted time against the target when both exist. It orders
the weekly focus suggestions by phase (base: easy runs first; build: steady volume; sharpen: even pacing; taper, race
week and recovery: recovery). It also goes to the coach (coach-1.4) as evidence, with the rule to plan backwards and
never build volume in a taper.

## Weekly digest (app)

On Monday from the start of the morning window, once per week: last week's review headline, this week's focus and
the review's next-week focus. Tapping opens the review.

## Week start

Weeks start on the runner's setting, else the first day of week in their Garmin profile, else Monday (`db.first_weekday`).
This applies to weekly reviews, the weekly focus, a run's "this week" totals, Trends' weekly running, the consistency
insight, the HRV weekly chart, the coach's weekly items, the app's Activities grouping, the VO₂ max chart and the
weekly digest, which arrives on the first day of the week. After a change, past reviews keep their weeks: a week that
overlaps an existing review by 4 days or more isn't reviewed again. The current week gets a newly picked focus.

## AI input on a run — `run_ai.py` (`run-ai-1.1`)

Only on request ("Get AI input" on a run). The answer has a short read, up to three points that went well, up to three
to work on, and one suggestion for next time with a direction. The evidence is the run's analysis plus its context:
similar runs, the run's week against the four before, that day's plan, that week's focus, any race goal and today's
advice. Run names and notes are never sent. The coach's checks apply, and "harder" is rejected while today holds
intensity back. Cached per run and input hash. Each request counts against the shared daily AI budget (25 calls a day per account).

Both the coach (coach-1.5) and run input (run-ai-1.1) start with a TL;DR: one checked sentence of up to 120 characters. Today's coach teaser shows the TL;DR.

## The week toward the race (`race-1.1`)

This is a deterministic weekly plan while a race is set. Planned running days get one long run (the last running day;
none in race week or recovery), the phase's quality sessions (base: strides; build: tempo; sharpen: race pace and
intervals; taper: race pace; race week: strides), and easy runs for the rest. Weekly minutes are the median of the last
four weeks you actually ran (weeks with no running are ignored), times a phase factor: base 1.05, build 1.08, sharpen
1.0, taper 0.7, race week and recovery 0.5. That is never more than +8% a week. The long run is about 30% of the week
but never shorter than your longest run of the previous four weeks. Easy runs are at least 25 min.

Guardrails: if today's advice holds intensity back, or Garmin rates the load above its range, volume doesn't grow and
quality sessions become optional. The plan is recomputed every day from what you actually ran. A run on a day off
stands in for the earliest missed session ("moved"). Missed sessions aren't made up later. If the week's target is
already met, the plan says so. Durations only, never paces.

## What changed since yesterday

The day's call shows when it was worked out and when the Garmin data is from, plus what changed against yesterday's
briefing: the call itself, core readings moving outside or back within your usual range, a plan being set and a
check-in being included. This is computed when the briefing is read, so it never creates report revisions.

## Health and fitness scores — `scores.py` (`scores-1.0`)

Each score runs from 0 to 100. Every part shows its value, points and weight. Missing parts are dropped and the
remaining weights rescaled, and at least two parts are needed. Labels: 85+ excellent, 70+ very good, 55+ good, 40+ fair.

| Score | Part (weight) | Points |
|---|---|---|
| Fitness | VO₂ max for age and sex (50) | the Cooper percentile; below the 40th, falls to 0 at 10 mL/kg/min under it; above the 95th, +1 per unit |
| Fitness | Age-graded running (25) | 40% scores 0, 90% scores 100 |
| Fitness | Consistency (25) | weeks with a run out of the last 8 complete weeks |
| Health | Resting HR for age and sex (30) | the share of the reference group with a higher resting HR |
| Health | Fitness age vs your age (25) | 50 + 10 per year younger (Garmin's fitness age) |
| Health | Sleep (25) | 7–9 h median over 14 nights scores 100; −50 per hour outside |
| Health | HRV vs your usual (20) | within your range scores 100, above 90, below scales down; only once the range exists |

These are deterministic summaries of the readings, not medical scores. No language model is involved in any number.

## Reading notes — `readings.py`

One verdict and one meaning per Today reading, worded deterministically from the numbers:
- sleep against 7–9 h;
- resting HR as the share of the age and sex group with a higher value, plus your usual range ("Very good" from the 75th percentile);
- HRV against your own range only;
- running time against the 4 weeks before;
- VO₂ max as the Cooper rating and percentile for the group.

## Last 4 weeks — `stats.py`

Per-week distance, time and climb, run count, average pace, average HR, longest run and the share of time in zones
4–5. Each covers the 28 days to today against the 28 days before, as a % change. Which direction is good is marked
per item: lower pace, HR and hard share are good. Calculated, never written by AI.

## Training readiness — `readiness.py` (`readiness-1.1`)

Calculated with the same rescaling as the scores (at least two parts). The weakest part caps the total at 40 points
above it. Labels: 75+ high, 50+ moderate, otherwise low. Garmin's training readiness is not used.

| Part (weight) | Points |
|---|---|
| HRV vs usual (20) | 100 down to 5% below usual, then −4 per % |
| Resting HR vs usual (15) | 100 up to +1 bpm, then −12 per bpm |
| Sleep last night (20) | 100 from 7 h, −40 per hour short |
| Training load (20) | acute/chronic ratio: 100 up to 1.1, then −160 per 1.0 (1.35 → 60, 1.6 → 20) |
| Recovery (25) | 100 − 80 × (effort still left from recent runs ÷ a typical run) |

Training load per run follows Edwards' heart-rate-zone method:
- moving minutes in zones 1–5, times 1–5 (below zone 1 counts half);
- scaled up to the whole run when heart rate covers part of it;
- runs without usable heart rate count minutes × 2.

How the loads are combined:
- **Acute and chronic:** fading daily averages of the loads (Banister-style), with time constants of 7 and 28 days.
- **Recovery:** the loads fade with a 48-hour time constant, compared with the median run load of the last 28 days.
- **Moment:** "now" for today, and 08:00 local for earlier days.
- **Minimum history:** 6 runs and 3 weeks.

Backtest against Garmin's own readiness (Sep 23 – Oct 2, 2026): after each run day both drop, and ours reaches its low
band on the same mornings (Sep 28: Garmin 15, ours 49; Oct 1: Garmin 18, ours 45). Garmin also uses sleep quality and
stress, and stays lower overall.

Each part also gets a verdict: good (85+ points), ok (60+) or low. Running more than 120% of usual is never
"good". The app shows that verdict and a plain line ("Normal for you", "Short (5 h 47 min)").

"Usual" is the personal range median. While that is still being learned, it is the median of at least 4 earlier days
in the last two weeks, marked provisional. When today's value isn't in yet, yesterday's is used and labelled.

## Next run

Next run day: today if it is a running day and you haven't run yet, otherwise the next running day.

The kind is chosen by the first rule that applies:
1. Rest, if readiness today is below 40.
2. Easy today, when the day's call holds intensity back or readiness is below 60.
3. Long or easy, when that's the race week plan's session for the day.
4. Easy, after a hard run in the last 2 days.
5. Easy, when more than 30% of the last 4 weeks was in zones 4–5.
6. Long, on the last running day of the week.
7. Otherwise steady (zone 3).

Distance comes from the runs of the last 4 weeks:
- easy: 90% of the typical (median) run, or 70% when readiness is below 60;
- steady: the typical run;
- long: at least the longest run, up to 10% more.

The heart-rate cap is the top of zone 2, or zone 3 for steady runs. Pace and time come from the measured easy pace.

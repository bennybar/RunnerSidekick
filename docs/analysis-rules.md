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

## Recommendation rules — `analytics/recommend.py` (`rules-1.1`)

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
| R3 | 1 group, no check-in | check_in_needed | yes |
| R4 | 1 group, check-in without concerns | usual_plan | no |
| R5 | no groups | usual_plan | only if overnight data missing |
| R1c | check-in but no overnight data | insufficient_data | yes |
| R1d | overnight data and check-in, no personal ranges, no signal | insufficient_data | yes |
| R1e | a signal (e.g. load) but no personal ranges | usual_plan (with check-in) / check_in_needed | yes |

"Readings look typical" is only said when overnight data and personal ranges exist (rules-1.3). With a day plan,
the suggestion names the planned session: swap it (consider_easier), keep its hard parts optional (suppressed
intensity), or go ahead.

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
and Garmin's training status. They're ordered by goal type. A week in progress is never scored as missed.

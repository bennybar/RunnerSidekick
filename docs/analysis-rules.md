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

A single low HRV never cancels a run by itself (R3/R4). A good score never overrides reported pain (R0).
There are no numeric pace or HR prescriptions in v1.

## Time and attribution

- Instants are stored in UTC, with the source offset kept (`utc_offset_s`).
- Activities are attributed to the **local date where they happened** (Garmin `startTimeLocal`). History isn't
  rewritten into the current zone.
- Primary sleep is attributed to the **local wake date**, and the original interval is kept. Naps are stored
  separately (`is_nap`) and excluded from `sleep_duration`.
- Daily Garmin metrics use Garmin's calendar date.

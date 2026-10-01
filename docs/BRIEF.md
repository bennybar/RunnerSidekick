# Android Running & Personal Health App — Implementation Brief

## 1. Your assignment

You are Claude Code, the implementation lead. Build this product inside the **existing Android Studio project**. Codex Astra will supervise architecture, correctness and implementation quality through review checkpoints.

This is an implementation brief, not a request for another proposal. Inspect the repository, document the actual starting point, then implement in working vertical slices. Do not recreate the project, change its application ID, replace working infrastructure, or overwrite existing instructions without a concrete reason. Read existing `CLAUDE.md`, `AGENTS.md` and project documentation first; surface conflicts instead of silently choosing one.

The initial product is for personal use, focused on **running and everyday health/recovery**. Use a replaceable Garmin integration so a future public version can use approved APIs. Public launch, subscriptions, social features and multi-sport coaching are outside v1.

Make reasonable reversible engineering decisions and continue. Ask only when missing information blocks a meaningful decision, credentials are required, or an external action needs authorization. Do not repeatedly ask whether to proceed with ordinary implementation.

## 2. Product intent

Create a polished native Android app that turns Garmin data into a useful daily briefing and deep running analysis.

The first screen must answer within five seconds:

1. How am I doing today?
2. What deserves my attention?
3. What training approach fits today?

Deeper screens must explain whether running performance is improving and how sleep, workload and reported wellbeing relate over time. Every important conclusion must expose its supporting evidence.

The app should feel like a thoughtful training journal and analyst. Avoid walls of metrics, repetitive motivational filler, unexplained scores and confident claims unsupported by the data.

## 3. Default decisions

| Area | Default |
| --- | --- |
| Client | Native Kotlin, Jetpack Compose, Material 3; respect existing compatible architecture |
| Local persistence | Room for cached records, check-ins and reports; DataStore for preferences |
| Background client work | WorkManager; best-effort refresh, never promise exact alarm timing |
| Backend | Small Python/FastAPI service, colocated in the repo if no backend exists |
| Initial connector | Maintained `python-garminconnect`, read operations only |
| Analytics | Deterministic, versioned Python functions; one authoritative implementation |
| Narrative | Optional provider-neutral LLM adapter behind the backend |
| Backend database | SQLite for the single-user prototype, migrations from day one; avoid unnecessary infrastructure |
| User experience | Local cached browsing, light/dark modes, accessible charts and typography |
| Units | Metric by default, canonical units in storage, explicit conversions at display boundaries |
| Language/time | English first, string resources for localization; default timezone Asia/Jerusalem, editable |

Do not pin dependency versions from this brief. Inspect the existing Gradle setup and verify compatible current versions through official documentation. Do not upgrade the entire toolchain gratuitously.

The backend is a deliberate prototype choice, not a claim that Android cannot access Garmin cloud services. Direct Kotlin implementation is technically possible, but reproducing authentication is out of scope initially. No MCP server is required for the app's normal operation.

## 4. Garmin integration and feasibility

### Initial route

Use the unofficial library to authenticate to the user's own Garmin account and retrieve available data. It accesses Garmin cloud services; it does not read the installed Garmin Connect app, borrow its session or pair directly with the watch.

Inspect the installed library's real API and authentication behavior. Do not invent endpoint paths, assume historical examples remain valid, or bake in undocumented token lifetimes. Handle MFA, expired sessions, rate limits and revoked access explicitly. Do not bypass authentication challenges.

Prefer a local administrative setup command for the personal prototype's initial Garmin authentication, with secure input and token storage. The Android client authenticates to our backend using a separate mechanism. Never expose an unauthenticated backend merely because the product is single-user.

Implement a connector interface with capabilities, connection state, historical reads and incremental reads. Future official Garmin and Health Connect adapters must be able to return different capability sets. Implement the initial connector and a deterministic fixture connector now; defer additional providers.

### First real-data task

Attempt an initial backfill of approximately 90 days with bounded requests, persisted progress and resumability. If account access is unavailable, complete the pipeline using visibly labelled synthetic fixtures and leave a precise, minimal setup step for the user. Never describe fixture results as a successful live integration.

Build a capability matrix from observed payloads:

| Area | Desired data, if actually available |
| --- | --- |
| Running | Activity IDs, distance, elapsed/moving duration, timestamps, laps, pace/speed, HR samples, cadence, elevation, route and relevant FIT fields |
| Sleep | Main sleep interval, duration, stages, score if provided, overnight HR/HRV where available |
| Recovery | Resting HR, HRV measurement and status, stress, Body Battery, respiration |
| Garmin training | Training load/status/readiness, recovery time, VO2max and training effect where supplied |
| Daily health | Steps, active duration, weight when recorded |

Unsupported, not measured, missing permission, delayed, invalid and missing-on-this-date are different states. None means zero. Do not promise every field for every Garmin device. Preserve Garmin-generated metrics under their own names; do not manufacture missing proprietary metrics.

### Future routes

Android Health Connect can provide a local basic-data mode, but Garmin's documented export list does not include all the rich recovery/training fields above. Its Garmin sharing requires Android 14+; verify current coverage before implementation. Do not raise the existing app's minimum SDK solely for a deferred feature.

Official Garmin Health/Activity APIs require approved business access and may have metric-specific commercial conditions. Coverage must be verified; replacing the connector is not a guarantee of identical data. Direct-to-watch Garmin SDKs and Connect IQ are outside this implementation.

## 5. Data architecture and synchronization

Preserve normalized data plus necessary source payloads/files with an explicit retention policy. Raw payloads are sensitive local/backend data, not repository fixtures. Use sanitized synthetic fixtures for tests.

Core entities should cover:

- Source connection and metric capabilities.
- Daily observations and time series with units, source, quality and coverage.
- Activities, laps and samples.
- Sleep sessions, including naps separately where available.
- User goals, running availability and configured HR zones.
- Check-ins and perceived workout effort.
- Derived features, findings and recommendations.
- Versioned reports and sync jobs.

Each record or finding must retain enough provenance to identify its source record, observation time/interval, ingestion time, timezone/date attribution and algorithm version. Derived values must be labelled as derived.

Synchronization requirements:

1. Use source identifiers for idempotent upserts. Re-running sync must not duplicate workouts or daily observations.
2. Persist a cursor/checkpoint and re-fetch a bounded recent window for delayed sleep and revised activity data.
3. Preserve instants in UTC and the relevant source offset/zone when available. Use a documented local-date policy; do not silently rewrite travel history into today's timezone.
4. Attribute primary sleep to its wake date for reporting, keeping the original interval. Test cross-midnight, DST and naps.
5. Distinguish elapsed, moving and timer duration; state which is used for each pace calculation.
6. Keep missing intervals visible. Do not interpolate across large gaps or silently replace missing HR with zero.
7. Track last successful source fetch separately from latest observation time and watch-sync time. If actual watch-sync time is unavailable, do not claim to know it.
8. Use bounded retries, exponential backoff with jitter and documented rate-limit handling. Never create retry storms on authentication failure.
9. Recompute affected findings when input data changes; preserve report revisions and prevent duplicate notifications.
10. If multiple sources are added later, apply documented deduplication and precedence. Never sum duplicate Garmin/Health Connect steps or workouts.

## 6. Deterministic analysis engine

The analysis engine owns calculations, eligibility, evidence selection and recommendation rules. The LLM does not compute statistics or decide whether raw sensor data establishes a medical condition.

### Personal baselines

- Compare daily metrics with the preceding 28 local days, excluding the target day to avoid leakage.
- Proposed v1 availability rule: require at least 14 valid daily observations for a baseline; otherwise show learning/insufficient history. These are configurable product heuristics, not validated medical thresholds.
- Prefer robust summaries such as median and interquartile range. Call this a personal reference range, not a clinical normal range or statistical confidence interval.
- Show absolute differences; percentage differences only when the denominator is meaningful and nonzero.
- Track sustained changes separately from one-day deviations. Set per-metric meaningful-change thresholds in versioned configuration and document their rationale before enabling alerts.
- Keep HRV measurements comparable: do not mix different measurement types, windows, devices or algorithms without marking a discontinuity.
- Handle watch changes, long non-wear periods and insufficient coverage explicitly.
- Show 7-day and longer-term trends without treating overlapping windows as independent samples.

### Running analysis

Implement these only when the required data quality and activity type support them:

| Analysis | Requirements |
| --- | --- |
| Summary and splits | Consistent units; moving/elapsed labels; exclude incomplete final lap from like-for-like split comparisons |
| Pacing consistency | Comparable segments; account for pauses, hills and intentional intervals |
| HR zones | User/Garmin-configured zones with provenance; do not assume generic age-based zones are personalized |
| HR drift/decoupling | Eligible steady aerobic segment, adequate continuous HR/speed data; exclude warm-up, pauses and obvious artifacts |
| Similar-run comparison | Transparent matching on distance/duration, terrain and workout type; weather only if available |
| Progress | Repeated comparable observations; distinguish descriptive improvement from a confident fitness conclusion |
| Weekly workload | Duration, distance, frequency, elevation and intensity separately; distinguish calendar week from trailing seven days |

For steady-run decoupling, a candidate definition is `100 * (EF_first - EF_second) / EF_first`, where EF is time-weighted mean speed divided by time-weighted mean HR in each half of the eligible segment. Positive values indicate reduced efficiency in the second half under this definition. Document segment selection, weighting, minimum coverage and exclusions before shipping. Test with hand-calculated examples. Do not label this a diagnosis or universal fitness score.

Do not mix Garmin load, distance and perceived-effort load into one arbitrary number. Session-RPE load can be added when both duration and user-reported effort exist, labelled as a separate measure.

Do not ship ACWR-based injury probabilities, universal safe workload ratios, illness predictions or invented recovery-time estimates. Descriptive workload changes and unusual combinations of readings are acceptable with restrained wording and visible evidence.

### Recommendations

Use explainable states such as `usual_plan`, `consider_easier`, `check_in_needed` and `insufficient_data`. They are product guidance states, not Garmin scores or medical classifications.

Consider recent training, available recovery signals, the user's goal, schedule and check-in. Avoid double-counting sleep/HRV and Garmin composite scores incorporating the same inputs. A single low HRV value must not automatically cancel a run; a high score must not override reported pain or illness.

Before emitting training adjustments, document a small conservative rule table with prerequisites, evidence IDs and uncertainty. Suppress intensity escalation when key information is missing or the user reports concerning symptoms. Do not generate numerical pace/HR prescriptions without a justified user-specific basis.

### Pattern discovery — later phase

Look for repeated associations such as late runs coinciding with shorter sleep. Require sufficient comparable observations, show sample size and confounders, avoid causal wording, and do not scan hundreds of correlations then present the largest as a discovery. Define candidate questions in advance and verify patterns on later data before increasing confidence.

## 7. Reports and AI contract

Build deterministic reports first. They must remain useful without any LLM key or network connection after caching.

Each finding needs:

- Stable ID and category.
- Observed value, unit, comparison value/range and delta if applicable.
- Supporting record IDs and date range.
- Sample size, coverage and data-quality limitations.
- Clear statement plus allowed interpretation.
- Algorithm version.

The report needs local date, generation time, data cutoff, completeness, input revision/hash, report type, findings, recommendation, and optional narrative provider/model/prompt version.

LLM input is a compact structured evidence bundle, not an entire raw account dump. Exclude credentials, unnecessary identifiers and precise routes. Treat notes/activity titles as untrusted data, never as instructions.

LLM output must follow a validated schema and refer to existing finding IDs. The UI renders numerical facts directly from deterministic findings. Prefer narrative references/placeholders resolved by the renderer rather than allowing freely invented numerical claims. Reject unknown evidence references and unsupported claims; fall back to templates on failure.

The LLM may explain and summarize supported associations. It may not add medical diagnoses, invent causal mechanisms, invent absent measurements or upgrade uncertainty. Version and cache outputs; regenerate only for meaningful input changes or an explicit request. Add request timeouts and configurable cost limits.

Report types:

1. Morning briefing: short summary, up to three important findings and today's suggestion.
2. Post-run report: what happened, pacing/effort analysis, comparable history and practical next focus.
3. Weekly review: consistency, performance observations, recovery context and next-week focus.

## 8. User experience and visual direction

Build an attractive, restrained Material 3 interface with strong typography, generous spacing, useful motion and well-designed charts. It should feel like a finished running product. Avoid a generic admin dashboard, excessive gradients, decorative gauges and fake precision.

### Today

- Date and honest data-freshness indicator.
- Readable headline: for example, "Mixed recovery signals today."
- One training suggestion and its main reasons.
- Up to three prioritized insight cards with tiny trend charts where useful.
- Expandable full briefing.
- Ten-second check-in: energy, soreness and perceived recovery; optional notes/tags.
- Recent run entry point.
- Every insight has a "Show why" drill-down with baseline, sample size, dates and limitations.

No invented 0–100 readiness score in v1. Display Garmin scores only when supplied and label their origin.

### Activities

Readable running history, filters and run details. Show splits, synchronized pace/HR charts, eligible drift analysis and comparable runs. Chart axes must have units and sensible scales; gaps must remain gaps. Routes/maps are optional after the core analysis works.

### Trends

7/28/90-day views for sleep, resting HR, comparable HRV, running volume and progress. Allow opening the underlying days/activities. Keep daily health and performance context connected without forcing every metric onto one chart.

### Journal

Morning reports, post-run analyses, weekly reviews and check-ins. Preserve historical report context instead of silently rewriting the past with current baselines.

### Settings and onboarding

Connection status/setup, timezone, units, goals, running days, available time, zone source, report timing, notification controls, AI opt-in, data export and deletion.

Persist check-ins locally and sync with an explicit conflict policy so they can be entered offline. Do not hardcode personal profile details beyond editable defaults.

Implement authentic loading, learning, empty, stale, partial, disconnected and failure states. Synthetic demo mode must have an unmistakable badge and must never mix with live records. Support font scaling, screen readers, adequate touch targets and information conveyed beyond color alone.

## 9. Scheduling, security and operation

- Generate morning reports after relevant overnight data arrives, within a configurable morning window. Display a provisional report if incomplete and revise when warranted.
- Generate post-run analysis after a newly synced eligible activity. Do not assume Garmin updates arrive in real time.
- WorkManager is best-effort. Start with in-app refresh, user-triggered refresh and best-effort local notifications; add push infrastructure only if it solves a demonstrated need.
- Keep Garmin credentials/tokens and LLM keys out of source control, logs, crash reports and the APK. Use secure backend storage and Keystore-backed protection for appropriate Android secrets.
- Require authenticated backend requests and encrypted transport outside explicitly documented local development. No global cleartext-network allowance in release builds.
- Bind development services safely and document emulator/physical-device connectivity. Do not publish services automatically.
- Separate raw-data retention from report retention. Provide deletion for source payloads, normalized records, reports and local caches; explain backup retention accurately.
- AI processing of health summaries must be explicitly enabled by the user. The deterministic product must work when disabled.
- No Garmin writes, workout uploads, edits, deletions or account changes in v1.

## 10. Implementation phases and acceptance criteria

### Phase 0 — Inspect and establish the baseline

Read the project, identify stack/build conventions, run the existing relevant build/checks, and record pre-existing failures. Create a concise implementation plan and architecture decision record. Preserve unrelated user changes.

Acceptance: documented actual repository state, chosen package/module structure and runnable baseline or precise explanation of environment blockers.

### Phase 1 — Data-to-screen vertical slice

Implement connector interface, fixture connector, initial real Garmin adapter, authentication setup, normalized persistence and sync state. Build a real Today screen reading the same API contract in fixture and live modes. Run the 90-day data audit when authorized credentials are available.

Acceptance: a sync can resume, repeat without duplicates and render available observations honestly; actual field coverage is documented. Live success must be demonstrated with real access, not inferred from mocks.

### Phase 2 — Useful running and health MVP

Implement baselines, core run analysis, check-ins, deterministic morning and post-run reports, Activities screen and evidence drill-downs.

Acceptance: selected calculations match hand-worked fixtures; each visible conclusion traces to evidence; missing data suppresses unsupported conclusions; cached reports work offline.

### Phase 3 — Narrative and polish

Add the optional LLM adapter, validation/fallback, report revisions, notification deduplication, complete UI states, accessibility and light/dark visual QA.

Acceptance: malformed/unsupported AI output cannot replace a valid deterministic report; app remains useful without an AI key; representative emulator screenshots have been reviewed.

### Phase 4 — Trends and weekly review

Add comparable-run history, Trends, Journal and weekly reports. Add pattern discovery only after data sufficiency and validation rules exist.

Acceptance: trend filters and source drill-downs agree; historical reports retain their original context; comparison limitations are visible.

Public launch, official API migration, Health Connect, route maps, widgets, chat and workout prescription are subsequent work, not prerequisites for the personal MVP.

## 11. Testing priorities

Prioritize tests protecting data correctness and user trust:

- Unit conversion, pace formatting, weighted averages and moving/elapsed distinctions.
- Baseline date exclusion, missing days, zero denominators and insufficient history.
- Cross-midnight sleep, DST and travel attribution.
- Steady versus interval run eligibility and sensor gaps.
- Sync idempotency, delayed corrections, resumability, rate limits and reauthentication.
- Check-in persistence and report input revisions.
- Evidence references, LLM schema failures, unsupported narrative and deterministic fallback.
- Backend authentication and sensitive-log redaction.
- Room migrations and persistence of offline reports.

Use unit tests for analytics and targeted integration/UI tests for critical flows. Do not create a huge suite of tests that merely duplicate implementation. Build the Android app and run applicable lint/tests at each meaningful milestone; report commands and actual results. Never claim device testing when only compilation occurred.

## 12. Claude Code / Codex Astra collaboration

Claude Code implements. Codex Astra reviews architecture, analysis correctness, data contracts, security and meaningful diffs. Review checkpoints:

1. Repository inspection and architecture plan.
2. Real data audit and connector/data model.
3. Analysis rules and deterministic report pipeline.
4. MVP implementation and verification evidence.

At each checkpoint, prepare a concise `docs/reviews/checkpoint-N.md` containing scope, files/commit under review, key decisions, formulas, test results, screenshots where applicable, remaining limitations and specific reviewer questions. Never include credentials or private raw health data.

If Codex tooling is actually configured, use the authorized review workflow and record real findings. Otherwise prepare the review packet for the user to pass to Codex Astra. Do not invent review results, assume another model is connected, or block all independent work waiting for a review. Keep progressing on reversible tasks; do not call a checkpoint approved until it has been reviewed.

Fix substantive review findings, rerun affected checks and record the resolution. Resolve disagreements with evidence and documented decisions.

Maintain a short `docs/STATUS.md` with completed work, current blockers, next steps and review state. Keep this brief as the product specification; do not overwrite it with progress logs.

## 13. Completion standard

The personal MVP is complete when the user can securely connect their account, synchronize available data, browse real runs, read an evidence-backed daily and post-run report, record a check-in and revisit cached reports offline. It must clearly identify stale/incomplete data and continue functioning without AI narrative.

Provide reproducible setup instructions for Android and the backend, required configuration names, local authentication steps, build/run commands, verification results and known limitations. Do not leave placeholder buttons or silently substitute synthetic data for unfinished features.

**Start now with repository inspection and Phase 0, then proceed into the first working vertical slice.**

## 14. Reference links to verify during implementation

- Garmin Connect Developer Program: https://developer.garmin.com/gc-developer-program/overview/
- Program requirements and metric limitations: https://developer.garmin.com/gc-developer-program/program-faq/
- Health API: https://developer.garmin.com/gc-developer-program/health-api/
- Activity API: https://developer.garmin.com/gc-developer-program/activity-api/
- Garmin SDK distinctions: https://developer.garmin.com/health-sdk/
- Garmin Health Connect export list: https://support.garmin.com/en-IN/?faq=JToBEy0jfe6pIygark2Ui5
- Unofficial connector, inspect current implementation: https://github.com/cyberjunky/python-garminconnect
- Android Health Connect: https://developer.android.com/health-and-fitness/health-connect
- WorkManager: https://developer.android.com/develop/background-work/background-tasks/persistent
- ACWR prediction limitations, original analysis: https://www.mdpi.com/2077-0383/11/19/5945
- Wearable respiratory-infection detection, prospective validation: https://pmc.ncbi.nlm.nih.gov/articles/PMC11292157/

This brief specifies engineering/product heuristics; it is not a validated clinical or coaching protocol. Verify changing APIs and dependency details against current sources rather than treating this document as API documentation.

package com.bennybar.runnersidekick.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Mirrors the backend contract (backend/sidekick/api.py, reports.py). Canonical units: m, s, m/s, bpm, ms.

@Serializable
data class Status(
    val mode: String,
    val synthetic: Boolean,
    val today: String,
    val timezone: String,
    val connection: Connection,
    @SerialName("latest_observation_date") val latestObservationDate: String? = null,
    @SerialName("latest_activity_start") val latestActivityStart: String? = null,
    @SerialName("sync_running") val syncRunning: Boolean = false,
    val backfill: Backfill? = null,
)

@Serializable
data class Connection(
    val state: String,
    val detail: String? = null,
    @SerialName("last_attempt_at") val lastAttemptAt: String? = null,
    @SerialName("last_success_at") val lastSuccessAt: String? = null,
    @SerialName("retry_not_before") val retryNotBefore: String? = null,
)

@Serializable
data class Backfill(
    @SerialName("backfill_target") val target: String? = null,
    @SerialName("oldest_done") val oldestDone: String? = null,
)

@Serializable
data class Observed(
    val value: Double? = null,
    val unit: String? = null,
    val date: String? = null,
    val method: String? = null,
    val label: String? = null,
    val runs: Int? = null,
    @SerialName("distance_m") val distanceM: Double? = null,
)

@Serializable
data class Comparison(
    val kind: String,
    val median: Double? = null,
    val q1: Double? = null,
    val q3: Double? = null,
    val n: Int? = null,
    val value: Double? = null,
    val window: List<String>? = null,
    @SerialName("concern_direction") val concernDirection: String? = null,
)

@Serializable
data class Delta(val abs: Double? = null, val pct: Double? = null)

@Serializable
data class Evidence(
    @SerialName("record_ids") val recordIds: List<String> = emptyList(),
    @SerialName("date_range") val dateRange: List<String> = emptyList(),
)

@Serializable
data class Point(val date: String, val value: Double)

@Serializable
data class Finding(
    val id: String,
    val category: String,
    val metric: String,
    val title: String,
    val status: String,           // within | outside | sustained | learning | missing | info
    val statement: String,
    val interpretation: String? = null,
    val observed: Observed? = null,
    val comparison: Comparison? = null,
    val delta: Delta? = null,
    val evidence: Evidence = Evidence(),
    @SerialName("sample_size") val sampleSize: Int? = null,
    val limitations: List<String> = emptyList(),
    @SerialName("algorithm_version") val algorithmVersion: String,
    val derived: Boolean = true,
    val sparkline: List<Point>? = null,
)

@Serializable
data class Recommendation(
    val state: String,            // usual_plan | consider_easier | check_in_needed | insufficient_data
    @SerialName("rule_id") val ruleId: String,
    val reason: String,
    val suggestion: String,
    @SerialName("evidence_ids") val evidenceIds: List<String> = emptyList(),
    @SerialName("suppress_intensity") val suppressIntensity: Boolean,
    val uncertainty: String? = null,
    @SerialName("rules_version") val rulesVersion: String,
)

@Serializable
data class GarminContext(val metric: String, val value: Double, val unit: String, val label: String? = null, val origin: String)

@Serializable
data class RecentRun(
    @SerialName("source_id") val sourceId: String,
    @SerialName("local_date") val localDate: String,
    val name: String? = null,
    @SerialName("distance_m") val distanceM: Double? = null,
    @SerialName("moving_s") val movingS: Double? = null,
    @SerialName("avg_hr") val avgHr: Double? = null,
)

@Serializable
data class NarrativeSentence(val text: String, @SerialName("finding_ids") val findingIds: List<String> = emptyList())

/** Optional AI summary. Numbers inside [sentences] were filled in by the backend from deterministic findings. */
@Serializable
data class Narrative(
    val status: String,           // ok | pending | disabled | not_configured | rejected | failed | budget_exceeded
    val provider: String? = null,
    val model: String? = null,
    val sentences: List<NarrativeSentence> = emptyList(),
    val focus: NarrativeSentence? = null,
    val detail: String? = null,
)

@Serializable
data class MorningReport(
    val id: Long,
    val type: String,
    @SerialName("local_date") val localDate: String,
    val revision: Int,
    @SerialName("generated_at") val generatedAt: String,
    @SerialName("data_cutoff") val dataCutoff: String? = null,
    val synthetic: Boolean,
    val provisional: Boolean,
    val headline: String,
    val recommendation: Recommendation,
    @SerialName("top_finding_ids") val topFindingIds: List<String>,
    val findings: List<Finding>,
    @SerialName("garmin_context") val garminContext: List<GarminContext> = emptyList(),
    val completeness: Map<String, kotlinx.serialization.json.JsonElement> = emptyMap(),
    val checkin: CheckinDto? = null,
    @SerialName("recent_run") val recentRun: RecentRun? = null,
    @SerialName("algorithm_version") val algorithmVersion: Map<String, String> = emptyMap(),
    val narrative: Narrative? = null,
)

@Serializable
data class ActivitySummary(
    @SerialName("source_id") val sourceId: String,
    val sport: String,
    val name: String? = null,
    @SerialName("start_utc") val startUtc: String,
    @SerialName("utc_offset_s") val utcOffsetS: Int? = null,
    @SerialName("local_date") val localDate: String,
    @SerialName("distance_m") val distanceM: Double? = null,
    @SerialName("elapsed_s") val elapsedS: Double? = null,
    @SerialName("moving_s") val movingS: Double? = null,
    @SerialName("avg_hr") val avgHr: Double? = null,
    @SerialName("elevation_gain_m") val elevationGainM: Double? = null,
    @SerialName("pace_moving_s_per_km") val paceMovingSPerKm: Double? = null,
    val synthetic: Boolean = false,
)

@Serializable
data class RunActivity(
    @SerialName("source_id") val sourceId: String,
    val name: String? = null,
    val sport: String,
    @SerialName("start_utc") val startUtc: String,
    @SerialName("utc_offset_s") val utcOffsetS: Int? = null,
    @SerialName("local_date") val localDate: String,
    @SerialName("distance_m") val distanceM: Double? = null,
    @SerialName("elapsed_s") val elapsedS: Double? = null,
    @SerialName("moving_s") val movingS: Double? = null,
    @SerialName("timer_s") val timerS: Double? = null,
    @SerialName("avg_hr") val avgHr: Double? = null,
    @SerialName("max_hr") val maxHr: Double? = null,
    @SerialName("elevation_gain_m") val elevationGainM: Double? = null,
    @SerialName("avg_cadence_spm") val avgCadenceSpm: Double? = null,
)

@Serializable
data class Split(
    val idx: Int,
    @SerialName("distance_m") val distanceM: Double? = null,
    @SerialName("moving_s") val movingS: Double? = null,
    @SerialName("avg_hr") val avgHr: Double? = null,
    @SerialName("elevation_gain_m") val elevationGainM: Double? = null,
    @SerialName("pace_s_per_km") val paceSPerKm: Double? = null,
    val complete: Boolean,
)

@Serializable
data class Classification(val kind: String, val reason: String)

@Serializable
data class Half(@SerialName("mean_speed_mps") val meanSpeedMps: Double, @SerialName("mean_hr") val meanHr: Double)

@Serializable
data class Decoupling(
    val eligible: Boolean,
    val reasons: List<String> = emptyList(),
    @SerialName("decoupling_pct") val decouplingPct: Double? = null,
    @SerialName("first_half") val firstHalf: Half? = null,
    @SerialName("second_half") val secondHalf: Half? = null,
    @SerialName("segment_moving_s") val segmentMovingS: Double? = null,
    @SerialName("hr_coverage") val hrCoverage: Double? = null,
    val method: String? = null,
)

@Serializable
data class ComparableRun(
    @SerialName("source_id") val sourceId: String,
    @SerialName("local_date") val localDate: String,
    @SerialName("distance_m") val distanceM: Double? = null,
    @SerialName("pace_s_per_km") val paceSPerKm: Double? = null,
    @SerialName("avg_hr") val avgHr: Double? = null,
)

@Serializable
data class Comparable(val n: Int = 0, val runs: List<ComparableRun> = emptyList())

@Serializable
data class Effort(val rpe: Int, @SerialName("session_rpe_load") val sessionRpeLoad: Int, val note: String)

@Serializable
data class PostRunReport(
    val id: Long,
    val revision: Int,
    @SerialName("generated_at") val generatedAt: String,
    val synthetic: Boolean,
    val activity: RunActivity,
    @SerialName("pace_moving_s_per_km") val paceMovingSPerKm: Double? = null,
    @SerialName("garmin_metrics") val garminMetrics: Map<String, kotlinx.serialization.json.JsonElement> = emptyMap(),
    val splits: List<Split> = emptyList(),
    val classification: Classification,
    val decoupling: Decoupling,
    val comparable: Comparable = Comparable(),
    val findings: List<Finding> = emptyList(),
    val effort: Effort? = null,
    @SerialName("next_focus") val nextFocus: String,
    val narrative: Narrative? = null,
)

@Serializable
data class Chart(
    val t: List<Double>,
    val hr: List<Double?>,
    val speed: List<Double?>,
    val elev: List<Double?>,
)

@Serializable
data class ActivityDetail(val report: PostRunReport? = null, val chart: Chart? = null)

@Serializable
data class ReportListItem(
    val id: Long,
    val type: String,
    @SerialName("subject_key") val subjectKey: String,
    @SerialName("local_date") val localDate: String,
    val revision: Int,
    @SerialName("generated_at") val generatedAt: String,
    val synthetic: Boolean = false,
    val title: String? = null,
    val state: String? = null,
)

@Serializable
data class CheckinDto(
    val id: String? = null,
    @SerialName("local_date") val localDate: String,
    val energy: Int? = null,
    val soreness: Int? = null,
    val recovery: Int? = null,
    val pain: Boolean = false,
    val illness: Boolean = false,
    val notes: String? = null,
    val tags: List<String> = emptyList(),
    @SerialName("client_updated_at") val clientUpdatedAt: String,
    val deleted: Boolean = false,
)

@Serializable
data class SettingsDto(
    val timezone: String,
    @SerialName("running_days") val runningDays: List<Int>,
    val goal: String? = null,
    @SerialName("available_minutes") val availableMinutes: Int? = null,
    @SerialName("hr_zone_source") val hrZoneSource: String = "garmin",
    @SerialName("ai_enabled") val aiEnabled: Boolean = false,
    @SerialName("ai_model") val aiModel: String = "gpt-6.1-sol",
    @SerialName("ai_available") val aiAvailable: Boolean = false,
    @SerialName("morning_window_start") val morningWindowStart: String = "06:00",
    @SerialName("morning_window_end") val morningWindowEnd: String = "10:00",
)

@Serializable
data class EffortIn(val rpe: Int, @SerialName("client_updated_at") val clientUpdatedAt: String)

@Serializable
data class Insight(
    val id: String,
    val question: String,
    val category: String,
    val verdict: String,          // pattern | no_clear_pattern | not_enough_data
    val headline: String,
    val detail: String,
    @SerialName("sample_size") val sampleSize: Int? = null,
    val method: String,
    val confounders: List<String> = emptyList(),
    val practical: String? = null,
    val confidence: String? = null, // emerging | consistent
    val chart: kotlinx.serialization.json.JsonObject? = null,
    val evidence: Evidence = Evidence(),
    @SerialName("algorithm_version") val algorithmVersion: String,
)

@Serializable
data class InsightsReport(
    val id: Long,
    @SerialName("local_date") val localDate: String,
    val revision: Int,
    @SerialName("generated_at") val generatedAt: String,
    val synthetic: Boolean,
    val insights: List<Insight>,
)

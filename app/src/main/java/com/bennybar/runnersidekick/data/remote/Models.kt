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
    @SerialName("week_start_day") val weekStartDay: String = "monday",
    val connection: Connection,
    @SerialName("latest_observation_date") val latestObservationDate: String? = null,
    @SerialName("latest_activity_start") val latestActivityStart: String? = null,
    @SerialName("sync_running") val syncRunning: Boolean = false,
    val backfill: Backfill? = null,
    @SerialName("garmin_official") val garminOfficial: GarminOfficial? = null,
)

@Serializable
data class GarminOfficial(val available: Boolean = false, val connected: Boolean = false, @SerialName("data_import") val dataImport: String? = null)

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
    /** For a reading not in yet today: the most recent measured value (last 3 days). */
    val last: Point? = null,
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
    val plan: DayPlan? = null,
)

@Serializable
data class DayPlan(val kind: String, val minutes: Int? = null)

@Serializable
data class DayPlanIn(val kind: String, val minutes: Int?, @SerialName("client_updated_at") val clientUpdatedAt: String)

@Serializable
data class RunIntent(val kind: String, val note: String? = null, val source: String = "user")

@Serializable
data class RunIntentIn(val kind: String, val note: String?, @SerialName("client_updated_at") val clientUpdatedAt: String)

@Serializable
data class FocusRun(val date: String, @SerialName("source_id") val sourceId: String? = null, val value: Double? = null, val met: Boolean = false)

@Serializable
data class FocusEval(
    val kind: String, val title: String, @SerialName("week_start") val weekStart: String, val complete: Boolean = false,
    val target: String? = null, val summary: String? = null, val status: String? = null, val felt: String? = null,
    val runs: List<FocusRun> = emptyList(),
    val auto: Boolean = false,
)

@Serializable
data class FocusOption(val kind: String, val title: String, val reason: String)

@Serializable
data class FocusState(
    @SerialName("week_start") val weekStart: String,
    val current: FocusEval? = null,
    @SerialName("last_week") val lastWeek: FocusEval? = null,
    val options: List<FocusOption> = emptyList(),
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
    @SerialName("checkin_prompt") val checkinPrompt: CheckinPrompt? = null,
    val highlights: List<Highlight> = emptyList(),
    val changes: List<String> = emptyList(),
    val race: RaceStatus? = null,
    val scores: Scores? = null,
    val readiness: Score? = null,
    @SerialName("next_run") val nextRun: NextRun? = null,
    @SerialName("reading_notes") val readingNotes: Map<String, ReadingNote> = emptyMap(),
)

/** How good a reading is and what it means, in one plain sentence each. */
@Serializable
data class ReadingNote(val verdict: String, val meaning: String)

@Serializable
data class StatItem(val id: String, val label: String, val value: String, val change: Int? = null,
                    @SerialName("higher_is") val higherIs: String = "neutral")

@Serializable
data class Stats(@SerialName("window_days") val windowDays: Int = 28, val items: List<StatItem> = emptyList(), val basis: String? = null)

@Serializable
data class ScoreComponent(val id: String, val title: String, val value: String? = null, val points: Int? = null,
                          @SerialName("weight_pct") val weightPct: Int = 0, val note: String? = null)

@Serializable
data class Score(val status: String, val score: Int? = null, val label: String? = null, val used: Int? = null, val of: Int? = null,
                 val components: List<ScoreComponent> = emptyList(), val detail: String? = null, val basis: String? = null,
                 @SerialName("capped_by") val cappedBy: String? = null)

/** The next run, calculated from readiness, recent runs and Garmin's zones. */
@Serializable
data class NextRunHr(val min: Int? = null, val max: Int? = null, val text: String)

@Serializable
data class NextRun(val date: String, @SerialName("day_label") val dayLabel: String, val kind: String, val title: String,
                   @SerialName("distance_km") val distanceKm: Double? = null, val minutes: Int? = null, val hr: NextRunHr? = null,
                   val pace: String? = null, val why: List<String> = emptyList(), val basis: String? = null)

@Serializable
data class Scores(val status: String, val age: Int? = null, val fitness: Score? = null, val health: Score? = null, val basis: String? = null,
                  val missing: List<String> = emptyList())

@Serializable
data class RaceSession(
    val date: String, val kind: String, val text: String, val minutes: Int? = null, val optional: Boolean = false,
    val status: String, @SerialName("ran_minutes") val ranMinutes: Int? = null, @SerialName("source_id") val sourceId: String? = null,
    @SerialName("moved_to") val movedTo: String? = null,
)

@Serializable
data class RaceWeek(
    @SerialName("week_start") val weekStart: String, val phase: String,
    @SerialName("target_minutes") val targetMinutes: Int? = null, @SerialName("done_minutes") val doneMinutes: Int = 0,
    val sessions: List<RaceSession> = emptyList(), val guardrail: String? = null, val basis: String? = null,
)

@Serializable
data class RaceStatus(
    val headline: String, val phase: String, @SerialName("phase_note") val phaseNote: String,
    @SerialName("days_to_go") val daysToGo: Int, @SerialName("prediction_text") val predictionText: String? = null,
    val week: RaceWeek? = null,
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
    @SerialName("gap_pace_s_per_km") val gapPaceSPerKm: Double? = null,
    @SerialName("cadence_spm") val cadenceSpm: Double? = null,
    val zone: Int? = null,
)

@Serializable
data class BestEffort(
    val label: String,
    @SerialName("elapsed_s") val elapsedS: Double,
    @SerialName("pace_s_per_km") val paceSPerKm: Double,
    @SerialName("previous_best_s") val previousBestS: Double? = null,
    @SerialName("is_best") val isBest: Boolean = false,
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
    @SerialName("garmin_vo2max_day") val garminVo2maxDay: Point? = null,
    val splits: List<Split> = emptyList(),
    val classification: Classification,
    val decoupling: Decoupling,
    val comparable: Comparable = Comparable(),
    val findings: List<Finding> = emptyList(),
    val effort: Effort? = null,
    @SerialName("next_focus") val nextFocus: String,
    val narrative: Narrative? = null,
    val story: List<String> = emptyList(),
    @SerialName("best_efforts") val bestEfforts: Map<String, BestEffort> = emptyMap(),
    val intent: RunIntent? = null,
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
    @SerialName("goal_type") val goalType: String? = null,
    @SerialName("ai_enabled") val aiEnabled: Boolean = false,
    @SerialName("ai_model") val aiModel: String = "gpt-6.1-sol",
    @SerialName("ai_available") val aiAvailable: Boolean = false,
    @SerialName("morning_window_start") val morningWindowStart: String = "06:00",
    @SerialName("morning_window_end") val morningWindowEnd: String = "10:00",
    @SerialName("profile_sex") val profileSex: String? = null,
    @SerialName("profile_birth_date") val profileBirthDate: String? = null,
    @SerialName("profile_detected") val profileDetected: CompareProfile? = null,
    @SerialName("race_date") val raceDate: String? = null,
    @SerialName("race_distance") val raceDistance: String? = null,
    @SerialName("race_target_s") val raceTargetS: Int? = null,
    @SerialName("race_name") val raceName: String? = null,
    @SerialName("week_start_day") val weekStartDay: String? = null,
    @SerialName("week_start_effective") val weekStartEffective: String = "monday",
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
    val novelty: String? = null,              // new | changed | continuing
    @SerialName("user_state") val userState: String? = null, // dismissed | working_on
)

@Serializable
data class InsightsReport(
    val id: Long,
    @SerialName("local_date") val localDate: String,
    val revision: Int,
    @SerialName("generated_at") val generatedAt: String,
    val synthetic: Boolean,
    val insights: List<Insight>,
    val stats: Stats? = null,
)

@Serializable
data class TrendPoint(val date: String, val value: Double? = null)

@Serializable
data class BandPoint(val date: String, val q1: Double? = null, val median: Double? = null, val q3: Double? = null)

@Serializable
data class TrendSummary(
    val n: Int,
    @SerialName("previous_n") val previousN: Int,
    val median: Double? = null,
    @SerialName("previous_median") val previousMedian: Double? = null,
    val change: Double? = null,
    val meaningful: Boolean = false,
    val enough: Boolean = false,
)

@Serializable
data class TrendMetric(
    val metric: String,
    val title: String,
    val unit: String,
    val points: List<TrendPoint>,
    val band: List<BandPoint>,
    val summary: TrendSummary,
    @SerialName("measured_days") val measuredDays: Int,
)

@Serializable
data class WeekVolume(
    @SerialName("week_start") val weekStart: String,
    val runs: Int,
    @SerialName("distance_m") val distanceM: Double,
    @SerialName("moving_s") val movingS: Double,
    val partial: Boolean,
    @SerialName("activity_ids") val activityIds: List<String> = emptyList(),
)

@Serializable
data class PacePoint(val date: String, @SerialName("pace_s_per_km") val paceSPerKm: Double, @SerialName("source_id") val sourceId: String? = null)

@Serializable
data class PaceSeries(val device: String, val points: List<PacePoint>)

@Serializable
data class PaceAtHr(@SerialName("band_bpm") val bandBpm: List<Int>? = null, val verdict: String, val headline: String, val series: List<PaceSeries> = emptyList())

@Serializable
data class Trends(
    val days: Int,
    val start: String,
    val end: String,
    val synthetic: Boolean,
    @SerialName("device_changes") val deviceChanges: List<String> = emptyList(),
    val metrics: List<TrendMetric>,
    @SerialName("weekly_running") val weeklyRunning: List<WeekVolume>,
    @SerialName("pace_at_hr") val paceAtHr: PaceAtHr,
    @SerialName("ai_summary") val aiSummary: ScreenSummary? = null,
)

@Serializable
data class FocusRule(val rule: String, val text: String)

@Serializable
data class WeeklyReport(
    val id: Long,
    val revision: Int,
    @SerialName("generated_at") val generatedAt: String,
    val synthetic: Boolean,
    @SerialName("week_start") val weekStart: String,
    @SerialName("week_end") val weekEnd: String,
    val headline: String,
    val findings: List<Finding>,
    @SerialName("next_week_focus") val nextWeekFocus: FocusRule,
)

@Serializable
data class RevisionInfo(val id: Long, val revision: Int, @SerialName("generated_at") val generatedAt: String, @SerialName("data_cutoff") val dataCutoff: String? = null)

@Serializable
data class RacePredictions(val date: String? = null, @SerialName("5k") val k5: Double? = null, @SerialName("10k") val k10: Double? = null,
                           val half: Double? = null, val marathon: Double? = null)

@Serializable
data class Vo2(val value: Double, val date: String? = null)

@Serializable
data class TrainingStatus(
    val phrase: String? = null, val date: String? = null, val since: String? = null, val paused: Boolean? = null,
    @SerialName("acute_load") val acuteLoad: Double? = null, @SerialName("chronic_min") val chronicMin: Double? = null,
    @SerialName("chronic_max") val chronicMax: Double? = null,
)

@Serializable
data class LoadBalance(@SerialName("trainingBalanceFeedbackPhrase") val phrase: String? = null)

@Serializable
data class GarminFitness(
    @SerialName("race_predictions") val racePredictions: RacePredictions? = null,
    val vo2max: Vo2? = null,
    @SerialName("training_status") val trainingStatus: TrainingStatus? = null,
    @SerialName("load_balance") val loadBalance: LoadBalance? = null,
    @SerialName("heat_acclimation_pct") val heatAcclimationPct: Double? = null,
    @SerialName("fetched_at") val fetchedAt: String? = null,
)

@Serializable
data class RecordBest(@SerialName("elapsed_s") val elapsedS: Double, val date: String, @SerialName("source_id") val sourceId: String)

@Serializable
data class RecordEntry(val label: String, val best: RecordBest? = null, val progression: List<RecordBest> = emptyList())

@Serializable
data class Fitness(
    val garmin: GarminFitness? = null,
    @SerialName("vo2max_series") val vo2maxSeries: List<Point> = emptyList(),
    val records: Map<String, RecordEntry> = emptyMap(),
    @SerialName("easy_pace") val easyPace: Insight? = null,
    val synthetic: Boolean = false,
)

@Serializable
data class Me(val id: Long, val email: String? = null, val name: String? = null, val role: String)

@Serializable
data class AuthResult(val token: String, val user: Me)

@Serializable
data class GoogleSignInBody(@SerialName("id_token") val idToken: String, @SerialName("device_name") val deviceName: String)

@Serializable
data class CheckinPrompt(val ask: Boolean = false, val reason: String? = null)

@Serializable
data class CoachInsight(val title: String, val text: String, @SerialName("evidence_ids") val evidenceIds: List<String> = emptyList(),
                        val confidence: String = "low")

@Serializable
data class CoachRec(val title: String, val text: String, val why: String, @SerialName("evidence_ids") val evidenceIds: List<String> = emptyList(),
                    val category: String = "training")

@Serializable
data class CoachTarget(val type: String, val id: String? = null, val date: String? = null)

@Serializable
data class CoachView(
    val status: String,                       // ok | pending | disabled | not_configured | rejected | failed | budget_exceeded
    val model: String? = null,
    @SerialName("generated_at") val generatedAt: String? = null,
    @SerialName("key_source") val keySource: String? = null,
    val tldr: String? = null,
    val summary: String? = null,
    val insights: List<CoachInsight> = emptyList(),
    val recommendations: List<CoachRec> = emptyList(),
    val targets: Map<String, CoachTarget> = emptyMap(),
    val detail: String? = null,
    val previous: CoachView? = null,
)

@Serializable
data class CompareProfile(
    val sex: String? = null,
    @SerialName("birth_date") val birthDate: String? = null,
    val age: Int? = null,
    val source: String? = null,
)

@Serializable
data class AgeGradeRow(
    val distance: String,
    val label: String,
    val kind: String,                                  // best | prediction
    @SerialName("time_s") val timeS: Double,
    val date: String? = null,
    @SerialName("source_id") val sourceId: String? = null,
    @SerialName("age_grade_pct") val ageGradePct: Double,
    @SerialName("class") val gradeClass: String,
    @SerialName("age_graded_time_s") val ageGradedTimeS: Double,
)

@Serializable
data class CompareItem(
    val id: String,
    val title: String,
    val status: String,                                // ok | unavailable | no_reference
    val headline: String? = null,
    val detail: String? = null,
    val method: String? = null,
    val source: String? = null,
    val caveats: List<String> = emptyList(),
    val rows: List<AgeGradeRow> = emptyList(),
    val chart: kotlinx.serialization.json.JsonObject? = null,
)

@Serializable
data class CompareReport(
    val profile: CompareProfile = CompareProfile(),
    val missing: List<String> = emptyList(),
    val items: List<CompareItem> = emptyList(),
    @SerialName("ai_summary") val aiSummary: ScreenSummary? = null,
)

@Serializable
data class SummarySentence(val text: String, @SerialName("evidence_ids") val evidenceIds: List<String> = emptyList())

/** A daily AI summary of one screen: ok | pending (with the previous one) | disabled | not_configured | rejected | failed | budget_exceeded. */
@Serializable
data class ScreenSummary(
    val status: String,
    val model: String? = null,
    @SerialName("generated_at") val generatedAt: String? = null,
    @SerialName("local_date") val localDate: String? = null,
    val sentences: List<SummarySentence> = emptyList(),
    val previous: ScreenSummary? = null,
)

@Serializable
data class HighlightTarget(val type: String, val id: String? = null)   // run | insights | compare | focus

/** Something that stands out today; tone is attention | positive | info. */
@Serializable
data class Highlight(
    val id: String,
    val tone: String,
    val kind: String,
    val title: String,
    val text: String = "",
    val target: HighlightTarget? = null,
    val source: String? = null,
)

@Serializable
data class RunAiPoint(val text: String, @SerialName("evidence_ids") val evidenceIds: List<String> = emptyList())

@Serializable
data class RunAiNext(val text: String, val direction: String = "same", @SerialName("evidence_ids") val evidenceIds: List<String> = emptyList())

/** AI input on one run: none (not asked yet) | pending | ok | disabled | not_configured | rejected | failed | budget_exceeded. */
@Serializable
data class RunAi(
    val status: String,
    val model: String? = null,
    @SerialName("generated_at") val generatedAt: String? = null,
    @SerialName("key_source") val keySource: String? = null,
    val tldr: String? = null,
    val summary: String? = null,
    @SerialName("went_well") val wentWell: List<RunAiPoint> = emptyList(),
    @SerialName("to_work_on") val toWorkOn: List<RunAiPoint> = emptyList(),
    @SerialName("next_time") val nextTime: RunAiNext? = null,
    val detail: String? = null,
    val previous: RunAi? = null,
)

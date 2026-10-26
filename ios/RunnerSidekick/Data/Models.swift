import Foundation

// Mirrors the backend contract (backend/sidekick/api.py, reports.py) as the Android app reads it. Canonical units:
// m, s, m/s, bpm, ms. Decoded with snake_case → camelCase; anything the server leaves out decodes as empty or nil.

struct Status: Codable {
    var mode: String
    var synthetic: Bool
    var today: String
    var timezone: String
    var weekStartDay: String?
    var connection: Connection
    var latestObservationDate: String?
    var latestActivityStart: String?
    @D var syncRunning: Bool
    var syncProgress: SyncProgress?
    var lastJob: SyncJob?
    /// When a manual Garmin sync is next allowed (the server's cooldown), or nil when it is now
    var syncNextAllowedAt: String?
    var backfill: Backfill?
    var garminOfficial: GarminOfficial?
    /// Garmin is connected for this account (true when an older server doesn't say)
    @DefaultTrue var garminLinked: Bool
    /// The runner's watch today: "garmin" or "samsung"
    var watch: String?
}

struct SyncJob: Codable { var outcome: String?; var detail: String?; var finishedAt: String? }
struct SyncProgress: Codable { @D var percent: Int; var phase: String? }
struct GarminOfficial: Codable { @D var available: Bool; @D var connected: Bool; var dataImport: String? }
struct Connection: Codable {
    var state: String
    var detail: String?
    var lastAttemptAt: String?
    var lastSuccessAt: String?
    var retryNotBefore: String?
}
struct Backfill: Codable {
    var target: String?
    var oldestDone: String?
    enum CodingKeys: String, CodingKey { case target = "backfillTarget", oldestDone }
}

struct Observed: Codable {
    var value: Double?
    var unit: String?
    var date: String?
    var method: String?
    var label: String?
    var runs: Int?
    var distanceM: Double?
}

struct Comparison: Codable {
    var kind: String
    var median: Double?
    var q1: Double?
    var q3: Double?
    var n: Int?
    var value: Double?
    var window: [String]?
    var concernDirection: String?
}

struct Delta: Codable { var abs: Double?; var pct: Double? }
struct Evidence: Codable { @D var recordIds: [String]; @D var dateRange: [String] }
struct Point: Codable, Hashable { var date: String; var value: Double }

struct Finding: Codable, Identifiable {
    /// For a reading not in yet today: the most recent measured value (last 3 days)
    var last: Point?
    var id: String
    var category: String
    var metric: String
    var title: String
    /// within | outside | sustained | learning | missing | info | not_compared
    var status: String
    var statement: String
    var interpretation: String?
    var observed: Observed?
    var comparison: Comparison?
    var delta: Delta?
    var evidence: Evidence?
    var sampleSize: Int?
    @D var limitations: [String]
    var algorithmVersion: String
    @DefaultTrue var derived: Bool
    var sparkline: [Point]?
}

struct Recommendation: Codable {
    var state: String
    var ruleId: String
    var reason: String
    var suggestion: String
    @D var evidenceIds: [String]
    @D var suppressIntensity: Bool
    var uncertainty: String?
    var rulesVersion: String
    var plan: DayPlan?
}

struct DayPlan: Codable { var kind: String; var minutes: Int? }

/// What a run was meant to be (stated, from the plan or inferred) and, when stated, the runner's own report on it.
struct RunIntent: Codable, Equatable {
    var kind: String
    var note: String?
    var source: String?
    var target: String?
    var effort: String?
    var feel: String?
    var limiter: String?
    var limiter2: String?
    var health: String?
}

struct FocusRun: Codable, Hashable { var date: String; var sourceId: String?; var value: Double?; @D var met: Bool }
struct FocusEval: Codable {
    var kind: String
    var title: String
    var weekStart: String
    @D var complete: Bool
    var target: String?
    var summary: String?
    var status: String?
    var felt: String?
    @D var runs: [FocusRun]
    @D var auto: Bool
}
struct FocusOption: Codable, Hashable { var kind: String; var title: String; var reason: String }
struct FocusState: Codable {
    var weekStart: String
    var current: FocusEval?
    var lastWeek: FocusEval?
    @D var options: [FocusOption]
}

struct GarminContext: Codable, Hashable { var metric: String; var value: Double; var unit: String; var label: String?; var origin: String }

struct RecentRun: Codable {
    var sourceId: String
    var localDate: String
    var name: String?
    var distanceM: Double?
    var movingS: Double?
    var avgHr: Double?
}

struct NarrativeSentence: Codable { var text: String; @D var findingIds: [String] }
struct Narrative: Codable {
    var status: String
    var provider: String?
    var model: String?
    @D var sentences: [NarrativeSentence]
    var focus: NarrativeSentence?
    var detail: String?
}

struct MorningReport: Codable {
    var id: Int
    var type: String
    var localDate: String
    var revision: Int
    var generatedAt: String
    var dataCutoff: String?
    var synthetic: Bool
    @D var provisional: Bool
    var headline: String
    var recommendation: Recommendation
    @D var topFindingIds: [String]
    @D var findings: [Finding]
    @D var garminContext: [GarminContext]
    /// Last night with the Samsung watch (context only), or nil
    var overnight: Overnight?
    var checkin: CheckinDto?
    var recentRun: RecentRun?
    @D var algorithmVersion: [String: String]
    var narrative: Narrative?
    @D var highlights: [Highlight]
    @D var changes: [String]
    var race: RaceStatus?
    var scores: Scores?
    var readiness: Score?
    var nextRun: NextRun?
    var decision: Decision?
    /// Keyed by metric, converted to camelCase by the decoder: look up with `note(for:)`
    @D var readingNotes: [String: ReadingNote]

    func note(for metric: String) -> ReadingNote? { readingNotes[JSON.camel(metric)] ?? readingNotes[metric] }
}

/// How good a reading is and what it means, in one plain sentence each.
struct ReadingNote: Codable { var verdict: String; var meaning: String }

struct StatItem: Codable, Identifiable {
    var id: String
    var label: String
    var value: String
    var change: Int?
    var higherIs: String?
}
struct Stats: Codable { var windowDays: Int?; @D var items: [StatItem]; var basis: String? }

struct ScoreComponent: Codable, Identifiable {
    var id: String
    var title: String
    var value: String?
    var points: Int?
    @D var weightPct: Int
    var note: String?
    var say: String?
    var verdict: String?
    /// Shown in the breakdown but not counted in the score
    @D var context: Bool
}

struct Score: Codable {
    var status: String
    var score: Int?
    var label: String?
    var used: Int?
    var of: Int?
    @D var components: [ScoreComponent]
    var detail: String?
    var basis: String?
    var cappedBy: String?
    var headline: String?
    var heldBackBy: String?
    @D var missing: [String]
    var trend: ScoreTrend?
    @D var improve: [ScoreStep]
    @D var stale: Bool
    var progress: FitnessProgress?
    var garmin: GarminReadiness?
    /// Readiness only: the hardest session today allows (rest, easy, steady, hard) and why it's held to easy
    var allows: String?
    var holdReason: String?
}

/// Garmin's own training readiness and what's left on its recovery timer: shown beside ours, and a cross-check.
struct GarminReadiness: Codable { var score: Int; var level: String?; var recoveryHours: Int? }

/// Is fitness improving? Three separate signals, not averaged into the score.
struct FitnessProgress: Codable {
    var verdict: String
    var confidence: String?
    var summary: String?
    @D var signals: [ProgressSignal]
    var basis: String?
    var agreement: String?
}
struct ProgressSignal: Codable, Identifiable { var id: String; var title: String; var direction: String?; var say: String; var note: String? }
struct ScoreStep: Codable, Hashable { var part: String; var text: String; var gain: Int; var horizon: String? }
struct ScoreTrend: Codable { var delta: Int; var days: Int?; var detail: String?; var note: String? }

struct NextRunHr: Codable { var min: Int?; var max: Int?; var text: String }
struct NextRun: Codable {
    var date: String
    var dayLabel: String
    var kind: String
    var title: String
    var distanceKm: Double?
    var minutes: Int?
    var hr: NextRunHr?
    var pace: String?
    var paceSPerKm: Double?
    /// "or_slower" (easy and long runs) or "around" (race pace)
    var paceWay: String?
    @D var why: [String]
    var basis: String?
    @D var optional: Bool
    var caution: String?
}

struct Scores: Codable {
    var status: String
    var age: Int?
    var fitness: Score?
    var health: Score?
    var basis: String?
    @D var scope: [String: String]
    @D var horizon: [String: String]
    @D var missing: [String]
}

struct RaceSession: Codable, Hashable {
    var date: String
    var kind: String
    var text: String
    var minutes: Int?
    @D var optional: Bool
    var status: String
    var ranMinutes: Int?
    var sourceId: String?
    var movedTo: String?
}
struct RaceWeek: Codable {
    var weekStart: String
    var phase: String
    var targetMinutes: Int?
    @D var doneMinutes: Int
    @D var sessions: [RaceSession]
    var guardrail: String?
    var basis: String?
}
struct RaceStatus: Codable {
    var headline: String
    var phase: String
    var phaseNote: String
    var daysToGo: Int
    var predictionText: String?
    var week: RaceWeek?
    var title: String?
}

struct ActivitySummary: Codable, Identifiable, Hashable {
    var id: String { sourceId }
    var sourceId: String
    var sport: String
    var name: String?
    var startUtc: String
    var utcOffsetS: Int?
    var localDate: String
    var distanceM: Double?
    var elapsedS: Double?
    var movingS: Double?
    var avgHr: Double?
    var elevationGainM: Double?
    var paceMovingSPerKm: Double?
    @D var synthetic: Bool
    @D var records: [RunRecord]
    /// The runner has said what the run was meant to be or how it went (else the app asks about its newest run)
    @D var answered: Bool
}

struct LabelValue: Codable, Hashable { var label: String; var value: String }
struct RunRecord: Codable, Hashable { var id: String; var title: String; var value: String }

struct RunActivity: Codable {
    var sourceId: String
    var name: String?
    var sport: String
    var startUtc: String
    var utcOffsetS: Int?
    var localDate: String
    var distanceM: Double?
    var elapsedS: Double?
    var movingS: Double?
    var timerS: Double?
    var avgHr: Double?
    var maxHr: Double?
    var elevationGainM: Double?
    var avgCadenceSpm: Double?
}

struct Split: Codable, Identifiable {
    var id: Int { idx }
    var idx: Int
    var distanceM: Double?
    var movingS: Double?
    var avgHr: Double?
    var elevationGainM: Double?
    var paceSPerKm: Double?
    var complete: Bool
    var gapPaceSPerKm: Double?
    var cadenceSpm: Double?
    var zone: Int?
}

struct BestEffort: Codable {
    var label: String
    var elapsedS: Double
    var paceSPerKm: Double
    var previousBestS: Double?
    @D var isBest: Bool
}

struct Classification: Codable { var kind: String; var reason: String }
struct Half: Codable { var meanSpeedMps: Double; var meanHr: Double }

struct Decoupling: Codable {
    var eligible: Bool
    /// Set when heart rate looked unreliable in parts of the run
    var hrCaveat: String?
    @D var reasons: [String]
    var decouplingPct: Double?
    var powerDecouplingPct: Double?
    @D var gradeAdjusted: Bool
    var firstHalf: Half?
    var secondHalf: Half?
    var segmentMovingS: Double?
    var hrCoverage: Double?
    var method: String?
}

struct ComparableRun: Codable, Identifiable {
    var id: String { sourceId }
    var sourceId: String
    var localDate: String
    var distanceM: Double?
    var paceSPerKm: Double?
    var avgHr: Double?
}
struct Comparable: Codable { @D var n: Int; @D var runs: [ComparableRun] }
struct Effort: Codable { var rpe: Int; var sessionRpeLoad: Int; var note: String }

struct PostRunReport: Codable {
    var id: Int
    var revision: Int
    var generatedAt: String
    var synthetic: Bool
    var activity: RunActivity
    var paceMovingSPerKm: Double?
    /// Garmin's own per-run numbers under Garmin's names (camelCase already)
    @D var garminMetrics: [String: JSONValue]
    /// Garmin's own reads of the run (performance condition, stamina left, HR vs its threshold)
    @D var garminExtra: [LabelValue]
    var garminVo2maxDay: Point?
    /// The app's own training load for the run (Edwards, from heart-rate zones)
    var load: Int?
    var hrQuality: HrQuality?
    var verdict: RunVerdict?
    /// The watch that recorded the run: "Garmin" or "Samsung"
    var watch: String?
    var recordedWith: String?
    var hrSensor: HrSensor?
    var vo2Ours: RunVo2?
    var garminReadinessDay: Point?
    @D var splits: [Split]
    var classification: Classification
    var decoupling: Decoupling
    var comparable: Comparable?
    @D var findings: [Finding]
    var effort: Effort?
    var nextFocus: String
    var narrative: Narrative?
    @D var story: [String]
    @D var checks: [RunCheck]
    @D var bestEfforts: [String: BestEffort]
    var intent: RunIntent?

    var watchName: String { watch ?? "Garmin" }
}

struct Chart: Codable {
    @D var t: [Double]
    @D var hr: [Double?]
    @D var speed: [Double?]
    @D var elev: [Double?]
}

struct ActivityDetail: Codable {
    var report: PostRunReport?
    var chart: Chart?
    var route: RunRoute?
    @D var watchletic: Bool
}

/// The repeat route this run belongs to (recognised from its shape), when it has one.
struct RunRoute: Codable { var id: String; var name: String; @D var distanceKm: Double; @D var loop: Bool; @D var runs: Int; var progress: String? }

struct RoutesReport: Codable { @D var routes: [RouteSummary]; @D var basis: String }
struct RouteSummary: Codable, Identifiable {
    var id: String
    var name: String
    @D var distanceKm: Double
    @D var loop: Bool
    @D var runs: Int
    var first: String?
    var last: String?
    var progress: String?
    @D var rows: [RouteRun]
    /// The route's shape in a unit box (no coordinates), for drawing
    @D var outline: [[Double]]
}
struct RouteRun: Codable, Identifiable {
    var id: String { sourceId + date }
    var sourceId: String
    var date: String
    var distanceM: Double?
    var paceSPerKm: Double?
    var avgHr: Double?
    var kind: String?
    var temperatureC: Double?
    var hot: Bool?
}

struct ReportListItem: Codable, Identifiable {
    var id: Int
    var type: String
    var subjectKey: String
    var localDate: String
    var revision: Int
    var generatedAt: String
    @D var synthetic: Bool
    var title: String?
    var state: String?
}

struct CheckinDto: Codable {
    var id: String?
    var localDate: String
    var energy: Int?
    var soreness: Int?
    var recovery: Int?
    @D var pain: Bool
    @D var illness: Bool
    var notes: String?
    @D var tags: [String]
    var clientUpdatedAt: String
    @D var deleted: Bool
}

/// Training numbers: lactate threshold, form, race predictions over time, heart-rate recovery, climbing speed.
struct TrainingNumbers: Codable { @D var items: [NumberItem] }
struct NumberItem: Codable, Identifiable {
    var id: String
    var title: String
    var status: String?
    var value: String?
    var headline: String?
    var detail: String?
    @D var basis: String
    @D var series: [NumberPoint]
    @D var lowerIsBetter: Bool
    var sourceId: String?
}
struct NumberPoint: Codable, Hashable { var date: String; var v: Double; var label: String?; var sourceId: String? }

/// Cardio fitness (experimental): the evidence about aerobic capacity side by side.
struct Cardio: Codable {
    var runs: CardioPart
    var questionnaire: CardioPart
    var performance: CardioPart
    var garmin: CardioPart
    var hunt: CardioPart?
    var combined: CardioCombined?
    @D var huntQuestions: [HuntQuestion]
    var hrMax: CardioHrMax?
    @D var notes: [String]
    @D var basis: String
    @D var parScale: [ParOption]
    var inputs: CardioInputs?
}
struct CardioInputs: Codable { var weightKg: Double?; var weightFrom: String?; var heightCm: Double?; var heightFrom: String? }
struct CardioPart: Codable, Identifiable {
    var id: String
    var title: String
    var maker: String?
    var status: String?
    var value: Double?
    var headline: String?
    var detail: String?
    var caveat: String?
    var source: String?
    var comparison: CardioComparison?
    var spread: [Int]?
    var sensitivity: String?
    var runsUsed: Int?
    var leftOut: [String: Int]?
    @D var points: [CardioPoint]
    var date: String?
    var sourceId: String?
}
struct CardioComparison: Codable { var headline: String; var detail: String?; var percentile: Int?; var source: String? }
struct CardioPoint: Codable, Hashable { var date: String; var value: Double; var sourceId: String }
struct CardioHrMax: Codable { var value: Double?; var source: String? }
struct ParOption: Codable, Hashable { var value: Int; var text: String }
struct CardioCombined: Codable { var value: Double; @D var inputs: [CombinedInput]; @D var spread: [Double] }
struct CombinedInput: Codable, Hashable { var id: String; var title: String; var value: Double }
struct HuntQuestion: Codable, Identifiable { var id: String { key }; var key: String; var title: String; @D var options: [HuntOption] }
struct HuntOption: Codable, Hashable { var value: String; var text: String }

/// Your records: Garmin's all-time personal records next to the app's bests.
struct Trophies: Codable { @D var groups: [TrophyGroup]; var historySince: String?; @D var basis: String }
struct TrophyGroup: Codable, Identifiable { var id: String; var title: String; @D var items: [Trophy] }
struct Trophy: Codable, Identifiable {
    var id: String
    var title: String
    var value: String
    var date: String?
    var sourceId: String?
    @D var source: String
    var comparison: TrophyComparison?
    @D var history: [TrophyPoint]
    @D var lowerIsBetter: Bool
}
struct TrophyPoint: Codable, Hashable { var date: String; var value: String; var v: Double; var sourceId: String?; @D var garmin: Bool }
struct TrophyComparison: Codable { var headline: String?; var detail: String? }

/// Today's decision, as far as the app needs it. unwellApplied: the server already acted on reported pain or illness.
struct Decision: Codable { @D var unwellApplied: Bool }

/// The settings as the screens read them. Saving goes through the raw JSON (see Repository.saveSettings), so every
/// field, including ones this app doesn't know, round-trips and a cleared value is sent as null.
struct SettingsDto: Codable {
    var timezone: String
    @D var runningDays: [Int]
    var goal: String?
    var availableMinutes: Int?
    var hrZoneSource: String?
    var goalType: String?
    @D var aiEnabled: Bool
    @DefaultTrue var weatherEnabled: Bool
    var aiModel: String?
    @D var aiAvailable: Bool
    var morningWindowStart: String?
    var morningWindowEnd: String?
    var profileSex: String?
    var profileBirthDate: String?
    var profileDetected: CompareProfile?
    var raceDate: String?
    var raceDistance: String?
    var raceTargetS: Int?
    var raceName: String?
    var weekStartDay: String?
    var weekStartEffective: String?
    var activityPar: Int?
    var activityParAt: String?
    var profileWeightKg: Double?
    var profileWeightKgAt: String?
    var profileHeightCm: Double?
    var profileHeightCmAt: String?
    var hrMax: Int?
    var hrMaxAt: String?
    var profileWaistCm: Double?
    var profileWaistCmAt: String?
    var huntFrequency: String?
    var huntFrequencyAt: String?
    var huntIntensity: String?
    var huntIntensityAt: String?
    var huntDuration: String?
    var huntDurationAt: String?
    var restingPulseSeated: Int?
    var restingPulseSeatedAt: String?
    var watch: String?
    var fitnessAgeSource: String?
    var vo2Source: String?
    var units: String?
    var appearance: String?
    var notifications: Bool?
    var backgroundRefresh: Bool?

    var windowStart: String { morningWindowStart ?? "06:00" }
    var windowEnd: String { morningWindowEnd ?? "10:00" }
}

struct TrendRun: Codable, Identifiable { var id: String { sourceId }; var sourceId: String; var localDate: String; var distanceM: Double?; var movingS: Double? }

/// One plain check of how a run went, with a verdict: good, ok, low or info.
struct RunCheck: Codable, Identifiable { var id: String; var title: String; var say: String; var verdict: String }

struct Insight: Codable, Identifiable {
    var id: String
    var question: String
    var category: String
    /// pattern | no_clear_pattern | not_enough_data
    var verdict: String
    var headline: String
    @D var detail: String
    var sampleSize: Int?
    @D var method: String
    @D var confounders: [String]
    var practical: String?
    var confidence: String?
    var chart: JSONValue?
    var evidence: Evidence?
    var algorithmVersion: String?
    var novelty: String?
    var userState: String?
}

struct InsightsReport: Codable {
    var id: Int
    var localDate: String
    var revision: Int
    var generatedAt: String
    @D var synthetic: Bool
    @D var insights: [Insight]
    var stats: Stats?
}

struct TrendPoint: Codable { var date: String; var value: Double? }
struct BandPoint: Codable { var date: String; var q1: Double?; var median: Double?; var q3: Double? }
struct TrendSummary: Codable {
    @D var n: Int
    @D var previousN: Int
    var median: Double?
    var previousMedian: Double?
    var change: Double?
    @D var meaningful: Bool
    @D var enough: Bool
}
struct TrendMetric: Codable, Identifiable {
    var id: String { metric }
    var metric: String
    var title: String
    var unit: String
    @D var points: [TrendPoint]
    @D var band: [BandPoint]
    var summary: TrendSummary
    @D var measuredDays: Int
}
struct WeekVolume: Codable, Identifiable {
    var id: String { weekStart }
    var weekStart: String
    var runs: Int
    var distanceM: Double
    var movingS: Double
    @D var partial: Bool
    @D var activityIds: [String]
    @D var runList: [TrendRun]
}
struct PacePoint: Codable { var date: String; var paceSPerKm: Double; var sourceId: String? }
struct PaceSeries: Codable { var device: String; @D var points: [PacePoint] }
struct PaceAtHr: Codable { var bandBpm: [Int]?; var verdict: String; var headline: String; @D var series: [PaceSeries] }
struct Trends: Codable {
    var days: Int
    var start: String
    var end: String
    @D var synthetic: Bool
    @D var deviceChanges: [String]
    @D var metrics: [TrendMetric]
    @D var weeklyRunning: [WeekVolume]
    var paceAtHr: PaceAtHr?
    var aiSummary: ScreenSummary?
}

struct FocusRule: Codable { var rule: String; var text: String }
struct WeeklyReport: Codable {
    var id: Int
    var revision: Int
    var generatedAt: String
    @D var synthetic: Bool
    var weekStart: String
    var weekEnd: String
    var headline: String
    @D var findings: [Finding]
    var nextWeekFocus: FocusRule
}

struct RevisionInfo: Codable, Identifiable { var id: Int; var revision: Int; var generatedAt: String; var dataCutoff: String? }

struct RacePredictions: Codable {
    var date: String?
    var k5: Double?
    var k10: Double?
    var half: Double?
    var marathon: Double?
    enum CodingKeys: String, CodingKey { case date, k5 = "5k", k10 = "10k", half, marathon }
}
struct Vo2: Codable { var value: Double; var date: String? }
struct TrainingStatus: Codable {
    var phrase: String?
    var date: String?
    var since: String?
    var paused: Bool?
    var acuteLoad: Double?
    var chronicMin: Double?
    var chronicMax: Double?
}
struct LoadBalance: Codable {
    var phrase: String?
    enum CodingKeys: String, CodingKey { case phrase = "trainingBalanceFeedbackPhrase" }
}
struct GarminFitness: Codable {
    var racePredictions: RacePredictions?
    var vo2max: Vo2?
    var trainingStatus: TrainingStatus?
    var loadBalance: LoadBalance?
    var heatAcclimationPct: Double?
    var fetchedAt: String?
}
struct RecordBest: Codable, Hashable { var elapsedS: Double; var date: String; var sourceId: String }
struct RecordEntry: Codable { var label: String; var best: RecordBest?; @D var progression: [RecordBest] }
struct Fitness: Codable {
    var garmin: GarminFitness?
    @D var vo2maxSeries: [Point]
    /// Whose VO2 max the series is: "Garmin", "Samsung" or "Runner Sidekick"
    var vo2Maker: String?
    @D var records: [String: RecordEntry]
    var easyPace: Insight?
    @D var synthetic: Bool

    var maker: String { vo2Maker ?? "Garmin" }
}

struct Me: Codable { var id: Int; var email: String?; var name: String?; var role: String }
struct AuthResult: Codable { var token: String; var user: Me }

struct CoachInsight: Codable, Hashable { var title: String; var text: String; @D var evidenceIds: [String]; var confidence: String? }
struct CoachRec: Codable, Hashable { var title: String; var text: String; var why: String; @D var evidenceIds: [String]; var category: String? }
struct CoachTarget: Codable { var type: String; var id: String?; var date: String? }
final class CoachView: Codable {
    var status: String
    var model: String?
    var generatedAt: String?
    var keySource: String?
    var tldr: String?
    var summary: String?
    @D var insights: [CoachInsight]
    @D var recommendations: [CoachRec]
    /// Keyed by evidence id (converted to camelCase): look up with `target(for:)`
    @D var targets: [String: CoachTarget]
    var detail: String?
    var previous: CoachView?

    func target(for id: String) -> CoachTarget? { targets[JSON.camel(id)] ?? targets[id] }
}

struct CompareProfile: Codable { var sex: String?; var birthDate: String?; var age: Int?; var source: String? }

struct AgeGradeRow: Codable, Hashable {
    var distance: String
    var label: String
    /// best | prediction
    var kind: String
    var timeS: Double
    var date: String?
    var sourceId: String?
    var ageGradePct: Double
    var gradeClass: String
    var ageGradedTimeS: Double
    enum CodingKeys: String, CodingKey {
        case distance, label, kind, timeS, date, sourceId, ageGradePct, gradeClass = "class", ageGradedTimeS
    }
}

struct CompareItem: Codable, Identifiable {
    var id: String
    var title: String
    /// ok | unavailable | no_reference
    var status: String
    var headline: String?
    var detail: String?
    var method: String?
    var source: String?
    @D var caveats: [String]
    @D var rows: [AgeGradeRow]
    var chart: JSONValue?
}

struct CompareReport: Codable {
    var profile: CompareProfile?
    @D var missing: [String]
    @D var items: [CompareItem]
    var aiSummary: ScreenSummary?
}

struct SummarySentence: Codable, Hashable { var text: String; @D var evidenceIds: [String] }

/// A daily AI summary of one screen: ok | pending (with the previous one) | disabled | not_configured | rejected | failed | budget_exceeded.
final class ScreenSummary: Codable {
    var status: String
    var model: String?
    var generatedAt: String?
    var localDate: String?
    @D var sentences: [SummarySentence]
    var previous: ScreenSummary?
}

struct HighlightTarget: Codable { var type: String; var id: String? }
/// Something that stands out today; tone is attention | positive | info.
struct Highlight: Codable, Identifiable {
    var id: String
    var tone: String
    var kind: String
    var title: String
    @D var text: String
    var target: HighlightTarget?
    var source: String?
}

struct RunAiPoint: Codable, Hashable { var text: String; @D var evidenceIds: [String] }
struct RunAiNext: Codable { var text: String; var direction: String?; @D var evidenceIds: [String] }

/// AI input on one run: none | pending | ok | disabled | not_configured | rejected | failed | budget_exceeded.
final class RunAi: Codable {
    var status: String
    var model: String?
    var generatedAt: String?
    var keySource: String?
    /// "auto" when written right after a sync for a new run, "asked" when requested
    var trigger: String?
    /// The run's type was changed after the input was written
    @D var stale: Bool
    var tldr: String?
    var summary: String?
    @D var wentWell: [RunAiPoint]
    @D var toWorkOn: [RunAiPoint]
    var nextTime: RunAiNext?
    var detail: String?
    var previous: RunAi?
}

/// Last night with the Samsung watch, each value against your previous nights.
struct Overnight: Codable {
    var measuredS: Double
    var asleepS: Double?
    var sleepHr: NightHr?
    var skinTemp: NightSkin?
    var spo2: NightSpo2?
}
struct NightHr: Codable { var avg: Double; var low: Double?; var delta: Double?; @D var nights: Int }
struct NightSkin: Codable { var value: Double; var delta: Double?; @D var nights: Int }
struct NightSpo2: Codable { var avg: Double; var min: Double?; var usual: [Double]?; @D var nights: Int }

/// Heart-rate data quality for a run.
struct HrQuality: Codable { var grade: String; @D var flaggedS: Double; @D var stretches: [HrStretch] }
struct HrStretch: Codable, Hashable { var startS: Double; var endS: Double; var reason: String }

struct RunVerdict: Codable {
    var verdict: String
    var label: String
    var judgedAs: String?
    var basis: String?
    var say: String
    var hrNote: String?
    var ageGrade: AgeGrade?
    var note: String?
}
struct AgeGrade: Codable {
    var pct: Double
    var gradeClass: String
    enum CodingKeys: String, CodingKey { case pct = "ageGradePct", gradeClass = "class" }
}

struct RunVo2: Codable {
    var value: Double?
    var why: String?
    @D var hillAdjusted: Bool
    /// The runner left this run out of Runner Sidekick's VO2 max
    @D var heldOut: Bool
}

struct HrSensor: Codable {
    var name: String?
    var kind: String?
    /// Its connection log, when the recording app keeps one (Watchletic): connects and dropouts
    @D var logged: Bool
    @D var events: [SensorEvent]
}
struct SensorEvent: Codable, Hashable { var atS: Double; var event: String; var device: String? }

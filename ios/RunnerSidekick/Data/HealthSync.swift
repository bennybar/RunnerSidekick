import CoreLocation
import Foundation
import HealthKit
import os

/// Apple Health → the runner's server (POST /v1/apple), read-only on HealthKit. Each kind of data has its own HealthKit
/// anchor, saved once the batch read with it was accepted: a later sync sends only what's new or changed, and an
/// interrupted import carries on where it stopped. The server upserts, so a batch sent twice is harmless.
/// Never logs or tracks health values.
actor HealthSync {
    static let shared = HealthSync()
    nonisolated static let health = HKHealthStore()
    nonisolated static let log = Logger(subsystem: "com.bennybarak.runnersidekick", category: "health")
    nonisolated static var available: Bool { HKHealthStore.isHealthDataAvailable() }

    /// What this phone remembers about the uploads, per account.
    struct State: Codable, Equatable {
        /// Where the import starts (a year back, set at the first sync); later syncs use the same window
        var since: Date?
        /// HealthKit anchors per kind of data (archived HKQueryAnchor)
        var anchors: [String: Data] = [:]
        var importDone = false
        var lastUploadAt: Date?
        var lastError: String?

        private static func key(_ account: String) -> String { "apple_health#\(account)" }
        static func load(_ account: String) -> State {
            UserDefaults.standard.data(forKey: key(account)).flatMap { try? JSONDecoder().decode(State.self, from: $0) } ?? State()
        }
        func save(_ account: String) { UserDefaults.standard.set(try? JSONEncoder().encode(self), forKey: Self.key(account)) }
    }

    enum Failure: LocalizedError {
        case notApple
        var errorDescription: String? { "The server doesn't have Apple Watch as this account's watch. Choose it again in Me." }
    }

    nonisolated static let readTypes: Set<HKObjectType> = {
        let q: [HKQuantityTypeIdentifier] = [.heartRate, .distanceWalkingRunning, .runningPower, .runningSpeed, .stepCount, .activeEnergyBurned,
                                             .runningStrideLength, .runningVerticalOscillation, .runningGroundContactTime, .restingHeartRate,
                                             .heartRateVariabilitySDNN, .vo2Max, .appleExerciseTime, .bodyMass]
        return Set(q.map { HKQuantityType($0) as HKObjectType })
            .union([HKObjectType.workoutType(), HKSeriesType.workoutRoute(), HKSeriesType.heartbeat(), HKCategoryType(.sleepAnalysis)])
    }()

    /// Asks for read access (the system sheet, once per type; HealthKit never says whether reading was allowed).
    nonisolated static func authorize() async throws {
        try await health.requestAuthorization(toShare: [], read: readTypes)
    }

    // MARK: Observers (background delivery)

    @MainActor private static var observers: [HKObserverQuery] = []

    /// iOS wakes the app when the watch syncs new data, also when the app isn't running (not after a force-quit): each
    /// wake runs an incremental sync, then tells HealthKit it's done. Registered at launch while the watch is Apple.
    @MainActor static func startObservers() {
        guard available, observers.isEmpty else { return }
        let watched: [(HKSampleType, HKUpdateFrequency)] = [
            (HKObjectType.workoutType(), .immediate), (HKCategoryType(.sleepAnalysis), .hourly), (HKQuantityType(.heartRateVariabilitySDNN), .hourly),
            (HKQuantityType(.restingHeartRate), .hourly), (HKQuantityType(.vo2Max), .hourly)]
        for (type, frequency) in watched {
            let q = HKObserverQuery(sampleType: type, predicate: nil) { _, done, error in
                if let error { log.error("Observer: \(error.localizedDescription, privacy: .public)"); done(); return }
                Task { @MainActor in
                    let m = await Store.shared.attempt { try await HealthSync.shared.sync() }
                    log.info("Apple Health sync on new data: \(m ?? "ok", privacy: .public)")
                    done()
                }
            }
            health.execute(q)
            observers.append(q)
            health.enableBackgroundDelivery(for: type, frequency: frequency) { ok, error in
                if !ok { log.error("Background delivery not enabled: \(error?.localizedDescription ?? "", privacy: .public)") }
            }
        }
    }

    @MainActor static func stopObservers() {
        observers.forEach { health.stop($0) }
        observers = []
        health.disableAllBackgroundDelivery { _, _ in }
    }

    // MARK: Sync

    private var current: Task<Void, Error>?
    private var again = false
    private var reporter: (@Sendable (Double, String) -> Void)?
    private var account = ""
    private var st = State()

    /// The continued processing task follows the progress (its system progress UI).
    func setReporter(_ r: (@Sendable (Double, String) -> Void)?) { reporter = r }

    func cancel() { current?.cancel() }

    /// One sync at a time: a call while one runs waits for it, and it runs once more afterwards for what came in meanwhile.
    func sync() async throws {
        if let c = current { again = true; try await c.value; return }
        let t = Task { try await self.loop() }
        current = t
        defer { current = nil }
        try await t.value
    }

    private func loop() async throws {
        // Done (or stopped): the progress goes, and the server's counts and last upload are fetched again
        defer { Task { @MainActor in Store.shared.healthRun = nil; if Store.shared.isApple { _ = try? await Store.shared.refreshApple() } } }
        repeat {
            again = false
            try await once()
        } while again && !Task.isCancelled
    }

    private func once() async throws {
        let apple = await MainActor.run { Store.shared.isApple && Store.shared.local.hasToken }
        guard Self.available, apple, let acct = try await Store.shared.confirmedAccount() else { return }
        account = acct
        st = State.load(acct)
        let since = st.since ?? Calendar.current.date(byAdding: .year, value: -1, to: Date())!
        st.since = since
        await save()
        let first = !st.importDone
        await report(0, first ? "Reading the last 12 months" : "Reading new data")
        do {
            let runs = NSCompoundPredicate(andPredicateWithSubpredicates: [HKQuery.predicateForWorkouts(with: .running), window(since)])
            try await pages("workouts", .workout(runs), limit: 5, from: 0, to: 0.5, label: "Runs") { ws in
                var items: [[String: Any]] = []
                for (i, w) in ws.enumerated() {
                    items.append(try await self.workout(w))
                    await self.report(nil, "Runs (\(i + 1) of \(ws.count) in this batch)")
                }
                return [["workouts": items]]
            }
            try await pages("sleep", .categorySample(type: HKCategoryType(.sleepAnalysis), predicate: window(since)), limit: 400, from: 0.5, to: 0.65, label: "Sleep") { s in
                [["sleep": s.compactMap(Self.sleepItem)]]
            }
            try await pages("hrv", .quantitySample(type: HKQuantityType(.heartRateVariabilitySDNN), predicate: window(since)), limit: 400, from: 0.65, to: 0.8, label: "HRV") { s in
                [["hrv": try await self.hrv(s)]]
            }
            let daily: [(String, HKQuantityTypeIdentifier, String)] = [("resting_hr", .restingHeartRate, "Resting heart rate"), ("steps", .stepCount, "Steps"),
                                                                      ("exercise", .appleExerciseTime, "Exercise minutes"), ("vo2max", .vo2Max, "VO₂ max"), ("weight", .bodyMass, "Weight")]
            for (i, (kind, id, label)) in daily.enumerated() {
                let from = 0.8 + 0.04 * Double(i)
                try await pages(kind, .quantitySample(type: HKQuantityType(id), predicate: window(since)), limit: 5000, from: from, to: from + 0.04, label: label) { s in
                    let cal = Calendar.current
                    let dates = Set(s.flatMap { [cal.startOfDay(for: $0.startDate), cal.startOfDay(for: $0.endDate.addingTimeInterval(-1))] })
                    let days = try await self.days(dates)
                    return stride(from: 0, to: days.count, by: 400).map { ["days": Array(days[$0..<min($0 + 400, days.count)])] }
                }
            }
            st.importDone = true
            st.lastError = nil
            await save()
            await report(1, "Done")
        } catch {
            if !(error is CancellationError) { st.lastError = (error as? APIError)?.userMessage ?? error.localizedDescription }
            await save()
            throw error
        }
    }

    private func window(_ since: Date) -> NSPredicate { HKQuery.predicateForSamples(withStart: since, end: nil) }

    /// Reads one kind of data page by page from its anchor, uploads each page (oldest first) and only then keeps the new
    /// anchor. A page shorter than the limit is the last.
    private func pages<S: HKSample>(_ kind: String, _ predicate: HKSamplePredicate<S>, limit: Int, from: Double, to: Double, label: String,
                                    build: @escaping ([S]) async throws -> [[String: Any]]) async throws {
        let span = max(1, Date().timeIntervalSince(st.since ?? Date()))
        while true {
            try Task.checkCancellation()
            let anchor = st.anchors[kind].flatMap { try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: $0) }
            let r = try await HKAnchoredObjectQueryDescriptor(predicates: [predicate], anchor: anchor, limit: limit).result(for: Self.health)
            let samples = r.addedSamples.sorted { $0.startDate < $1.startDate }
            if !samples.isEmpty {
                await report(from + (to - from) * 0.02, label)
                for body in try await build(samples) { try await upload(body) }
            }
            st.anchors[kind] = try? NSKeyedArchiver.archivedData(withRootObject: r.newAnchor, requiringSecureCoding: true)
            await save()
            let done = r.addedSamples.count < limit
            let at = samples.last.map { min(1, max(0, $0.startDate.timeIntervalSince(st.since ?? Date()) / span)) } ?? 1
            await report(from + (to - from) * (done ? 1 : at), label)
            if done { return }
        }
    }

    /// POST /v1/apple, retried with backoff on network and server errors. A batch the server refuses as malformed is
    /// skipped (and said), so one bad item can't hold every later upload back.
    private func upload(_ body: [String: Any]) async throws {
        var body = body
        body["tz"] = TimeZone.current.identifier
        let data = try JSONSerialization.data(withJSONObject: body)
        var delay = 2.0
        for attempt in 1...5 {
            try Task.checkCancellation()
            do {
                _ = try await API.shared.post("/v1/apple", data)
                st.lastUploadAt = Date()
                return
            } catch APIError.http(409, _) {
                throw Failure.notApple
            } catch APIError.http(let code, let detail) where code == 413 || code == 422 {
                Self.log.error("Apple batch refused (\(code)): \(detail ?? "", privacy: .public)")
                st.lastError = "The server refused some Apple Health data: \(detail ?? "HTTP \(code)")"
                return
            } catch APIError.http(let code, _) where code < 500 && code != 408 && code != 429 {
                throw APIError.http(code, nil)
            } catch let e as APIError {
                if case .unauthorized = e { throw e }
                if case .notConfigured = e { throw e }
                if attempt == 5 { throw e }
            }
            try await Task.sleep(for: .seconds(delay))
            delay *= 3
        }
    }

    private func save() async {
        if !account.isEmpty { st.save(account) }
        let s = st
        await MainActor.run { Store.shared.healthState = s }
    }

    /// fraction nil: the same place, with a new label (the system's progress still moves on a little).
    private func report(_ fraction: Double?, _ label: String) async {
        reporter?(fraction ?? -1, label)
        await MainActor.run {
            let f = fraction ?? Store.shared.healthRun?.fraction ?? 0
            Store.shared.healthRun = Progress(fraction: f, label: "Apple Health · \(label)")
        }
    }

    // MARK: Workouts

    private func workout(_ w: HKWorkout) async throws -> [String: Any] {
        let indoor = (w.metadata?[HKMetadataKeyIndoorWorkout] as? NSNumber)?.boolValue ?? false
        var item: [String: Any] = ["uuid": w.uuid.uuidString, "start": Self.iso(w.startDate), "end": Self.iso(w.endDate),
                                   "sport": indoor ? "treadmill_running" : "running", "indoor": indoor,
                                   "moving_s": w.duration, "elapsed_s": w.endDate.timeIntervalSince(w.startDate)]
        func stat(_ id: HKQuantityTypeIdentifier) -> HKStatistics? { w.statistics(for: HKQuantityType(id)) }
        if let d = stat(.distanceWalkingRunning)?.sumQuantity() { item["distance_m"] = d.doubleValue(for: .meter()) }
        if let e = stat(.activeEnergyBurned)?.sumQuantity() { item["energy_kcal"] = e.doubleValue(for: .kilocalorie()) }
        if let g = w.metadata?[HKMetadataKeyElevationAscended] as? HKQuantity { item["elevation_gain_m"] = g.doubleValue(for: .meter()) }
        if let device = w.device?.name ?? w.device?.model ?? Optional(w.sourceRevision.source.name) { item["device"] = device }
        item["events"] = (w.workoutEvents ?? []).compactMap { e -> [String: Any]? in
            let type: String? = switch e.type {
            case .pause, .motionPaused: "pause"
            case .resume, .motionResumed: "resume"
            case .lap: "lap"
            case .segment: "segment"
            default: nil
            }
            return type.map { ["type": $0, "start": Self.iso(e.dateInterval.start), "end": Self.iso(e.dateInterval.end)] }
        }
        let bpm = HKUnit.count().unitDivided(by: .minute())
        var series: [String: Any] = [:]
        series["hr"] = try await self.series(.heartRate, w, bpm, cumulative: false)
        series["distance"] = try await self.series(.distanceWalkingRunning, w, .meter(), cumulative: true)
        series["power"] = try await self.series(.runningPower, w, .watt(), cumulative: false)
        series["steps"] = try await self.series(.stepCount, w, .count(), cumulative: true)
        series["speed"] = try await self.series(.runningSpeed, w, HKUnit.meter().unitDivided(by: .second()), cumulative: false)
        series["route"] = try await route(w)
        item["series"] = series.filter { !(($0.value as? [Any])?.isEmpty ?? true) }
        var dyn: [String: Any] = [:]
        if let v = stat(.runningStrideLength)?.averageQuantity() { dyn["stride_m"] = Self.r(v.doubleValue(for: .meter()), 3) }
        if let v = stat(.runningVerticalOscillation)?.averageQuantity() { dyn["vertical_osc_cm"] = Self.r(v.doubleValue(for: .meterUnit(with: .centi)), 1) }
        if let v = stat(.runningGroundContactTime)?.averageQuantity() { dyn["ground_contact_ms"] = Self.r(v.doubleValue(for: .secondUnit(with: .milli)), 0) }
        if !dyn.isEmpty { item["dynamics"] = dyn }
        return item
    }

    /// [[seconds from start, value]]: the samples the watch tied to the workout; for a workout without any (some apps),
    /// the samples in its time from the same device. cumulative: a running total (distance, steps).
    private func series(_ id: HKQuantityTypeIdentifier, _ w: HKWorkout, _ unit: HKUnit, cumulative: Bool) async throws -> [[Double]] {
        var out = try await points(HKQuantityType(id), HKQuery.predicateForObjects(from: w), w.startDate, unit, cumulative)
        if out.isEmpty {
            var p = [HKQuery.predicateForSamples(withStart: w.startDate, end: w.endDate, options: [.strictStartDate, .strictEndDate])]
            if let d = w.device { p.append(HKQuery.predicateForObjects(from: [d])) }
            out = try await points(HKQuantityType(id), NSCompoundPredicate(andPredicateWithSubpredicates: p), w.startDate, unit, cumulative)
        }
        return out
    }

    private func points(_ type: HKQuantityType, _ predicate: NSPredicate, _ start: Date, _ unit: HKUnit, _ cumulative: Bool) async throws -> [[Double]] {
        var raw: [(Double, Double)] = []
        let q = HKQuantitySeriesSampleQueryDescriptor(predicate: .quantitySample(type: type, predicate: predicate), options: .orderByQuantitySampleStartDate)
        for try await r in q.results(for: Self.health) {
            let t = (cumulative ? r.dateInterval.end : r.dateInterval.start).timeIntervalSince(start)
            raw.append((t, r.quantity.doubleValue(for: unit)))
        }
        raw.sort { $0.0 < $1.0 }
        guard cumulative else { return raw.map { [Self.r($0.0, 1), Self.r($0.1, 1)] } }
        var total = 0.0
        var out: [[Double]] = raw.first.map { $0.0 > 0 ? [[0, 0]] : [] } ?? []
        for (t, v) in raw { total += v; out.append([Self.r(t, 1), Self.r(total, 1)]) }
        return out
    }

    /// [[seconds from start, lat, lon, altitude m, speed m/s]], unknown values null.
    private func route(_ w: HKWorkout) async throws -> [[Any]] {
        let routes = try await HKSampleQueryDescriptor(predicates: [.workoutRoute(HKQuery.predicateForObjects(from: w))],
                                                       sortDescriptors: [SortDescriptor(\.startDate)]).result(for: Self.health)
        var out: [[Any]] = []
        for r in routes {
            for try await l in HKWorkoutRouteQueryDescriptor(r).results(for: Self.health) {
                out.append([Self.r(l.timestamp.timeIntervalSince(w.startDate), 1), Self.r(l.coordinate.latitude, 6), Self.r(l.coordinate.longitude, 6),
                            l.verticalAccuracy >= 0 ? Self.r(l.altitude, 1) : NSNull(), l.speed >= 0 ? Self.r(l.speed, 2) : NSNull()])
            }
        }
        return out
    }

    // MARK: Sleep, HRV, days

    nonisolated private static func sleepItem(_ s: HKCategorySample) -> [String: Any]? {
        let stage: String? = switch HKCategoryValueSleepAnalysis(rawValue: s.value) {
        case .inBed: "in_bed"
        case .asleepUnspecified: "asleep"
        case .awake: "awake"
        case .asleepCore: "core"
        case .asleepDeep: "deep"
        case .asleepREM: "rem"
        default: nil
        }
        return stage.map { ["start": iso(s.startDate), "end": iso(s.endDate), "stage": $0] }
    }

    /// SDNN as Apple stores it, plus RMSSD worked out here from the reading's beat-to-beat series when there is one.
    private func hrv(_ samples: [HKQuantitySample]) async throws -> [[String: Any]] {
        guard let lo = samples.first?.startDate, let hi = samples.map(\.endDate).max() else { return [] }
        let beats = try await HKSampleQueryDescriptor(predicates: [.heartbeatSeries(HKQuery.predicateForSamples(withStart: lo.addingTimeInterval(-120), end: hi.addingTimeInterval(120)))],
                                                      sortDescriptors: []).result(for: Self.health)
        var out: [[String: Any]] = []
        for s in samples {
            var item: [String: Any] = ["time": Self.iso(s.startDate), "sdnn_ms": Self.r(s.quantity.doubleValue(for: .secondUnit(with: .milli)), 1)]
            let series = beats.filter { $0.startDate <= s.endDate.addingTimeInterval(5) && $0.endDate >= s.startDate.addingTimeInterval(-5) }
                .min { abs($0.startDate.timeIntervalSince(s.startDate)) < abs($1.startDate.timeIntervalSince(s.startDate)) }
            if let series {
                let (rmssd, n) = try await Self.rmssd(series)
                if let rmssd { item["rmssd_ms"] = Self.r(rmssd, 1) }
                item["beats"] = n
            }
            out.append(item)
        }
        return out
    }

    /// Root mean square of successive differences of beat-to-beat intervals (ms). An interval that ends on a beat
    /// marked precededByGap isn't real (beats are missing before it), so it's skipped and the chain starts again.
    nonisolated static func rmssd(_ series: HKHeartbeatSeriesSample) async throws -> (Double?, Int) {
        var beats = 0, n = 0
        var prevT: Double?, prevRR: Double?
        var sum = 0.0
        for try await b in HKHeartbeatSeriesQueryDescriptor(series).results(for: health) {
            beats += 1
            defer { prevT = b.timeIntervalSinceStart }
            guard let p = prevT, !b.precededByGap else { prevRR = nil; continue }
            let rr = (b.timeIntervalSinceStart - p) * 1000
            if let last = prevRR { sum += (rr - last) * (rr - last); n += 1 }
            prevRR = rr
        }
        return (n > 0 ? (sum / Double(n)).squareRoot() : nil, beats)
    }

    /// Whole days (phone's time zone), every field worked out afresh, so a day sent again is complete: resting HR (the
    /// day's average), steps and exercise minutes (HealthKit's de-duplicated sums), VO2 max and weight (latest).
    private func days(_ dates: Set<Date>) async throws -> [[String: Any]] {
        let cal = Calendar.current
        guard let lo = dates.min(), let last = dates.max(), let hi = cal.date(byAdding: .day, value: 1, to: last) else { return [] }
        func stats(_ id: HKQuantityTypeIdentifier, _ options: HKStatisticsOptions) async throws -> HKStatisticsCollection {
            try await HKStatisticsCollectionQueryDescriptor(predicate: .quantitySample(type: HKQuantityType(id), predicate: HKQuery.predicateForSamples(withStart: lo, end: hi)),
                                                            options: options, anchorDate: lo, intervalComponents: DateComponents(day: 1)).result(for: Self.health)
        }
        let rhr = try await stats(.restingHeartRate, .discreteAverage), steps = try await stats(.stepCount, .cumulativeSum)
        let ex = try await stats(.appleExerciseTime, .cumulativeSum), vo2 = try await stats(.vo2Max, .mostRecent), kg = try await stats(.bodyMass, .mostRecent)
        let bpm = HKUnit.count().unitDivided(by: .minute())
        let vo2Unit = HKUnit.literUnit(with: .milli).unitDivided(by: HKUnit.gramUnit(with: .kilo).unitMultiplied(by: .minute()))
        var out: [[String: Any]] = []
        for d in dates.sorted() {
            var item: [String: Any] = ["date": Self.day(d)]
            if let v = rhr.statistics(for: d)?.averageQuantity() { item["resting_hr"] = Int(v.doubleValue(for: bpm).rounded()) }
            if let v = steps.statistics(for: d)?.sumQuantity() { item["steps"] = Int(v.doubleValue(for: .count()).rounded()) }
            if let v = ex.statistics(for: d)?.sumQuantity() { item["exercise_min"] = Int(v.doubleValue(for: .minute()).rounded()) }
            if let v = vo2.statistics(for: d)?.mostRecentQuantity() { item["vo2max"] = Self.r(v.doubleValue(for: vo2Unit), 1) }
            if let v = kg.statistics(for: d)?.mostRecentQuantity() { item["weight_kg"] = Self.r(v.doubleValue(for: .gramUnit(with: .kilo)), 1) }
            if item.count > 1 { out.append(item) }
        }
        return out
    }

    // MARK: Formats

    nonisolated private static func r(_ v: Double, _ places: Int) -> Double {
        guard v.isFinite else { return 0 }
        let m = pow(10, Double(places))
        return (v * m).rounded() / m
    }

    nonisolated static func iso(_ d: Date) -> String {
        let f = ISO8601DateFormatter()
        f.timeZone = .current
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: d)
    }

    nonisolated static func day(_ d: Date) -> String {
        let c = Calendar.current.dateComponents([.year, .month, .day], from: d)
        return String(format: "%04d-%02d-%02d", c.year!, c.month!, c.day!)
    }
}

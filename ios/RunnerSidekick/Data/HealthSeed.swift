#if DEBUG
import CoreLocation
import Foundation
import HealthKit

/// Debug only (launch with RSK_SEED_HEALTH=1): writes a realistic set of Apple Health data into the Simulator, so the
/// whole Apple Watch flow can be tried against a local server. Runs once per Health database (it looks for its own runs
/// first). Heartbeat series can't reasonably be written by an app, so HRV is SDNN only; Exercise minutes are Apple's own
/// and can't be written either.
enum HealthSeed {
    private static let store = HealthSync.health
    private static let bpm = HKUnit.count().unitDivided(by: .minute())

    static func run() async {
        let q: [HKQuantityTypeIdentifier] = [.heartRate, .distanceWalkingRunning, .runningPower, .runningSpeed, .stepCount, .activeEnergyBurned,
                                             .runningStrideLength, .runningVerticalOscillation, .runningGroundContactTime,
                                             .restingHeartRate, .heartRateVariabilitySDNN, .vo2Max, .bodyMass]
        let share = Set(q.map { HKQuantityType($0) as HKSampleType })
            .union([HKObjectType.workoutType(), HKSeriesType.workoutRoute(), HKCategoryType(.sleepAnalysis)])
        do {
            try await store.requestAuthorization(toShare: share, read: HealthSync.readTypes)
            let mine = try await HKSampleQueryDescriptor(predicates: [.workout(HKQuery.predicateForObjects(from: .default()))], sortDescriptors: [], limit: 1).result(for: store)
            guard mine.isEmpty else { HealthSync.log.info("Seed: already there"); return }
            let cal = Calendar.current
            let today = cal.startOfDay(for: Date())
            func at(_ daysAgo: Int, _ hour: Int, _ minute: Int = 0) -> Date {
                cal.date(byAdding: .minute, value: hour * 60 + minute, to: cal.date(byAdding: .day, value: -daysAgo, to: today)!)!
            }
            // Runs: easy, hilly (with a pause), treadmill, long
            try await workout(start: at(9, 7), minutes: 50, paceSPerKm: 330, hilly: false, indoor: false, pause: false)
            try await workout(start: at(7, 18, 30), minutes: 42, paceSPerKm: 345, hilly: true, indoor: false, pause: true)
            try await workout(start: at(4, 6, 45), minutes: 30, paceSPerKm: 320, hilly: false, indoor: true, pause: false)
            try await workout(start: at(1, 7, 15), minutes: 85, paceSPerKm: 350, hilly: true, indoor: false, pause: false)

            var samples: [HKSample] = []
            func qs(_ id: HKQuantityTypeIdentifier, _ v: Double, _ unit: HKUnit, _ s: Date, _ e: Date? = nil) {
                samples.append(HKQuantitySample(type: HKQuantityType(id), quantity: HKQuantity(unit: unit, doubleValue: v), start: s, end: e ?? s))
            }
            let vo2Unit = HKUnit.literUnit(with: .milli).unitDivided(by: HKUnit.gramUnit(with: .kilo).unitMultiplied(by: .minute()))
            for d in 0..<14 {
                // Sleep: in bed ~23:00 to ~06:45, in 90-minute cycles of core, deep, core, REM, with a short wake
                let bed = at(d + 1, 23, d % 3 * 10)
                samples.append(HKCategorySample(type: HKCategoryType(.sleepAnalysis), value: HKCategoryValueSleepAnalysis.inBed.rawValue, start: bed, end: bed.addingTimeInterval(7.75 * 3600)))
                var t = bed.addingTimeInterval(12 * 60)
                for cycle in 0..<5 {
                    let parts: [(HKCategoryValueSleepAnalysis, Double)] = [(.asleepCore, 30), (.asleepDeep, cycle < 2 ? 30 : 12), (.asleepCore, 20), (.asleepREM, cycle < 2 ? 12 : 25), (.awake, cycle == 2 ? 6 : 1)]
                    for (stage, mins) in parts {
                        let e = t.addingTimeInterval(mins * 60)
                        samples.append(HKCategorySample(type: HKCategoryType(.sleepAnalysis), value: stage.rawValue, start: t, end: e))
                        t = e
                    }
                }
                // HRV (SDNN) three times a night, resting HR, steps through the day, VO2 max weekly, weight now and then
                for (i, h) in [1.5, 3.5, 5.5].enumerated() { qs(.heartRateVariabilitySDNN, 42 + Double((d * 7 + i * 5) % 17), .secondUnit(with: .milli), bed.addingTimeInterval(h * 3600)) }
                qs(.restingHeartRate, 50 + Double(d % 5), bpm, at(d, 8), at(d, 8))
                for h in stride(from: 8, through: 20, by: 3) { qs(.stepCount, Double(900 + (d * 131 + h * 57) % 1400), .count(), at(d, h), at(d, h, 50)) }
                if d % 7 == 2 { qs(.vo2Max, 48.6 + Double(d) * 0.1, vo2Unit, at(d, 9)) }
                if d % 4 == 0 { qs(.bodyMass, 72.4 - Double(d) * 0.05, .gramUnit(with: .kilo), at(d, 7, 30)) }
            }
            try await store.save(samples)
            HealthSync.log.info("Seed: wrote 4 runs and \(samples.count) other samples")
        } catch {
            HealthSync.log.error("Seed failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// One outdoor or treadmill run built like the Workout app does: samples every 5 s tied to the workout, events, a
    /// route with altitude and speed (outdoor), elevation gain in the metadata.
    private static func workout(start: Date, minutes: Double, paceSPerKm: Double, hilly: Bool, indoor: Bool, pause: Bool) async throws {
        let config = HKWorkoutConfiguration()
        config.activityType = .running
        config.locationType = indoor ? .indoor : .outdoor
        let builder = HKWorkoutBuilder(healthStore: store, configuration: config, device: .local())
        try await builder.beginCollection(at: start)
        let pauseAt = minutes * 60 * 0.4, pauseLen = pause ? 120.0 : 0
        let end = start.addingTimeInterval(minutes * 60 + pauseLen)
        var samples: [HKSample] = []
        var locations: [CLLocation] = []
        var climb = 0.0, lastAlt = 20.0, meters = 0.0
        func q(_ id: HKQuantityTypeIdentifier, _ v: Double, _ unit: HKUnit, _ s: Date, _ e: Date) {
            samples.append(HKQuantitySample(type: HKQuantityType(id), quantity: HKQuantity(unit: unit, doubleValue: v), start: s, end: e))
        }
        var t = 0.0, moving = 0.0
        while t < minutes * 60 + pauseLen {
            let paused = pause && t >= pauseAt && t < pauseAt + pauseLen
            let s = start.addingTimeInterval(t), e = start.addingTimeInterval(t + 5)
            let alt = hilly ? 20 + 25 * sin(moving / 600) : 20
            let grade = (alt - lastAlt) / max(1, 5 * 1000 / paceSPerKm)
            let speed = paused ? 0 : 1000 / paceSPerKm * (1 - 3 * grade) * (1 + 0.05 * sin(moving / 47))
            if !paused {
                let d = speed * 5
                meters += d
                q(.distanceWalkingRunning, d, .meter(), s, e)
                q(.heartRate, 138 + 14 * (moving / (minutes * 60)) + 18 * max(0, grade * 10) + 3 * sin(moving / 31), bpm, s, s)
                q(.runningPower, 230 + 300 * grade + 8 * sin(moving / 23), .watt(), s, s)
                q(.runningSpeed, speed, HKUnit.meter().unitDivided(by: .second()), s, s)
                if Int(t) % 60 == 0 { q(.stepCount, 170, .count(), s, start.addingTimeInterval(t + 60)) }
                if !indoor {
                    for k in 0..<5 {
                        let sec = moving + Double(k)
                        let lat = 32.0700 + 0.004 * sin(sec / 900), lon = 34.7800 + (meters - d + speed * Double(k)) / 94_000
                        locations.append(CLLocation(coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon), altitude: alt, horizontalAccuracy: 4,
                                                    verticalAccuracy: 3, course: 90, speed: speed, timestamp: s.addingTimeInterval(Double(k))))
                    }
                }
                moving += 5
            }
            if alt > lastAlt { climb += alt - lastAlt }
            lastAlt = alt
            t += 5
        }
        q(.activeEnergyBurned, meters / 1000 * 70, .kilocalorie(), start, end)
        q(.runningStrideLength, 1.05, .meter(), start, end)
        q(.runningVerticalOscillation, 8.9, .meterUnit(with: .centi), start, end)
        q(.runningGroundContactTime, 251, .secondUnit(with: .milli), start, end)
        try await builder.addSamples(samples)
        var events: [HKWorkoutEvent] = []
        if pause {
            events.append(HKWorkoutEvent(type: .pause, dateInterval: DateInterval(start: start.addingTimeInterval(pauseAt), duration: 0), metadata: nil))
            events.append(HKWorkoutEvent(type: .resume, dateInterval: DateInterval(start: start.addingTimeInterval(pauseAt + pauseLen), duration: 0), metadata: nil))
        }
        if !events.isEmpty { try await builder.addWorkoutEvents(events) }
        var meta: [String: Any] = [HKMetadataKeyIndoorWorkout: indoor]
        if hilly { meta[HKMetadataKeyElevationAscended] = HKQuantity(unit: .meter(), doubleValue: climb.rounded()) }
        try await builder.addMetadata(meta)
        try await builder.endCollection(at: end)
        guard let workout = try await builder.finishWorkout() else { return }
        if !locations.isEmpty {
            let route = HKWorkoutRouteBuilder(healthStore: store, device: .local())
            try await route.insertRouteData(locations)
            _ = try await route.finishRoute(with: workout, metadata: nil)
        }
    }
}
#endif

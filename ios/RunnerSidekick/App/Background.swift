import BackgroundTasks
import Foundation
import UserNotifications

/// Best-effort background refresh (iOS decides when): keeps today's briefing and runs fresh and posts the
/// notifications. The server syncs Garmin itself, so this only fetches.
enum Background {
    static let id = "com.bennybarak.runnersidekick.refresh"

    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: id, using: nil) { task in
            schedule()  // the next one
            let work = Task { @MainActor in
                let store = Store.shared
                _ = await store.attempt { try await store.backgroundRefresh() }
                await Notifier.check(store)
            }
            task.expirationHandler = { work.cancel() }
            Task { _ = await work.result; task.setTaskCompleted(success: true) }
        }
    }

    /// Hourly with notifications on (so the morning window can be met); every 3 hours when it only keeps the phone's
    /// copy fresh; not at all when neither is wanted.
    @MainActor
    static func schedule() {
        let s = Store.shared.local
        guard s.hasToken, s.notificationsEnabled || s.backgroundRefresh else {
            BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: id)
            return
        }
        let r = BGAppRefreshTaskRequest(identifier: id)
        r.earliestBeginDate = Date().addingTimeInterval(s.notificationsEnabled ? 3600 : 3 * 3600)
        try? BGTaskScheduler.shared.submit(r)
    }
}

/// Best-effort local notifications, de-duplicated on the phone:
///  - morning briefing: once per date, inside the morning window; when the window ends a provisional briefing is posted
///    as provisional. A later change of suggestion updates the same notification quietly.
///  - weekly digest: on the first day of the week, once.
///  - run report: once per new run that started in the last 24 h. Runs already known at first use are never notified.
@MainActor
enum Notifier {
    static func requestPermission() async -> Bool {
        (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])) ?? false
    }

    static func check(_ store: Store, now: Date = Date()) async {
        guard store.local.notificationsEnabled else { return }
        let center = UNUserNotificationCenter.current()
        guard await center.notificationSettings().authorizationStatus == .authorized else { return }
        var state = NotifyState.load()
        let remote = store.settings?.value
        let zone = remote.flatMap { TimeZone(identifier: $0.timezone) } ?? .current
        var cal = Calendar(identifier: .gregorian); cal.timeZone = zone
        let parts = cal.dateComponents([.year, .month, .day, .hour, .minute, .weekday], from: now)
        let today = String(format: "%04d-%02d-%02d", parts.year!, parts.month!, parts.day!)
        let hhmm = String(format: "%02d:%02d", parts.hour!, parts.minute!)
        let start = remote?.windowStart ?? "06:00", end = remote?.windowEnd ?? "10:00"

        if let r = store.today?.value {
            let ready = !r.provisional || hhmm >= end
            // The same one decision Today shows: readiness and the next run. A changed decision updates the notification.
            let rd = r.readiness?.status == "ok" ? r.readiness : nil
            let title = rd.map { "Readiness \($0.score.map(String.init) ?? "—") · \($0.headline ?? $0.label ?? "")" } ?? r.headline
            let text = r.nextRun.map { n in
                [n.title + (n.optional ? " (optional)" : "") + " " + n.dayLabel.lowercased(),
                 n.distanceKm.map { Fmt.distance($0 * 1000, store.units) } ?? n.minutes.map { "about \($0) min" }, n.hr?.text, n.caution]
                    .compactMap { $0 }.joined(separator: " · ")
            } ?? r.recommendation.suggestion
            let key = "\(rd?.score ?? -1)|\(title)|\(text)"
            if r.localDate == today && hhmm >= start && ready && (state.morningDate != r.localDate || state.morningState != key) {
                let first = state.morningDate != r.localDate
                let c = UNMutableNotificationContent()
                c.title = title
                c.body = text + ((r.nextRun?.why ?? []).isEmpty ? "" : "\n" + r.nextRun!.why.joined(separator: " · "))
                if first { c.sound = .default }  // a revision updates quietly
                try? await center.add(UNNotificationRequest(identifier: "morning", content: c, trigger: nil))
                state.morningDate = r.localDate
                state.morningState = key
            }
        }

        // Weekly digest: on the first day of the week, from the start of the morning window, once per week
        let weekStart = Fmt.weekStart(today, store.firstWeekday)
        if weekStart == today && hhmm >= start && state.weeklyWeek != weekStart, let w = store.weekly?.value,
           w.weekStart == Fmt.addDays(weekStart, -7) {
            let focus = store.focus?.value.current?.title
            let c = UNMutableNotificationContent()
            c.title = "Last week: \(w.headline)"
            c.body = "This week's focus: \(focus ?? "pick one in Today")\nNext week from the review: \(w.nextWeekFocus.text)"
            c.userInfo = ["report": w.id]
            try? await center.add(UNNotificationRequest(identifier: "weekly", content: c, trigger: nil))
            state.weeklyWeek = weekStart
        }

        let acts = store.activities?.value ?? []
        if !state.runsSeeded {
            state.runsSeen = acts.map(\.sourceId)  // first use: history is not news
            state.runsSeeded = true
            state.save()
            return
        }
        for a in acts where !state.runsSeen.contains(a.sourceId) && now.timeIntervalSince(Fmt.instant(a.startUtc) ?? .distantPast) < 86400 {
            let c = UNMutableNotificationContent()
            // A run that set a record says so first
            c.title = a.records.isEmpty ? "Run report ready" : a.records.count == 1 ? "New record: \(a.records[0].title) \(a.records[0].value)"
                : "New records: " + a.records.map { $0.title.replacingOccurrences(of: "Fastest ", with: "") }.joined(separator: ", ")
            c.body = "\(Fmt.distance(a.distanceM, store.units)) · \(Fmt.pace(a.paceMovingSPerKm, store.units)) · \(Fmt.shortDate(a.localDate))"
            c.userInfo = ["run": a.sourceId]
            try? await center.add(UNNotificationRequest(identifier: "run-\(a.sourceId)", content: c, trigger: nil))
        }
        if !acts.isEmpty { state.runsSeen = Array((state.runsSeen + acts.map(\.sourceId)).suffix(200)) }
        state.save()
    }
}

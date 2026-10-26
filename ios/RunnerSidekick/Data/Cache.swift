import Foundation

/// A cached value plus when this device last fetched it, so the UI can be honest about staleness.
struct Cached<T> {
    var value: T
    var fetchedAt: Date
}

/// The offline copy: the server's raw answers as files, one per key ("today", "activity:<id>", ...). What the screens
/// show is decoded from these, so an answer the app can't read is never saved over a good one.
enum DiskCache {
    private static var dir: URL = {
        let d = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("cache", isDirectory: true)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        var v = URLResourceValues(); v.isExcludedFromBackup = true  // health data stays off iCloud backups
        var u = d; try? u.setResourceValues(v)
        return d
    }()

    private static func file(_ key: String) -> URL {
        let safe = key.map { $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" ? $0 : "_" }
        return dir.appendingPathComponent(String(safe) + ".json")
    }

    static func read(_ key: String) -> (Data, Date)? {
        let f = file(key)
        guard let d = try? Data(contentsOf: f) else { return nil }
        let at = (try? f.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
        return (d, at)
    }

    /// Unchanged content isn't rewritten, but its date is, so it reads as fresh and isn't pruned.
    static func write(_ key: String, _ data: Data) {
        let f = file(key)
        if let old = try? Data(contentsOf: f), old == data {
            try? FileManager.default.setAttributes([.modificationDate: Date()], ofItemAtPath: f.path)
            return
        }
        try? data.write(to: f, options: .atomic)
    }

    static func remove(_ key: String) { try? FileManager.default.removeItem(at: file(key)) }

    static func clear() {
        for f in (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? [] { try? FileManager.default.removeItem(at: f) }
    }

    /// Per-run and per-day copies not opened for a while (the main screens' copies are kept, always fresh).
    static func pruneOld(before: Date) {
        let prefixes = ["activity_", "runai_", "day_", "trends_", "report_"]
        for f in (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: [.contentModificationDateKey])) ?? [] {
            guard prefixes.contains(where: { f.lastPathComponent.hasPrefix($0) }) else { continue }
            let at = (try? f.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            if at < before { try? FileManager.default.removeItem(at: f) }
        }
    }
}

/// This phone's own preferences (the server keeps a copy of the shared ones, see Store.restorePreferences).
enum Units: String { case metric, imperial }
enum Appearance: String, CaseIterable {
    case system = "SYSTEM", light = "LIGHT", dark = "DARK"
    var label: String { switch self { case .system: "System"; case .light: "Light"; case .dark: "Dark" } }
}

struct LocalSettings {
    var hasToken: Bool
    var units: Units
    var appearance: Appearance
    var notificationsEnabled: Bool
    var backgroundRefresh: Bool
    /// "<backend url>#<user id>" of the signed-in account, once known. Scopes local check-ins.
    var account: String?
    var hasOwnAiKey: Bool
    /// "Skip for now" on Connect Garmin: it isn't opened by itself again on this sign-in
    var garminPromptSkipped: Bool
    /// Ask about the newest run when Runs opens; runAsked is the last run asked about
    var askAboutRuns: Bool
    var runAsked: String?

    static func load() -> LocalSettings {
        let d = UserDefaults.standard
        return LocalSettings(
            hasToken: Keychain.get("device_token") != nil,
            units: Units(rawValue: d.string(forKey: "units") ?? "") ?? .metric,
            appearance: Appearance(rawValue: d.string(forKey: "appearance") ?? "") ?? .system,
            notificationsEnabled: d.bool(forKey: "notifications_enabled"),
            backgroundRefresh: d.bool(forKey: "background_refresh"),
            account: d.string(forKey: "current_account"),
            hasOwnAiKey: Keychain.get("own_openai_key") != nil,
            garminPromptSkipped: d.bool(forKey: "garmin_prompt_skipped"),
            askAboutRuns: d.object(forKey: "ask_about_runs") as? Bool ?? true,
            runAsked: d.string(forKey: "run_asked"))
    }

    func save() {
        let d = UserDefaults.standard
        d.set(units.rawValue, forKey: "units")
        d.set(appearance.rawValue, forKey: "appearance")
        d.set(notificationsEnabled, forKey: "notifications_enabled")
        d.set(backgroundRefresh, forKey: "background_refresh")
        d.set(account, forKey: "current_account")
        d.set(garminPromptSkipped, forKey: "garmin_prompt_skipped")
        d.set(askAboutRuns, forKey: "ask_about_runs")
        d.set(runAsked, forKey: "run_asked")
    }
}

/// Notification de-duplication state, kept on the phone.
struct NotifyState: Codable {
    var morningDate: String?
    var morningState: String?
    var runsSeen: [String] = []
    var runsSeeded = false
    var weeklyWeek: String?

    static func load() -> NotifyState {
        (UserDefaults.standard.data(forKey: "notify_state")).flatMap { try? JSONDecoder().decode(NotifyState.self, from: $0) } ?? NotifyState()
    }
    func save() { UserDefaults.standard.set(try? JSONEncoder().encode(self), forKey: "notify_state") }
}

/// A check-in written on this phone first and uploaded later. Conflict policy (backend): last clientUpdatedAt wins.
struct LocalCheckin: Codable, Identifiable {
    var id: String
    var localDate: String
    var energy: Int?
    var soreness: Int?
    var recovery: Int?
    var pain: Bool
    var illness: Bool
    var notes: String?
    var tags: [String]
    var clientUpdatedAt: String
    var pendingSync: Bool
    /// The account that owns it; never uploaded under another one
    var account: String
}

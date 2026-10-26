import Foundation
import SwiftUI
import UIKit

/// What a refresh or sync is doing and how far it has got (0–1). hint: a second line (the Garmin download runs on the
/// server and takes a while).
struct Progress: Equatable {
    var fraction: Double
    var label: String
    var hint: String? = nil
}

/// Everything the screens show, cached on this phone and refreshed from the backend. The iOS counterpart of the
/// Android app's Repository: same endpoints, same steps, same rules.
@MainActor
@Observable
final class Store {
    static let shared = Store()

    static let serverSyncHint = "Runs on the server, so you can leave the app. A first download takes a few minutes; " +
        "older history keeps filling in over the next hours."

    // MARK: State the screens read

    var local = LocalSettings.load()
    var status: Cached<Status>?
    var today: Cached<MorningReport>?
    var activities: Cached<[ActivitySummary]>?
    var insights: Cached<InsightsReport>?
    var weekly: Cached<WeeklyReport>?
    var fitness: Cached<Fitness>?
    var me: Cached<Me>?
    var focus: Cached<FocusState>?
    var coach: Cached<CoachView>?
    var routes: Cached<RoutesReport>?
    var numbers: Cached<TrainingNumbers>?
    var cardio: Cached<Cardio>?
    var trophies: Cached<Trophies>?
    var compare: Cached<CompareReport>?
    var settings: Cached<SettingsDto>?
    /// The settings exactly as the server sent them (snake_case keys), for saving every field back
    private var settingsRaw: [String: JSONValue] = [:]
    var trends: [Int: Cached<Trends>] = [:]
    var days: [String: Cached<MorningReport>] = [:]
    var details: [String: Cached<ActivityDetail>] = [:]
    var runAis: [String: Cached<RunAi>] = [:]
    var journal: [ReportListItem] = []
    var checkins: [LocalCheckin] = []
    var progress: Progress?
    /// Shown once on the sign-in screen after the server ended this session
    var signInNote: String?
    /// A one-off message at the bottom of the screen ("Saved", "2 new runs", an error)
    var toast: String?

    private var timezoneChecked = false
    private var refreshing: Task<Void, Error>?

    init() {
        loadFromDisk()
    }

    // MARK: Derived

    var aiEnabled: Bool { settings?.value.aiEnabled == true }
    var units: Units { local.units }

    /// The day weeks start on (Settings, else Garmin's profile, else Monday), as the backend reports it (1 = Sunday … 7 = Saturday).
    var firstWeekday: Int { Fmt.weekday(status?.value.weekStartDay) }

    private var account: String { local.account ?? "" }
    var myCheckins: [LocalCheckin] { checkins.filter { $0.account == account }.sorted { $0.localDate > $1.localDate } }

    /// "Not feeling well" today that the server's briefing doesn't include yet (offline, or not synced): until it does,
    /// the app applies it itself everywhere (rest), and advice written without it (the AI coach) is held back.
    var unwellPending: Bool {
        let d = Fmt.todayISO()
        guard myCheckins.first(where: { $0.localDate == d })?.illness == true else { return false }
        return today?.value.localDate != d || today?.value.decision?.unwellApplied != true
    }

    // MARK: Disk

    private func cached<T: Decodable>(_ key: String, _ t: T.Type) -> Cached<T>? {
        guard let (d, at) = DiskCache.read(key), let v = try? JSON.decode(t, d) else { return nil }
        return Cached(value: v, fetchedAt: at)
    }

    /// Saved data a screen asks for while it draws (a run, a range of charts, a day), read from disk once and then kept:
    /// reading and decoding it on every redraw made scrolling stutter. Not observed; a fresh fetch replaces it.
    @ObservationIgnored private var memo: [String: Any] = [:]
    private func remembered<T: Decodable>(_ key: String, _ t: T.Type) -> Cached<T>? {
        if let v = memo[key] as? Cached<T> { return v }
        let v = cached(key, t)
        if let v { memo[key] = v }
        return v
    }

    private func loadFromDisk() {
        status = cached("status", Status.self)
        today = cached("today", MorningReport.self)
        activities = cached("activities", [ActivitySummary].self)
        insights = cached("insights", InsightsReport.self)
        weekly = cached("weekly", WeeklyReport.self)
        fitness = cached("fitness", Fitness.self)
        me = cached("me", Me.self)
        focus = cached("focus", FocusState.self)
        coach = cached("coach", CoachView.self)
        routes = cached("routes", RoutesReport.self)
        numbers = cached("numbers", TrainingNumbers.self)
        cardio = cached("cardio", Cardio.self)
        trophies = cached("trophies", Trophies.self)
        compare = cached("compare", CompareReport.self)
        if let (d, at) = DiskCache.read("settings") { applySettings(d, at: at) }
        journal = cached("journal", [ReportListItem].self)?.value ?? []
        if let (d, _) = DiskCache.read("checkins"), let c = try? JSONDecoder().decode([LocalCheckin].self, from: d) { checkins = c }
    }

    private func saveCheckins() { DiskCache.write("checkins", (try? JSONEncoder().encode(checkins)) ?? Data()) }

    /// Decodes a response the way its screen will (off the main thread) before it's cached: one the app can't read
    /// throws here instead of replacing good saved data with something that shows as an empty screen.
    private func put<T: Decodable>(_ key: String, _ data: Data, _ t: T.Type) async throws -> Cached<T> {
        let v = try await Task.detached(priority: .userInitiated) { try JSON.decode(t, data) }.value
        DiskCache.write(key, data)
        return Cached(value: v, fetchedAt: Date())
    }

    func detail(_ id: String) -> Cached<ActivityDetail>? {
        if let d = details[id] { return d }
        return remembered("activity:\(id)", ActivityDetail.self)
    }
    func runAi(_ id: String) -> Cached<RunAi>? { runAis[id] ?? remembered("runai:\(id)", RunAi.self) }
    func trend(_ days: Int) -> Cached<Trends>? { trends[days] ?? remembered("trends:\(days)", Trends.self) }
    func day(_ date: String) -> Cached<MorningReport>? { days[date] ?? remembered("day:\(date)", MorningReport.self) }
    func reportBody(_ id: Int) -> Data? { DiskCache.read("report:\(id)")?.0 }

    // MARK: Errors

    /// Runs an action with the app's error handling: a failure becomes a message (never a crash), and a rejected token
    /// ends the session. Returns the message, or nil when it worked.
    @discardableResult
    func attempt(_ op: () async throws -> Void) async -> String? {
        do {
            try await op()
            return nil
        } catch is CancellationError {
            return nil  // leaving the screen cancels its work; that isn't an error
        } catch let e as APIError {
            if case .unauthorized = e { sessionExpired() }
            return e.userMessage
        } catch is DecodingError {
            return "Unexpected response from the backend. Showing saved data."
        } catch {
            return "Something went wrong. Showing saved data."
        }
    }

    /// The same, showing the message at the bottom of the screen.
    func act(_ op: @escaping () async throws -> Void) {
        Task { if let m = await attempt(op) { toast = m } }
    }

    // MARK: Account and session

    /// The runner's own OpenAI key, sent only with requests that may call the AI (coach, screen summaries).
    private var aiHeaders: [String: String] { Keychain.get("own_openai_key").map { ["X-OpenAI-Key": $0] } ?? [:] }

    func setToken(_ token: String) {
        Keychain.set("device_token", token)
        local.hasToken = true
    }

    /// Checks a device token with the server before it's saved; a message when it doesn't work, nil when it does.
    func checkToken(_ token: String) async throws -> String? {
        switch try await API.shared.getWithToken("/v1/me", token: token).0 {
        case 200: return nil
        case 401, 403: return "The server didn't accept this device token."
        case 429: return "Too many tries from this network. Wait a minute and try again."
        default: return "The server answered with an error. Check the address."
        }
    }

    /// Exchanges a Google ID token for an app token and stores it. Returns an error message, or nil on success.
    func signInWithGoogle(idToken: String) async throws -> String? {
        let (code, body) = try await API.shared.postPublic("/v1/auth/google", JSON.body(["id_token": idToken, "device_name": UIDevice.current.name]))
        switch code {
        case 200:
            let r = try JSON.decode(AuthResult.self, body)
            setToken(r.token)
            return nil
        case 403:
            let d = (try? JSONSerialization.jsonObject(with: body) as? [String: Any])?["detail"] as? String
            if let d { return d.contains("invited") ? "\(d). Ask the server owner to invite your Google email." : d }
            return "This Google account can't sign in here. Ask the server owner."
        case 503: return "Google sign-in isn't set up on this server yet."
        case 429: return "Too many tries from this network. Wait a minute and try again."
        default: return "Sign-in failed (HTTP \(code))."
        }
    }

    /// The server rejected the token: back to sign-in with a note. Unsent check-ins stay on this phone.
    func sessionExpired() {
        guard local.hasToken else { return }
        signInNote = "Your session has ended. Please sign in again."
        clearLocal(includeCheckins: false)
        clearToken()
    }

    func signOut() async {
        // The token stops working on the server too; offline or slow, signing out here doesn't wait long for it
        _ = try? await withTimeout(5) { _ = try await API.shared.post("/v1/auth/logout") }
        clearLocal(includeCheckins: false)
        clearToken()
    }

    func deleteAccount() async throws {
        _ = try await API.shared.delete("/v1/account")
        clearLocal(includeCheckins: true)
        clearToken()
    }

    /// Signing out also forgets the runner's own OpenAI key, so a later account never inherits it.
    private func clearToken() {
        Keychain.set("device_token", nil)
        Keychain.set("own_openai_key", nil)
        local.hasToken = false
        local.hasOwnAiKey = false
        local.account = nil
        local.garminPromptSkipped = false
        local.save()
    }

    func clearLocal(includeCheckins: Bool) {
        DiskCache.clear()
        memo = [:]
        Task { await API.shared.forget() }
        status = nil; today = nil; activities = nil; insights = nil; weekly = nil; fitness = nil; me = nil; focus = nil
        coach = nil; routes = nil; numbers = nil; cardio = nil; trophies = nil; compare = nil; settings = nil; settingsRaw = [:]
        trends = [:]; days = [:]; details = [:]; runAis = [:]; journal = []
        if includeCheckins { checkins = [] }
        saveCheckins()
    }

    /// Identifies the signed-in account and scopes local data to it. A different account than last time clears the
    /// cached reports (never another account's check-ins, which stay hidden and are never uploaded under this account).
    private func establishAccount() async throws {
        let body = try await API.shared.get("/v1/me")
        let m = try await put("me", body, Me.self)
        let key = "\(Backend.url)#\(m.value.id)"
        if local.account != key {
            let keep = DiskCache.read("status")
            let wasNone = local.account == nil
            DiskCache.clear()
            if let (d, _) = keep { DiskCache.write("status", d) }
            journal = []; trends = [:]; days = [:]; details = [:]; runAis = [:]
            if wasNone {
                for i in checkins.indices where checkins[i].account.isEmpty { checkins[i].account = key }
                saveCheckins()
            } else {
                Keychain.set("own_openai_key", nil)  // a key belongs to one account
                local.hasOwnAiKey = false
            }
            local.account = key
            local.save()
            timezoneChecked = false
            DiskCache.write("me", body)
        }
        me = m
    }

    /// A new account starts in the phone's time zone (the server's default is just a guess); once set, it's left alone.
    private func ensureTimezone() async {
        guard !timezoneChecked else { return }
        if let d = try? await API.shared.get("/v1/settings"),
           let s = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
            if s["timezone_set"] as? Bool == false {
                _ = try? await API.shared.put("/v1/settings", JSON.body(["timezone": TimeZone.current.identifier]))
            }
            timezoneChecked = true
        }
    }

    // MARK: Settings

    private func applySettings(_ data: Data, at: Date = Date()) {
        guard let s = try? JSON.decode(SettingsDto.self, data),
              let raw = try? JSONDecoder().decode([String: JSONValue].self, from: data) else { return }
        settings = Cached(value: s, fetchedAt: at)
        settingsRaw = raw
    }

    @discardableResult
    func remoteSettings() async throws -> SettingsDto {
        let body = try await API.shared.get("/v1/settings")
        _ = try JSON.decode(SettingsDto.self, body)
        DiskCache.write("settings", body)  // kept, so the app knows (offline too) whether AI is on
        applySettings(body)
        restorePreferences()
        return settings!.value
    }

    /// Saves changed fields (snake_case keys; nil clears) along with every other field as the server has it.
    @discardableResult
    func saveSettings(_ changes: [String: Any?]) async throws -> SettingsDto {
        if settingsRaw.isEmpty { try await remoteSettings() }
        var all: [String: Any?] = settingsRaw.mapValues { $0 }
        for (k, v) in changes { all[k] = v }
        let body = try await API.shared.put("/v1/settings", JSON.body(all))
        _ = try JSON.decode(SettingsDto.self, body)
        DiskCache.write("settings", body)
        applySettings(body)
        return settings!.value
    }

    /// The app's preferences live on the server: what it has wins on this phone (a reinstall gets them back); what it
    /// doesn't have yet is sent from this phone once.
    private func restorePreferences() {
        guard let s = settings?.value else { return }
        var missing: [String: Any?] = [:]
        if let u = s.units { local.units = u == "imperial" ? .imperial : .metric } else { missing["units"] = local.units.rawValue }
        if let a = s.appearance, let ap = Appearance(rawValue: a) { local.appearance = ap } else { missing["appearance"] = local.appearance.rawValue }
        if let n = s.notifications { if !n { local.notificationsEnabled = false } } else { missing["notifications"] = local.notificationsEnabled }
        if let b = s.backgroundRefresh { local.backgroundRefresh = b } else { missing["background_refresh"] = local.backgroundRefresh }
        local.save()
        if !missing.isEmpty { Task { _ = try? await API.shared.put("/v1/settings", JSON.body(missing)) } }
    }

    /// One app preference changed on this phone: saved here at once and on the server (best effort).
    func savePreference(_ key: String, _ value: Any) {
        local.save()
        Task { _ = try? await API.shared.put("/v1/settings", JSON.body([key: value])) }
    }

    func setOwnAiKey(_ key: String?) {
        Keychain.set("own_openai_key", key?.trimmingCharacters(in: .whitespaces))
        local.hasOwnAiKey = Keychain.get("own_openai_key") != nil
    }

    // MARK: Refresh

    @discardableResult
    func refreshStatus() async throws -> Status {
        let body = try await API.shared.get("/v1/status")
        let s = try await put("status", body, Status.self)
        // A change of backend mode (demo data ↔ live) wipes the other mode's cache
        if let old = status?.value.mode, old != s.value.mode { clearLocal(includeCheckins: false); DiskCache.write("status", body) }
        status = s
        return s.value
    }

    /// One full refresh at a time: a second call while one runs waits for it instead of fetching everything again.
    func refreshAll(from: Double = 0, to: Double = 1) async throws {
        if let r = refreshing { try await r.value; return }
        let t = Task { try await refreshAllNow(from: from, to: to) }
        refreshing = t
        defer { refreshing = nil }
        try await t.value
    }

    private func refreshAllNow(from: Double, to: Double) async throws {
        defer { if to >= 1 { progress = nil } }
        let total = 7.0
        progress = Progress(fraction: from, label: "Checking the connection")
        // The connection first, then every screen at once: the server answers them side by side
        try await refreshStatus()
        try await establishAccount()
        await ensureTimezone()
        _ = try? await remoteSettings()
        try await pushPendingCheckins()
        try await pullCheckins()
        DiskCache.pruneOld(before: Date().addingTimeInterval(-30 * 86400))  // runs and days not opened for 30 days
        var done = 1.0
        progress = Progress(fraction: from + (to - from) * done / total, label: "Loading your data")
        try await withThrowingTaskGroup(of: Void.self) { g in
            g.addTask { try await self.refreshToday() }
            g.addTask { try await self.refreshActivities() }
            g.addTask { try await self.refreshInsights() }
            g.addTask { try await self.refreshWeekly(); try await self.refreshFocus() }
            g.addTask { try await self.refreshFitness() }
            g.addTask { try await self.refreshJournal() }
            for try await _ in g {
                done += 1
                progress = Progress(fraction: from + (to - from) * done / total, label: "Loading your data")
            }
        }
    }

    func refreshToday() async throws {
        let body = try await API.shared.get("/v1/today")
        let r = try await put("today", body, MorningReport.self)
        today = r
        DiskCache.write("report:\(r.value.id)", body)  // the journal opens it offline
    }

    func refreshActivities() async throws { activities = try await put("activities", try await API.shared.get("/v1/activities"), [ActivitySummary].self) }
    func refreshInsights() async throws { insights = try await put("insights", try await API.shared.get("/v1/insights"), InsightsReport.self) }
    func refreshFitness() async throws { fitness = try await put("fitness", try await API.shared.get("/v1/fitness"), Fitness.self) }
    func refreshFocus() async throws { focus = try await put("focus", try await API.shared.get("/v1/focus"), FocusState.self) }
    func refreshRoutes() async throws { routes = try await put("routes", try await API.shared.get("/v1/routes"), RoutesReport.self) }
    func refreshNumbers() async throws { numbers = try await put("numbers", try await API.shared.get("/v1/numbers"), TrainingNumbers.self) }
    func refreshCardio() async throws { cardio = try await put("cardio", try await API.shared.get("/v1/cardio"), Cardio.self) }
    func refreshTrophies() async throws { trophies = try await put("trophies", try await API.shared.get("/v1/trophies"), Trophies.self) }

    func refreshWeekly() async throws {
        do { weekly = try await put("weekly", try await API.shared.get("/v1/weekly/latest"), WeeklyReport.self) }
        catch APIError.http(404, _) { }  // no weekly review yet
    }

    /// Returns true while the screen's AI summary is still being written.
    func refreshCompare() async throws -> Bool {
        let c = try await put("compare", try await API.shared.get("/v1/compare", headers: aiHeaders), CompareReport.self)
        compare = c
        return c.value.aiSummary?.status == "pending"
    }

    func refreshTrends(_ d: Int) async throws -> Bool {
        let t = try await put("trends:\(d)", try await API.shared.get("/v1/trends", query: ["days": "\(d)"], headers: aiHeaders), Trends.self)
        trends[d] = t
        return t.value.aiSummary?.status == "pending"
    }

    func refreshDay(_ date: String) async throws { days[date] = try await put("day:\(date)", try await API.shared.get("/v1/today", query: ["date": date]), MorningReport.self) }

    /// A "pending" answer carries the previous analysis, which the UI shows marked as updating.
    @discardableResult
    func refreshCoach() async throws -> String {
        let c = try await put("coach", try await API.shared.get("/v1/coach", headers: aiHeaders), CoachView.self)
        coach = c
        return c.value.status
    }

    private var coachPoll: Task<Void, Never>?
    var coachLoading = false
    /// Fetches the coach analysis, polling (bounded) while the backend writes a new one for changed inputs. One poll at a time.
    func pollCoach() {
        guard coachPoll == nil else { return }
        coachLoading = true
        coachPoll = Task {
            defer { coachPoll = nil; coachLoading = false }
            for attempt in 0..<20 {
                if ((try? await refreshCoach()) ?? "failed") != "pending" { return }
                try? await Task.sleep(for: .seconds(min(15, 3 * pow(1.5, Double(attempt)))))
            }
        }
    }

    func refreshActivity(_ id: String) async throws { details[id] = try await put("activity:\(id)", try await API.shared.get("/v1/activities/\(id)"), ActivityDetail.self) }

    /// The run as one Markdown file (built by the backend).
    func exportRun(_ id: String) async throws -> String {
        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? ""
        return String(decoding: try await API.shared.get("/v1/activities/\(id)/export.md", query: ["v": v]), as: UTF8.self)
    }

    /// The run's AI input; request asks for it to be written (only then does it cost an AI call). Returns the status.
    @discardableResult
    func refreshRunAi(_ id: String, request: Bool = false) async throws -> String {
        let body = request ? try await API.shared.post("/v1/activities/\(id)/ai", headers: aiHeaders)
            : try await API.shared.get("/v1/activities/\(id)/ai", headers: aiHeaders)
        let r = try await put("runai:\(id)", body, RunAi.self)
        runAis[id] = r
        return r.value.status
    }

    /// Asks for the AI input, then follows it (bounded) while it is written in the background.
    func askAi(_ id: String) async throws {
        guard try await refreshRunAi(id, request: true) == "pending" else { return }
        Task {
            for attempt in 0..<20 {
                try? await Task.sleep(for: .seconds(min(15, 3 * pow(1.5, Double(attempt)))))
                if ((try? await refreshRunAi(id)) ?? "failed") != "pending" { break }
            }
        }
    }

    // MARK: Journal

    func refreshJournal() async throws {
        let list = try await Task.detached { try JSON.decode([ReportListItem].self, try await API.shared.get("/v1/reports", query: ["limit": "200"])) }.value
        // The latest revision per report; older revisions stay cached so a report opened offline shows what was known then
        var latest: [String: ReportListItem] = [:]
        for r in list where (latest["\(r.type)|\(r.subjectKey)"]?.revision ?? -1) < r.revision { latest["\(r.type)|\(r.subjectKey)"] = r }
        journal = latest.values.sorted { ($0.localDate, $0.id) > ($1.localDate, $1.id) }
        DiskCache.write("journal", (try? JSONEncoder().encode(journal)) ?? Data())
    }

    /// Fetches a report's body once (then it reads offline).
    func loadReport(_ id: Int) async throws {
        if reportBody(id) != nil { return }
        DiskCache.write("report:\(id)", try await API.shared.get("/v1/reports/\(id)"))
    }

    /// Earlier revisions of a report, newest first.
    func revisions(type: String, key: String) async throws -> [RevisionInfo] {
        try JSON.decode([RevisionInfo].self, try await API.shared.get("/v1/reports/\(type)/\(key)/revisions"))
    }

    // MARK: Sync

    /// Starts a backend sync and waits (bounded) for it to finish, then refreshes the cache. For an explicit tap only.
    func syncNow() async throws {
        defer { progress = nil }
        progress = Progress(fraction: 0, label: "Starting the Garmin sync")
        // The server holds a sync back only when Garmin asked us to wait: say until when
        let started = (try? JSONSerialization.jsonObject(with: try await API.shared.post("/v1/sync")) as? [String: Any]) ?? [:]
        if let at = started["next_allowed_at"] as? String {
            try await refreshStatus()
            throw APIError.sync("Garmin asked us to wait before syncing again. Next sync from \(Fmt.clock(iso: at)).")
        }
        // The server's own progress fills the first 85%; loading the results fills the rest
        var s = try await refreshStatus()
        for attempt in 0..<30 {
            try await Task.sleep(for: .seconds(min(2, 1 * pow(1.5, Double(attempt)))))
            s = try await refreshStatus()
            if !s.syncRunning { break }
            if let p = s.syncProgress { progress = Progress(fraction: 0.85 * Double(p.percent) / 100, label: p.phase ?? "Syncing with Garmin", hint: Self.serverSyncHint) }
        }
        try await refreshAll(from: 0.85, to: 1)
        // Say how the sync really ended, never "synced" after a failure or while it's still going
        if s.syncRunning { throw APIError.sync("Still syncing with Garmin on the server; new data will appear shortly.") }
        switch s.lastJob?.outcome {
        case "ok", "partial", nil: break
        case "auth_failed": throw APIError.sync("Garmin needs you to sign in again before it can sync.")
        case "rate_limited", "deferred": throw APIError.sync("Garmin asked us to wait; the sync will retry automatically.")
        default: throw APIError.sync("The Garmin sync didn't finish" + (s.lastJob?.detail.map { ": \($0)" } ?? "."))
        }
    }

    /// Syncs with Garmin now and says how many new runs arrived.
    func syncRunsNow() async throws -> Int {
        let before = Set((activities?.value ?? []).map(\.sourceId))
        try await syncNow()
        return (activities?.value ?? []).filter { !before.contains($0.sourceId) }.count
    }

    /// The background refresh: what the notifications read, nothing else.
    func backgroundRefresh() async throws {
        try await pushPendingCheckins()
        try await refreshToday()
        try await refreshActivities()
        try await refreshWeekly()
        try await refreshFocus()
    }

    // MARK: Actions

    func setIntent(_ id: String, _ i: RunIntent) async throws {
        func text(_ s: String?) -> String? { s?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty }
        _ = try await API.shared.put("/v1/activities/\(id)/intent", JSON.body([
            "kind": i.kind, "note": text(i.note), "target": text(i.target), "effort": i.effort, "feel": i.feel, "limiter": i.limiter,
            "limiter2": i.limiter2, "health": i.health, "client_updated_at": Fmt.nowISO()]))
        try await refreshActivity(id)
        try? await refreshActivities()  // the run now counts as answered
        try await refreshFocus()
        _ = try? await refreshRunAi(id)  // the AI input was written for the old type: "Update AI input" shows straight away
    }

    func markRunAsked(_ id: String) { local.runAsked = id; local.save() }

    func chooseFocus(_ kind: String) async throws {
        focus = try await put("focus", try await API.shared.put("/v1/focus", JSON.body(["kind": kind])), FocusState.self)
    }

    func setInsightState(_ id: String, _ state: String?) async throws {
        insights = try await put("insights", try await API.shared.put("/v1/insights/\(id)/state", JSON.body(["state": state])), InsightsReport.self)
    }

    /// Leaves a run out of Runner Sidekick's VO2 max, or takes it back in.
    func holdOutVo2(_ id: String, _ held: Bool) async throws {
        _ = try await API.shared.put("/v1/activities/\(id)/vo2-hold", JSON.body(["held_out": held]))
        try await refreshActivity(id)
        try? await refreshCardio()
    }

    /// "Different route": this run leaves the route it was grouped with, for good.
    func differentRoute(_ id: String) async throws {
        _ = try await API.shared.post("/v1/activities/\(id)/different-route")
        try await refreshRoutes()
        try await refreshActivity(id)
    }

    /// Deletes a run on the server (kept aside there, never imported again), then refreshes what lists it.
    func deleteRun(_ id: String) async throws {
        _ = try await API.shared.delete("/v1/activities/\(id)")
        try await refreshActivities()
        try? await refreshAll()
    }

    // MARK: Check-ins

    func saveCheckin(date: String, illness: Bool, tags: [String]) {
        let existing = myCheckins.first { $0.localDate == date }
        let c = LocalCheckin(id: existing?.id ?? UUID().uuidString, localDate: date, energy: nil, soreness: nil, recovery: nil, pain: false,
                             illness: illness, notes: nil, tags: tags, clientUpdatedAt: Fmt.nowISO(), pendingSync: true, account: account)
        checkins.removeAll { $0.id == c.id }
        checkins.append(c)
        saveCheckins()
    }

    /// "Not feeling well" for one day: tapping again clears it. Saved on the phone first (Today applies it straight away);
    /// uploaded and refreshed when the server can be reached.
    func setUnwell(date: String, on: Bool) async {
        saveCheckin(date: date, illness: on, tags: on ? ["unwell"] : [])
        try? await pushPendingCheckins()
        try? await refreshToday()
    }

    func pushPendingCheckins() async throws {
        guard local.account != nil else { return }  // unknown account: upload nothing
        for c in checkins where c.pendingSync && c.account == account {
            let dto: [String: Any?] = ["local_date": c.localDate, "energy": c.energy, "soreness": c.soreness, "recovery": c.recovery,
                                       "pain": c.pain, "illness": c.illness, "notes": c.notes, "tags": c.tags, "client_updated_at": c.clientUpdatedAt]
            let stored = try JSON.decode(CheckinDto.self, try await API.shared.put("/v1/checkins/\(c.id)", JSON.body(dto)))
            // A newer version on the server wins; keep that one instead of ours
            if stored.clientUpdatedAt != c.clientUpdatedAt { merge(stored) }
            else if let i = checkins.firstIndex(where: { $0.id == c.id && $0.clientUpdatedAt == c.clientUpdatedAt }) { checkins[i].pendingSync = false }
        }
        saveCheckins()
    }

    /// Pulls the account's check-ins so a reinstall or second phone shows the same history. Last write wins.
    func pullCheckins() async throws {
        guard local.account != nil else { return }
        for s in try JSON.decode([CheckinDto].self, try await API.shared.get("/v1/checkins")) { merge(s) }
        saveCheckins()
    }

    private func merge(_ s: CheckinDto) {
        guard let id = s.id else { return }
        let local = checkins.first { $0.id == id }
        if let l = local, l.clientUpdatedAt >= s.clientUpdatedAt { return }
        checkins.removeAll { $0.id == id }
        if s.deleted { return }
        checkins.append(LocalCheckin(id: id, localDate: s.localDate, energy: s.energy, soreness: s.soreness, recovery: s.recovery, pain: s.pain,
                                     illness: s.illness, notes: s.notes, tags: s.tags, clientUpdatedAt: s.clientUpdatedAt, pendingSync: false,
                                     account: account))
    }

    // MARK: Garmin

    func garminAuthorizeUrl() async throws -> URL {
        let d = try await API.shared.post("/v1/garmin/oauth/start")
        guard let s = (try JSONSerialization.jsonObject(with: d) as? [String: Any])?["authorize_url"] as? String, let u = URL(string: s) else {
            throw APIError.sync("Garmin sign-in isn't available")
        }
        return u
    }

    /// Hands the server the one-time ticket from Garmin's sign-in page; it connects Garmin and starts the first sync.
    func linkGarmin(ticket: String) async throws {
        _ = try await API.shared.post("/v1/garmin/ticket", JSON.body(["ticket": ticket]))
        _ = try? await refreshStatus()
    }

    /// Finishes connecting Garmin (official sign-in): the server's callback page hands Garmin's answer to the app.
    func completeGarmin(state: String, code: String) async throws {
        _ = try await API.shared.post("/v1/garmin/oauth/complete", JSON.body(["state": state, "code": code]))
        try await refreshStatus()
    }

    func disconnectGarmin() async throws {
        _ = try await API.shared.delete("/v1/garmin/connection")
        try await refreshStatus()
        local.garminPromptSkipped = true  // disconnecting on purpose: Connect Garmin doesn't then open by itself
        local.save()
    }

    // MARK: Data

    func exportJson() async throws -> Data { try await API.shared.get("/v1/export") }

    func deleteRemote(_ scope: String) async throws {
        _ = try await API.shared.delete("/v1/data", query: ["scope": scope])
        clearLocal(includeCheckins: scope == "all")
    }
}

extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

/// Runs op, giving up after seconds.
func withTimeout<T: Sendable>(_ seconds: Double, _ op: @escaping @Sendable () async throws -> T) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { g in
        g.addTask { try await op() }
        g.addTask { try await Task.sleep(for: .seconds(seconds)); throw CancellationError() }
        let r = try await g.next()!
        g.cancelAll()
        return r
    }
}

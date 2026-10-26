import SwiftUI

private let dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
private let goals = [("consistency", "Consistency"), ("distance", "Go longer"), ("performance", "Get faster"), ("health", "Health")]
private let races = [("5k", "5K"), ("10k", "10K"), ("half", "Half"), ("marathon", "Marathon")]
private func hms(_ s: Int) -> String { s >= 3600 ? String(format: "%d:%02d:%02d", s / 3600, s % 3600 / 60, s % 60) : String(format: "%d:%02d", s / 60, s % 60) }

private enum MeSheet: String, Identifiable { case training, race, about, window, key, aiInfo; var id: String { rawValue } }
private enum Confirm: String, Identifiable { case local, raw, all, signout, account, garmin; var id: String { rawValue } }

struct MeView: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @Environment(\.openURL) private var openURL
    @State private var sheet: MeSheet?
    @State private var confirm: Confirm?
    @State private var garminConnect = false
    @State private var exportFile: URL?
    @State private var busy = false

    var body: some View {
        let s = store.status?.value
        let r = store.settings?.value
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Me").font(Typo.headlineLarge).frame(maxWidth: .infinity, alignment: .leading).accessibilityAddTraits(.isHeader)
                    if s?.synthetic == true { DemoBadge() }
                }
                .padding(.horizontal, 12).padding(.top, 40).padding(.bottom, 6)
                // Only a Garmin problem is shown up here; everything else lives in its own section
                if let st = s?.connection.state, ["reauth_required", "not_configured", "error"].contains(st) {
                    CardGroup(tint: .orange) {
                        GroupRow(st == "error" ? "Garmin sync failing" : "Garmin sign-in needed",
                                 supporting: st == "error" ? s?.connection.detail ?? "The last sync failed; it retries on its own."
                                 : st == "not_configured" ? "Garmin isn't connected yet: tap Connect next to Garmin below."
                                 : "Garmin ended this connection, so syncing is paused: tap Connect next to Garmin below.",
                                 icon: "icloud.slash", shape: .burst)
                    }
                }
                profile(s)
                CardGroup(title: "Reports", tint: .purple) {
                    GroupRow("Morning briefings, run reports, weekly reviews", supporting: "By month, with every version") { nav.open(.journal) }
                }
                garminGroup(s)
                if let r { training(r) }
                appearance
                notifications(r)
                if let r { ai(r) }
                dataGroup
                CardGroup(title: "Account") {
                    GroupRow("Sign out", supporting: "Removes the token and cached data from this phone") { confirm = .signout }
                    if store.me?.value.role == "member" {
                        GroupRow("Delete my account", supporting: "Deletes all your data on the server and disconnects Garmin") { confirm = .account }
                    }
                }
                CardGroup(title: "About") {
                    GroupRow("Runner Sidekick \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "")",
                             supporting: "Guidance only, not medical advice. Garmin data via an unofficial, read-only connector.")
                }
            }
            .padding(.horizontal, 12)
        }
        .navBarRoom()
        .refreshable { await load() }
        .screenBackground()
        .toolbar(.hidden, for: .navigationBar)
        .task { await load() }
        .sheet(item: $sheet) { which in
            Group {
                switch which {
                case .training: if let r { TrainingSheet(r: r) }
                case .race: if let r { RaceSheet(r: r) }
                case .about: if let r { AboutYouSheet(r: r) }
                case .window: if let r { WindowSheet(r: r) }
                case .key: KeySheet()
                case .aiInfo: AiInfoSheet()
                }
            }
            .environment(store)
        }
        .sheet(item: $exportFile) { ShareSheet(items: [$0]) }
        .fullScreenCover(isPresented: $garminConnect) { GarminConnectView(onSkip: nil) { garminConnect = false } }
        .alert(confirmTitle, isPresented: Binding(get: { confirm != nil }, set: { if !$0 { confirm = nil } }), presenting: confirm) { c in
            Button(c == .signout ? "Sign out" : c == .garmin ? "Disconnect" : "Delete", role: .destructive) { run(c) }
            Button("Cancel", role: .cancel) {}
        } message: { c in Text(confirmText(c)) }
    }

    private func load() async {
        busy = true
        defer { busy = false }
        let m = await store.attempt {
            _ = try await store.refreshStatus()
            try await store.remoteSettings()
        }
        if let m { store.toast = m }
    }

    @ViewBuilder private func profile(_ s: Status?) -> some View {
        let m = store.me?.value
        let name = m?.email ?? (m?.role == "owner" ? "Owner (signed in with a device token)" : "Signed in")
        Tile(tint: .green) {
            HStack(spacing: 14) {
                Text(String(name.prefix(1)).uppercased()).font(Typo.titleMedium).foregroundStyle(Tint.green.ink)
                    .frame(width: 48, height: 48).background(Circle().fill(Palette.card.opacity(0.8)))
                VStack(alignment: .leading) {
                    Text(name).font(Typo.titleMedium)
                    let sub = [m.map { $0.role == "owner" ? "Server owner" : "Member" }, s.map { $0.synthetic ? "Demo data" : $0.watch == "samsung" ? "Samsung Galaxy Watch" : "Garmin" }]
                        .compactMap { $0 }.joined(separator: " · ")
                    if !sub.isEmpty { Text(sub).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
                }
            }
        }
    }

    @ViewBuilder private func garminGroup(_ s: Status?) -> some View {
        let g = s?.garminOfficial
        let supporting: String = {
            guard let s else { return "" }
            if s.synthetic { return "Demo data source" }
            if s.watch == "samsung" && s.garminLinked { return "Paused while your watch is the Samsung one. Your Garmin history stays." }
            if g?.connected == true { return "Connected with Garmin's official sign-in. " + (g?.dataImport ?? "") }
            if !s.garminLinked { return "Not connected. Connect to download your runs, sleep and health data." }
            if s.connection.state == "connected" {
                return "Connected · last fetch \(Fmt.ago(Fmt.instant(s.connection.lastSuccessAt)))" + (s.backfill?.oldestDone.map { " · history from \($0)" } ?? "")
            }
            return g?.available == true ? "Not connected" : "Connected"
        }()
        CardGroup(title: "Watch and data sources") {
            GroupRow(headline: "Garmin", supporting: supporting) {
                if let s, !s.synthetic {
                    // Garmin ended the connection: Connect again (it replaces the old one)
                    if s.connection.state == "reauth_required" && g?.connected != true {
                        PillButton(title: "Connect", filled: false) { garminConnect = true }
                    } else if g?.connected == true || s.garminLinked {
                        LinkButton(title: "Disconnect") { confirm = .garmin }
                    } else if g?.available == true {
                        PillButton(title: "Connect", filled: false) {
                            Task {
                                var url: URL?
                                if let m = await store.attempt({ url = try await store.garminAuthorizeUrl() }) { store.toast = m }
                                if let url { openURL(url) }
                            }
                        }
                    } else {
                        PillButton(title: "Connect", filled: false) { garminConnect = true }
                    }
                }
            }
        }
    }

    @ViewBuilder private func training(_ r: SettingsDto) -> some View {
        CardGroup(title: "Training") {
            GroupRow("Training", supporting: [r.runningDays.sorted().map { dayNames[$0] }.joined(separator: ", ").nilIfEmpty ?? "No running days",
                                              goals.first { $0.0 == r.goalType }.map { "goal: \($0.1.lowercased())" },
                                              r.availableMinutes.map { "\($0) min a run" }].compactMap { $0 }.joined(separator: " · ")) { sheet = .training }
            GroupRow("Race", supporting: r.raceDate.map { d in [r.raceName, races.first { $0.0 == r.raceDistance }?.1, Fmt.shortDate(d),
                                                               r.raceTargetS.map { "target \(hms($0))" }].compactMap { $0 }.joined(separator: " · ") } ?? "No race set") { sheet = .race }
            GroupRow("About you", supporting: [(r.profileSex ?? r.profileDetected?.sex).map { Fmt.capitalized($0) },
                                               (r.profileBirthDate ?? r.profileDetected?.birthDate).map { "born \($0)" },
                                               r.profileSex == nil && r.profileBirthDate == nil ? "from Garmin" : nil].compactMap { $0 }.joined(separator: " · ").nilIfEmpty ?? "Not set") { sheet = .about }
            choiceRow("VO₂ max for scores", r.vo2Source == "watch" ? "Your watch's estimate"
                      : "Runner Sidekick's experimental estimate, from your steady runs on any watch (needs 3 in 60 days)",
                      ["Watch", "Sidekick"], ["watch", "sidekick"], r.vo2Source, key: "vo2_source")
            choiceRow("Fitness age", r.fitnessAgeSource == "sidekick" ? "Runner Sidekick's: the age your VO₂ max (as chosen above) is typical for"
                      : "Garmin's (VO₂ max, resting HR, activity, BMI)", ["Garmin", "Sidekick"], ["garmin", "sidekick"], r.fitnessAgeSource, key: "fitness_age_source")
        }
    }

    private func choiceRow(_ title: String, _ supporting: String, _ labels: [String], _ keys: [String], _ current: String?, key: String) -> some View {
        GroupCustom {
            Text(title).font(Typo.bodyLarge)
            Text(supporting).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
            ChoiceGroup(labels: labels, selected: keys.firstIndex { $0 == current }, enabled: !busy) { i in
                if current != keys[i] { save([key: keys[i]]) }
            }
            .padding(.top, 4)
        }
    }

    private var appearance: some View {
        CardGroup(title: "Appearance") {
            GroupCustom {
                Text("Appearance").font(Typo.bodyLarge).padding(.bottom, 4)
                ChoiceGroup(labels: Appearance.allCases.map(\.label), selected: Appearance.allCases.firstIndex(of: store.local.appearance)) { i in
                    store.local.appearance = Appearance.allCases[i]
                    store.savePreference("appearance", store.local.appearance.rawValue)
                }
            }
            GroupCustom {
                Text("Units").font(Typo.bodyLarge).padding(.bottom, 4)
                ChoiceGroup(labels: ["Metric (km)", "Imperial (mi)"], selected: store.local.units == .metric ? 0 : 1) { i in
                    store.local.units = i == 0 ? .metric : .imperial
                    store.savePreference("units", store.local.units.rawValue)
                }
            }
        }
    }

    @ViewBuilder private func notifications(_ r: SettingsDto?) -> some View {
        let notif = store.local.notificationsEnabled
        CardGroup(title: "Notifications") {
            GroupRow(headline: "Morning briefing and run reports", supporting: "Best effort: iOS decides exact timing.") {
                Toggle("", isOn: Binding(get: { notif }, set: { on in
                    Task {
                        let granted = on ? await Notifier.requestPermission() : false
                        if on && !granted { store.toast = "Notifications aren't allowed for Runner Sidekick in Settings" }
                        store.local.notificationsEnabled = granted
                        store.savePreference("notifications", granted)
                        Background.schedule()
                    }
                })).labelsHidden()
            }
            GroupRow(headline: "Background refresh", supporting: notif ? "Already on with notifications (about hourly)."
                     : "Keeps today's briefing and your runs ready offline, about every 3 hours. Garmin itself syncs on the server either way.") {
                Toggle("", isOn: Binding(get: { notif || store.local.backgroundRefresh }, set: { on in
                    store.local.backgroundRefresh = on
                    store.savePreference("background_refresh", on)
                    Background.schedule()
                })).labelsHidden().disabled(notif)
            }
            GroupRow(headline: "Ask about your newest run", supporting: "When you open Runs: what it was meant to be and how it went, a few taps. Skipped runs aren't asked again.") {
                Toggle("", isOn: Binding(get: { store.local.askAboutRuns }, set: { store.local.askAboutRuns = $0; store.local.save() })).labelsHidden()
            }
            if let r {
                GroupRow("Morning window", supporting: "\(r.windowStart)–\(r.windowEnd) · the briefing comes once your sleep has synced, or at the end of the window as provisional") {
                    sheet = .window
                }
            }
        }
    }

    @ViewBuilder private func ai(_ r: SettingsDto) -> some View {
        let ownKey = store.local.hasOwnAiKey
        CardGroup(title: "AI coach (optional)") {
            GroupRow(headline: "AI coach and summaries", supporting: ownKey ? "Uses OpenAI with your own key." : r.aiAvailable ? "Uses OpenAI. Off by default." : "Add your own OpenAI key to use it.") {
                Toggle("", isOn: Binding(get: { r.aiEnabled }, set: { save(["ai_enabled": $0]) })).labelsHidden()
                    .disabled(busy || !(r.aiAvailable || ownKey || r.aiEnabled))
            }
            GroupRow("Your own OpenAI key", supporting: ownKey ? "Saved on this phone" : "Optional: the server's key is used otherwise") { sheet = .key }
            GroupRow("What's sent to the AI", supporting: "Findings and numbers only; never your notes, run names or routes") { sheet = .aiInfo }
        }
        CardGroup(title: "Weather") {
            GroupRow(headline: "Weather for your runs",
                     supporting: "Temperature and humidity, so hot, humid runs are read fairly. Sends each outdoor run's start area (rounded to about 1 km) and time to Open-Meteo, nothing else. Off: nothing is sent; estimates already kept stay.") {
                Toggle("", isOn: Binding(get: { r.weatherEnabled }, set: { save(["weather_enabled": $0]) })).labelsHidden().disabled(busy)
            }
        }
    }

    private var dataGroup: some View {
        CardGroup(title: "Your data") {
            GroupRow("Export all data", supporting: "JSON file with records, check-ins and reports") {
                Task {
                    var data = Data()
                    if let m = await store.attempt({ data = try await store.exportJson() }) { store.toast = m; return }
                    let url = FileManager.default.temporaryDirectory.appendingPathComponent("runner-sidekick-export.json")
                    try? data.write(to: url, options: .completeFileProtection)
                    exportFile = url
                }
            }
            GroupRow("Clear this phone's cache", supporting: "Unsent check-ins are kept") { confirm = .local }
            GroupRow("Delete raw Garmin payloads", supporting: "On the backend. Records and reports stay.") { confirm = .raw }
            GroupRow("Delete everything on the backend", supporting: "Records, reports, check-ins and settings") { confirm = .all }
            GroupCustom {
                Text("Health data lives on your backend and in this phone's cache, which is left out of iCloud backups. Your server's own backups may still include its data folder.")
                    .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }

    private func save(_ changes: [String: Any?]) {
        busy = true
        Task {
            let m = await store.attempt { try await store.saveSettings(changes) }
            busy = false
            store.toast = m ?? "Saved"
            if m == nil { Task { _ = await store.attempt { try await store.refreshAll() } } }
        }
    }

    private var confirmTitle: String {
        switch confirm {
        case .signout: "Sign out?"
        case .account: "Delete your account?"
        case .garmin: "Disconnect Garmin?"
        default: "Delete data?"
        }
    }

    private func confirmText(_ c: Confirm) -> String {
        switch c {
        case .local: "Removes cached reports and runs from this phone. Unsent check-ins are kept."
        case .raw: "Removes stored Garmin source payloads. Normalised records and reports stay."
        case .signout: "You can sign in again any time. Unsent check-ins stay on this phone."
        case .garmin: "Syncing stops and the server forgets this Garmin connection. Data already downloaded stays. You can connect again any time."
        case .account: "Permanently deletes all your health data, reports and check-ins on the server, and disconnects Garmin. This can't be undone."
        case .all: "Removes all records, reports, check-ins and settings from the backend and this phone. Garmin sign-in tokens aren't affected. This can't be undone."
        }
    }

    private func run(_ c: Confirm) {
        Task {
            switch c {
            case .local: store.clearLocal(includeCheckins: false); store.toast = "Local cache cleared"
            case .signout: await store.signOut()
            case .account: if let m = await store.attempt({ try await store.deleteAccount() }) { store.toast = m }
            case .garmin: store.toast = await store.attempt { try await store.disconnectGarmin() } ?? "Garmin disconnected"
            case .raw, .all: store.toast = await store.attempt { try await store.deleteRemote(c.rawValue) } ?? "Deleted"
            }
        }
    }
}

// MARK: Sheets

/// One section's sheet with its own Save. Swiping it away with unsaved edits asks first, so nothing is lost silently.
private struct SectionSheet<Content: View>: View {
    var title: String
    var dirty: Bool
    var canSave: Bool
    var onSave: () async -> String?
    @ViewBuilder var content: Content
    @Environment(\.dismiss) private var dismiss
    @State private var error: String?
    @State private var saving = false
    @State private var ask = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    content
                    if let error { Text(error).font(Typo.bodyMedium).foregroundStyle(Palette.error) }
                }
                .padding(.horizontal, 24).padding(.bottom, 32)
            }
            .screenBackground()
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { if dirty { ask = true } else { dismiss() } } }
                if canSave || dirty {
                    ToolbarItem(placement: .confirmationAction) {
                        Button(dirty ? "Save" : "Saved") {
                            Task {
                                saving = true
                                // Failure: the sheet stays open with its edits and the error
                                error = await onSave()
                                saving = false
                                if error == nil { dismiss() }
                            }
                        }
                        .disabled(!canSave || !dirty || saving)
                    }
                }
            }
        }
        .interactiveDismissDisabled(dirty)
        .confirmationDialog("Discard changes?", isPresented: $ask, titleVisibility: .visible) {
            Button("Discard", role: .destructive) { dismiss() }
            Button("Keep editing", role: .cancel) {}
        } message: { Text("Your edits in \(title) haven't been saved.") }
    }
}

private struct FieldLabel: View {
    var text: String
    var hint: String? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(text).font(Typo.titleMedium)
            if let hint { Text(hint).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
        }
    }
}

private extension Store {
    /// Saves a sheet's changes; returns the error to show, or nil. A refresh follows in the background.
    func saveSheet(_ changes: [String: Any?]) async -> String? {
        let m = await attempt { try await saveSettings(changes) }
        if m == nil {
            toast = "Saved"
            Task { _ = await attempt { try await refreshAll() } }
        }
        return m
    }
}

private struct TrainingSheet: View {
    var r: SettingsDto
    @Environment(Store.self) private var store
    @State private var days: Set<Int>
    @State private var goalType: String?
    @State private var goal: String
    @State private var minutes: String
    @State private var weekStart: String?
    @State private var zones: String?
    @State private var tz: String

    init(r: SettingsDto) {
        self.r = r
        _days = State(initialValue: Set(r.runningDays)); _goalType = State(initialValue: r.goalType); _goal = State(initialValue: r.goal ?? "")
        _minutes = State(initialValue: r.availableMinutes.map(String.init) ?? ""); _weekStart = State(initialValue: r.weekStartDay)
        _zones = State(initialValue: r.hrZoneSource); _tz = State(initialValue: r.timezone)
    }

    var body: some View {
        let phoneTz = TimeZone.current.identifier
        let tzOk = TimeZone(identifier: tz.trimmingCharacters(in: .whitespaces)) != nil
        let dirty = days != Set(r.runningDays) || goalType != r.goalType || goal != (r.goal ?? "") || minutes != (r.availableMinutes.map(String.init) ?? "")
            || weekStart != r.weekStartDay || zones != r.hrZoneSource || tz.trimmingCharacters(in: .whitespaces) != r.timezone
        SectionSheet(title: "Training", dirty: dirty, canSave: tzOk, onSave: {
            await store.saveSheet(["running_days": days.sorted(), "goal_type": goalType, "goal": goal.nilIfEmpty, "available_minutes": Int(minutes),
                                   "week_start_day": weekStart, "hr_zone_source": zones, "timezone": tz.trimmingCharacters(in: .whitespaces)])
        }) {
            FieldLabel(text: "Running days")
            ToggleRow(labels: dayNames, checked: { days.contains($0) }) { i in if days.contains(i) { days.remove(i) } else { days.insert(i) } }
            FieldLabel(text: "Main goal", hint: "Orders the weekly focus suggestions.")
            ToggleRow(labels: goals.map(\.1), checked: { goalType == goals[$0].0 }) { i in goalType = goalType == goals[i].0 ? nil : goals[i].0 }
            FieldBox(placeholder: "Goal in your words (optional)", text: Binding(get: { goal }, set: { goal = String($0.prefix(200)) }))
            FieldBox(placeholder: "Usual time per run (min)", text: Binding(get: { minutes }, set: { minutes = String($0.filter(\.isNumber).prefix(3)) }), keyboard: .numberPad)
            FieldLabel(text: "Week starts on", hint: weekStart == nil ? "Now: \(Fmt.capitalized(r.weekStartEffective ?? "monday")) (from Garmin, or Monday)."
                       : "Used for weekly reviews, the weekly focus, Runs and charts.")
            let starts: [(String?, String)] = [(nil, "As in Garmin"), ("monday", "Monday"), ("sunday", "Sunday"), ("saturday", "Saturday")]
            ToggleRow(labels: starts.map(\.1), checked: { weekStart == starts[$0].0 }) { weekStart = starts[$0].0 }
            FieldLabel(text: "Heart-rate zones")
            ChoiceGroup(labels: ["From Garmin", "Don't use"], selected: ["garmin", "none"].firstIndex { $0 == zones }) { zones = ["garmin", "none"][$0] }
            FieldLabel(text: "Time zone", hint: "Decides when your day starts and ends.")
            FieldBox(placeholder: "Europe/London", text: $tz)
            if !tzOk { Text("Not a time zone name, e.g. Europe/London").font(Typo.bodySmall).foregroundStyle(Palette.error) }
            if tz.trimmingCharacters(in: .whitespaces) != phoneTz { LinkButton(title: "Use this phone's (\(phoneTz))") { tz = phoneTz } }
        }
    }
}

private struct RaceSheet: View {
    var r: SettingsDto
    @Environment(Store.self) private var store
    @State private var dist: String?
    @State private var date: String?
    @State private var name: String
    @State private var h: String
    @State private var m: String
    @State private var s: String

    init(r: SettingsDto) {
        self.r = r
        let t0 = r.raceTargetS ?? 0
        _dist = State(initialValue: r.raceDistance); _date = State(initialValue: r.raceDate); _name = State(initialValue: r.raceName ?? "")
        _h = State(initialValue: r.raceTargetS != nil ? "\(t0 / 3600)" : "")
        _m = State(initialValue: r.raceTargetS != nil ? String(format: "%02d", t0 % 3600 / 60) : "")
        _s = State(initialValue: r.raceTargetS != nil ? String(format: "%02d", t0 % 60) : "")
    }

    var body: some View {
        let blank = h.isEmpty && m.isEmpty && s.isEmpty
        let mi = Int(m) ?? 0, si = Int(s) ?? 0
        let total = (Int(h) ?? 0) * 3600 + mi * 60 + si
        let target: Int? = blank ? nil : (mi < 60 && si < 60 && (600...36000).contains(total) ? total : nil)
        let targetOk = blank || target != nil
        let dirty = dist != r.raceDistance || date != r.raceDate || name.trimmingCharacters(in: .whitespaces).nilIfEmpty != r.raceName || target != r.raceTargetS
        SectionSheet(title: "Race", dirty: dirty, canSave: targetOk && (date == nil) == (dist == nil), onSave: {
            await store.saveSheet(["race_distance": dist, "race_date": date, "race_name": name.trimmingCharacters(in: .whitespaces).nilIfEmpty, "race_target_s": target])
        }) {
            Text("The weekly focus, Today and the AI coach plan backwards from it: base, build, sharpen, taper, race week.")
                .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            FieldLabel(text: "Distance")
            ToggleRow(labels: races.map(\.1), checked: { dist == races[$0].0 }) { i in dist = dist == races[i].0 ? nil : races[i].0 }
            FieldLabel(text: "Date")
            DatePicker("Race date", selection: Binding(get: { date.flatMap { Fmt.day($0) } ?? Date() }, set: { date = Fmt.iso($0) }),
                       in: Calendar.current.date(byAdding: .day, value: -30, to: Date())!..., displayedComponents: .date)
                .datePickerStyle(.compact)
            if (date == nil) != (dist == nil) { Text("Set both a distance and a date, or neither").font(Typo.bodySmall).foregroundStyle(Palette.error) }
            FieldLabel(text: "Target time (optional)")
            HStack(spacing: 8) {
                FieldBox(placeholder: "h", text: Binding(get: { h }, set: { h = String($0.filter(\.isNumber).prefix(2)) }), keyboard: .numberPad)
                FieldBox(placeholder: "min", text: Binding(get: { m }, set: { m = String($0.filter(\.isNumber).prefix(2)) }), keyboard: .numberPad)
                FieldBox(placeholder: "s", text: Binding(get: { s }, set: { s = String($0.filter(\.isNumber).prefix(2)) }), keyboard: .numberPad)
            }
            if !targetOk { Text("Between 10 minutes and 10 hours").font(Typo.bodySmall).foregroundStyle(Palette.error) }
            FieldBox(placeholder: "Race name (optional)", text: Binding(get: { name }, set: { name = String($0.prefix(60)) }))
            if dist != nil || date != nil { LinkButton(title: "Remove race") { dist = nil; date = nil; h = ""; m = ""; s = ""; name = "" } }
        }
    }
}

private struct AboutYouSheet: View {
    var r: SettingsDto
    @Environment(Store.self) private var store
    @State private var sex: String?
    @State private var birth: String?

    init(r: SettingsDto) { self.r = r; _sex = State(initialValue: r.profileSex); _birth = State(initialValue: r.profileBirthDate) }

    var body: some View {
        let det = r.profileDetected
        SectionSheet(title: "About you", dirty: sex != r.profileSex || birth != r.profileBirthDate, canSave: true, onSave: {
            await store.saveSheet(["profile_sex": sex, "profile_birth_date": birth])
        }) {
            Text(det?.sex != nil || det?.birthDate != nil ? "From Garmin: \([det?.sex, det?.birthDate].compactMap { $0 }.joined(separator: ", ")). Set these only to override Garmin."
                 : "Garmin didn't provide these; set them to see age and sex comparisons.").font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            FieldLabel(text: "Sex")
            let sexes: [(String?, String)] = [(nil, "As in Garmin"), ("male", "Male"), ("female", "Female")]
            ChoiceGroup(labels: sexes.map(\.1), selected: sexes.firstIndex { $0.0 == sex }) { sex = sexes[$0].0 }
            FieldLabel(text: "Birth date")
            HStack {
                if birth == nil {
                    OutlineButton(title: "As in Garmin · set one") { birth = "1985-01-01" }
                } else {
                    DatePicker("Birth date", selection: Binding(get: { birth.flatMap { Fmt.day($0) } ?? Date() }, set: { birth = Fmt.iso($0) }),
                               in: ...Calendar.current.date(byAdding: .day, value: -1, to: Date())!, displayedComponents: .date)
                        .labelsHidden()
                    Spacer()
                    LinkButton(title: "Use Garmin's") { birth = nil }
                }
            }
        }
    }
}

private struct WindowSheet: View {
    var r: SettingsDto
    @Environment(Store.self) private var store
    @State private var start: String
    @State private var end: String

    init(r: SettingsDto) { self.r = r; _start = State(initialValue: r.windowStart); _end = State(initialValue: r.windowEnd) }

    private func time(_ v: Binding<String>) -> Binding<Date> {
        Binding(get: {
            let p = v.wrappedValue.split(separator: ":").compactMap { Int($0) }
            return Calendar.current.date(bySettingHour: p.first ?? 6, minute: p.count > 1 ? p[1] : 0, second: 0, of: Date()) ?? Date()
        }, set: { d in
            let c = Calendar.current.dateComponents([.hour, .minute], from: d)
            v.wrappedValue = String(format: "%02d:%02d", c.hour ?? 0, c.minute ?? 0)
        })
    }

    var body: some View {
        SectionSheet(title: "Morning window", dirty: start != r.windowStart || end != r.windowEnd, canSave: start < end, onSave: {
            await store.saveSheet(["morning_window_start": start, "morning_window_end": end])
        }) {
            Text("The briefing is sent once your sleep has synced, or at the end of the window as provisional.").font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            DatePicker("From", selection: time($start), displayedComponents: .hourAndMinute)
            DatePicker("Until", selection: time($end), displayedComponents: .hourAndMinute)
            if start >= end { Text("The window has to end after it starts").font(Typo.bodySmall).foregroundStyle(Palette.error) }
        }
        .environment(\.locale, Locale(identifier: "en_GB"))  // 24-hour times, as the server stores them
    }
}

private struct KeySheet: View {
    @Environment(Store.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var key = ""
    var body: some View {
        let own = store.local.hasOwnAiKey
        SectionSheet(title: "Your own OpenAI key", dirty: !key.isEmpty, canSave: key.hasPrefix("sk-"), onSave: {
            store.setOwnAiKey(key)
            store.toast = "Key saved on this phone"
            return nil
        }) {
            Text("Kept in this phone's keychain and sent only with AI requests. The server uses it for that request and never stores it.")
                .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            SecureField(own ? "Saved · enter a new key to replace" : "sk-…", text: Binding(get: { key }, set: { key = $0.trimmingCharacters(in: .whitespaces) }))
                .font(Typo.bodyLarge).padding(14)
                .background(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Palette.outline))
                .textInputAutocapitalization(.never).autocorrectionDisabled()
            if own {
                LinkButton(title: "Remove saved key") {
                    store.setOwnAiKey(nil)
                    store.toast = "Your key was removed"
                    dismiss()
                }
            }
        }
    }
}

private struct AiInfoSheet: View {
    var body: some View {
        SectionSheet(title: "What's sent to the AI", dirty: false, canSave: false, onSave: { nil }) {
            Text("Runs get AI input automatically on the server: each new run, and your latest 3 runs whenever one has none yet (a failed try is tried again after 6 hours). At most 3 per sync, never using the last 5 AI calls of the day. Older runs: tap Get AI input. There's no free-text chat with the AI.")
                .font(Typo.bodyMedium)
            Text("What is sent: finding titles, statuses, values and ranges. Never your notes, run names, routes or identifiers. Numbers in summaries are filled in from the report, not written by the AI. If its output doesn't pass checks, nothing is shown.")
                .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
        }
        .presentationDetents([.medium, .large])
    }
}

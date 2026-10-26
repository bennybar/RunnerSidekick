import SwiftUI

/// Garmin names most runs just "Running"; only show names that say something.
func displayName(_ name: String?) -> String? {
    guard let n = name, !n.isEmpty, n.lowercased() != "running", !n.hasSuffix(" Running") else { return nil }
    return n
}

private enum RunFilter: Int, CaseIterable {
    case all, road, trail, treadmill
    var label: String { ["All", "Road", "Trail", "Treadmill"][rawValue] }
    func keeps(_ a: ActivitySummary) -> Bool {
        switch self {
        case .all: true
        case .road: a.sport == "running"
        case .trail: a.sport == "trail_running"
        case .treadmill: a.sport == "treadmill_running"
        }
    }
}

struct RunsView: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @State private var filter: RunFilter = .all
    @State private var busy = false
    @State private var wizard: ActivitySummary?

    var body: some View {
        let units = store.units
        let all = (store.activities?.value ?? []).filter { $0.sport != "other" }
        let shown = all.filter { filter.keeps($0) }
        let weeks = Dictionary(grouping: shown) { Fmt.weekStart($0.localDate, store.firstWeekday) }.sorted { $0.key > $1.key }
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Text("Runs").font(Typo.headlineLarge).frame(maxWidth: .infinity, alignment: .leading)
                    if all.contains(where: \.synthetic) { DemoBadge() }
                    Button { nav.open(.trophies) } label: { Image(systemName: "trophy").font(.title3) }
                        .buttonStyle(PressStyle()).foregroundStyle(Palette.onSurface).accessibilityLabel("Your records")
                    // Fetch a run you just finished from Garmin without waiting for the hourly sync
                    TimelineView(.periodic(from: .now, by: 30)) { ctx in
                        let wait = syncWait(store.status?.value.syncNextAllowedAt, now: ctx.date)
                        PillButton(title: busy ? "Syncing…" : wait.map { "Next sync \($0)" } ?? "Get new runs", icon: "arrow.triangle.2.circlepath",
                                   filled: false, busy: busy) { Task { await sync() } }
                            .disabled(busy || wait != nil)
                    }
                }
                .padding(.horizontal, 12).padding(.top, 40).padding(.bottom, 6)
                if let (start, runs) = weeks.first { WeekHero(start: start, runs: runs, units: units, thisWeek: start == Fmt.weekStart(Fmt.todayISO(), store.firstWeekday)) }
                ChoiceGroup(labels: RunFilter.allCases.map(\.label), selected: filter.rawValue) { filter = RunFilter(rawValue: $0)! }
                if shown.isEmpty {
                    EmptyState(icon: "figure.run", title: store.activities == nil ? "No runs loaded" : "No runs here",
                               message: store.activities == nil ? "Pull down to load your runs." : "No runs match this filter in the synced period.")
                }
                ForEach(weeks, id: \.key) { start, runs in
                    let dist = runs.reduce(0) { $0 + ($1.distanceM ?? 0) }, time = runs.reduce(0) { $0 + ($1.movingS ?? 0) }
                    CardGroup(title: "Week of \(Fmt.shortDate(start)) · \(runs.count) \(runs.count == 1 ? "run" : "runs") · \(Fmt.distance(dist, units)) · \(Fmt.hoursMinutes(time))") {
                        ForEach(runs.sorted { $0.startUtc > $1.startUtc }) { a in RunRow(a: a, units: units) { nav.open(.run(a.sourceId)) } }
                    }
                }
            }
            .padding(.horizontal, 12)
        }
        .navBarRoom()
        .refreshable { if let m = await store.attempt({ try await store.refreshAll() }) { store.toast = m } }
        .screenBackground()
        .toolbar(.hidden, for: .navigationBar)
        // The newest run, if nothing's been said about it and it hasn't been asked about: a few questions, once (Me turns it off)
        .task(id: store.activities?.value.first?.sourceId) { await askAboutNewest() }
        .sheet(item: $wizard) { run in
            RunWizard(title: "\(Fmt.activityTime(run.startUtc, run.utcOffsetS)) · \(Fmt.distance(run.distanceM, units)) at \(Fmt.pace(run.paceMovingSPerKm, units))",
                      guess: store.detail(run.sourceId)?.value.report?.intent,
                      onClose: { store.markRunAsked(run.sourceId); wizard = nil },
                      onSave: { i in store.act { try await store.setIntent(run.sourceId, i) } })
        }
    }

    private func askAboutNewest() async {
        guard let run = store.activities?.value.first, !run.synthetic, !run.answered, store.local.askAboutRuns, run.sourceId != store.local.runAsked else { return }
        // Its guessed type first, so the first question starts from it
        if store.detail(run.sourceId) == nil { _ = await store.attempt { try await store.refreshActivity(run.sourceId) } }
        if store.detail(run.sourceId) != nil { wizard = run }
    }

    private func sync() async {
        busy = true
        defer { busy = false }
        var n = 0
        if let m = await store.attempt({ n = try await store.syncRunsNow() }) { store.toast = m; return }
        store.toast = "Synced with Garmin · " + (n == 0 ? "no new runs" : n == 1 ? "1 new run" : "\(n) new runs")
    }
}

/// One run in a week's list: when, distance and pace, then name, moving time and heart rate; a run that set a record
/// says so in words and wears a trophy.
private struct RunRow: View {
    var a: ActivitySummary
    var units: Units
    var onTap: () -> Void
    var body: some View {
        let best = !a.records.isEmpty
        Button(action: onTap) {
            HStack(spacing: 14) {
                ShapeBadge(symbol: best ? "trophy" : "figure.run", shape: best ? .sunny : .cookie6, size: 36,
                           container: (best ? Tint.amber : Tint.orange).hue.opacity(0.22), content: (best ? Tint.amber : Tint.orange).ink)
                    .accessibilityLabel(best ? "Set a record" : "")
                VStack(alignment: .leading, spacing: 2) {
                    Text(Fmt.activityTime(a.startUtc, a.utcOffsetS)).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                    Text("\(Fmt.distance(a.distanceM, units)) · \(Fmt.pace(a.paceMovingSPerKm, units))").font(Typo.titleMedium)
                    Text([displayName(a.name), "\(Fmt.duration(a.movingS)) moving", a.avgHr.map { "\(Int($0.rounded())) bpm" }].compactMap { $0 }.joined(separator: " · "))
                        .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                    if best {
                        Text("New best: " + a.records.map { "\($0.title.replacingOccurrences(of: "Fastest ", with: "")) \($0.value)" }.joined(separator: ", "))
                            .font(Typo.labelLarge).foregroundStyle(Tint.amber.ink)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(Palette.onSurfaceVariant)
            }
            .padding(.horizontal, 18).padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(PressStyle())
    }
}

private struct WeekHero: View {
    var start: String
    var runs: [ActivitySummary]
    var units: Units
    var thisWeek: Bool
    var body: some View {
        let d = Fmt.distance(runs.reduce(0) { $0 + ($1.distanceM ?? 0) }, units).split(separator: " ")
        Tile(tint: .orange, spacing: 12) {
            Text(thisWeek ? "This week" : "Week of \(Fmt.shortDate(start))").font(Typo.titleSmall)
            HStack(alignment: .top) {
                stat(String(d.first ?? ""), String(d.last ?? ""))
                stat("\(runs.count)", runs.count == 1 ? "run" : "runs")
                stat(Fmt.hoursMinutes(runs.reduce(0) { $0 + ($1.movingS ?? 0) }).replacingOccurrences(of: " min", with: "m").replacingOccurrences(of: " h ", with: "h "), "moving")
            }
        }
    }
    private func stat(_ v: String, _ l: String) -> some View {
        VStack(alignment: .leading) {
            Text(v).font(Typo.headlineMedium).lineLimit(1)
            Text(l).font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: Run type and how it went

let intentKinds = [("recovery", "Recovery"), ("easy", "Easy"), ("steady", "Steady aerobic"), ("long", "Long run"), ("tempo", "Tempo"),
                   ("threshold", "Threshold"), ("intervals", "Intervals"), ("race", "Race"), ("progression", "Progression"), ("free", "Free run"), ("other", "Other")]
let efforts = [("very_easy", "Very easy"), ("easy", "Easy"), ("easy_moderate", "Easy-moderate"), ("moderate", "Moderate"),
               ("moderate_hard", "Moderate-hard"), ("hard", "Hard"), ("very_hard", "Very hard")]
let feels = [("great", "Great"), ("good", "Good"), ("okay", "Okay"), ("poor", "Poor"), ("very_poor", "Very poor")]
let limiters = [("none", "None"), ("cardio", "Cardio"), ("breathing", "Breathing"), ("legs", "Legs"), ("feet", "Feet"), ("muscular_fatigue", "Muscular fatigue"),
                ("heat", "Heat"), ("humidity", "Humidity"), ("hills", "Hills"), ("illness", "Illness"), ("pain", "Pain"), ("gi", "Stomach"),
                ("motivation", "Motivation"), ("other", "Other")]
let healths = [("normal", "Normal"), ("recovering", "Recovering from illness"), ("mild_symptoms", "Mild symptoms"), ("poor_sleep", "Poor sleep"),
               ("fatigued", "Fatigued"), ("sore", "Sore"), ("other", "Other")]

func optionLabel(_ options: [(String, String)], _ key: String?) -> String? { options.first { $0.0 == key }?.1 ?? key }

/// The run's type as one row; tapping opens an optional sheet for what it was meant to be and how it went.
struct IntentPicker: View {
    var intent: RunIntent?
    var onSave: (RunIntent) -> Void
    @State private var open = false
    var body: some View {
        let stated = intent?.source == "user"
        let said = stated ? [intent?.feel.map { "felt \(optionLabel(feels, $0)!.lowercased())" },
                             intent?.limiter.flatMap { $0 == "none" ? nil : "limited by \(optionLabel(limiters, $0)!.lowercased())" }].compactMap { $0 } : []
        let supporting = switch intent?.source {
        case "user": (said.isEmpty ? "Your run type" : Fmt.capitalized(said.joined(separator: " · "))) + " · tap to edit"
        case "plan": "From today's plan · tap to change or add how it went"
        default: "Inferred from pace and heart rate · tap to set it or add how it went"
        }
        CardGroup(title: "Run type") {
            GroupRow(intent.map { (stated ? "" : "Looks like: ") + (optionLabel(intentKinds, $0.kind) ?? $0.kind) } ?? "Not set",
                     supporting: supporting) { open = true }
        }
        .sheet(isPresented: $open) { RunContextSheet(intent: intent) { onSave($0); open = false } }
    }
}

/// One labelled row of choices; tapping the selected one again clears an optional answer.
private struct Choice: View {
    var title: String
    var options: [(String, String)]
    @Binding var selected: String?
    var optional = true
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(Typo.titleSmall).padding(.leading, 4)
            ToggleRow(labels: options.map(\.1), checked: { selected == options[$0].0 }) { i in
                let k = options[i].0
                selected = selected == k && optional ? nil : k
            }
        }
    }
}

private struct RunContextSheet: View {
    var intent: RunIntent?
    var onSave: (RunIntent) -> Void
    @State private var kind: String?
    @State private var target = ""
    @State private var effort: String?
    @State private var feel: String?
    @State private var limiter: String?
    @State private var limiter2: String?
    @State private var health: String?
    @State private var note = ""

    init(intent: RunIntent?, onSave: @escaping (RunIntent) -> Void) {
        self.intent = intent; self.onSave = onSave
        let stated = intent?.source == "user"
        _kind = State(initialValue: intent?.kind)
        _target = State(initialValue: stated ? intent?.target ?? "" : "")
        _effort = State(initialValue: stated ? intent?.effort : nil)
        _feel = State(initialValue: stated ? intent?.feel : nil)
        _limiter = State(initialValue: stated ? intent?.limiter : nil)
        _limiter2 = State(initialValue: stated ? intent?.limiter2 : nil)
        _health = State(initialValue: stated ? intent?.health : nil)
        _note = State(initialValue: stated ? intent?.note ?? "" : "")
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("This run").font(Typo.headlineSmall)
                Text("All optional. What you say here comes first in the run's advice, AI input and export; blanks are left out.")
                    .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
                Choice(title: "Meant to be", options: intentKinds, selected: $kind, optional: false)
                FieldBox(placeholder: "Target (e.g. HR ≤ 160, 5:30 /km)", text: $target)
                Choice(title: "Perceived effort", options: efforts, selected: $effort)
                Choice(title: "Overall feel", options: feels, selected: $feel)
                Choice(title: "What limited you", options: limiters, selected: $limiter)
                if let l = limiter, l != "none" { Choice(title: "Anything else", options: limiters.filter { $0.0 != l }, selected: $limiter2) }
                Choice(title: "Health", options: healths, selected: $health)
                FieldBox(placeholder: "Notes (private, never sent to AI)", text: $note, multiline: true)
                Button {
                    if let k = kind {
                        onSave(RunIntent(kind: k, note: note, source: "user", target: target, effort: effort, feel: feel, limiter: limiter,
                                         limiter2: limiter != nil && limiter != "none" ? limiter2 : nil, health: health))
                    }
                } label: {
                    Text("Save").font(Typo.titleMedium).foregroundStyle(Palette.onPrimary).frame(maxWidth: .infinity, minHeight: 52)
                        .background(Capsule().fill(Palette.primary))
                }
                .buttonStyle(PressStyle()).disabled(kind == nil)
            }
            .padding(18).padding(.bottom, 16)
        }
        .screenBackground()
        .presentationDragIndicator(.visible)
    }
}

/// A text field in the app's style.
struct FieldBox: View {
    var placeholder: String
    @Binding var text: String
    var multiline = false
    var keyboard: UIKeyboardType = .default
    var body: some View {
        Group {
            if multiline { TextField(placeholder, text: $text, axis: .vertical).lineLimit(2...5) }
            else { TextField(placeholder, text: $text).keyboardType(keyboard) }
        }
        .font(Typo.bodyLarge)
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Palette.outline))
    }
}

/// A few questions about a run, one at a time: what it was meant to be (pre-set to the plan's or the data's guess), how
/// hard it felt, how it went, what limited you, health, a note. Every step can be skipped; one tap on a single answer
/// moves on. Closing it early keeps what was answered.
struct RunWizard: View {
    var title: String
    var guess: RunIntent?
    var onClose: () -> Void
    var onSave: (RunIntent) -> Void
    @State private var step = 0
    @State private var kind: String?
    @State private var target = ""
    @State private var effort: String?
    @State private var feel: String?
    @State private var limiter: String?
    @State private var limiter2: String?
    @State private var health: String?
    @State private var note = ""
    @State private var saved = false
    private let last = 5

    init(title: String, guess: RunIntent?, onClose: @escaping () -> Void, onSave: @escaping (RunIntent) -> Void) {
        self.title = title; self.guess = guess; self.onClose = onClose; self.onSave = onSave
        _kind = State(initialValue: guess?.kind)
    }

    private var said: Bool {
        kind != guess?.kind || !target.isEmpty || effort != nil || feel != nil || limiter != nil || health != nil || !note.isEmpty
    }

    private func save() {
        guard let k = kind, !saved else { return }
        saved = true
        onSave(RunIntent(kind: k, note: note, source: "user", target: target, effort: effort, feel: feel, limiter: limiter,
                         limiter2: limiter != nil && limiter != "none" ? limiter2 : nil, health: health))
    }
    private func next() { if step < last { withAnimation { step += 1 } } else { save(); onClose() } }

    var body: some View {
        let (question, hint): (String, String?) = switch step {
        case 0: ("What was it meant to be?", guess.map { g in (g.source == "plan" ? "From today's plan: " : "Looks like: ") + "\(optionLabel(intentKinds, g.kind) ?? g.kind). Change it if not." })
        case 1: ("How hard did it feel?", nil)
        case 2: ("How did it go overall?", nil)
        case 3: ("What limited you?", limiter != nil && limiter != "none" ? "Anything else? Optional." : nil)
        case 4: ("How's your health?", nil)
        default: ("Anything to note?", "Private: never sent to the AI.")
        }
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("About your run · \(step + 1) of \(last + 1)").font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
                Text(title).font(Typo.titleMedium)
                ProgressView(value: Double(step + 1), total: Double(last + 1)).tint(Palette.primary)
                Text(question).font(Typo.headlineSmall)
                if let hint { Text(hint).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
                switch step {
                case 0:
                    ToggleRow(labels: intentKinds.map(\.1), checked: { kind == intentKinds[$0].0 }) { kind = intentKinds[$0].0 }
                    FieldBox(placeholder: "Target, optional (e.g. HR ≤ 160, 5:30 /km)", text: $target)
                case 1: single(efforts, $effort)
                case 2: single(feels, $feel)
                case 3:
                    ToggleRow(labels: limiters.map(\.1), checked: { limiter == limiters[$0].0 }) { i in
                        let k = limiters[i].0
                        limiter = limiter == k ? nil : k
                        limiter2 = nil
                        if limiter == "none" { next() }  // nothing limited you: nothing more to ask here
                    }
                    if let l = limiter, l != "none" {
                        let rest = limiters.filter { $0.0 != l && $0.0 != "none" }
                        ToggleRow(labels: rest.map(\.1), checked: { limiter2 == rest[$0].0 }) { limiter2 = limiter2 == rest[$0].0 ? nil : rest[$0].0 }
                    }
                case 4: single(healths, $health)
                default: FieldBox(placeholder: "Notes", text: $note, multiline: true)
                }
                HStack {
                    // "Not now" keeps nothing; swiping the sheet away keeps what was answered
                    if step > 0 { LinkButton(title: "Back") { withAnimation { step -= 1 } } } else { LinkButton(title: "Not now") { saved = true; onClose() } }
                    Spacer()
                    PillButton(title: step == last ? "Save" : "Next", action: next).disabled(kind == nil).opacity(kind == nil ? 0.4 : 1)
                }
            }
            .padding(18)
        }
        .screenBackground()
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .onDisappear { if said { save() }; onClose() }
    }

    /// Picking a single answer moves on; picking it again clears it and stays.
    private func single(_ options: [(String, String)], _ value: Binding<String?>) -> some View {
        ToggleRow(labels: options.map(\.1), checked: { value.wrappedValue == options[$0].0 }) { i in
            let k = options[i].0
            if value.wrappedValue == k { value.wrappedValue = nil } else { value.wrappedValue = k; next() }
        }
    }
}

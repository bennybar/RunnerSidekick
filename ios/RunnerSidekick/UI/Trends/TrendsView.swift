import SwiftUI

private let repeatedElsewhere: Set<String> = ["intensity", "efficiency"]

func categoryStyle(_ category: String) -> (String, BadgeShape) {
    switch category {
    case "training": ("dumbbell", .cookie9)
    case "fitness": ("chart.line.uptrend.xyaxis", .sunny)
    case "running": ("figure.run", .cookie6)
    case "sleep": ("moon", .clover4)
    case "recovery": ("heart", .softBurst)
    default: ("lightbulb", .circle)
    }
}

/// A quiet pause between polls that back off: 3 s, 4.5 s, … up to 15 s.
func pollPause(_ attempt: Int) async { try? await Task.sleep(for: .seconds(min(15, 3 * pow(1.5, Double(attempt))))) }

struct TrendsView: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @State private var tab = 0
    @State private var days = 28
    @State private var busy = false

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Trends").font(Typo.headlineLarge).frame(maxWidth: .infinity, alignment: .leading).accessibilityAddTraits(.isHeader)
                    if store.insights?.value.synthetic == true { DemoBadge() }
                }
                .padding(.horizontal, 12).padding(.top, 40).padding(.bottom, 6)
                ChoiceGroup(labels: ["Summary", "Compare", "Charts"], selected: tab) { tab = $0 }
                switch tab {
                case 1: CompareSection(r: store.compare?.value) { nav.tab = .me }
                case 2: TrendsSection(t: store.trend(days)?.value, days: $days, loading: busy)
                default: SummarySection()
                }
            }
            .padding(.horizontal, 12)
            .animation(.easeInOut(duration: 0.2), value: tab)
        }
        .navBarRoom()
        .refreshable { await refresh() }
        .screenBackground()
        .toolbar(.hidden, for: .navigationBar)
        .onAppear { if let t = nav.trendsTab { tab = t; nav.trendsTab = nil } }
        .onChange(of: nav.trendsTab) { _, t in if let t { tab = t; nav.trendsTab = nil } }
        .task { await refresh() }
        // Compare and Charts load when shown, then poll quietly while their AI summary is being written; switching away
        // (or to another range) cancels the poll
        .task(id: tab == 1 ? "compare" : tab == 2 ? "trends\(days)" : "") {
            switch tab {
            case 1: await fetchThenPoll { try await store.refreshCompare() }
            case 2: await fetchThenPoll { try await store.refreshTrends(days) }
            default: break
            }
        }
    }

    private func fetchThenPoll(_ fetch: @escaping () async throws -> Bool) async {
        busy = true
        var pending = false
        if let m = await store.attempt({ pending = try await fetch() }) { store.toast = m }
        busy = false
        guard pending else { return }
        for attempt in 0..<10 {
            await pollPause(attempt)
            if Task.isCancelled { return }
            if !((try? await fetch()) ?? false) { return }
        }
    }

    private func refresh() async {
        busy = true
        defer { busy = false }
        let m = await store.attempt {
            try await store.refreshInsights()
            try await store.refreshWeekly()
            try await store.refreshFitness()
            try await store.refreshCardio()
            try await store.refreshNumbers()
        }
        if let m { store.toast = m }
        if store.aiEnabled { store.pollCoach() }
        if tab == 2 { _ = await store.attempt { _ = try await store.refreshTrends(days) } }
        if tab == 1 { _ = await store.attempt { _ = try await store.refreshCompare() } }
    }
}

private struct SummarySection: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav

    var body: some View {
        let items = store.insights?.value.insights ?? []
        if let st = store.insights?.value.stats, !st.items.isEmpty { StatsGrid(st: st) }
        // Advice written before "not feeling well" reached the server is held back until it has (it would say train)
        if store.aiEnabled {
            if store.unwellPending {
                CardGroup(title: "AI coach") {
                    GroupRow("Waiting for today's check-in", supporting: "You said you're not feeling well. The coach's advice comes back once the server has your check-in (when you're online). Until then: rest or a short walk.",
                             icon: "brain", shape: .flower)
                }
            } else if let c = store.coach?.value {
                CoachCard(view: c, loading: store.coachLoading, insights: items)
            }
        }
        if let f = store.fitness?.value { FitnessSection(f: f) }
        if let n = store.numbers?.value, !n.items.isEmpty { NumbersCard(n: n) }
        if let c = store.cardio?.value { CardioCard(c: c) { nav.open(.cardio) } }
        if let w = store.weekly?.value { WeeklyCard(w: w) { nav.open(.report(w.id)) } }
        if items.isEmpty { EmptyState(icon: "lightbulb", title: "No insights yet", message: "Pull down to load them after your first sync.") }
        // Hard-running share is in the stats grid and the coach; pace at the same heart rate is charted in Charts
        let patterns = items.filter { $0.verdict == "pattern" && !repeatedElsewhere.contains($0.id) }
        let nulls = items.filter { $0.verdict == "no_clear_pattern" }
        let waiting = items.filter { $0.verdict == "not_enough_data" }
        if !patterns.isEmpty { SectionLabel(text: "Patterns") }
        ForEach(patterns) { i in InsightCard(i: i, emphasised: i.userState == nil) { nav.open(.insight(i.id)) } }
        if !nulls.isEmpty {
            CardGroup(title: "Checked, nothing notable") {
                ForEach(nulls) { i in
                    let (icon, shape) = categoryStyle(i.category)
                    GroupRow(i.headline, icon: icon, shape: shape, accent: i.category) { nav.open(.insight(i.id)) }
                }
            }
        }
        if !waiting.isEmpty {
            CardGroup(title: "Still collecting data") {
                ForEach(waiting) { i in
                    let (icon, shape) = categoryStyle(i.category)
                    GroupRow(i.question, supporting: i.headline, icon: icon, shape: shape, accent: i.category) { nav.open(.insight(i.id)) }
                }
            }
        }
    }
}

/// Each stat's tile colour, by its kind of data: running volume and intensity orange, pace blue, heart rate pink.
private func statTint(_ id: String) -> Tint { id == "pace_s_per_km" ? .blue : id == "avg_hr" ? .pink : .orange }

/// The key numbers of the last 4 weeks, each with its change against the 4 weeks before.
private struct StatsGrid: View {
    var st: Stats
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionLabel(text: "Last 4 weeks")
            ForEach(Array(stride(from: 0, to: st.items.count, by: 2)), id: \.self) { i in
                HStack(alignment: .top, spacing: 10) {
                    ForEach(st.items[i..<min(i + 2, st.items.count)]) { s in
                        Tile(tint: statTint(s.id), spacing: 2) {
                            Text(s.label).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                            Text(s.value).font(Typo.headlineSmall).lineLimit(1).minimumScaleFactor(0.7)
                            if let c = s.change {
                                // Said in words and coloured: green in the better direction (lower pace/HR/hard share), orange the other way
                                let good: Bool? = c == 0 ? nil : s.higherIs == "lower" ? c < 0 : s.higherIs == "higher" ? c > 0 : nil
                                Text(c == 0 ? "Same as before" : (c > 0 ? "+" : "") + "\(c)% vs before" + (good == true ? " · better" : good == false ? " · worse" : ""))
                                    .font(good != nil ? Typo.labelMedium.weight(.semibold) : Typo.labelMedium)
                                    .foregroundStyle(good == true ? Tint.green.ink : good == false ? Tint.orange.ink : Palette.onSurfaceVariant)
                            }
                            Spacer(minLength: 0)
                        }
                        .frame(maxHeight: .infinity)
                    }
                    if i + 1 >= st.items.count { Color.clear.frame(maxWidth: .infinity) }
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

// MARK: AI coach

private func recIcon(_ category: String?) -> String {
    switch category { case "sleep": "moon"; case "recovery": "heart"; case "pacing": "speedometer"; case "habits": "repeat"; default: "dumbbell" }
}

/// AI coach: cross-domain insights and recommendations written from the deterministic data. Every item cites its evidence.
private struct CoachCard: View {
    var view: CoachView
    var loading: Bool
    var insights: [Insight]
    @State private var full = false

    var body: some View {
        let shown: CoachView? = view.status == "ok" ? view : (view.previous?.status == "ok" ? view.previous : nil)
        if view.status == "disabled" {
            EmptyView()
        } else if shown == nil && (view.status == "pending" || loading) {
            Tile {
                HStack(spacing: 10) {
                    ProgressView()
                    Text("Your AI coach is reading your data…").font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
                }
            }
        } else if let s = shown {
            Tile(spacing: 12) {
                HStack(spacing: 10) {
                    Image(systemName: "brain").font(.title3)
                    VStack(alignment: .leading) {
                        Text("AI coach").font(Typo.titleSmall)
                        Text(view.status == "pending" || loading ? "Updating with your latest data…"
                             : s !== view ? "From an earlier analysis · \(Fmt.ago(Fmt.instant(s.generatedAt)))" : "Across running, sleep, recovery and habits")
                            .font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    if view.status == "pending" || loading { ProgressView() }
                }
                if let t = s.tldr { Tldr(text: t) }
                // Compact by default: two findings and the first thing to try; the full analysis on request
                if !full {
                    ForEach(s.insights.prefix(2).map(\.title) + s.recommendations.prefix(1).map { "Try: \($0.title)" }, id: \.self) { Bullet(text: $0) }
                    LinkButton(title: "Show full analysis") { withAnimation { full = true } }
                } else {
                    if let sum = s.summary { Text(sum).font(Typo.bodyLarge) }
                    if !s.insights.isEmpty {
                        Divider()
                        Text("What stands out").font(Typo.titleSmall).foregroundStyle(Palette.primary)
                        ForEach(s.insights, id: \.self) { i in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(i.title).font(Typo.titleMedium)
                                Text(i.text).font(Typo.bodyMedium)
                                if let c = i.confidence { Text("\(Fmt.capitalized(c)) confidence").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant) }
                                EvidenceChips(ids: i.evidenceIds, v: s, insights: insights)
                            }
                        }
                    }
                    if !s.recommendations.isEmpty {
                        Divider()
                        Text("Try this").font(Typo.titleSmall).foregroundStyle(Palette.primary)
                        ForEach(s.recommendations, id: \.self) { r in
                            let a = Tint.accent(r.category)
                            HStack(alignment: .top, spacing: 12) {
                                ShapeBadge(symbol: recIcon(r.category), shape: .cookie6, size: 36, container: a.map { $0.hue.opacity(0.24) } ?? Palette.cardHighest,
                                           content: a?.ink ?? Palette.onSurface)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(r.title).font(Typo.titleMedium)
                                    Text(r.text).font(Typo.bodyMedium)
                                    Text("Why: \(r.why)").font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
                                    EvidenceChips(ids: r.evidenceIds, v: s, insights: insights)
                                }
                            }
                        }
                    }
                }
                Text(["Written by AI (\(s.model ?? "OpenAI")) from your data", s.keySource == "user" ? "your key" : nil, "numbers come from the app",
                      "guidance, not medical advice"].compactMap { $0 }.joined(separator: " · ")).font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
            }
        } else {
            Tile {
                Text("AI coach").font(Typo.titleSmall)
                Text(view.status == "not_configured" ? "AI coach is off: add your own OpenAI key in Me to turn it on."
                     : view.status == "budget_exceeded" ? "AI coach has reached today's limit. The deterministic insights below are complete."
                     : "AI coach couldn't produce a checked analysis this time. The insights below are complete.")
                    .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }
}

/// Chips only for evidence the app can open: runs and deterministic insights.
private struct EvidenceChips: View {
    var ids: [String]
    var v: CoachView
    var insights: [Insight]
    @Environment(Nav.self) private var nav
    var body: some View {
        var seen = Set<String>()
        let chips: [(String, Route)] = ids.filter { seen.insert($0).inserted }.compactMap { id in
            guard let t = v.target(for: id) else { return nil }
            switch t.type {
            case "run": return t.id.map { ("Run" + (t.date.map { " · \(Fmt.shortDate($0))" } ?? ""), .run($0)) }
            case "insight": return insights.first { $0.id == t.id }.map { ($0.question, .insight($0.id)) }
            default: return nil
            }
        }.prefix(3).map { $0 }
        if !chips.isEmpty {
            FlowLayout(spacing: 8, lineSpacing: 8) {
                ForEach(chips, id: \.0) { label, route in
                    Button { nav.open(route) } label: {
                        Text(label).font(Typo.labelLarge).lineLimit(1).padding(.horizontal, 12).frame(minHeight: 32)
                            .background(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(Palette.outline))
                    }
                    .buttonStyle(PressStyle()).foregroundStyle(Palette.onSurface)
                }
            }
        }
    }
}

// MARK: Fitness

/// Garmin's training-status phrases (e.g. "OVERREACHING_3") as Garmin names them in its app.
func trainingStatusLabel(_ phrase: String?) -> String? {
    guard let p = phrase?.components(separatedBy: "_").first else { return nil }
    return p == "NO" ? "No status" : Fmt.capitalized(p.lowercased())
}

/// Garmin's load-balance feedback, e.g. "AEROBIC_LOW_SHORTAGE" -> "Low aerobic shortage".
func loadBalanceLabel(_ phrase: String?) -> String? {
    switch phrase {
    case nil: nil
    case "AEROBIC_LOW_SHORTAGE": "Low aerobic shortage"
    case "AEROBIC_HIGH_SHORTAGE": "High aerobic shortage"
    case "ANAEROBIC_SHORTAGE": "Anaerobic shortage"
    case "AEROBIC_LOW_FOCUS": "Low aerobic focus"
    case "AEROBIC_HIGH_FOCUS": "High aerobic focus"
    case "ANAEROBIC_FOCUS": "Anaerobic focus"
    case "BALANCED": "Balanced"
    default: Fmt.capitalized(phrase!.lowercased().replacingOccurrences(of: "_", with: " "))
    }
}

/// Garmin's view of your training (status, load against its range, race predictions) and your records.
private struct FitnessSection: View {
    var f: Fitness
    @Environment(Nav.self) private var nav
    var body: some View {
        let g = f.garmin
        let recs = ["1k", "5k", "10k", "half"].compactMap { f.records[$0] }.filter { $0.best != nil }
        if g != nil || !recs.isEmpty { SectionLabel(text: "Fitness") }
        if let g {
            Tile(tint: .blue, spacing: 14) {
                HStack(spacing: 10) {
                    Image(systemName: "waveform.path.ecg").foregroundStyle(Tint.blue.ink)
                    VStack(alignment: .leading) {
                        Text("Garmin training status").font(Typo.titleSmall)
                        Text("Calculated by Garmin").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
                    }
                }
                // VO2 max lives on Today and in Compare; this card is Garmin's view of your training
                if let st = g.trainingStatus, let label = trainingStatusLabel(st.phrase) {
                    let warn = ["Overreaching", "Strained", "Unproductive", "Detraining"].contains(label)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Training status").font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
                        HStack(spacing: 10) {
                            Text(label).font(Typo.titleLarge).foregroundStyle(warn ? Tint.orange.ink : Palette.onSurface)
                                .padding(.horizontal, 12).padding(.vertical, 6)
                                .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(warn ? Tint.orange.hue.opacity(0.28) : Palette.card.opacity(0.75)))
                            if let s = st.since { Text("since \(Fmt.shortDate(s))").font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant) }
                        }
                    }
                }
                if let st = g.trainingStatus, let acute = st.acuteLoad, let lo = st.chronicMin, let hi = st.chronicMax { LoadBar(acute: acute, lo: lo, hi: hi) }
                if let r = g.racePredictions {
                    Text("Garmin race predictions").font(Typo.titleSmall)
                    HStack {
                        ForEach([("5K", r.k5), ("10K", r.k10), ("Half", r.half), ("Marathon", r.marathon)], id: \.0) { l, v in
                            VStack(alignment: .leading) {
                                Text(l).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                                Text(Fmt.clock(v)).font(Typo.titleLarge).lineLimit(1).minimumScaleFactor(0.7)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                let extra = [loadBalanceLabel(g.loadBalance?.phrase).map { "Load balance: \($0)" }, g.heatAcclimationPct.map { "Heat acclimation: \(Int($0))%" }].compactMap { $0 }
                if !extra.isEmpty { Text(extra.joined(separator: " · ") + " (Garmin)").font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
            }
        }
        if !recs.isEmpty {
            CardGroup(tint: .amber) {
                GroupCustom {
                    Text("Personal records").font(Typo.titleSmall)
                    Text("Fastest segment inside any synced run").font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                }
                ForEach(recs, id: \.label) { r in
                    let b = r.best!
                    GroupRow("\(r.label): \(Fmt.clock(b.elapsedS))", supporting: "Set \(Fmt.shortDate(b.date)) · improved \(r.progression.count - 1) times",
                             icon: "trophy", shape: .sunny) { nav.open(.run(b.sourceId)) }
                }
            }
        }
    }
}

/// Garmin's acute load against Garmin's own optimal range for you. The ratio between them is not shown.
private struct LoadBar: View {
    var acute: Double
    var lo: Double
    var hi: Double
    var body: some View {
        let top = max(acute, hi) * 1.15
        VStack(alignment: .leading, spacing: 4) {
            Text("Acute load \(Int(acute)) · Garmin's optimal range \(Int(lo))–\(Int(hi))").font(Typo.titleSmall)
            Canvas { ctx, size in
                func x(_ v: Double) -> CGFloat { v / top * size.width }
                ctx.fill(Path(roundedRect: CGRect(origin: .zero, size: size), cornerRadius: 9), with: .color(Palette.onSurface.opacity(0.08)))
                ctx.fill(Path(roundedRect: CGRect(x: x(lo), y: 0, width: x(hi) - x(lo), height: size.height), cornerRadius: 9), with: .color(Tint.blue.ink.opacity(0.35)))
                let r = size.height * 0.7
                ctx.fill(Path(ellipseIn: CGRect(x: x(acute) - r, y: size.height / 2 - r, width: 2 * r, height: 2 * r)), with: .color(acute > hi ? DataColors.attention : Tint.blue.ink))
            }
            .frame(height: 18)
            .accessibilityLabel("Acute load \(Int(acute)), Garmin optimal range \(Int(lo)) to \(Int(hi))")
            Text(acute > hi ? "Above Garmin's optimal range" : acute < lo ? "Below Garmin's optimal range" : "Inside Garmin's optimal range")
                .font(Typo.labelMedium).foregroundStyle(acute > hi ? DataColors.attention : Palette.onSurfaceVariant)
        }
    }
}

// MARK: Numbers, cardio, weekly, insights

private func numberIcon(_ id: String) -> (String, BadgeShape) {
    switch id {
    case "threshold": ("speedometer", .cookie9)
    case "form": ("bolt", .sunny)
    case "predictions": ("timer", .cookie4)
    case "recovery": ("heart", .flower)
    case "climbing": ("mountain.2", .burst)
    default: ("chart.line.uptrend.xyaxis", .circle)
    }
}

/// One row per training number: its value and what changed. Each opens its history.
private struct NumbersCard: View {
    var n: TrainingNumbers
    @Environment(Nav.self) private var nav
    var body: some View {
        CardGroup(title: "Training numbers") {
            // Recovery and climbing appear once there's something to show (sessions with repeats, runs with real climbs)
            ForEach(n.items.filter { $0.status == "ok" || !["recovery", "climbing"].contains($0.id) }) { it in
                let (icon, shape) = numberIcon(it.id)
                GroupRow(it.title, supporting: [it.value, it.headline?.nilIfEmpty].compactMap { $0 }.joined(separator: " · "), icon: icon, shape: shape) {
                    nav.open(.number(it.id))
                }
            }
        }
    }
}

struct NumberPage: View {
    var id: String
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    var body: some View {
        let item = store.numbers?.value.items.first { $0.id == id }
        DetailPage(title: item?.title ?? "Training number") {
            if let item {
                VStack(alignment: .leading, spacing: 6) {
                    if let v = item.value { Text(v).font(Typo.displaySmall) }
                    if let h = item.headline?.nilIfEmpty { Text(h).font(Typo.titleMedium) }
                    if let d = item.detail?.nilIfEmpty { Text(d).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
                }
                .padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 4)
                if item.series.count >= 2 {
                    Tile {
                        Text("Over time" + (item.lowerIsBetter ? " · better is up" : "")).font(Typo.titleSmall)
                        // Faster paces and times are drawn upward; the load balance has no better or worse direction
                        Sparkline(values: item.series.map { item.lowerIsBetter ? -$0.v : $0.v },
                                  description: "\(item.title) from \(item.series.first!.date) to \(item.series.last!.date)").frame(height: 80)
                        Text("\(Fmt.shortDate(item.series.first!.date)) – \(Fmt.shortDate(item.series.last!.date))").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
                    }
                    CardGroup {
                        ForEach(Array(item.series.suffix(6).reversed()), id: \.self) { p in
                            GroupRow(p.label ?? Fmt.f1(p.v), supporting: Fmt.shortDate(p.date), action: p.sourceId.map { sid in { nav.open(.run(sid)) } })
                        }
                    }
                }
                Footnote(text: item.basis)
            }
        }
    }
}

private func cardioShort(_ p: CardioPart) -> String {
    switch p.id { case "runs": "Your runs"; case "garmin": p.maker ?? "Garmin"; case "questionnaire": "Questionnaire"; case "hunt": "HUNT"; default: p.title }
}

/// One line per piece of evidence, in the Summary tab; the detail page has the rest.
private struct CardioCard: View {
    var c: Cardio
    var onOpen: () -> Void
    var body: some View {
        let parts = [c.runs, c.garmin, c.hunt, c.questionnaire].compactMap { $0 }.filter { $0.value != nil }
        Tile(tint: .teal, onTap: onOpen) {
            HStack(spacing: 10) {
                Image(systemName: "waveform.path.ecg").foregroundStyle(Tint.teal.ink)
                Text("Cardio fitness (experimental)").font(Typo.titleSmall).frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(Palette.onSurfaceVariant)
            }
            Text(parts.isEmpty ? "Not enough evidence yet" : parts.map { "\(cardioShort($0)) \(Int($0.value!))" }.joined(separator: " · ")).font(Typo.titleMedium)
            Text([c.runs.comparison?.headline ?? c.garmin.comparison?.headline, c.performance.value.map { "Running performance: VDOT \(Int($0))" },
                  "VO₂ max estimates side by side, each with its method"].compactMap { $0 }.joined(separator: "\n"))
                .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
        }
    }
}

struct WeeklyCard: View {
    var w: WeeklyReport
    var onOpen: () -> Void
    var body: some View {
        Tile(tint: .purple, onTap: onOpen) {
            Text("Weekly review · \(Fmt.shortDate(w.weekStart)) – \(Fmt.shortDate(w.weekEnd))").font(Typo.titleSmall)
            Text(w.headline).font(Typo.titleLarge)
            HStack {
                Text("Next week's focus and details").font(Typo.labelLarge).foregroundStyle(Tint.purple.ink).frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").foregroundStyle(Tint.purple.ink)
            }
        }
    }
}

struct InsightCard: View {
    var i: Insight
    var emphasised: Bool
    var onMethod: () -> Void
    var body: some View {
        let (icon, _) = categoryStyle(i.category)
        let accent = emphasised ? Tint.accent(i.category) : nil
        Tile(spacing: 10) {
            HStack(spacing: 8) {
                Label(Fmt.capitalized(i.category), systemImage: icon).font(Typo.labelMedium)
                    .foregroundStyle(accent?.ink ?? Palette.onSurface)
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(accent.map { $0.hue.opacity(0.24) } ?? Palette.cardHighest))
                if i.verdict == "pattern", let n = i.novelty, ["new", "changed"].contains(n) {
                    Text(n == "new" ? "New" : "Changed").font(Typo.labelMedium).padding(.horizontal, 10).padding(.vertical, 5)
                        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Palette.cardHighest))
                }
            }
            Text(i.question).font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
            Text(i.headline).font(emphasised ? Typo.titleLarge : Typo.titleMedium)
            if let c = i.chart { InsightChart(chart: c) }
            HStack {
                Text([i.sampleSize.map { "\($0) runs" }, i.confidence == "consistent" ? "held on newer data" : i.confidence == "emerging" ? "emerging" : nil]
                    .compactMap { $0 }.joined(separator: " · ")).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                    .frame(maxWidth: .infinity, alignment: .leading)
                LinkButton(title: "Details", action: onMethod)
            }
        }
    }
}

struct InsightPage: View {
    var id: String
    @Environment(Store.self) private var store
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        let i = store.insights?.value.insights.first { $0.id == id } ?? store.fitness?.value.easyPace.flatMap { $0.id == id ? $0 : nil }
        DetailPage(title: i?.verdict == "pattern" ? "Pattern" : "Details") {
            if let i {
                VStack(alignment: .leading, spacing: 6) {
                    Text(i.question).font(Typo.headlineSmall)
                    Text(i.headline).font(Typo.bodyLarge)
                    if !i.detail.isEmpty { Text(i.detail).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
                }
                .padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 4)
                if let p = i.practical {
                    Tile(tint: .green) { Text("Try this").font(Typo.titleSmall); Text(p).font(Typo.bodyMedium) }
                }
                CardGroup(title: "Method") { GroupCustom { Text(i.method).font(Typo.bodyMedium) } }
                if !i.confounders.isEmpty { CardGroup(title: "What else could explain it") { ForEach(i.confounders, id: \.self) { GroupRow($0) } } }
                // Marking a pattern lives here, not on the card
                if i.verdict == "pattern" {
                    HStack(spacing: 8) {
                        if i.userState == nil {
                            OutlineButton(title: "I'm working on it") { store.act { try await store.setInsightState(i.id, "working_on") } }
                            OutlineButton(title: "Dismiss") { store.act { try await store.setInsightState(i.id, "dismissed") }; dismiss() }
                        } else {
                            Text(i.userState == "working_on" ? "You're working on this" : "Dismissed").font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
                                .padding(.leading, 12).frame(maxWidth: .infinity, alignment: .leading)
                            OutlineButton(title: "Undo") { store.act { try await store.setInsightState(i.id, nil) } }.frame(width: 120)
                        }
                    }
                }
                Text([i.sampleSize.map { "Sample size \($0)" }, i.evidence.flatMap { $0.dateRange.count == 2 ? "\($0.dateRange[0]) – \($0.dateRange[1])" : nil },
                      i.algorithmVersion, "Associations only, not causes or medical advice"].compactMap { $0 }.joined(separator: " · "))
                    .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).padding(.horizontal, 8)
            }
        }
    }
}

/// Small purpose-built visuals for insight types. Every value is also stated in the card text. Chart data is read
/// defensively: a missing or reshaped field draws less (or nothing), never crashes the screen.
private struct InsightChart: View {
    var chart: JSONValue
    var body: some View {
        switch chart["type"]?.string {
        case "stacked_share": stacked
        case "pace_trend": paceTrend
        case "weekly_bars": weeklyBars
        default: EmptyView()
        }
    }

    @ViewBuilder private var stacked: some View {
        let colors = [Palette.primary.opacity(0.25), Palette.primary.opacity(0.45), Palette.primary.opacity(0.65), Tint.purple.ink, Palette.error]
        let labels = Array((chart["labels"]?.array ?? []).map { $0.string ?? "" }.prefix(colors.count))
        let values = Array((chart["values"]?.array ?? []).map { $0.double ?? 0 }.prefix(colors.count))
        if !values.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Canvas { ctx, size in
                    var x: CGFloat = 0
                    for (k, v) in values.enumerated() {
                        let w = v * size.width
                        if w > 0 { ctx.fill(Path(roundedRect: CGRect(x: x, y: 0, width: max(1, w - 3), height: size.height), cornerRadius: 5), with: .color(colors[k])) }
                        x += w
                    }
                }
                .frame(height: 28)
                .accessibilityLabel(zip(labels, values).map { "\($0) \(Int($1 * 100))%" }.joined(separator: ", "))
                FlowLayout(spacing: 12, lineSpacing: 4) {
                    ForEach(Array(zip(labels, values).enumerated()), id: \.offset) { k, lv in
                        HStack(spacing: 4) {
                            Circle().fill(colors[k]).frame(width: 10, height: 10)
                            Text("\(lv.0) \(Int(lv.1 * 100))%").font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder private var paceTrend: some View {
        let series = (chart["series"]?.array ?? []).map { s in (s["points"]?.array ?? []).compactMap { $0["paceSPerKm"]?.double ?? $0["pace_s_per_km"]?.double } }.filter { !$0.isEmpty }
        let all = series.flatMap { $0 }
        if all.count >= 2 {
            let lo = all.min()! - 5, hi = all.max()! + 5
            let palette = [Palette.primary, Tint.purple.ink, Tint.blue.ink]
            VStack(alignment: .leading, spacing: 2) {
                Text(Fmt.pace(lo + 5, .metric) + " (faster)").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
                Canvas { ctx, size in
                    let total = series.reduce(0) { $0 + $1.count } + series.count - 1
                    var idx = 0
                    for (k, pts) in series.enumerated() {
                        var path = Path()
                        for (j, p) in pts.enumerated() {
                            let x = CGFloat(idx + j) / CGFloat(max(1, total - 1)) * size.width
                            let y = (p - lo) / (hi - lo) * size.height  // lower pace (faster) at top
                            j == 0 ? path.move(to: CGPoint(x: x, y: y)) : path.addLine(to: CGPoint(x: x, y: y))
                            ctx.fill(Path(ellipseIn: CGRect(x: x - 4, y: y - 4, width: 8, height: 8)), with: .color(palette[k % 3]))
                        }
                        ctx.stroke(path, with: .color(palette[k % 3].opacity(0.6)), lineWidth: 2)
                        idx += pts.count + 1  // gap between watches: never joined
                    }
                }
                .frame(height: 96)
                .accessibilityLabel("Pace at the same heart rate over time, one line per watch")
                Text(Fmt.pace(hi - 5, .metric) + " (slower) · each colour is a different watch").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }

    @ViewBuilder private var weeklyBars: some View {
        let pts = (chart["points"]?.array ?? []).map { $0["movingS"]?.double ?? $0["moving_s"]?.double ?? 0 }
        if !pts.isEmpty {
            let mx = max(1, pts.max()!)
            Canvas { ctx, size in
                let w = size.width / CGFloat(pts.count)
                for (k, v) in pts.enumerated() {
                    let h = max(2, v / mx * size.height)
                    ctx.fill(Path(roundedRect: CGRect(x: CGFloat(k) * w + w * 0.15, y: size.height - h, width: w * 0.7, height: h), cornerRadius: 4), with: .color(Palette.primary))
                }
            }
            .frame(height: 64)
            .accessibilityLabel("Weekly running time, last 8 weeks")
        }
    }
}

/// Today's AI summary of a screen (Compare, Trends). Hidden when AI is off; earlier summaries are labelled as such.
struct ScreenSummaryCard: View {
    var s: ScreenSummary?
    @Environment(Store.self) private var store
    @State private var more = false
    var body: some View {
        if let s, !["disabled", "not_configured"].contains(s.status), store.aiEnabled {
            let shown: ScreenSummary? = s.status == "ok" ? s : (s.previous?.status == "ok" ? s.previous : nil)
            if let shown {
                Tile {
                    HStack(spacing: 10) {
                        Image(systemName: "sparkles")
                        VStack(alignment: .leading) {
                            Text("Today's summary · AI").font(Typo.titleSmall)
                            Text(shown !== s ? "From \(shown.localDate.map { Fmt.shortDate($0) } ?? "earlier") · updating…" : "Written by AI from this screen · numbers come from the app")
                                .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        if s.status == "pending" { ProgressView() }
                    }
                    // The takeaway on its own; the rest on tap
                    Text((more ? shown.sentences : Array(shown.sentences.prefix(1))).map(\.text).joined(separator: " ")).font(Typo.bodyLarge)
                    if shown.sentences.count > 1 { LinkButton(title: more ? "Less" : "More") { withAnimation { more.toggle() } } }
                }
            } else if s.status == "pending" {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("Writing today's AI summary…").font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
                }
                .padding(.horizontal, 4)
            }
        }
    }
}

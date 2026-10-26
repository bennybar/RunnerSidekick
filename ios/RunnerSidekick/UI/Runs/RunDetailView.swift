import SwiftUI

// Garmin's training effect is shown with a verdict under "How it went", so it isn't repeated here
private let garminLabels = ["activityTrainingLoad": "Training load", "calories": "Calories (kcal)"]

/// Garmin's numbers as people read them: whole numbers where decimals mean nothing.
private func garminValue(_ key: String, _ v: JSONValue) -> String {
    if ["activityTrainingLoad", "calories"].contains(key), let d = v.double { return "\(Int(d.rounded()))" }
    return v.string ?? ""
}

struct RunDetailView: View {
    var id: String
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @Environment(\.dismiss) private var dismiss
    @State private var busy = false
    @State private var evidence: Finding?
    @State private var confirmDelete = false
    @State private var share: URL?
    @State private var aiAsked = 0

    var body: some View {
        let detail = store.detail(id)?.value
        let r = detail?.report
        let units = store.units
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    if let r {
                        RunTitle(r: r)
                        RunHero(r: r, units: units)
                        if let v = r.verdict { VerdictCard(v: v) }
                        // Shown also when it couldn't be measured, saying why, instead of nothing
                        if r.decoupling.decouplingPct != nil || !r.decoupling.reasons.isEmpty { DecouplingCard(dc: r.decoupling) }
                        // Shown at the top once asked for (or already written); the button lives in the top bar
                        if store.aiEnabled, let ai = store.runAi(id)?.value, ai.status != "none" || ai.previous != nil {
                            RunAiCard(v: ai) { askAi() }.id("ai")
                        }
                        IntentPicker(intent: r.intent) { i in store.act { try await store.setIntent(id, i) } }
                        // The repeat route this run belongs to, recognised from its shape; opens how the route has gone
                        if let rt = detail?.route {
                            CardGroup(title: "Route", tint: .blue) {
                                GroupRow(routeTitle(rt.name, rt.distanceKm, rt.loop, rt.runs), supporting: rt.progress ?? "Recognised from its shape") {
                                    nav.open(.route(rt.id, current: id))
                                }
                            }
                        }
                        if !r.checks.isEmpty {
                            CardGroup(title: "How it went") {
                                ForEach(r.checks) { c in GroupRow(headline: c.title, supporting: c.say) { VerdictChip(verdict: c.verdict) } }
                            }
                        } else if !r.story.isEmpty {
                            CardGroup(title: "How the run went") { GroupCustom { ForEach(r.story, id: \.self) { Bullet(text: $0).font(Typo.bodyLarge) } } }
                        }
                        let efforts = ["1k", "5k", "10k", "half"].compactMap { r.bestEfforts[$0] }
                        if !efforts.isEmpty {
                            CardGroup(title: "Best efforts in this run") {
                                ForEach(efforts, id: \.label) { e in
                                    GroupRow(headline: "\(e.label): \(Fmt.duration(e.elapsedS))",
                                             supporting: Fmt.pace(e.paceSPerKm, units) + (e.previousBestS.map { " · your previous best \(Fmt.duration($0))" } ?? " · first one recorded")) {
                                        if e.isBest { TagChip(text: "New best", container: Tint.amber.hue.opacity(0.22), content: Tint.amber.ink) }
                                    }
                                }
                            }
                        }
                        if let c = detail?.chart {
                            SectionLabel(text: "Pace and heart rate")
                            Tile(spacing: 20) {
                                SeriesChart(title: "Pace (moving)", t: c.t, values: c.speed.map { $0.flatMap { $0 > 0 ? 1000 / $0 : nil } }, color: DataColors.pace,
                                            formatY: { Fmt.pace($0, units) }, invert: true, description: "Pace over time. Gaps are stops or missing data.")
                                SeriesChart(title: "Heart rate (bpm)", t: c.t, values: c.hr, color: DataColors.heartRate, formatY: { "\(Int($0.rounded()))" },
                                            description: "Heart rate over time. Gaps are missing sensor data, not zero.")
                                Text("Gaps are stops or missing data. They aren't filled in.").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
                            }
                        }
                        Tile(tint: .green, spacing: 4) {
                            Text("Next focus").font(Typo.titleSmall)
                            Text(r.nextFocus).font(Typo.bodyLarge)
                        }
                        // Only findings that say something; checks that couldn't run aren't listed
                        if !r.findings.isEmpty {
                            CardGroup(title: "Analysis") { ForEach(r.findings) { f in GroupRow(f.title, supporting: f.statement) { evidence = f } } }
                        }
                        if !r.splits.isEmpty { Splits(r: r, units: units) }
                        if let comp = r.comparable, !comp.runs.isEmpty {
                            CardGroup(title: "Similar runs (\(comp.n)) · distance ±20%, similar climbing, steady") {
                                GroupRow("This run", supporting: "\(Fmt.pace(r.paceMovingSPerKm, units)) · \(r.activity.avgHr.map { "\(Int($0.rounded())) bpm" } ?? "no HR")")
                                ForEach(comp.runs) { c in
                                    GroupRow("\(Fmt.shortDate(c.localDate)) · \(Fmt.distance(c.distanceM, units))",
                                             supporting: "\(Fmt.pace(c.paceSPerKm, units)) · \(c.avgHr.map { "\(Int($0.rounded())) bpm" } ?? "no HR")") { nav.open(.run(c.sourceId)) }
                                }
                            }
                        }
                        WatchNumbers(r: r) { held in store.act { try await store.holdOutVo2(id, held) } }
                    } else {
                        EmptyState(icon: "figure.run", title: busy ? "Loading run" : "Run not cached",
                                   message: busy ? "Fetching analysis…" : "Connect to the backend to load this run.")
                    }
                }
                .padding(.horizontal, 12).padding(.bottom, 32)
            }
            .onChange(of: aiAsked) { _, _ in withAnimation { proxy.scrollTo("ai", anchor: .top) } }
        }
        .refreshable { await refresh() }
        .screenBackground()
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { toolbar(r) }
        .task { await refresh() }
        .sheet(item: $evidence) { EvidenceSheet(finding: $0) }
        .sheet(item: $share) { ShareSheet(items: [$0]) }
        .confirmationDialog("Delete this run?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) {
                Task {
                    if let m = await store.attempt({ try await store.deleteRun(id) }) { store.toast = m } else { dismiss() }
                }
            }
        } message: {
            Text("It leaves your runs, records, trends and reports, and won't come back with the next sync or upload. Use it for test recordings and mistakes.")
        }
    }

    @ToolbarContentBuilder private func toolbar(_ r: PostRunReport?) -> some ToolbarContent {
        ToolbarItemGroup(placement: .topBarTrailing) {
            if r?.synthetic == true { DemoBadge() }
            if let r {
                // AI input next to the title: one tap asks for it, then the page scrolls to its card at the top
                if store.aiEnabled {
                    let v = store.runAi(id)?.value
                    // Any finished AI input for this run counts, unless the run's type changed since (then it can be rewritten)
                    let st = v.map { v in v.status != "ok" && v.previous?.status == "ok" && !v.stale ? "ok" : v.status }
                    Button { askAi(); aiAsked += 1 } label: {
                        Label(st == "ok" ? "AI input ready" : v?.stale == true ? "Update AI input" : "Get AI input",
                              systemImage: st == "ok" ? "checkmark.circle" : st == "pending" ? "hourglass" : "sparkles")
                    }
                    .disabled(["ok", "pending", "disabled", "not_configured", "budget_exceeded"].contains(st ?? ""))
                }
                Menu {
                    // The whole run (analysis, splits, minute-by-minute data, AI input) as one Markdown file
                    Button { export(r) } label: { Label("Export run (Markdown)", systemImage: "square.and.arrow.up") }
                    if !r.synthetic { Button(role: .destructive) { confirmDelete = true } label: { Label("Delete run", systemImage: "trash") } }
                } label: { Image(systemName: "ellipsis.circle") }
            }
        }
    }

    private func refresh() async {
        busy = true
        defer { busy = false }
        if let m = await store.attempt({ try await store.refreshActivity(id) }) { store.toast = m }
        _ = await store.attempt { try await store.refreshRunAi(id) }
    }

    private func askAi() { store.act { try await store.askAi(id) } }

    private func export(_ r: PostRunReport) {
        Task {
            var text = ""
            if let m = await store.attempt({ text = try await store.exportRun(id) }) { store.toast = m; return }
            let tz = TimeZone(secondsFromGMT: r.activity.utcOffsetS ?? 0) ?? .current
            let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd-HHmmss"; f.timeZone = tz; f.locale = Locale(identifier: "en_US_POSIX")
            let name = (Fmt.instant(r.activity.startUtc).map { f.string(from: $0) } ?? r.activity.localDate) + "-running.md"
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
            try? text.write(to: url, atomically: true, encoding: .utf8)
            share = url
        }
    }
}

extension URL: @retroactive Identifiable { public var id: String { absoluteString } }

/// The system share sheet (save to Files, AirDrop, a chat...).
struct ShareSheet: UIViewControllerRepresentable {
    var items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: items, applicationActivities: nil) }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}

/// The sensor's connection log in words: each dropout with when it came back, or that it stayed connected.
private func sensorLog(_ s: HrSensor) -> String {
    guard s.logged else { return "" }
    let drops = s.events.filter { $0.event.localizedCaseInsensitiveContains("disconnect") }
    if drops.isEmpty { return " · connected the whole run" }
    return " · " + drops.map { d in
        let back = s.events.first { $0.atS > d.atS && $0.event.localizedCaseInsensitiveContains("connected") && !$0.event.localizedCaseInsensitiveContains("disconnect") }
        return "dropped out at \(Fmt.duration(d.atS))" + (back.map { ", back at \(Fmt.duration($0.atS))" } ?? " and didn't come back")
    }.joined(separator: "; ")
}

/// The page's big title: the run's day ("Sunday run"), then the date, start time and the run's name.
private struct RunTitle: View {
    var r: PostRunReport
    var body: some View {
        let a = r.activity
        VStack(alignment: .leading, spacing: 4) {
            Text("\(Fmt.weekdayName(a.localDate)) run").font(Typo.headlineLarge).accessibilityAddTraits(.isHeader)
            Text([Fmt.dayMonth(a.localDate), Fmt.activityTime(a.startUtc, a.utcOffsetS).components(separatedBy: " · ").last, displayName(a.name),
                  r.recordedWith.map { "recorded with \($0)" }].compactMap { $0 }.joined(separator: " · "))
                .font(Typo.bodyLarge).foregroundStyle(Palette.onSurfaceVariant)
            // Where the heart rate came from, when it wasn't the watch's own sensor
            if let s = r.hrSensor {
                Text("Heart rate from \(s.name ?? "an external sensor")" + (s.name != nil ? " (external sensor)" : "") + sensorLog(s))
                    .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
        .padding(.horizontal, 12).padding(.bottom, 6)
        .accessibilityElement(children: .combine)
    }
}

/// The run's header, in the orange hero tile: distance with the moving pace beside it, six numbers, then what the numbers
/// leave out (stops, the watch's VO2 max, doubtful heart rate).
private struct RunHero: View {
    var r: PostRunReport
    var units: Units
    var body: some View {
        let a = r.activity
        let d = Fmt.distance(a.distanceM, units).split(separator: " ")
        let te = r.garminMetrics["aerobicTrainingEffect"]?.double
        // The watch's VO2 max on the day of the run; the run's own estimate as a fallback
        let vo2 = r.garminVo2maxDay.map { Fmt.f1($0.value) } ?? r.garminMetrics["vO2MaxValue"]?.string
        let ours = r.vo2Ours?.value
        let tiles: [(String, String)] = [
            ("Avg heart rate", a.avgHr.map { "\(Int($0.rounded()))" } ?? "—"),
            // Garmin's Training Effect; a watch without it shows the app's own training load for the run
            te.map { ("Aerobic TE", Fmt.f1($0)) } ?? ("Training load", r.load.map(String.init) ?? "—"),
            // Garmin's training readiness on the morning of the run; without it, the run's highest heart rate
            r.garminReadinessDay.map { ("Garmin readiness", "\(Int($0.value.rounded()))") } ?? ("Max heart rate", a.maxHr.map { "\(Int($0.rounded()))" } ?? "—"),
            ("Moving time", Fmt.duration(a.movingS)),
            ("Climb", "+" + Fmt.elevation(a.elevationGainM, units)),
            // Ours from this run, big; the watch's in the footnote
            ours.map { ("VO₂ Sidekick", Fmt.f0($0)) } ?? ("VO₂ (\(r.watchName))", vo2 ?? "—"),
        ]
        Tile(tint: .orange, spacing: 14) {
            HStack {
                BigValue(value: String(d.first ?? ""), unit: String(d.last ?? "")).frame(maxWidth: .infinity, alignment: .leading)
                Text("\(Fmt.pace(r.paceMovingSPerKm, units)) moving").font(Typo.labelLarge).padding(.horizontal, 12).padding(.vertical, 6)
                    .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Palette.card.opacity(0.75)))
            }
            ForEach([0, 3], id: \.self) { i in
                HStack(alignment: .top, spacing: 8) {
                    ForEach(i..<i + 3, id: \.self) { k in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(tiles[k].0).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant).lineLimit(1)
                            Text(tiles[k].1).font(Typo.titleLarge).lineLimit(1).minimumScaleFactor(0.7)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityElement(children: .combine)
                    }
                }
            }
            let parts = [(a.elapsedS ?? 0) - (a.movingS ?? 0) >= 30 ? "Elapsed \(Fmt.duration(a.elapsedS)) with stops" : nil,
                         ours != nil ? vo2.map { "\(r.watchName)'s VO₂ max \($0)" } : vo2 != nil ? "Sidekick VO₂ max: n/a" : nil].compactMap { $0 }.joined(separator: " · ")
            let hrq = r.hrQuality.flatMap { q in q.grade == "good" ? nil : " The heart-rate recording looked \(q.grade) in \(q.stretches.count) \(q.stretches.count == 1 ? "stretch" : "stretches") ("
                + q.stretches.prefix(3).map { "\(Fmt.duration($0.startS))–\(Fmt.duration($0.endS))" }.joined(separator: ", ") + "), so read heart-rate numbers loosely." } ?? ""
            Text((parts.isEmpty ? "" : parts + ". ") + "Pace uses moving time (stops excluded). Elapsed includes stops." + hrq)
                .font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
        }
    }
}

/// How the run went against what it was meant to be: a verdict for training runs, the age grade for a race.
private struct VerdictCard: View {
    var v: RunVerdict
    var body: some View {
        // On target in green; off it (harder, easier, cut short) in pink; the label says which in words
        let tint: Tint = v.verdict == "on_target" ? .green : ["harder", "easier", "shortened"].contains(v.verdict) ? .pink : .neutral
        Tile(tint: tint, spacing: 6) {
            if let ag = v.ageGrade {
                Text(String(format: "Age grade %.1f%%", ag.pct)).font(Typo.headlineMedium)
                Text(Fmt.capitalized(ag.gradeClass)).font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
            } else {
                Text(v.label).font(Typo.titleMedium)
            }
            Text(v.say).font(Typo.bodyMedium)
            let meta = [v.judgedAs.map { k in "Judged as \(k.replacingOccurrences(of: "_", with: " "))" + (v.basis.map { " from \($0)" } ?? "") },
                        v.verdict == "not_enough_data" && v.judgedAs == nil ? "Set the run type below" : nil, v.hrNote, v.note].compactMap { $0 }
            if !meta.isEmpty { Text(meta.joined(separator: " · ")).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
        }
    }
}

/// Aerobic decoupling for every run, pace:HR and power:HR (first half against second), in a blue tile.
private struct DecouplingCard: View {
    var dc: Decoupling
    @State private var info = false
    var body: some View {
        Tile(tint: .blue, spacing: 12) {
            HStack {
                Text("Aerobic decoupling").font(Typo.titleSmall).frame(maxWidth: .infinity, alignment: .leading)
                Button { info = true } label: { Image(systemName: "info.circle") }.foregroundStyle(Palette.onSurface)
                    .accessibilityLabel("About aerobic decoupling")
                    .popover(isPresented: $info) {
                        Text("How much heart rate rose against pace (or power) from the first half to the second, after a 10-minute warm-up. Lower is better; under 5% means the effort held steady. On hilly runs, power:HR is the better read.")
                            .font(Typo.bodyMedium).padding().frame(width: 300).presentationCompactAdaptation(.popover)
                    }
            }
            if dc.decouplingPct == nil {
                let why = dc.reasons.first ?? ""
                let m = why.firstMatch(of: /eligible segment (\d+) min < (\d+) min/)
                Text("Not measured on this run: " + (m.map { "it needs \($0.2) minutes of running after the warm-up, and this run had \($0.1). On shorter runs a few beats of noise would swing it too much." }
                    ?? (why.localizedCaseInsensitiveContains("heart") ? "too little heart rate was recorded." : why.isEmpty ? "not enough data." : why)))
                    .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
            } else {
                HStack(alignment: .top, spacing: 10) {
                    // power:HR only when the watch records running power
                    ForEach([(dc.decouplingPct, "Pace : heart rate")] + (dc.powerDecouplingPct.map { [($0 as Double?, "Power : heart rate")] } ?? []), id: \.1) { v, l in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(l).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                            Text(v.map { String(format: "%.1f%%", $0) } ?? "—").font(Typo.headlineMedium)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                Text(!dc.eligible ? "Indicative here: " + (dc.reasons.contains { $0.hasPrefix("run is not steady") } ? "the pace wasn't steady" : dc.reasons.first ?? "not a steady run") + "."
                     : "Under 5% means heart rate kept pace with the effort. Lower is better" + (dc.powerDecouplingPct != nil ? "; on hills, power:HR is the better read." : ".") + (dc.hrCaveat.map { " \($0)" } ?? ""))
                    .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }
}

/// AI input on this run, written only when asked. Every number comes from the analysis; every point cites it.
private struct RunAiCard: View {
    var v: RunAi
    var onAsk: () -> Void
    @State private var more = false
    var body: some View {
        let shown: RunAi? = v.status == "ok" ? v : (v.previous?.status == "ok" ? v.previous : nil)
        Tile(spacing: 10) {
            HStack {
                VStack(alignment: .leading) {
                    Text("AI input on this run").font(Typo.titleSmall)
                    Text("Coaching from this run's analysis, its week and your plan").font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if v.status == "pending" { ProgressView() }
            }
            if let s = shown {
                if let t = s.tldr { Tldr(text: t) }
                // Older input has no one-liner: its summary is shown as plain text instead
                if more || s.tldr == nil, let sum = s.summary { Text(sum).font(Typo.bodyMedium) }
                if more && !s.wentWell.isEmpty { Text("Went well").font(Typo.titleSmall); ForEach(s.wentWell, id: \.self) { Bullet(text: $0.text) } }
                if more && !s.toWorkOn.isEmpty { Text("To work on").font(Typo.titleSmall); ForEach(s.toWorkOn, id: \.self) { Bullet(text: $0.text) } }
                if let n = s.nextTime {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Next time · " + (n.direction == "easier" ? "easier" : n.direction == "harder" ? "harder" : "similar effort")).font(Typo.labelLarge)
                        Text(n.text).font(Typo.bodyMedium)
                    }
                    .padding(14).frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 20, style: .continuous).fill(Palette.cardHighest))
                }
                if !more && (!s.wentWell.isEmpty || !s.toWorkOn.isEmpty) { LinkButton(title: "What went well, what to work on") { withAnimation { more = true } } }
                Text((s.trigger == "auto" ? "Written automatically for this new run · " : "") + "AI (\(s.model ?? "OpenAI"))" + (s.keySource == "user" ? " with your key" : "")
                     + " · numbers come from the app · guidance, not medical advice").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
            } else {
                switch v.status {
                case "none": PillButton(title: "Get AI input", icon: "sparkles", filled: false, action: onAsk)
                case "pending": Text("Reading this run…").font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                case "disabled": Text("Turn on the AI coach in Me to get input on your runs.").font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                case "not_configured": Text("AI input isn't set up on the server yet (or add your own OpenAI key in Me).").font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                default:
                    Text(v.status == "budget_exceeded" ? "Today's AI limit is reached. Try again tomorrow." : v.status == "failed" ? v.detail ?? "The AI call failed. Try again in a moment."
                         : "The AI input didn't pass the app's checks this time.").font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                    if v.status != "budget_exceeded" { LinkButton(title: "Try again", action: onAsk) }
                }
            }
        }
        .animation(.easeInOut, value: more)
    }
}

/// Per km: pace capsules (taller = faster, the hilliest km in full orange with its flat-equivalent), then the table.
private struct Splits: View {
    var r: PostRunReport
    var units: Units
    var body: some View {
        let paced = r.splits.compactMap(\.paceSPerKm)
        let hilly = r.splits.filter(\.complete).max { ($0.elevationGainM ?? 0) < ($1.elevationGainM ?? 0) }
            .flatMap { ($0.elevationGainM ?? 0) >= 10 && $0.gapPaceSPerKm != nil ? $0 : nil }
        CardGroup(title: "Splits") {
            if paced.count >= 2 {
                let fastest = paced.min()!, slowest = paced.max()!
                GroupCustom {
                    HStack(alignment: .bottom, spacing: 6) {
                        ForEach(r.splits) { s in
                            let f = s.paceSPerKm.map { slowest > fastest ? 0.35 + 0.65 * (slowest - $0) / (slowest - fastest) : 1 } ?? 0.1
                            RoundedRectangle(cornerRadius: 6, style: .continuous)
                                .fill(s.idx == hilly?.idx ? DataColors.pace.opacity(s.complete ? 1 : 0.45) : Tint.orange.hue.opacity(s.complete ? 0.45 : 0.2))
                                .frame(maxWidth: .infinity).frame(height: 110 * f)
                        }
                    }
                    .frame(height: 110, alignment: .bottom)
                    .accessibilityLabel("Pace per kilometre, taller is faster")
                    HStack(spacing: 6) {
                        ForEach(r.splits) { Text("\($0.idx + 1)").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).frame(maxWidth: .infinity) }
                    }
                    if let h = hilly {
                        Text("Km \(h.idx + 1) climbed \(Fmt.elevation(h.elevationGainM, units)): \(Fmt.pace(h.paceSPerKm, units)) actual, \(Fmt.pace(h.gapPaceSPerKm, units)) on the flat.")
                            .font(Typo.bodyMedium).padding(.horizontal, 14).padding(.vertical, 12)
                            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Tint.orange.hue.opacity(0.16)))
                            .padding(.top, 10)
                    }
                }
            }
            GroupCustom {
                Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 10) {
                    GridRow {
                        ForEach(["#", "Pace", "Flat", "HR", "Zone", "Climb"], id: \.self) { Text($0).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant) }
                    }
                    Divider()
                    ForEach(r.splits) { s in
                        GridRow {
                            Text("\(s.idx + 1)").font(Typo.bodyMedium)
                            Text(Fmt.pace(s.paceSPerKm, units).components(separatedBy: " ").first! + (s.complete ? "" : "*")).font(Typo.titleSmall)
                            Text(Fmt.pace(s.gapPaceSPerKm, units).components(separatedBy: " ").first!).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                            Text(s.avgHr.map { "\(Int($0.rounded()))" } ?? "—").font(Typo.bodyMedium)
                            Text(s.zone.flatMap { $0 > 0 ? "Z\($0)" : nil } ?? "—").font(Typo.bodyMedium)
                            Text("+" + Fmt.elevation(s.elevationGainM, units)).font(Typo.bodyMedium)
                        }
                    }
                }
                Text("Flat = flat-equivalent: the pace this effort would give on flat ground.").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
                if r.splits.contains(where: { !$0.complete }) { Text("* Partial km").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant) }
            }
        }
    }
}

/// The watch's headline VO2 max for that day (one decimal, as the watch shows it), the run's own estimate only when the
/// day's value is missing, Runner Sidekick's from this run, and the watch's other numbers.
private struct WatchNumbers: View {
    var r: PostRunReport
    var onHold: (Bool) -> Void
    var body: some View {
        let vo2: [(String, String)] = r.garminVo2maxDay.map { [("VO₂ max (\(r.watchName)'s)", Fmt.f1($0.value))] }
            ?? r.garminMetrics["vO2MaxValue"].map { [("VO₂ max (this run's estimate)", $0.string ?? "")] } ?? []
        let ours: [(String, String)] = r.vo2Ours.map { o in [("VO₂ max (Runner Sidekick, this run\(o.hillAdjusted ? ", hill-adjusted" : ""))", o.value.map { Fmt.f1($0) } ?? "—")] } ?? []
        let garmin = r.garminMetrics.keys.sorted().compactMap { k in garminLabels[k].map { ($0, garminValue(k, r.garminMetrics[k]!)) } }
        let rows = vo2 + ours + garmin + r.garminExtra.map { ($0.label, $0.value) }
        if !rows.isEmpty {
            CardGroup(title: "VO₂ max and the watch's numbers", tint: .teal) {
                ForEach(rows, id: \.0) { l, v in GroupRow(headline: l) { Text(v).font(Typo.titleMedium) } }
                // The runner can leave a run out of our VO2 max (heart rate that looked wrong, say): its own value stays here
                if let o = r.vo2Ours, o.value != nil || o.heldOut {
                    GroupRow(headline: "Leave out of Runner Sidekick's VO₂ max", supporting: o.heldOut ? "Held out by you: not in the estimate" : "For a run whose heart rate looked wrong") {
                        Toggle("", isOn: Binding(get: { o.heldOut }, set: onHold)).labelsHidden()
                    }
                }
                if let why = r.vo2Ours?.why {
                    GroupCustom {
                        Text("No Runner Sidekick VO₂ max from this run: \(why). It needs a steady, flat run of 20+ minutes after the warm-up with good heart rate.")
                            .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

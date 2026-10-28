import SwiftUI

struct ReadinessPage: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    var body: some View {
        DetailPage(title: "Training readiness") {
            if let r = store.today?.value, let raw = r.readiness {
                let s = store.unwellPending ? raw.unwellShown : raw
                PageHead(value: s.score.map(String.init) ?? "—", unit: "/100" + (s.label.map { " · \($0)" } ?? ""), lines: [s.headline])
                CardGroup(title: "What goes into it", tint: .green) {
                    ForEach(s.components) { c in GroupRow(headline: c.title, supporting: c.say ?? c.value) { VerdictChip(verdict: c.verdict) } }
                }
                // Garmin's own number, side by side: it weighs its recovery timer much more heavily than ours does
                if let g = s.garmin {
                    CardGroup(title: "Garmin's training readiness") {
                        GroupRow("\(g.score)" + (g.level.map { " · \($0)" } ?? ""), supporting: g.recoveryHours.map { h in
                            h > 0 ? "Recovery timer: about \(h) h left" + (h >= 24 ? " · nothing harder than easy until it's under a day" : "") : "Recovery timer: done"
                        } ?? "Calculated by Garmin")
                    }
                }
                if !r.changes.isEmpty { CardGroup(title: "Since yesterday") { ForEach(r.changes, id: \.self) { GroupRow($0) } } }
                OutlineButton(title: "All readings and Garmin scores") { nav.open(.briefing) }
                Footnote(text: "Calculated from your own data, not Garmin's. A guide, not medical advice.")
            }
        }
    }
}

private func garminName(_ metric: String) -> String {
    switch metric {
    case "garmin_training_readiness": "Training readiness"
    case "garmin_sleep_score", "samsung_sleep_score": "Sleep score"
    case "body_battery_high": "Body Battery high"
    case "body_battery_low": "Body Battery low"
    case "avg_stress": "Average stress"
    case "garmin_vo2max_running": "VO₂ max"
    default: metric
    }
}

struct BriefingPage: View {
    @Environment(Store.self) private var store
    @State private var evidence: Finding?
    var body: some View {
        DetailPage(title: "Full briefing") {
            if let r = store.today?.value {
                CardGroup(title: "Findings", tint: .green) {
                    ForEach(r.findings) { f in GroupRow(f.title, supporting: f.statement) { evidence = f } }
                }
                if !r.garminContext.isEmpty {
                    let origins = Set(r.garminContext.map(\.origin))
                    CardGroup(title: "From " + (origins.count == 1 ? origins.first! : "your watches")) {
                        // The label (Garmin's level, and for readiness what it was built from) under the name, the number on the right
                        ForEach(r.garminContext, id: \.self) { g in
                            GroupRow(headline: garminName(g.metric), supporting: g.label.map { l in
                                Fmt.capitalized(l == l.uppercased() ? l.replacingOccurrences(of: "_", with: " ").lowercased() : l) }) {
                                Text("\(Int(g.value.rounded()))").font(Typo.titleSmall)
                            }
                        }
                    }
                    Footnote(text: "The watch's own scores, shown for context. They don't feed the suggestion, which avoids counting sleep and HRV twice.")
                }
                Text("Revision \(r.revision) · generated \(Fmt.ago(Fmt.instant(r.generatedAt))) · rules \(r.recommendation.rulesVersion) (\(r.recommendation.ruleId))")
                    .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).padding(8)
            }
        }
        .sheet(item: $evidence) { EvidenceSheet(finding: $0, note: store.today?.value.note(for: $0.metric)) }
    }
}

struct ScorePage: View {
    var which: String
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @State private var how = false

    var body: some View {
        let sc = store.today?.value.scores
        let s = which == "health" ? sc?.health : sc?.fitness
        DetailPage(title: which == "health" ? "Healthy habits" : "Fitness") {
            if let s {
                let tint: Tint = which == "health" ? .purple : .blue
                VStack(alignment: .leading, spacing: 4) {
                    BigValue(value: s.score.map(String.init) ?? "—", unit: "/100")
                    Text([s.label, s.trend.map { t in (t.delta == 0 ? "same as 4 weeks ago" : String(format: "%+d in 4 weeks", t.delta)) + (t.detail.map { " (\($0))" } ?? "") },
                          s.stale ? "based on an old VO₂ max" : nil].compactMap { $0 }.joined(separator: " · ")).font(Typo.titleMedium)
                    if let sc = sc?.scope[which] { Text(sc).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
                    if let n = s.trend?.note { Text(n).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
                    if let d = s.detail { Text(d).font(Typo.bodyMedium) }
                }
                .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 4)
                CardGroup(title: "What goes into it", tint: tint) {
                    ForEach(s.components.filter { !$0.context }) { c in
                        // "How it's calculated" adds each part's rule and its share of the score under its reading
                        GroupRow(headline: c.title, supporting: (c.say ?? c.value ?? c.note ?? "") + (how ? "\n" + [c.note, c.weightPct > 0 ? "\(c.weightPct)% of the score" : nil].compactMap { $0 }.joined(separator: " · ") : "")) {
                            VerdictChip(verdict: c.verdict)
                        }
                    }
                }
                OutlineButton(title: how ? "Hide how it's calculated" : "How it's calculated") { how.toggle() }
                // VO2 max and its progress live under Fitness (Today's health card is about last night)
                if which == "fitness", chosenVo2(store.fitness?.value) != nil { OutlineButton(title: "VO₂ max and its progress") { nav.open(.vo2) } }
                if let p = s.progress {
                    // Is it improving? Separate signals from different data, with how much they agree
                    CardGroup(title: "Progress · " + (p.verdict == "insufficient" ? "not enough evidence yet" : p.verdict)
                              + (p.agreement.map { " · \($0) agree" } ?? p.confidence.map { " · \($0) confidence" } ?? "")) {
                        if let sum = p.summary { GroupCustom { Text(sum).font(Typo.bodyMedium) } }
                        ForEach(p.signals) { g in
                            GroupRow(headline: g.title, supporting: g.say + (how ? "\n" + (g.note ?? "") : "")) {
                                // Garmin's VO2 max is a device estimate: a dip is an estimate trend, not a decline
                                let dip = g.id == "vo2" && g.direction == "declining"
                                VerdictChip(verdict: dip ? "ok" : ["improving": "good", "stable": "ok", "declining": "low"][g.direction ?? ""],
                                            label: dip ? "Estimate dipped" : ["improving": "Improving", "stable": "Stable", "declining": "Declining", "inconclusive": "Inconclusive"][g.direction ?? ""])
                            }
                        }
                    }
                }
                let ctx = s.components.filter(\.context)
                if !ctx.isEmpty {
                    CardGroup(title: "Context · not counted") {
                        ForEach(ctx) { c in GroupRow(headline: c.title, supporting: c.say ?? c.note) { VerdictChip(verdict: c.verdict) } }
                    }
                }
                if !s.improve.isEmpty {
                    CardGroup(title: "Potential score changes") {
                        ForEach(s.improve, id: \.self) { x in
                            GroupRow(headline: x.part, supporting: x.text + (x.horizon.map { " · \($0)" } ?? "")) {
                                TagChip(text: "+\(x.gain)", container: Tint.green.hue.opacity(0.22), content: Tint.green.ink)
                            }
                        }
                    }
                }
                if !s.improve.isEmpty { Footnote(text: "What the score would show if that part reached its target; not a prediction of how much effort it takes.") }
                if !s.missing.isEmpty, s.score != nil { Footnote(text: "Partial: \(s.missing.joined(separator: ", ").lowercased()) not available yet, so the score uses the other parts.") }
                if let b = sc?.basis { Footnote(text: b) }
            }
        }
    }
}

struct Vo2Page: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    var body: some View {
        DetailPage(title: "VO₂ max") {
            if let r = store.today?.value, let f = store.fitness?.value {
                if let v = chosenVo2(f) {
                    PageHead(value: Fmt.f1(v), unit: "ml/kg/min", lines: [f.maker == "Runner Sidekick" ? "Runner Sidekick's estimate" : "\(f.maker)'s latest reading"])
                }
                Tile(tint: .teal, spacing: 12) { Vo2Progress(series: f.vo2maxSeries, maker: f.maker, today: r.localDate) }
                if let n = r.note(for: "vo2max") { NoteBlock(note: n) }
                OutlineButton(title: "Compare with your age group") { nav.trendsTab = 1; nav.paths[.today] = []; nav.tab = .trends }
            }
        }
    }
}

/// VO2 max progress: the chosen source's readings since 3 months, 6 months or a year ago.
private struct Vo2Progress: View {
    var series: [Point]
    var maker: String
    var today: String
    @State private var months = 3

    var body: some View {
        let from = Fmt.addMonths(today, -months)
        let pts = series.filter { $0.date >= from }
        VStack(alignment: .leading, spacing: 12) {
            Text("Progress").font(Typo.titleSmall)
            ChoiceGroup(labels: ["3 months", "6 months", "1 year"], selected: [3, 6, 12].firstIndex(of: months)) { months = [3, 6, 12][$0] }
            if pts.count < 2 {
                Text("Not enough \(maker) readings in this period yet.").font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
            } else {
                let ch = pts.last!.value - pts.first!.value
                Text((abs(ch) < 0.05 ? "About the same" : String(format: "%+.1f", ch)) + " since \(Fmt.shortDate(pts.first!.date)) (\(Fmt.f1(pts.first!.value)) → \(Fmt.f1(pts.last!.value)))")
                    .font(Typo.bodyLarge)
                let lo = (pts.map(\.value).min()! - 0.5).rounded(.down), hi = (pts.map(\.value).max()! + 0.5).rounded(.up)
                HStack(alignment: .top, spacing: 0) {
                    VStack(alignment: .leading) { Text(Fmt.f0(hi)); Spacer(); Text(Fmt.f0(lo)) }
                        .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).frame(width: 36, height: 140, alignment: .leading)
                    Canvas { ctx, size in
                        let d0 = Fmt.day(pts.first!.date)!, span = max(Fmt.day(pts.last!.date)!.timeIntervalSince(d0), 86400)
                        func x(_ p: Point) -> CGFloat { CGFloat(Fmt.day(p.date)!.timeIntervalSince(d0) / span) * size.width }
                        func y(_ v: Double) -> CGFloat { size.height * CGFloat(1 - (v - lo) / (hi - lo)) }
                        for gy in [0, size.height] {
                            var g = Path(); g.move(to: CGPoint(x: 0, y: gy)); g.addLine(to: CGPoint(x: size.width, y: gy))
                            ctx.stroke(g, with: .color(Palette.outlineVariant), style: StrokeStyle(lineWidth: 1, dash: [6, 6]))
                        }
                        var path = Path()
                        for (i, p) in pts.enumerated() { i == 0 ? path.move(to: CGPoint(x: x(p), y: y(p.value))) : path.addLine(to: CGPoint(x: x(p), y: y(p.value))) }
                        ctx.stroke(path, with: .color(Tint.teal.ink), style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                        for p in pts { ctx.fill(Path(ellipseIn: CGRect(x: x(p) - 3, y: y(p.value) - 3, width: 6, height: 6)), with: .color(Tint.teal.ink)) }
                    }
                    .frame(height: 140)
                    .accessibilityLabel("VO2 max from \(Fmt.f1(pts.first!.value)) to \(Fmt.f1(pts.last!.value)) over \(pts.count) readings")
                }
                HStack { Text(Fmt.shortDate(pts.first!.date)); Spacer(); Text(Fmt.shortDate(pts.last!.date)) }
                    .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).padding(.leading, 36)
                Text(maker == "Runner Sidekick" ? "Runner Sidekick's estimate as it stood after each qualifying run." : "\(maker)'s readings.")
                    .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }
}

private let sessionNames = ["easy": "Easy run", "long": "Long run", "tempo": "Tempo", "intervals": "Intervals", "race_pace": "Race pace",
                            "strides": "Easy + strides", "race": "Race day", "rest": "Rest"]

/// The week toward the race: each day's session, ticked off as runs come in. Recomputed daily from what was run.
struct RacePage: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    var body: some View {
        DetailPage(title: "Race week") {
            if let race = store.today?.value.race, let w = race.week {
                Tile(tint: .amber) {
                    Text("This week toward \(race.title ?? race.headline)").font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
                    Text("\(Fmt.capitalized(w.phase.replacingOccurrences(of: "_", with: " "))) · \(daysToGo(race.daysToGo))" + (race.daysToGo > 0 ? " to go" : ""))
                        .font(Typo.titleLarge)
                    Text(w.targetMinutes.map { "About \($0) min this week · \(w.doneMinutes) min done" } ?? "\(w.doneMinutes) min done this week").font(Typo.bodyLarge)
                    if let t = w.targetMinutes, t > 0 { ProgressBar(fraction: Double(w.doneMinutes) / Double(t), fill: Tint.amber.hue) }
                    if let g = w.guardrail { Text(g).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
                }
                CardGroup {
                    ForEach(w.sessions.filter { !($0.kind == "rest" && $0.status == "rest") }, id: \.self) { s in
                        let status: String? = switch s.status {
                        case "done": "Done" + (s.ranMinutes.map { " · \($0) min" } ?? "")
                        case "moved": "Moved to \(s.movedTo.map { Fmt.weekdayShort($0) } ?? "another day")"
                        case "missed": "Missed · not made up"
                        case "today": "Today"
                        case "extra": "Extra run" + (s.ranMinutes.map { " · \($0) min" } ?? "")
                        default: nil
                        }
                        let icon = switch s.status { case "done", "extra": "checkmark.circle"; case "today": "figure.run"; case "moved": "arrow.right"; case "missed": "xmark"; default: "calendar" }
                        let accent: String? = switch s.status { case "done", "extra": "running"; case "moved": "fitness"; case "missed": "recovery"; case "today": "training"; default: nil }
                        GroupRow("\(Fmt.weekdayShort(s.date)) \(Fmt.dayOfMonth(s.date)) · \(sessionNames[s.kind] ?? s.kind)" + (s.minutes.map { " · ~\($0) min" } ?? "") + (s.optional ? " (optional)" : ""),
                                 supporting: [["tempo", "intervals", "race_pace", "strides"].contains(s.kind) ? s.text : nil, status].compactMap { $0 }.joined(separator: " · ").nilIfEmpty,
                                 icon: icon, shape: .circle, accent: accent, action: s.sourceId.map { id in { nav.open(.run(id)) } })
                    }
                }
                if let b = w.basis { Footnote(text: b) }
            }
        }
    }
}

/// One focus for the week, chosen from data-based suggestions, then measured on the week's runs.
struct FocusPage: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @State private var changing = false

    var body: some View {
        DetailPage(title: "This week's focus") {
            if let state = store.focus?.value {
                if state.current == nil || changing {
                    CardGroup(title: "Choose this week's focus") {
                        if let lw = state.lastWeek { GroupRow("Last week: \(lw.title)", supporting: "\(focusStatusLabel(lw.status)). \(lw.summary ?? "")") }
                        ForEach(state.options, id: \.self) { o in
                            GroupRow(o.title, supporting: o.reason, icon: "scope", shape: .sunny) {
                                changing = false
                                store.act { try await store.chooseFocus(o.kind) }
                            }
                        }
                    }
                } else if let cur = state.current {
                    Tile(tint: .amber) {
                        HStack(alignment: .top) {
                            Text(cur.title).font(Typo.titleLarge).frame(maxWidth: .infinity, alignment: .leading)
                            FocusStatusChip(status: cur.status)
                        }
                        if let s = cur.summary { Text(s).font(Typo.bodyLarge) }
                        let meta = [cur.target.map { "Target: \($0)" }, cur.auto ? "picked for you" : nil].compactMap { $0 }.joined(separator: " · ")
                        if !meta.isEmpty { Text(Fmt.capitalized(meta)).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
                        if let f = cur.felt { Text(f).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
                        let runs = cur.runs.filter { $0.sourceId != nil }
                        if !runs.isEmpty {
                            FlowLayout(spacing: 6, lineSpacing: 6) {
                                ForEach(runs, id: \.self) { r in
                                    Button { nav.open(.run(r.sourceId!)) } label: {
                                        Text("\(Fmt.weekdayShort(r.date)) \(Fmt.dayOfMonth(r.date))" + (r.met ? " ✓" : "")).font(Typo.labelLarge)
                                            .padding(.horizontal, 12).padding(.vertical, 8).background(Capsule().fill(Palette.card.opacity(0.75)))
                                    }.buttonStyle(PressStyle())
                                }
                            }
                        }
                    }
                    if let lw = state.lastWeek {
                        Tile(spacing: 4) {
                            Text("Last week").font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
                            Text("\(lw.title): \(focusStatusLabel(lw.status).lowercased()). \(lw.summary ?? "")").font(Typo.bodyMedium)
                        }
                    }
                    if state.options.count > 1 { OutlineButton(title: "Change") { changing = true } }
                }
            }
        }
    }
}

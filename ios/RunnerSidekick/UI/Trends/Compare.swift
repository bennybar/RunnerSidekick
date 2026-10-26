import SwiftUI

/// Each comparison's tile colour, by its kind of data.
private func compareTint(_ id: String) -> Tint {
    switch id { case "vo2max": .teal; case "fitness_age": .blue; case "resting_hr", "hrv": .pink; case "age_grade": .amber; default: .neutral }
}

private func trimmed(_ v: Double) -> String { v.truncatingRemainder(dividingBy: 1) == 0 ? "\(Int(v))" : String(format: "%.1f", v) }

/// You against people of your sex and age. Every card says which reference it uses and what limits the comparison.
struct CompareSection: View {
    var r: CompareReport?
    var onOpenSettings: () -> Void
    var body: some View {
        if let r {
            if !r.missing.isEmpty {
                Tile {
                    Text("Comparisons need your \(r.missing.joined(separator: " and "))").font(Typo.titleMedium)
                    Text("Garmin didn't provide \(r.missing.count > 1 ? "them" : "it"). Add it in Me; nothing is guessed.")
                        .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                    LinkButton(title: "Open Me", action: onOpenSettings)
                }
            } else {
                ScreenSummaryCard(s: r.aiSummary)
                if let p = r.profile {
                    HStack {
                        Text("Compared with \(p.sex == "female" ? "women" : "men") of your age (\(p.age.map(String.init) ?? "—"))"
                             + (p.source == "settings" ? " · your settings" : " · from Garmin"))
                            .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant).frame(maxWidth: .infinity, alignment: .leading)
                        LinkButton(title: "Change", action: onOpenSettings)
                    }
                    .padding(.leading, 8)
                }
                ForEach(r.items) { CompareCard(i: $0) }
                Text("Population comparisons describe where you sit among others; they aren't health assessments or medical advice.")
                    .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).padding(.horizontal, 8)
            }
        } else {
            ProgressView().frame(maxWidth: .infinity).padding(.top, 32)
        }
    }
}

private struct CompareCard: View {
    var i: CompareItem
    @State private var more = false
    var body: some View {
        let tint = compareTint(i.id)
        // Charts draw in the tile's own ink (neutral tiles in plain text colour)
        let accent = tint == .neutral ? Palette.onSurface : tint.ink
        Tile(tint: tint, spacing: 10) {
            Text(i.title).font(Typo.titleSmall)
            if let h = i.headline { Text(h).font(Typo.titleLarge) }
            if let c = i.chart {
                switch c["type"]?.string {
                case "bands": BandsChart(c: c, accent: accent)
                case "ages": AgesChart(c: c, accent: accent)
                case "distribution": DistributionChart(c: c, accent: accent)
                case "age_grade": AgeGradeChart(rows: i.rows, accent: accent)
                case "weekly_dots":
                    let band = (c["band"]?.array ?? []).compactMap(\.double)
                    WeeklyDotChart(points: (c["points"]?.array ?? []).compactMap { p in
                        p["week"]?.string.map { WeekPoint(week: $0, value: p["value"]?.double ?? 0, newWatch: p["newWatch"]?.string == "true" || p["newWatch"]?.bool == true) }
                    }, decimals: Int(c["decimals"]?.double ?? 0), step: c["step"]?.double ?? 5, caption: "Weekly median (\(c["unit"]?.string ?? ""))",
                                   description: i.title, band: band.count == 2 ? (band[0], band[1]) : nil)
                default: EmptyView()
                }
            }
            if i.detail != nil || i.method != nil || !i.caveats.isEmpty {
                if more {
                    if let d = i.detail { Text(d).font(Typo.bodyMedium) }
                    if let m = i.method { Text(m).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
                    ForEach(i.caveats, id: \.self) { Text("• \($0)").font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
                    if let s = i.source { Text("Reference: \(s)").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant) }
                }
                LinkButton(title: more ? "Less" : "Details") { withAnimation { more.toggle() } }
            }
        }
    }
}

/// VO2 max: the rating bands for your group with your value marked.
private struct BandsChart: View {
    var c: JSONValue
    var accent: Color
    var body: some View {
        // Only well-formed bands (a label, from and to); nothing drawn without them
        let bands = (c["bands"]?.array ?? []).filter { $0["label"]?.string != nil && $0["from"]?.double != nil && $0["to"]?.double != nil }
        if let value = c["value"]?.double, !bands.isEmpty, let lo = bands.first?["from"]?.double, let hi = bands.last?["to"]?.double, hi > lo {
            let colors = [Palette.onSurface.opacity(0.08), accent.opacity(0.25), accent.opacity(0.45), accent.opacity(0.7), accent]
            VStack(spacing: 2) {
                Canvas { ctx, size in
                    func x(_ v: Double) -> CGFloat { (min(hi, max(lo, v)) - lo) / (hi - lo) * size.width }
                    for (k, b) in bands.enumerated() {
                        let x0 = x(b["from"]!.double!), x1 = x(b["to"]!.double!)
                        ctx.fill(Path(roundedRect: CGRect(x: x0 + 1, y: 6, width: max(1, x1 - x0 - 2), height: size.height - 12), cornerRadius: 5), with: .color(colors[k % colors.count]))
                    }
                    let m = CGPoint(x: x(value), y: size.height / 2)
                    ctx.fill(Path(ellipseIn: CGRect(x: m.x - 9, y: m.y - 9, width: 18, height: 18)), with: .color(Palette.onSurface))
                    ctx.fill(Path(ellipseIn: CGRect(x: m.x - 5, y: m.y - 5, width: 10, height: 10)), with: .color(Palette.background))
                }
                .frame(height: 36)
                .accessibilityLabel("Your value \(String(format: "%.1f", value)) on the rating scale " + bands.compactMap { $0["label"]?.string }.joined(separator: ", "))
                GeometryReader { g in
                    HStack(spacing: 0) {
                        ForEach(Array(bands.enumerated()), id: \.offset) { _, b in
                            Text(b["label"]?.string ?? "").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).multilineTextAlignment(.center)
                                .frame(width: g.size.width * (b["to"]!.double! - b["from"]!.double!) / (hi - lo))
                        }
                    }
                }
                .frame(height: 30)
            }
        }
    }
}

/// Fitness age: your real age, Garmin's fitness age, what Garmin says is achievable, and the age your VO2 max is typical for.
private struct AgesChart: View {
    var c: JSONValue
    var accent: Color
    var body: some View {
        let marks: [(String, Double, Color)] = [
            c["age"]?.double.map { ("Your age", $0, Palette.onSurfaceVariant) },
            c["fitnessAge"]?.double.map { ("Fitness age", $0, accent) },
            c["achievable"]?.double.map { ("Achievable", $0, Tint.green.ink) },
            c["vo2Age"]?.double.map { ("VO₂ max typical for", $0, Tint.teal.ink) },
        ].compactMap { $0 }
        if marks.count >= 2 {
            let lo = marks.map(\.1).min()! - 3, hi = marks.map(\.1).max()! + 3
            VStack(spacing: 6) {
                Canvas { ctx, size in
                    func x(_ v: Double) -> CGFloat { (v - lo) / (hi - lo) * size.width }
                    ctx.fill(Path(roundedRect: CGRect(x: 0, y: size.height / 2 - 4, width: size.width, height: 8), cornerRadius: 4), with: .color(Palette.onSurface.opacity(0.08)))
                    for (_, v, col) in marks { ctx.fill(Path(ellipseIn: CGRect(x: x(v) - 8, y: size.height / 2 - 8, width: 16, height: 16)), with: .color(col)) }
                }
                .frame(height: 28)
                .accessibilityLabel(marks.map { "\($0.0) \(String(format: "%.1f", $0.1))" }.joined(separator: ", "))
                ForEach(marks, id: \.0) { label, v, col in
                    HStack(spacing: 8) {
                        Circle().fill(col).frame(width: 10, height: 10)
                        Text(label).font(Typo.bodyMedium).frame(maxWidth: .infinity, alignment: .leading)
                        Text(trimmed((v * 10).rounded() / 10)).font(Typo.titleMedium)
                    }
                }
            }
        }
    }
}

/// Resting heart rate: the population's spread (2.5th–97.5th, middle half darker, median tick) with your value.
private struct DistributionChart: View {
    var c: JSONValue
    var accent: Color
    var body: some View {
        let pts = (c["points"]?.array ?? []).compactMap(\.double)
        if let value = c["value"]?.double, pts.count >= 9 {
            let lo = min(pts.first!, value) - 4, hi = max(pts.last!, value) + 4
            VStack(alignment: .leading, spacing: 2) {
                Canvas { ctx, size in
                    func x(_ v: Double) -> CGFloat { (v - lo) / (hi - lo) * size.width }
                    let mid = size.height / 2
                    ctx.fill(Path(roundedRect: CGRect(x: x(pts[0]), y: mid - 10, width: x(pts[8]) - x(pts[0]), height: 20), cornerRadius: 10), with: .color(accent.opacity(0.18)))
                    ctx.fill(Path(roundedRect: CGRect(x: x(pts[3]), y: mid - 10, width: x(pts[5]) - x(pts[3]), height: 20), cornerRadius: 10), with: .color(accent.opacity(0.4)))
                    var tick = Path(); tick.move(to: CGPoint(x: x(pts[4]), y: mid - 16)); tick.addLine(to: CGPoint(x: x(pts[4]), y: mid + 16))
                    ctx.stroke(tick, with: .color(accent), lineWidth: 3)
                    ctx.fill(Path(ellipseIn: CGRect(x: x(value) - 9, y: mid - 9, width: 18, height: 18)), with: .color(Palette.onSurface))
                    ctx.fill(Path(ellipseIn: CGRect(x: x(value) - 5, y: mid - 5, width: 10, height: 10)), with: .color(Palette.background))
                }
                .frame(height: 40)
                .accessibilityLabel("Your \(Int(value)) bpm; population middle \(Int(pts[4])) bpm, typical range \(Int(pts[0])) to \(Int(pts[8]))")
                HStack {
                    Text("\(Int(pts[0])) bpm").foregroundStyle(Palette.onSurfaceVariant)
                    Spacer()
                    Text("middle \(Int(pts[4]))").foregroundStyle(accent)
                    Spacer()
                    Text("\(Int(pts[8])) bpm").foregroundStyle(Palette.onSurfaceVariant)
                }
                .font(Typo.labelSmall)
                Text("You: \(Int(value)) bpm · darker band = middle half of people").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }
}

/// Age grade per distance on a 40–100% scale with the class thresholds marked.
private struct AgeGradeChart: View {
    var rows: [AgeGradeRow]
    var accent: Color
    @Environment(Nav.self) private var nav
    var body: some View {
        let lo = 40.0, hi = 100.0
        VStack(alignment: .leading, spacing: 10) {
            ForEach(rows.sorted { ($0.kind != "best" ? 1 : 0, $0.timeS) < ($1.kind != "best" ? 1 : 0, $1.timeS) }, id: \.self) { r in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .lastTextBaseline) {
                        Text(r.label + (r.kind == "prediction" ? " · Garmin prediction" : " · your best")).font(Typo.labelLarge).frame(maxWidth: .infinity, alignment: .leading)
                        Text("\(Fmt.clock(r.timeS)) → \(String(format: "%.0f", r.ageGradePct))%").font(Typo.titleSmall)
                    }
                    Canvas { ctx, size in
                        func x(_ v: Double) -> CGFloat { (min(hi, max(lo, v)) - lo) / (hi - lo) * size.width }
                        ctx.fill(Path(roundedRect: CGRect(origin: .zero, size: size), cornerRadius: 4), with: .color(Palette.onSurface.opacity(0.08)))
                        ctx.fill(Path(roundedRect: CGRect(x: 0, y: 0, width: x(r.ageGradePct), height: size.height), cornerRadius: 4),
                                 with: .color(r.kind == "best" ? accent : accent.opacity(0.45)))
                        for t in [60.0, 70, 80, 90] {
                            var l = Path(); l.move(to: CGPoint(x: x(t), y: 0)); l.addLine(to: CGPoint(x: x(t), y: size.height))
                            ctx.stroke(l, with: .color(Palette.onSurface.opacity(0.25)), lineWidth: 1)
                        }
                    }
                    .frame(height: 10)
                    .accessibilityLabel("\(r.label) \(String(format: "%.0f", r.ageGradePct)) percent age grade, \(r.gradeClass)")
                    HStack {
                        Text(Fmt.capitalized(r.gradeClass) + " · open-age equivalent \(Fmt.clock(r.ageGradedTimeS))").font(Typo.labelSmall)
                            .foregroundStyle(Palette.onSurfaceVariant).frame(maxWidth: .infinity, alignment: .leading)
                        if let sid = r.sourceId { LinkButton(title: "Run") { nav.open(.run(sid)) } }
                    }
                }
            }
            Text("Scale 40–100%. Lines mark 60% local, 70% regional, 80% national and 90% world class.").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
        }
    }
}

// MARK: Charts tab

private func trendTint(_ metric: String) -> Tint {
    switch metric { case "sleep_duration": .indigo; case "resting_hr", "hrv_overnight_avg": .pink; default: .neutral }
}

/// Charts tab: daily series with personal-range band, gaps and watch changes; each point opens its day.
struct TrendsSection: View {
    var t: Trends?
    @Binding var days: Int
    var loading: Bool
    var body: some View {
        ChoiceGroup(labels: ["7 days", "28 days", "90 days"], selected: [7, 28, 90].firstIndex(of: days)) { days = [7, 28, 90][$0] }
        if let t {
            ScreenSummaryCard(s: t.aiSummary)
            if !t.deviceChanges.isEmpty {
                Label("Watch changed on \(t.deviceChanges.map { Fmt.shortDate($0) }.joined(separator: ", ")). Shown as a dashed line; ranges restart there.",
                      systemImage: "applewatch").font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant).padding(.horizontal, 8)
            }
            ForEach(t.metrics) { MetricTrendCard(m: $0, t: t) }
            if !t.weeklyRunning.isEmpty { WeeklyVolumeCard(weeks: t.weeklyRunning) }
            PaceCard(t: t)
        } else {
            Footnote(text: loading ? "Loading trends…" : "Couldn't load trends. Pull down to try again.")
        }
    }
}

private struct MetricTrendCard: View {
    var m: TrendMetric
    var t: Trends
    @State private var selected: Int?
    @Environment(Nav.self) private var nav
    var body: some View {
        let s = m.summary
        let tint = trendTint(m.metric)
        let line = tint == .neutral ? Palette.onSurface : tint.ink
        Tile(tint: tint) {
            Text(m.title).font(Typo.titleSmall)
            HStack(alignment: .lastTextBaseline, spacing: 8) {
                Text(Fmt.metricValue(m.metric, s.median)).font(Typo.headlineMedium)
                Text("median, \(s.n) of \(t.days) days").font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
            }
            Text(s.enough && s.change != nil
                 ? "\(Fmt.signedDelta(m.metric, s.change)) vs the previous \(t.days) days (\(s.previousN) days of data)" + (s.meaningful ? ". A notable change." : ", within normal variation.")
                 : "Not enough data in the previous \(t.days) days to compare.")
                .font(Typo.bodyMedium).foregroundStyle(s.meaningful ? DataColors.attention : Palette.onSurfaceVariant)
            TrendChart(m: m, t: t, selected: $selected, line: line)
            if let i = selected, i < m.points.count {
                let sel = m.points[i]
                HStack {
                    Text("\(Fmt.shortDate(sel.date)) · \(sel.value.map { Fmt.metricValue(m.metric, $0) } ?? "no data")").font(Typo.titleSmall)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    PillButton(title: "Open day", filled: false) { nav.open(.day(sel.date)) }
                }
            } else {
                Text("Tap the chart to see a day.").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
        .onChange(of: t.days) { _, _ in selected = nil }
    }
}

private struct TrendChart: View {
    var m: TrendMetric
    var t: Trends
    @Binding var selected: Int?
    var line: Color
    var body: some View {
        let values = m.points.map(\.value)
        let present = values.compactMap { $0 } + m.band.compactMap(\.q1) + m.band.compactMap(\.q3)
        if present.count < 2 {
            Text("No data in this period.").font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
        } else {
            let lo = present.min()!, hi0 = present.max()!
            let hi = hi0 == lo ? lo + 1 : hi0
            let eras = t.deviceChanges.compactMap { d in m.points.firstIndex { $0.date == d } }
            VStack(spacing: 2) {
                HStack(spacing: 0) {
                    VStack(alignment: .leading) { Text(Fmt.metricValue(m.metric, hi)); Spacer(); Text(Fmt.metricValue(m.metric, lo)) }
                        .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).frame(width: 64, height: 140, alignment: .leading)
                    GeometryReader { g in
                        Canvas { ctx, size in
                            let n = values.count
                            func x(_ i: Int) -> CGFloat { n <= 1 ? 0 : CGFloat(i) * size.width / CGFloat(n - 1) }
                            func y(_ v: Double) -> CGFloat { size.height * (1 - (v - lo) / (hi - lo)) }
                            // Personal range band, per contiguous run of days that have both ends of it
                            func has(_ k: Int) -> Bool { k < m.band.count && m.band[k].q1 != nil && m.band[k].q3 != nil }
                            var i = 0
                            while i < n {
                                if !has(i) { i += 1; continue }
                                var j = i
                                while j + 1 < n && has(j + 1) { j += 1 }
                                var p = Path()
                                p.move(to: CGPoint(x: x(i), y: y(m.band[i].q3!)))
                                for k in i...j { p.addLine(to: CGPoint(x: x(k), y: y(m.band[k].q3!))) }
                                for k in stride(from: j, through: i, by: -1) { p.addLine(to: CGPoint(x: x(k), y: y(m.band[k].q1!))) }
                                p.closeSubpath()
                                ctx.fill(p, with: .color(line.opacity(0.14)))
                                i = j + 1
                            }
                            for e in eras {
                                var l = Path(); l.move(to: CGPoint(x: x(e), y: 0)); l.addLine(to: CGPoint(x: x(e), y: size.height))
                                ctx.stroke(l, with: .color(Palette.outlineVariant), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                            }
                            var path = Path()
                            var pen = false
                            for (k, v) in values.enumerated() {
                                guard let v else { pen = false; continue }
                                let pt = CGPoint(x: x(k), y: y(v))
                                pen ? path.addLine(to: pt) : path.move(to: pt)
                                pen = true
                                if n <= 31 { ctx.fill(Path(ellipseIn: CGRect(x: pt.x - 3, y: pt.y - 3, width: 6, height: 6)), with: .color(line)) }
                            }
                            ctx.stroke(path, with: .color(line), style: StrokeStyle(lineWidth: 2, lineJoin: .round))
                            if let s = selected, s < n {
                                var l = Path(); l.move(to: CGPoint(x: x(s), y: 0)); l.addLine(to: CGPoint(x: x(s), y: size.height))
                                ctx.stroke(l, with: .color(Palette.onSurface.opacity(0.4)), lineWidth: 1)
                                if let v = values[s] { ctx.fill(Path(ellipseIn: CGRect(x: x(s) - 6, y: y(v) - 6, width: 12, height: 12)), with: .color(Palette.onSurface)) }
                            }
                        }
                        .contentShape(Rectangle())
                        .gesture(DragGesture(minimumDistance: 0).onEnded { v in
                            selected = min(values.count - 1, max(0, Int((v.location.x / g.size.width * CGFloat(values.count - 1)).rounded())))
                        })
                    }
                    .frame(height: 140)
                    .accessibilityLabel("\(m.title) over \(t.days) days. Shaded band is your usual range; gaps are days without data.")
                }
                HStack { Text(Fmt.shortDate(t.start)); Spacer(); Text(Fmt.shortDate(t.end)) }
                    .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).padding(.leading, 64)
            }
        }
    }
}

private struct WeeklyVolumeCard: View {
    var weeks: [WeekVolume]
    @State private var selected: Int?
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    var body: some View {
        let mx = max(1, weeks.map(\.movingS).max() ?? 1)
        let bar = Tint.orange.ink
        let units = store.units
        Tile(tint: .orange, spacing: 10) {
            Text("Running per week").font(Typo.titleSmall)
            Text("Moving time per calendar week. The lighter bar is the current, unfinished week. Tap a week for its runs.")
                .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            GeometryReader { g in
                Canvas { ctx, size in
                    let w = size.width / CGFloat(weeks.count)
                    for (k, wk) in weeks.enumerated() {
                        let h = max(3, wk.movingS / mx * size.height)
                        let c = selected == k ? Palette.onSurface : wk.partial ? bar.opacity(0.45) : bar
                        ctx.fill(Path(roundedRect: CGRect(x: CGFloat(k) * w + w * 0.18, y: size.height - h, width: w * 0.64, height: h), cornerRadius: 5), with: .color(c))
                    }
                }
                .contentShape(Rectangle())
                .gesture(DragGesture(minimumDistance: 0).onEnded { v in
                    selected = min(weeks.count - 1, max(0, Int(v.location.x / g.size.width * CGFloat(weeks.count))))
                })
            }
            .frame(height: 110)
            .accessibilityLabel("Weekly running time")
            let sel = selected.flatMap { $0 < weeks.count ? weeks[$0] : nil } ?? weeks.last!
            Text("Week of \(Fmt.shortDate(sel.weekStart)): \(sel.runs) \(sel.runs == 1 ? "run" : "runs") · \(Fmt.distance(sel.distanceM, units)) · \(Fmt.hoursMinutes(sel.movingS))"
                 + (sel.partial ? " (so far)" : "")).font(Typo.titleSmall)
            ForEach(sel.runList) { r in
                Divider().overlay(Palette.onSurface.opacity(0.07))
                Button { nav.open(.run(r.sourceId)) } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "figure.run").foregroundStyle(bar)
                        VStack(alignment: .leading) {
                            Text("\(Fmt.shortDate(r.localDate)) · \(Fmt.distance(r.distanceM, units))").font(Typo.bodyLarge)
                            Text(Fmt.pace(r.distanceM.flatMap { d in r.movingS.flatMap { d > 0 ? $0 / (d / 1000) : nil } }, units))
                                .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(Palette.onSurfaceVariant)
                    }
                    .frame(minHeight: 48).contentShape(Rectangle())
                }
                .buttonStyle(PressStyle()).foregroundStyle(Palette.onSurface)
            }
        }
    }
}

private struct PaceCard: View {
    var t: Trends
    @State private var selected: Int?
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    var body: some View {
        if let p = t.paceAtHr, let band = p.bandBpm {
            let pts = p.series.flatMap { s in s.points.map { (s.device, $0) } }
            if !pts.isEmpty {
                let units = store.units
                let palette = [Tint.blue.ink, Tint.orange.ink, Tint.purple.ink]
                let devices = p.series.map(\.device)
                let lo = pts.map(\.1.paceSPerKm).min()! - 5, hi = pts.map(\.1.paceSPerKm).max()! + 5
                Tile(tint: .blue, spacing: 10) {
                    Text("Pace at \(band.first.map(String.init) ?? "–")–\(band.count > 1 ? String(band[1]) : "–") bpm").font(Typo.titleSmall)
                    Text(p.headline).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                    Text("\(Fmt.pace(lo + 5, units)) (faster)").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
                    GeometryReader { g in
                        Canvas { ctx, size in
                            for (k, dp) in pts.enumerated() {
                                let x = pts.count == 1 ? size.width / 2 : CGFloat(k) * size.width / CGFloat(pts.count - 1)
                                let y = (dp.1.paceSPerKm - lo) / (hi - lo) * size.height
                                let r: CGFloat = selected == k ? 7 : 5
                                ctx.fill(Path(ellipseIn: CGRect(x: x - r, y: y - r, width: 2 * r, height: 2 * r)),
                                         with: .color(selected == k ? Palette.onSurface : palette[(devices.firstIndex(of: dp.0) ?? 0) % 3]))
                            }
                        }
                        .contentShape(Rectangle())
                        .gesture(DragGesture(minimumDistance: 0).onEnded { v in
                            selected = min(pts.count - 1, max(0, Int((v.location.x / g.size.width * CGFloat(pts.count - 1)).rounded())))
                        })
                    }
                    .frame(height: 110)
                    .accessibilityLabel("Pace at the same heart rate, per run; colours are watches")
                    Text("\(Fmt.pace(hi - 5, units)) (slower) · each colour is a different watch").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
                    if devices.count > 1 {
                        FlowLayout(spacing: 12, lineSpacing: 4) {
                            ForEach(Array(devices.enumerated()), id: \.offset) { k, d in
                                HStack(spacing: 4) { Circle().fill(palette[k % 3]).frame(width: 10, height: 10); Text(d).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant) }
                            }
                        }
                    }
                    if let s = selected, s < pts.count {
                        let pt = pts[s].1
                        HStack {
                            Text("\(Fmt.shortDate(pt.date)) · \(Fmt.pace(pt.paceSPerKm, units))").font(Typo.titleSmall).frame(maxWidth: .infinity, alignment: .leading)
                            if let sid = pt.sourceId { PillButton(title: "Open run", filled: false) { nav.open(.run(sid)) } }
                        }
                    }
                }
                .onChange(of: t.days) { _, _ in selected = nil }
            }
        }
    }
}

// MARK: Cardio page

private func cardioFrom(_ src: String?) -> String {
    guard let s = src else { return "set by you" }
    return s.hasPrefix("from") ? s : "set \(Fmt.shortDate(s))"
}

private struct NumberQuestion: Identifiable {
    var id: String { key }
    var key: String
    var title: String
    var current: Double?
    var range: ClosedRange<Double>
    var clear: String
    var hint: String?
}

/// Cardio fitness: each VO2 max estimate with its method, how they relate, and the answers they use.
struct CardioPage: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @State private var combinedOpen = false
    @State private var number: NumberQuestion?
    @State private var numberText = ""
    @State private var choice: String?

    var body: some View {
        DetailPage(title: "Cardio fitness") {
            if let c = store.cardio?.value {
                let a = store.settings?.value
                Footnote(text: c.basis)
                ForEach([c.runs, c.garmin, c.hunt, c.questionnaire, c.performance].compactMap { $0 }) { CardioEvidence(p: $0) }
                if !c.notes.isEmpty {
                    Tile(spacing: 6) {
                        Text("How they relate").font(Typo.titleSmall)
                        ForEach(c.notes, id: \.self) { Text($0).font(Typo.bodyMedium) }
                    }
                }
                // Technical detail, collapsed: the estimates side by side already show how far apart they are
                if let m = c.combined {
                    Tile(spacing: 4, onTap: { withAnimation { combinedOpen.toggle() } }) {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(combinedOpen ? "Hide the median of the estimates" : "Median of the estimates").font(Typo.titleSmall)
                                Text("Technical detail · not used by any score").font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            Image(systemName: combinedOpen ? "chevron.up" : "chevron.down").foregroundStyle(Palette.onSurfaceVariant)
                        }
                        if combinedOpen {
                            Text("\(trimmed(m.value)) from " + m.inputs.map { "\($0.title) \(trimmed($0.value))" }.joined(separator: " · ")).font(Typo.bodyMedium)
                            Text("Not used by any score or by fitness age, which use the VO₂ max chosen in Me. HUNT counts only with a seated pulse.")
                                .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
                        }
                    }
                }
                // The answers these estimates use, each with the day it was given
                CardGroup(title: "Your answers") {
                    GroupRow("Activity level, last month", supporting: a?.activityPar.map { "\($0) of 7" + (a?.activityParAt.map { " · answered \(Fmt.shortDate($0))" } ?? "") } ?? "Not answered") { choice = "par" }
                    GroupRow("Weight", supporting: c.inputs?.weightKg.map { "\(trimmed($0)) kg · " + cardioFrom(c.inputs?.weightFrom) } ?? "Not set") {
                        ask(NumberQuestion(key: "profile_weight_kg", title: "Weight (kg)", current: a?.profileWeightKg, range: 30...250, clear: "Clear (use Garmin's)"))
                    }
                    GroupRow("Height", supporting: c.inputs?.heightCm.map { "\(trimmed($0)) cm · " + cardioFrom(c.inputs?.heightFrom) } ?? "Not set") {
                        ask(NumberQuestion(key: "profile_height_cm", title: "Height (cm)", current: a?.profileHeightCm, range: 100...250, clear: "Clear (use Garmin's)"))
                    }
                    GroupRow("Maximum heart rate", supporting: c.hrMax?.value.map { "\(Int($0)) bpm · \(c.hrMax?.source ?? "")" } ?? "Not known yet") {
                        ask(NumberQuestion(key: "hr_max", title: "Maximum heart rate (bpm)", current: a?.hrMax.map(Double.init), range: 120...230, clear: "Clear (work it out from your runs)",
                                           hint: "Only if you know it from an all-out race finish or a test. Otherwise leave it: the app uses the higher of Garmin's setting and the highest you've held for a minute."))
                    }
                    GroupRow("Resting pulse, seated", supporting: a?.restingPulseSeated.map { "\($0) bpm · " + cardioFrom(a?.restingPulseSeatedAt) } ?? "Not set (HUNT uses your watch's overnight value)") {
                        ask(NumberQuestion(key: "resting_pulse_seated", title: "Resting pulse, seated (bpm)", current: a?.restingPulseSeated.map(Double.init), range: 30...120,
                                           clear: "Clear (use the watch's overnight value)",
                                           hint: "Sit quietly for 5 minutes. Take a fresh heart-rate measurement on your watch (not its daily resting heart rate), or count your pulse for 60 seconds. The study measured resting heart rate by ECG after 5 minutes of rest."))
                    }
                    GroupRow("Waist", supporting: a?.profileWaistCm.map { "\(trimmed($0)) cm · " + cardioFrom(a?.profileWaistCmAt) } ?? "Not set") {
                        ask(NumberQuestion(key: "profile_waist_cm", title: "Waist (cm)", current: a?.profileWaistCm, range: 50...200, clear: "Clear",
                                           hint: "Around your waist at the navel, standing relaxed, after breathing out."))
                    }
                    ForEach(c.huntQuestions) { q in
                        let (v, at) = huntAnswer(a, q.key)
                        GroupRow(q.title, supporting: q.options.first { $0.value == v }.map { $0.text + (at.map { " · answered \(Fmt.shortDate($0))" } ?? "") } ?? "Not answered") { choice = q.key }
                    }
                }
                choiceDialogs(c, a)
            }
        }
        .task { _ = await store.attempt { try await store.remoteSettings() } }
        .alert(number?.title ?? "", isPresented: Binding(get: { number != nil }, set: { if !$0 { number = nil } }), presenting: number) { q in
            TextField("", text: $numberText).keyboardType(.decimalPad)
            let v = Double(numberText.replacingOccurrences(of: ",", with: "."))
            Button("Save") { save(q.key, v.map { q.key == "hr_max" || q.key == "resting_pulse_seated" ? Int($0) as Any : $0 as Any }) }
                .disabled(v == nil || !q.range.contains(v!))
            if q.current != nil { Button(q.clear, role: .destructive) { save(q.key, nil) } }
            Button("Cancel", role: .cancel) {}
        } message: { q in
            Text(q.hint ?? "Between \(Int(q.range.lowerBound)) and \(Int(q.range.upperBound)).")
        }
    }

    @ViewBuilder private func choiceDialogs(_ c: Cardio, _ a: SettingsDto?) -> some View {
        Color.clear.frame(height: 0)
            .confirmationDialog("Your activity, last month", isPresented: Binding(get: { choice == "par" }, set: { if !$0 { choice = nil } }), titleVisibility: .visible) {
                ForEach(c.parScale, id: \.self) { o in Button("\(o.value). \(o.text)" + (o.value == a?.activityPar ? " ✓" : "")) { save("activity_par", o.value) } }
                if a?.activityPar != nil { Button("Clear", role: .destructive) { save("activity_par", nil) } }
            }
            .confirmationDialog(c.huntQuestions.first { $0.key == choice }?.title ?? "", isPresented: Binding(get: { c.huntQuestions.contains { $0.key == choice } },
                                                                                                                set: { if !$0 { choice = nil } }), titleVisibility: .visible) {
                if let q = c.huntQuestions.first(where: { $0.key == choice }) {
                    let cur = huntAnswer(a, q.key).0
                    ForEach(q.options, id: \.self) { o in Button(o.text + (o.value == cur ? " ✓" : "")) { save(q.key, o.value) } }
                    if cur != nil { Button("Clear", role: .destructive) { save(q.key, nil) } }
                }
            }
    }

    private func ask(_ q: NumberQuestion) { numberText = q.current.map(trimmed) ?? ""; number = q }

    /// Saves an answer for the cardio estimates, then recalculates.
    private func save(_ key: String, _ value: Any?) {
        number = nil; choice = nil
        store.act {
            try await store.saveSettings([key: value])
            try await store.refreshCardio()
        }
    }

    private func huntAnswer(_ a: SettingsDto?, _ key: String) -> (String?, String?) {
        switch key {
        case "hunt_frequency": (a?.huntFrequency, a?.huntFrequencyAt)
        case "hunt_intensity": (a?.huntIntensity, a?.huntIntensityAt)
        default: (a?.huntDuration, a?.huntDurationAt)
        }
    }
}

private struct CardioEvidence: View {
    var p: CardioPart
    @Environment(Nav.self) private var nav
    var body: some View {
        // Running performance is a different quantity (orange, like runs); an estimate without a value stays plain
        let tint: Tint = p.id == "performance" ? .orange : p.value != nil ? .teal : .neutral
        Tile(tint: tint, spacing: 4) {
            Text(p.title).font(Typo.titleSmall)
            HStack(alignment: .lastTextBaseline, spacing: 10) {
                if let v = p.value { Text("\(Int(v))").font(Typo.headlineLarge) }
                Text(p.headline ?? "").font(Typo.bodyLarge).foregroundStyle(p.value != nil ? Palette.onSurfaceVariant : Palette.onSurface)
            }
            if let c = p.comparison { Text([c.headline, c.detail].compactMap { $0 }.joined(separator: ". ")).font(Typo.bodyMedium) }
            if let d = p.detail?.nilIfEmpty { Text(d).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
            if let s = p.sensitivity { Text(s).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
            if let lo = p.leftOut, !lo.isEmpty {
                Text("Left out: " + lo.sorted { $0.key < $1.key }.map { "\($0.value) \($0.key)" }.joined(separator: ", ")).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            }
            if !p.points.isEmpty {
                Text("Runs used: " + p.points.suffix(8).map { "\(Fmt.shortDate($0.date)) \(Int($0.value))" }.joined(separator: ", ")).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            }
            if let c = p.caveat { Text(c).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant) }
            if let s = p.comparison?.source { Text("Reference: \(s)").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant) }
            if let id = p.sourceId { LinkButton(title: "Open the run") { nav.open(.run(id)) } }
        }
    }
}

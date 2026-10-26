import SwiftUI

/// Tiny trend line. band draws the personal reference range (q1..q3) behind it. Missing days are never drawn as zero:
/// points are placed by index, and a missing day breaks the line. Draws itself left to right once.
struct Sparkline: View {
    var values: [Double?]
    var band: (Double, Double)? = nil
    var color: Color = Palette.primary
    var description: String
    @State private var reveal: CGFloat = 0

    var body: some View {
        Canvas { ctx, size in
            let present = values.compactMap { $0 }
            guard present.count >= 2 else { return }
            var lo = present.min()!, hi = present.max()!
            if let b = band { lo = min(lo, b.0); hi = max(hi, b.1) }
            if hi == lo { hi += 1; lo -= 1 }
            let pad: CGFloat = 5
            let h = size.height - 2 * pad
            func y(_ v: Double) -> CGFloat { pad + h * CGFloat(1 - (v - lo) / (hi - lo)) }
            let step = (size.width - pad) / CGFloat(max(values.count - 1, 1))
            if let b = band {
                ctx.fill(Path(roundedRect: CGRect(x: 0, y: y(b.1), width: size.width, height: y(b.0) - y(b.1)), cornerRadius: 4), with: .color(Tint.teal.hue.opacity(0.14)))
            }
            // Each unbroken run of values: a smooth curve with a soft fill underneath
            var runs: [[CGPoint]] = [[]]
            for (i, v) in values.enumerated() {
                if let v { runs[runs.count - 1].append(CGPoint(x: CGFloat(i) * step, y: y(v))) } else { runs.append([]) }
            }
            var clipped = ctx
            clipped.clip(to: Path(CGRect(x: 0, y: 0, width: size.width * reveal, height: size.height)))
            for pts in runs where pts.count >= 2 {
                var line = Path()
                line.move(to: pts[0])
                for k in 1..<pts.count {
                    let m = CGPoint(x: (pts[k - 1].x + pts[k].x) / 2, y: (pts[k - 1].y + pts[k].y) / 2)
                    line.addQuadCurve(to: m, control: pts[k - 1])
                }
                line.addLine(to: pts.last!)
                var area = line
                area.addLine(to: CGPoint(x: pts.last!.x, y: size.height))
                area.addLine(to: CGPoint(x: pts[0].x, y: size.height))
                area.closeSubpath()
                clipped.fill(area, with: .color(color.opacity(0.16)))
                clipped.stroke(line, with: .color(color), style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
            }
            // Today's value: a dot with a soft halo, once the line has reached it
            if let last = values.last, let v = last {
                let c = CGPoint(x: CGFloat(values.count - 1) * step, y: y(v))
                let a = max(0, min(1, (reveal - 0.85) / 0.15))
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - 7, y: c.y - 7, width: 14, height: 14)), with: .color(color.opacity(0.22 * a)))
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - 4.5, y: c.y - 4.5, width: 9, height: 9)), with: .color(Palette.card.opacity(a)))
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - 3, y: c.y - 3, width: 6, height: 6)), with: .color(color.opacity(a)))
            }
        }
        .accessibilityLabel(description)
        .onAppear { withAnimation(.easeOut(duration: 0.7)) { reveal = 1 } }
    }
}

/// Time-series chart with a labelled y-axis (min/max) and x-axis in minutes. Nils break the line (gaps stay gaps).
/// invert puts lower values at the top (pace, where faster = fewer s/km). Scaled to the 2nd–98th percentile so start-up
/// sensor readings don't flatten the trace.
struct SeriesChart: View {
    var title: String
    var t: [Double]
    var values: [Double?]
    var color: Color
    var formatY: (Double) -> String
    var invert = false
    var description: String

    var body: some View {
        let present = values.compactMap { $0 }.sorted()
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
            if present.count < 2 || t.count < 2 {
                Text("No data recorded").font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant).padding(.vertical, 24)
            } else {
                let lo = present[Int(Double(present.count) * 0.02)]
                let hiRaw = present[Int(Double(present.count - 1) * 0.98)]
                let hi = hiRaw <= lo ? lo + 1 : hiRaw
                HStack(alignment: .top, spacing: 0) {
                    VStack(alignment: .leading) {
                        Text(formatY(invert ? lo : hi))
                        Spacer()
                        Text(formatY(invert ? hi : lo))
                    }
                    .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).frame(width: 56, height: 120, alignment: .leading)
                    Canvas { ctx, size in
                        let t0 = t.first!, span = max(t.last! - t0, 1)
                        func x(_ v: Double) -> CGFloat { CGFloat((v - t0) / span) * size.width }
                        func y(_ v: Double) -> CGFloat {
                            let f = CGFloat((min(max(v, lo), hi) - lo) / (hi - lo))
                            return size.height * (invert ? f : 1 - f)
                        }
                        let dash = StrokeStyle(lineWidth: 1, dash: [6, 6])
                        for gy in [0, size.height] {
                            var g = Path(); g.move(to: CGPoint(x: 0, y: gy)); g.addLine(to: CGPoint(x: size.width, y: gy))
                            ctx.stroke(g, with: .color(Palette.outlineVariant), style: dash)
                        }
                        var path = Path(), pen = false
                        for i in t.indices {
                            guard i < values.count, let v = values[i] else { pen = false; continue }
                            let p = CGPoint(x: x(t[i]), y: y(v))
                            if pen { path.addLine(to: p) } else { path.move(to: p) }
                            pen = true
                        }
                        ctx.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: 1.75, lineJoin: .round))
                    }
                    .frame(height: 120)
                    .accessibilityLabel(description)
                }
                HStack {
                    Text("0 min")
                    Spacer()
                    Text("\(Int((t.last! - t.first!) / 60)) min")
                }
                .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).padding(.leading, 56)
            }
        }
    }
}

struct WeekPoint: Hashable { var week: String; var value: Double; var newWatch = false }

/// Weekly values as labelled dots on a zoomed scale with gridlines every step (position encodes the value, so a
/// narrow range isn't exaggerated as bar lengths would be). Missing weeks are marked "gap" and a watch change "new
/// watch"; the line never crosses either. band shades a personal range.
struct WeeklyDotChart: View {
    var points: [WeekPoint]
    var decimals: Int
    var step: Double
    var caption: String
    var description: String
    var band: (Double, Double)? = nil

    private enum Slot { case week(WeekPoint), marker(String) }

    var body: some View {
        if points.count >= 2 {
            let slots: [Slot] = points.enumerated().flatMap { i, p -> [Slot] in
                var out: [Slot] = []
                if i > 0 && p.newWatch { out.append(.marker("new watch")) }
                else if i > 0 && Fmt.addDays(p.week, -7) != points[i - 1].week { out.append(.marker("gap")) }
                out.append(.week(p))
                return out
            }
            let weights: [CGFloat] = slots.map { if case .marker = $0 { 0.7 } else { 1 } }
            let all = points.map(\.value) + [band?.0, band?.1].compactMap { $0 }
            let lo = ((all.min()! - step / 2) / step).rounded(.down) * step
            let hi = ((all.max()! + step / 2) / step).rounded(.up) * step
            let fmt = "%.\(decimals)f"
            VStack(alignment: .leading, spacing: 4) {
                Canvas { ctx, size in
                    let gap: CGFloat = 6, axis: CGFloat = 28
                    let plotW = size.width - axis
                    let unit = (plotW - gap * CGFloat(slots.count - 1)) / weights.reduce(0, +)
                    var x0: CGFloat = 0
                    let centers: [CGFloat] = weights.map { w in defer { x0 += w * unit + gap }; return x0 + w * unit / 2 }
                    let top: CGFloat = 26, bottom = size.height - 8
                    func y(_ v: Double) -> CGFloat { bottom - CGFloat((v - lo) / (hi - lo)) * (bottom - top) }
                    if let (a, b) = band { ctx.fill(Path(CGRect(x: 0, y: y(b), width: plotW, height: y(a) - y(b))), with: .color(Palette.primary.opacity(0.08))) }
                    var g = lo
                    while g <= hi + 1e-9 {
                        var line = Path(); line.move(to: CGPoint(x: 0, y: y(g))); line.addLine(to: CGPoint(x: plotW, y: y(g)))
                        ctx.stroke(line, with: .color(Palette.outlineVariant), lineWidth: 1)
                        ctx.draw(Text(String(format: "%.0f", g)).font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant),
                                 at: CGPoint(x: size.width, y: y(g)), anchor: .trailing)
                        g += step
                    }
                    for (k, s) in slots.enumerated() {
                        switch s {
                        case .marker(let m):
                            ctx.draw(Text(m.replacingOccurrences(of: " ", with: "\n")).font(Typo.labelSmall).foregroundStyle(Palette.outline),
                                     at: CGPoint(x: centers[k], y: bottom), anchor: .bottom)
                        case .week(let p):
                            if k > 0, case .week(let prev) = slots[k - 1] {
                                var l = Path(); l.move(to: CGPoint(x: centers[k - 1], y: y(prev.value))); l.addLine(to: CGPoint(x: centers[k], y: y(p.value)))
                                ctx.stroke(l, with: .color(Palette.primary.opacity(0.45)), lineWidth: 2)
                            }
                        }
                    }
                    for (k, s) in slots.enumerated() {
                        guard case .week(let p) = s else { continue }
                        let last = k == slots.count - 1
                        let c = CGPoint(x: centers[k], y: y(p.value))
                        let r: CGFloat = last ? 7 : 5
                        ctx.fill(Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: 2 * r, height: 2 * r)), with: .color(last ? Palette.primary : Palette.primary.opacity(0.7)))
                        ctx.draw(Text(String(format: fmt, p.value)).font(last ? Typo.labelLarge : Typo.labelSmall)
                                    .foregroundStyle(last ? Palette.primary : Palette.onSurfaceVariant), at: CGPoint(x: c.x, y: c.y - 8), anchor: .bottom)
                    }
                }
                .frame(height: 120)
                .accessibilityLabel(description + ": " + points.map { "\($0.week) \(String(format: fmt, $0.value))" }.joined(separator: ", "))
                // The month is named only where it changes (6 Jul, 13, 20, … 3 Aug), so the labels fit
                HStack(spacing: 6) {
                    ForEach(Array(slots.enumerated()), id: \.offset) { k, s in
                        Group {
                            if case .week(let p) = s {
                                let prevMonth = slots[..<k].reversed().compactMap { if case .week(let q) = $0 { return String(q.week.prefix(7)) } else { return nil } }.first
                                Text(prevMonth == String(p.week.prefix(7)) ? "\(Fmt.dayOfMonth(p.week))" : Fmt.shortDate(p.week).split(separator: " ").dropFirst().joined(separator: " "))
                            } else { Text("") }
                        }
                        .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).lineLimit(1).minimumScaleFactor(0.7)
                        .frame(maxWidth: .infinity)
                        .layoutPriority(Double(weights[k]))
                    }
                }
                .padding(.trailing, 28)
                Text(caption + (slots.contains { if case .marker("gap") = $0 { true } else { false } } ? " · gap = weeks without a reading" : "")
                     + (band != nil ? " · shaded = your usual range" : ""))
                    .font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }
}

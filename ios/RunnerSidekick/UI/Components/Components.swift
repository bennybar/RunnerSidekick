import SwiftUI

// MARK: Tiles

/// A card: rounded, with a flat tint for its kind of data, a thin bright edge and, in light mode, a faint glow of its
/// own colour. onTap makes the whole tile a button.
struct Tile<Content: View>: View {
    var tint: Tint = .neutral
    var padding: EdgeInsets = EdgeInsets(top: 16, leading: 18, bottom: 16, trailing: 18)
    var spacing: CGFloat = 8
    var onTap: (() -> Void)? = nil
    @ViewBuilder var content: Content
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 26, style: .continuous)
        let edge: Color = scheme == .dark ? (tint == .neutral ? .white.opacity(0.07) : tint.hue.opacity(0.22)) : .white.opacity(0.9)
        let glow = tint == .neutral ? Color(hex: 0x1E2846) : tint.hue
        let body = VStack(alignment: .leading, spacing: spacing) { content }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(padding)
            .background(shape.fill(tint.fill))
            .overlay(shape.strokeBorder(edge, lineWidth: 1))
            .shadow(color: scheme == .dark ? .clear : glow.opacity(0.13), radius: 6, y: 2)
            .contentShape(shape)
        if let onTap {
            Button(action: onTap) { body }.buttonStyle(PressStyle())
        } else {
            body
        }
    }
}

/// A light press: the pressed tile dims a touch, so a tap reads without a heavy highlight.
struct PressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.opacity(configuration.isPressed ? 0.7 : 1).animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// A small uppercase label above a group of tiles ("READINGS", "LATEST RUN").
struct SectionLabel: View {
    var text: String
    var body: some View {
        Text(text.uppercased()).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
            .padding(.leading, 8).padding(.top, 10)
            .accessibilityAddTraits(.isHeader)
    }
}

/// A titled list of rows in one card (tinted), rows separated by thin lines.
struct CardGroup<Content: View>: View {
    var title: String? = nil
    var tint: Tint = .neutral
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let title { SectionLabel(text: title) }
            Tile(tint: tint, padding: EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0), spacing: 0) {
                Group(subviews: content) { rows in
                    ForEach(Array(rows.enumerated()), id: \.offset) { i, row in
                        if i > 0 { Divider().overlay(Palette.onSurface.opacity(0.07)).padding(.horizontal, 18) }
                        row
                    }
                }
            }
        }
    }
}

/// A row in a CardGroup. action makes it a button (with a chevron unless it has its own trailing view).
struct GroupRow<Trailing: View>: View {
    var headline: String
    var supporting: String? = nil
    var overline: String? = nil
    var icon: String? = nil
    var shape: BadgeShape = .circle
    var accent: String? = nil
    var action: (() -> Void)? = nil
    @ViewBuilder var trailing: Trailing

    var body: some View {
        let row = HStack(spacing: 14) {
            if let icon {
                let a = Tint.accent(accent)
                ShapeBadge(symbol: icon, shape: shape, size: 36, container: a.map { $0.hue.opacity(0.24) } ?? Palette.cardHighest,
                           content: a?.ink ?? Palette.onSurface, iconSize: 18)
            }
            VStack(alignment: .leading, spacing: 2) {
                if let overline { Text(overline).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant) }
                Text(headline).font(Typo.bodyLarge).foregroundStyle(Palette.onSurface).lineLimit(2)
                if let supporting, !supporting.isEmpty { Text(supporting).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if Trailing.self != EmptyView.self { trailing }
            else if action != nil { Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(Palette.onSurfaceVariant) }
        }
        .padding(.horizontal, 18).padding(.vertical, 10)
        .frame(minHeight: 56)
        .contentShape(Rectangle())
        if let action { Button(action: action) { row }.buttonStyle(PressStyle()) } else { row }
    }
}

extension GroupRow where Trailing == EmptyView {
    init(_ headline: String, supporting: String? = nil, overline: String? = nil, icon: String? = nil, shape: BadgeShape = .circle,
         accent: String? = nil, action: (() -> Void)? = nil) {
        self.init(headline: headline, supporting: supporting, overline: overline, icon: icon, shape: shape, accent: accent, action: action) { EmptyView() }
    }
}

/// Free content inside a CardGroup, padded like a row.
struct GroupCustom<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 8) { content }.frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 18).padding(.vertical, 16)
    }
}

// MARK: Chips and buttons

/// Good / OK / Low (or Info) next to a plain-language check.
struct VerdictChip: View {
    var verdict: String?
    var label: String? = nil
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        let a = scheme == .dark ? 0.28 : 0.20
        let (text, bg, fg): (String, Color, Color) = switch verdict {
        case "good": ("Good", Tint.green.hue.opacity(a), Palette.onSurface)
        case "ok": ("OK", Tint.amber.hue.opacity(a), Palette.onSurface)
        case "low": ("Low", Tint.pink.hue.opacity(a), Palette.onSurface)
        case "info": ("Info", Palette.cardHighest, Palette.onSurfaceVariant)
        default: ("—", Palette.cardHighest, Palette.onSurfaceVariant)
        }
        Text(label ?? text).font(Typo.labelLarge).foregroundStyle(fg)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(Capsule().fill(bg))
            .fixedSize()
    }
}

/// A small rounded label on a tile: a distance, a status, a day.
struct TagChip: View {
    var text: String
    var container: Color = Palette.card.opacity(0.75)
    var content: Color = Palette.onSurface
    var body: some View {
        Text(text).font(Typo.labelLarge).foregroundStyle(content)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(container))
            .fixedSize()
    }
}

/// One choice from a few, as a connected group: the chosen one fills in and rounds (the Android app's Expressive
/// button group). selected nil shows none chosen.
struct ChoiceGroup: View {
    var labels: [String]
    var selected: Int?
    var enabled = true
    var onSelect: (Int) -> Void

    var body: some View {
        HStack(spacing: 2) {
            ForEach(Array(labels.enumerated()), id: \.offset) { i, l in
                let on = selected == i
                let inner: CGFloat = on ? 20 : 6
                let shape = UnevenRoundedRectangle(
                    topLeadingRadius: i == 0 || on ? 20 : inner, bottomLeadingRadius: i == 0 || on ? 20 : inner,
                    bottomTrailingRadius: i == labels.count - 1 || on ? 20 : inner, topTrailingRadius: i == labels.count - 1 || on ? 20 : inner,
                    style: .continuous)
                Button { onSelect(i) } label: {
                    Text(l).font(Typo.labelLarge).lineLimit(1).minimumScaleFactor(0.8)
                        .foregroundStyle(on ? Palette.onPrimary : Palette.onSurface)
                        .frame(maxWidth: .infinity, minHeight: 40)
                        .padding(.horizontal, 6)
                        .background(shape.fill(on ? Palette.primary : Palette.cardHighest))
                        .contentShape(shape)
                }
                .buttonStyle(PressStyle())
                .accessibilityAddTraits(on ? [.isSelected, .isButton] : .isButton)
            }
        }
        .animation(.spring(response: 0.3, dampingFraction: 0.75), value: selected)
        .disabled(!enabled)
        .opacity(enabled ? 1 : 0.5)
    }
}

/// Options that each turn on and off (or one choice that can be cleared): toggle buttons whose shape changes when on.
struct ToggleRow: View {
    var labels: [String]
    var checked: (Int) -> Bool
    var onToggle: (Int) -> Void

    var body: some View {
        FlowLayout(spacing: 8, lineSpacing: 6) {
            ForEach(Array(labels.enumerated()), id: \.offset) { i, l in
                let on = checked(i)
                Button { onToggle(i) } label: {
                    Text(l).font(Typo.labelLarge)
                        .foregroundStyle(on ? Palette.onPrimary : Palette.onSurface)
                        .padding(.horizontal, 16).frame(minHeight: 40)
                        .background(RoundedRectangle(cornerRadius: on ? 12 : 20, style: .continuous).fill(on ? Palette.primary : Palette.cardHighest))
                }
                .buttonStyle(PressStyle())
                .accessibilityAddTraits(on ? [.isSelected, .isButton] : .isButton)
                .animation(.spring(response: 0.3, dampingFraction: 0.7), value: on)
            }
        }
    }
}

/// Wraps its children onto as many lines as they need.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    var lineSpacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, line: CGFloat = 0, widest: CGFloat = 0
        for s in subviews {
            let sz = s.sizeThatFits(.unspecified)
            if x > 0 && x + sz.width > width { y += line + lineSpacing; x = 0; line = 0 }
            x += sz.width + spacing
            line = max(line, sz.height)
            widest = max(widest, x - spacing)
        }
        return CGSize(width: proposal.width ?? widest, height: y + line)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, line: CGFloat = 0
        for s in subviews {
            let sz = s.sizeThatFits(.unspecified)
            if x > bounds.minX && x + sz.width > bounds.maxX { y += line + lineSpacing; x = bounds.minX; line = 0 }
            s.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(sz))
            x += sz.width + spacing
            line = max(line, sz.height)
        }
    }
}

/// A filled or tonal button in the app's style.
struct PillButton: View {
    var title: String
    var icon: String? = nil
    var filled = true
    var busy = false
    var action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if busy { ProgressView().controlSize(.small).tint(filled ? Palette.onPrimary : Palette.onSurface) }
                else if let icon { Image(systemName: icon) }
                Text(title).font(Typo.labelLarge)
            }
            .foregroundStyle(filled ? Palette.onPrimary : Palette.onSurface)
            .padding(.horizontal, 18).frame(minHeight: 44)
            .background(Capsule().fill(filled ? Palette.primary : Palette.cardHighest))
        }
        .buttonStyle(PressStyle())
    }
}

/// An outlined full-width button (the Android app's OutlinedButton).
struct OutlineButton: View {
    var title: String
    var action: () -> Void
    var body: some View {
        Button(action: action) {
            Text(title).font(Typo.labelLarge).foregroundStyle(Palette.onSurface)
                .frame(maxWidth: .infinity, minHeight: 48)
                .overlay(Capsule().strokeBorder(Palette.outline, lineWidth: 1))
                .contentShape(Capsule())
        }
        .buttonStyle(PressStyle())
    }
}

/// A text-only button (the Android app's TextButton).
struct LinkButton: View {
    var title: String
    var action: () -> Void
    var body: some View {
        Button(action: action) { Text(title).font(Typo.labelLarge).foregroundStyle(Palette.onSurface).padding(.vertical, 8) }
            .buttonStyle(PressStyle())
    }
}

// MARK: Shapes and badges

/// The Expressive shapes the Android app uses for icon badges: rounded scallops with n lobes, a heart, a circle.
enum BadgeShape {
    case circle, cookie4, cookie6, cookie9, cookie12, sunny, clover4, softBurst, burst, flower, heart

    var shape: AnyShape {
        switch self {
        case .circle: AnyShape(Circle())
        case .cookie4: AnyShape(Scallop(lobes: 4, depth: 0.16))
        case .cookie6: AnyShape(Scallop(lobes: 6, depth: 0.10))
        case .cookie9: AnyShape(Scallop(lobes: 9, depth: 0.07))
        case .cookie12: AnyShape(Scallop(lobes: 12, depth: 0.06))
        case .sunny: AnyShape(Scallop(lobes: 8, depth: 0.11, pointy: true))
        case .clover4: AnyShape(Scallop(lobes: 4, depth: 0.30))
        case .softBurst: AnyShape(Scallop(lobes: 10, depth: 0.12, pointy: true))
        case .burst: AnyShape(Scallop(lobes: 12, depth: 0.16, pointy: true))
        case .flower: AnyShape(Scallop(lobes: 8, depth: 0.22))
        case .heart: AnyShape(HeartShape())
        }
    }
}

/// A circle with n rounded lobes around it (cookie, clover, flower), or soft points (sunny, burst).
struct Scallop: Shape {
    var lobes: Int
    var depth: CGFloat
    var pointy = false

    func path(in rect: CGRect) -> Path {
        let c = CGPoint(x: rect.midX, y: rect.midY)
        let r = min(rect.width, rect.height) / 2
        var p = Path()
        let steps = 240
        for i in 0...steps {
            let t = CGFloat(i) / CGFloat(steps) * 2 * .pi
            let wave = pointy ? pow(abs(cos(CGFloat(lobes) * t / 2)), 1.6) * 2 - 1 : cos(CGFloat(lobes) * t)
            let rr = r * (1 - depth) + r * depth * wave
            let pt = CGPoint(x: c.x + rr * cos(t - .pi / 2), y: c.y + rr * sin(t - .pi / 2))
            i == 0 ? p.move(to: pt) : p.addLine(to: pt)
        }
        p.closeSubpath()
        return p
    }
}

struct HeartShape: Shape {
    func path(in rect: CGRect) -> Path {
        let w = rect.width, h = rect.height
        var p = Path()
        p.move(to: CGPoint(x: rect.midX, y: rect.minY + h * 0.92))
        p.addCurve(to: CGPoint(x: rect.minX + w * 0.02, y: rect.minY + h * 0.36),
                   control1: CGPoint(x: rect.minX + w * 0.30, y: rect.minY + h * 0.78), control2: CGPoint(x: rect.minX + w * 0.02, y: rect.minY + h * 0.60))
        p.addCurve(to: CGPoint(x: rect.midX, y: rect.minY + h * 0.20),
                   control1: CGPoint(x: rect.minX + w * 0.02, y: rect.minY + h * 0.06), control2: CGPoint(x: rect.minX + w * 0.40, y: rect.minY + h * 0.02))
        p.addCurve(to: CGPoint(x: rect.maxX - w * 0.02, y: rect.minY + h * 0.36),
                   control1: CGPoint(x: rect.maxX - w * 0.40, y: rect.minY + h * 0.02), control2: CGPoint(x: rect.maxX - w * 0.02, y: rect.minY + h * 0.06))
        p.addCurve(to: CGPoint(x: rect.midX, y: rect.minY + h * 0.92),
                   control1: CGPoint(x: rect.maxX - w * 0.02, y: rect.minY + h * 0.60), control2: CGPoint(x: rect.maxX - w * 0.30, y: rect.minY + h * 0.78))
        return p
    }
}

/// An icon on an Expressive shape, tinted with a container colour.
struct ShapeBadge: View {
    var symbol: String
    var shape: BadgeShape
    var size: CGFloat = 36
    var container: Color = Palette.cardHighest
    var content: Color = Palette.onSurface
    var iconSize: CGFloat = 18

    var body: some View {
        ZStack {
            shape.shape.fill(container)
            Image(systemName: symbol).font(.system(size: iconSize, weight: .medium)).foregroundStyle(content)
                .offset(y: shape == .heart ? -size * 0.04 : 0)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

// MARK: Numbers

/// A big number with an optional unit beside it.
struct BigValue: View {
    var value: String
    var unit: String? = nil
    var font: Font = Typo.displayMedium
    var body: some View {
        HStack(alignment: .lastTextBaseline, spacing: 6) {
            Text(value).font(font).lineLimit(1).minimumScaleFactor(0.6)
            if let unit { Text(unit).font(Typo.titleMedium).foregroundStyle(Palette.onSurfaceVariant) }
        }
    }
}

/// Big-numeral tile for a reading, tinted for its kind of data. Colour is never the only signal: the status line has
/// text and an icon, and a flagged reading also says so in words.
struct MetricTile<ChartView: View>: View {
    var label: String
    var value: String
    var unit: String?
    var status: String
    var statusIcon: String?
    var flagged: Bool
    var tint: Tint = .neutral
    var badge: (String, BadgeShape)? = nil
    var onTap: () -> Void
    @ViewBuilder var chart: ChartView

    var body: some View {
        let shown: Tint = flagged ? .orange : tint
        Tile(tint: shown, spacing: 4, onTap: onTap) {
            HStack {
                Text(label).font(Typo.labelLarge).foregroundStyle(Palette.onSurface).frame(maxWidth: .infinity, alignment: .leading)
                if let (icon, shape) = badge {
                    ShapeBadge(symbol: icon, shape: shape, size: 30, container: shown.hue.opacity(0.24), content: shown.ink, iconSize: 14)
                }
            }
            Spacer(minLength: 0)
            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(value).font(Typo.headlineMedium).foregroundStyle(Palette.onSurface).lineLimit(1).minimumScaleFactor(0.7)
                if let unit { Text(unit).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
            }
            HStack(spacing: 4) {
                if let statusIcon { Image(systemName: statusIcon).font(.caption).foregroundStyle(Palette.onSurfaceVariant) }
                Text(status).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant).lineLimit(2)
            }
            chart.padding(.top, 8)
        }
        .frame(minHeight: 104)
    }
}

/// A thin rounded progress bar.
struct ProgressBar: View {
    var fraction: Double
    var fill: Color
    var body: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(Palette.onSurface.opacity(0.08))
                Capsule().fill(fill).frame(width: g.size.width * min(1, max(0, fraction)))
            }
        }
        .frame(height: 6)
    }
}

// MARK: Pages and states

/// The headline number of a detail page, with a line or two under it.
struct PageHead: View {
    var value: String
    var unit: String?
    var lines: [String?] = []
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            BigValue(value: value, unit: unit)
            ForEach(Array(lines.compactMap { $0 }.enumerated()), id: \.offset) { _, l in Text(l).font(Typo.bodyLarge) }
        }
        .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A detail page: a scrolling column of tiles under a title, pushed onto the tab's navigation.
struct DetailPage<Content: View>: View {
    var title: String
    @ViewBuilder var content: Content
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) { content }
                .padding(.horizontal, 12).padding(.top, 8).padding(.bottom, 32)
        }
        .background(Palette.background)
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// Small grey text under a tile.
struct Footnote: View {
    var text: String
    var body: some View { Text(text).font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant).padding(.horizontal, 8) }
}

struct EmptyState: View {
    var icon: String
    var title: String
    var message: String
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon).font(.system(size: 44)).foregroundStyle(Palette.primary)
            Text(title).font(Typo.titleLarge).multilineTextAlignment(.center)
            Text(message).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant).multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity).padding(32)
    }
}

/// The plain verdict for a reading (how good it is) and what it means.
struct NoteBlock: View {
    var note: ReadingNote
    var body: some View {
        Tile(tint: .teal, spacing: 6) {
            Text(note.verdict).font(Typo.titleMedium)
            Text(note.meaning).font(Typo.bodyMedium)
        }
    }
}

/// The one line to read if you read nothing else.
struct Tldr: View {
    var text: String
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text("TL;DR").font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
            Text(text).font(Typo.titleMedium)
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.onSurface.opacity(0.05)))
    }
}

struct Bullet: View {
    var text: String
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text("•").foregroundStyle(Palette.onSurfaceVariant)
            Text(text)
        }
        .font(Typo.bodyMedium)
    }
}

/// "Demo data": the backend is serving its synthetic fixture.
struct DemoBadge: View {
    var body: some View {
        Label("Demo data", systemImage: "flask").font(Typo.labelMedium)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(Capsule().fill(Tint.pink.hue.opacity(0.22)))
    }
}

/// The screen's background colour behind everything.
extension View {
    func screenBackground() -> some View { background(Palette.background.ignoresSafeArea()) }
}

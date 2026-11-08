import SwiftUI
import UIKit

extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255, opacity: alpha)
    }
    /// One colour in light mode, another in dark.
    static func dyn(_ light: UInt32, _ dark: UInt32) -> Color {
        Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(Color(hex: dark)) : UIColor(Color(hex: light)) })
    }
}

/// iOS's own grouped colours (they follow light/dark and Increase Contrast); the accent is the icon's teal. Colour lives
/// on the tiles, never the background.
enum Palette {
    static let background = Color(.systemGroupedBackground)
    static let onSurface = Color(.label)
    static let onSurfaceVariant = Color(.secondaryLabel)
    static let card = Color(.secondarySystemGroupedBackground)
    static let cardHigh = Color(.secondarySystemGroupedBackground)
    static let cardHighest = Color(.tertiarySystemFill)
    static let primary = Color.dyn(0x0A8A85, 0x18A79D)
    static let onPrimary = Color.white
    static let outline = Color(.systemGray3)
    static let outlineVariant = Color(.separator)
    static let error = Color(.systemRed)
}

/// The tile colours, one per kind of data: hue tints the tile, ink is the readable colour for text and icons on it.
/// Colour is never the only signal; text always says it too.
enum Tint {
    case neutral, green, orange, blue, purple, teal, pink, indigo, amber

    private var hues: (UInt32, UInt32, UInt32) {
        switch self {
        case .neutral: (0x8E8E95, 0x1C1C1E, 0xF2F2F4)
        case .green: (0x34C778, 0x1E7A45, 0x5BD68E)    // readiness, recovery, good
        case .orange: (0xFF8C46, 0x9A4310, 0xFF9A5C)   // runs, training, the next run
        case .blue: (0x4678FA, 0x2A56C9, 0x8AAEFF)     // fitness
        case .purple: (0x9664F5, 0x6A3FC2, 0xC0A2FF)   // healthy habits, reports
        case .teal: (0x1EB4AA, 0x136B5F, 0x52D6C8)     // VO2 max, cardio
        case .pink: (0xF0506E, 0xB4233F, 0xFF8AA0)     // heart rate, attention
        case .indigo: (0x5F5AE6, 0x3F3AB8, 0xA6A2FF)   // sleep, overnight
        case .amber: (0xF0AA28, 0x8A5A00, 0xFFCB66)    // focus, records, race
        }
    }
    var hue: Color { Color(hex: hues.0) }
    /// Readable text/icon colour on this tint, in the current mode.
    var ink: Color { Color.dyn(hues.1, hues.2) }

    /// The tile's fill: an even wash of its hue over the plain card colour (neutral is the plain card).
    var fill: Color {
        if self == .neutral { return Palette.card }
        let h = hues.0
        return Color(UIColor { t in
            let dark = t.userInterfaceStyle == .dark
            let card = dark ? UIColor(Color(hex: 0x1C1C1E)) : .white
            return Tint.blend(UIColor(Color(hex: h)), over: card, alpha: dark ? 0.18 : 0.20)
        })
    }

    static func blend(_ top: UIColor, over base: UIColor, alpha: CGFloat) -> UIColor {
        var (r1, g1, b1, a1): (CGFloat, CGFloat, CGFloat, CGFloat) = (0, 0, 0, 0)
        var (r2, g2, b2, a2): (CGFloat, CGFloat, CGFloat, CGFloat) = (0, 0, 0, 0)
        top.getRed(&r1, green: &g1, blue: &b1, alpha: &a1)
        base.getRed(&r2, green: &g2, blue: &b2, alpha: &a2)
        return UIColor(red: r1 * alpha + r2 * (1 - alpha), green: g1 * alpha + g2 * (1 - alpha), blue: b1 * alpha + b2 * (1 - alpha), alpha: 1)
    }

    /// Badge colours by insight/coach category, from the tile hues.
    static func accent(_ category: String?) -> Tint? {
        switch category {
        case "training", "intensity", "pacing": .orange
        case "sleep": .indigo
        case "recovery": .pink
        case "running": .teal
        case "fitness": .blue
        case "habits": .purple
        default: nil
        }
    }
}

/// Semantic colours for data viz. Always paired with text so meaning never relies on colour alone.
enum DataColors {
    static let heartRate = Tint.pink.ink
    static let pace = Color.dyn(0xE7742E, 0xFF9A5C)
    static let attention = Tint.orange.ink
}

/// San Francisco on iOS's text styles, so Dynamic Type scales everything; big numbers in SF Rounded, as Apple's
/// health and fitness apps show them. The names keep the Android type scale's, so screens read the same in both.
enum Typo {
    private static func numbers(_ size: CGFloat, relativeTo style: Font.TextStyle) -> Font {
        .system(size: UIFontMetrics(forTextStyle: style.uiKit).scaledValue(for: size), weight: .bold, design: .rounded)
    }
    static let displayMedium = numbers(44, relativeTo: .largeTitle)
    static let displaySmall = numbers(34, relativeTo: .largeTitle)
    static let headlineLarge = Font.largeTitle.bold()
    static let headlineMedium = numbers(26, relativeTo: .title)
    static let headlineSmall = Font.title2.bold()
    static let titleLarge = Font.title2.bold()
    static let titleMedium = Font.headline
    static let titleSmall = Font.subheadline.weight(.semibold)
    static let bodyLarge = Font.body
    static let bodyMedium = Font.subheadline
    static let bodySmall = Font.footnote
    static let labelLarge = Font.subheadline.weight(.semibold)
    static let labelMedium = Font.caption.weight(.semibold)
    static let labelSmall = Font.caption2
}

private extension Font.TextStyle {
    var uiKit: UIFont.TextStyle {
        switch self {
        case .largeTitle: .largeTitle
        case .title: .title1
        case .title2: .title2
        case .title3: .title3
        case .headline: .headline
        case .subheadline: .subheadline
        case .callout: .callout
        case .footnote: .footnote
        case .caption: .caption1
        case .caption2: .caption2
        default: .body
        }
    }
}

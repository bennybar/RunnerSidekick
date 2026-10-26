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

/// The neutral base (light grey / true black) with plain cards; colour lives on the tiles, never the background.
/// The Android app's colour scheme, one for one.
enum Palette {
    static let background = Color.dyn(0xF3F4F7, 0x000000)
    static let onSurface = Color.dyn(0x1C1C1E, 0xF2F2F4)
    static let onSurfaceVariant = Color.dyn(0x55555C, 0xA1A1A8)
    static let card = Color.dyn(0xFFFFFF, 0x1C1C1E)           // surfaceContainer
    static let cardHigh = Color.dyn(0xFFFFFF, 0x232326)       // surfaceContainerHigh
    static let cardHighest = Color.dyn(0xE9E9EE, 0x2C2C30)    // surfaceContainerHighest
    static let primary = Color.dyn(0x1C1C1E, 0xF2F2F4)
    static let onPrimary = Color.dyn(0xFFFFFF, 0x000000)
    static let outline = Color.dyn(0x8E8E95, 0x7C7C84)
    static let outlineVariant = Color.dyn(0xD4D4DA, 0x3A3A3F)
    static let error = Color.dyn(0xB3261E, 0xF2B8B5)
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

/// Google Sans throughout (a variable font, 400–700), on the Material type scale the Android app uses.
enum Typo {
    static func sans(_ size: CGFloat, _ weight: Font.Weight = .regular, relativeTo style: Font.TextStyle = .body) -> Font {
        .custom("Google Sans", size: size, relativeTo: style).weight(weight)
    }
    static let displayMedium = sans(44, .bold, relativeTo: .largeTitle)
    static let displaySmall = sans(34, .bold, relativeTo: .largeTitle)
    static let headlineLarge = sans(32, .bold, relativeTo: .largeTitle)
    static let headlineMedium = sans(26, .bold, relativeTo: .title)
    static let headlineSmall = sans(22, .bold, relativeTo: .title2)
    static let titleLarge = sans(22, .bold, relativeTo: .title2)
    static let titleMedium = sans(16, .semibold, relativeTo: .headline)
    static let titleSmall = sans(14, .semibold, relativeTo: .subheadline)
    static let bodyLarge = sans(16, .regular, relativeTo: .body)
    static let bodyMedium = sans(14, .regular, relativeTo: .callout)
    static let bodySmall = sans(12, .regular, relativeTo: .footnote)
    static let labelLarge = sans(14, .semibold, relativeTo: .subheadline)
    static let labelMedium = sans(12, .semibold, relativeTo: .caption)
    static let labelSmall = sans(11, .medium, relativeTo: .caption2)
}

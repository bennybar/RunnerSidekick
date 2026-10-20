package com.bennybar.runnersidekick.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialExpressiveTheme
import androidx.compose.material3.MotionScheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bennybar.runnersidekick.R

// A clean, neutral base (light grey / true black) with plain cards; colour lives on the tiles, one hue per kind of
// data (see Tint), never on the background
private val Light = lightColorScheme(
    primary = Color(0xFF1C1C1E), onPrimary = Color.White, primaryContainer = Color(0xFFE6E6EB), onPrimaryContainer = Color(0xFF1C1C1E),
    secondary = Color(0xFF55555C), onSecondary = Color.White, secondaryContainer = Color(0xFFE6E6EB), onSecondaryContainer = Color(0xFF1C1C1E),
    tertiary = Color(0xFFB4501A), onTertiary = Color.White, tertiaryContainer = Color(0xFFFFE3D1), onTertiaryContainer = Color(0xFF6B2A05),
    background = Color(0xFFF3F4F7), onBackground = Color(0xFF1C1C1E), surface = Color(0xFFF3F4F7), onSurface = Color(0xFF1C1C1E),
    onSurfaceVariant = Color(0xFF55555C), surfaceContainerLowest = Color.White, surfaceContainerLow = Color(0xFFF8F8FA),
    surfaceContainer = Color.White, surfaceContainerHigh = Color.White, surfaceContainerHighest = Color(0xFFE9E9EE),
    outline = Color(0xFF8E8E95), outlineVariant = Color(0xFFD4D4DA),
)
private val Dark = darkColorScheme(
    primary = Color(0xFFF2F2F4), onPrimary = Color.Black, primaryContainer = Color(0xFF2C2C30), onPrimaryContainer = Color(0xFFF2F2F4),
    secondary = Color(0xFFA1A1A8), onSecondary = Color.Black, secondaryContainer = Color(0xFF2C2C30), onSecondaryContainer = Color(0xFFF2F2F4),
    tertiary = Color(0xFFFF9A5C), onTertiary = Color(0xFF3A1600), tertiaryContainer = Color(0xFF42230F), onTertiaryContainer = Color(0xFFFFC6A3),
    background = Color.Black, onBackground = Color(0xFFF2F2F4), surface = Color.Black, onSurface = Color(0xFFF2F2F4),
    onSurfaceVariant = Color(0xFFA1A1A8), surfaceContainerLowest = Color(0xFF0B0B0C), surfaceContainerLow = Color(0xFF111113),
    surfaceContainer = Color(0xFF1C1C1E), surfaceContainerHigh = Color(0xFF232326), surfaceContainerHighest = Color(0xFF2C2C30),
    outline = Color(0xFF7C7C84), outlineVariant = Color(0xFF3A3A3F),
)

/** Light, dark, or following the phone. */
enum class Appearance(val label: String) { SYSTEM("System"), LIGHT("Light"), DARK("Dark");
    companion object { fun of(name: String?) = entries.firstOrNull { it.name == name } ?: SYSTEM }
}

/** The tile colours, one per kind of data: [hue] tints the tile, [light]/[dark] is the readable ink for text and
 *  icons on it in each mode. Colour is never the only signal; text always says it too. */
enum class Tint(val hue: Color, val light: Color, val dark: Color) {
    NEUTRAL(Color(0xFF8E8E95), Color(0xFF1C1C1E), Color(0xFFF2F2F4)),
    GREEN(Color(0xFF34C778), Color(0xFF1E7A45), Color(0xFF5BD68E)),   // readiness, recovery, good
    ORANGE(Color(0xFFFF8C46), Color(0xFF9A4310), Color(0xFFFF9A5C)),  // runs, training, the next run
    BLUE(Color(0xFF4678FA), Color(0xFF2A56C9), Color(0xFF8AAEFF)),    // fitness
    PURPLE(Color(0xFF9664F5), Color(0xFF6A3FC2), Color(0xFFC0A2FF)),  // healthy habits, reports
    TEAL(Color(0xFF1EB4AA), Color(0xFF136B5F), Color(0xFF52D6C8)),    // VO2 max, cardio
    PINK(Color(0xFFF0506E), Color(0xFFB4233F), Color(0xFFFF8AA0)),    // heart rate, attention
    INDIGO(Color(0xFF5F5AE6), Color(0xFF3F3AB8), Color(0xFFA6A2FF)),  // sleep, overnight
    AMBER(Color(0xFFF0AA28), Color(0xFF8A5A00), Color(0xFFFFCB66)),   // focus, records, race
}

/** Whether the app is drawing dark right now (for tiles and anything else that differs by mode). */
val LocalDark = staticCompositionLocalOf { false }

/** Readable text/icon colour for [t] in the current mode. */
@Composable
@ReadOnlyComposable
fun ink(t: Tint): Color = if (LocalDark.current) t.dark else t.light

/** Semantic colours for data viz. Always paired with text/icons so meaning never relies on colour alone. */
@Immutable
data class DataColors(val heartRate: Color, val pace: Color, val attention: Color, val neutral: Color, val band: Color)

val LocalDataColors = staticCompositionLocalOf { DataColors(Color.Red, Color.Blue, Color.Red, Color.Gray, Color.LightGray) }

private fun dataColors(dark: Boolean) = DataColors(
    heartRate = if (dark) Tint.PINK.dark else Tint.PINK.light,
    pace = if (dark) Tint.ORANGE.dark else Color(0xFFE7742E),
    attention = if (dark) Tint.ORANGE.dark else Tint.ORANGE.light,
    neutral = if (dark) Color(0xFF7C7C84) else Color(0xFF8E8E95),
    band = (if (dark) Tint.TEAL.dark else Tint.TEAL.hue).copy(alpha = 0.14f),
)

/** A container/on-container pair for a small accent (icon badges). */
@Immutable
data class Accent(val container: Color, val content: Color)

/** Badge colours by insight/coach category, from the tile hues. */
@Composable
fun accentFor(category: String): Accent? {
    val t = when (category) {
        "training", "intensity", "pacing" -> Tint.ORANGE
        "sleep" -> Tint.INDIGO
        "recovery" -> Tint.PINK
        "running" -> Tint.TEAL
        "fitness" -> Tint.BLUE
        "habits" -> Tint.PURPLE
        else -> return null
    }
    return Accent(t.hue.copy(alpha = if (LocalDark.current) 0.26f else 0.18f), ink(t))
}

@OptIn(ExperimentalTextApi::class)
private fun gs(w: FontWeight) = Font(R.font.google_sans, w, variationSettings = FontVariation.Settings(FontVariation.weight(w.weight)))

/** Google Sans throughout (a variable font, 400–700). */
private val Sans = FontFamily(gs(FontWeight.Normal), gs(FontWeight.Medium), gs(FontWeight.SemiBold), gs(FontWeight.Bold))

private val base = Typography()
private val AppTypography = base.copy(
    displayLarge = base.displayLarge.copy(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 52.sp, lineHeight = 56.sp, letterSpacing = (-1).sp),
    displayMedium = base.displayMedium.copy(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 44.sp, lineHeight = 48.sp, letterSpacing = (-1).sp),
    displaySmall = base.displaySmall.copy(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 34.sp, lineHeight = 40.sp, letterSpacing = (-0.5).sp),
    headlineLarge = base.headlineLarge.copy(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 32.sp, lineHeight = 38.sp, letterSpacing = (-0.4).sp),
    headlineMedium = base.headlineMedium.copy(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 26.sp, lineHeight = 32.sp),
    headlineSmall = base.headlineSmall.copy(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 22.sp, lineHeight = 28.sp),
    titleLarge = base.titleLarge.copy(fontFamily = Sans, fontWeight = FontWeight.Bold),
    titleMedium = base.titleMedium.copy(fontFamily = Sans, fontWeight = FontWeight.SemiBold),
    titleSmall = base.titleSmall.copy(fontFamily = Sans, fontWeight = FontWeight.SemiBold),
    bodyLarge = base.bodyLarge.copy(fontFamily = Sans),
    bodyMedium = base.bodyMedium.copy(fontFamily = Sans),
    bodySmall = base.bodySmall.copy(fontFamily = Sans),
    labelLarge = base.labelLarge.copy(fontFamily = Sans, fontWeight = FontWeight.SemiBold),
    labelMedium = base.labelMedium.copy(fontFamily = Sans, fontWeight = FontWeight.SemiBold),
    labelSmall = base.labelSmall.copy(fontFamily = Sans, fontWeight = FontWeight.Medium),
)

private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(12.dp), medium = RoundedCornerShape(20.dp),
    large = RoundedCornerShape(26.dp), extraLarge = RoundedCornerShape(32.dp),
)

@Composable
fun RunnerTheme(appearance: Appearance = Appearance.SYSTEM, content: @Composable () -> Unit) {
    val dark = when (appearance) { Appearance.SYSTEM -> isSystemInDarkTheme(); Appearance.LIGHT -> false; Appearance.DARK -> true }
    androidx.compose.runtime.CompositionLocalProvider(LocalDataColors provides dataColors(dark), LocalDark provides dark) {
        @OptIn(ExperimentalMaterial3ExpressiveApi::class)
        val cs = if (dark) Dark else Light
        MaterialExpressiveTheme(colorScheme = cs, typography = AppTypography, shapes = AppShapes, motionScheme = MotionScheme.expressive()) {
            // Text outside any Surface (sign-in, plain pages) takes the theme's colour, not black
            androidx.compose.runtime.CompositionLocalProvider(androidx.compose.material3.LocalContentColor provides cs.onBackground, content = content)
        }
    }
}

package com.bennybar.runnersidekick.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialExpressiveTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MotionScheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.bennybar.runnersidekick.R
import androidx.compose.ui.unit.dp

// Design B ("Expressive Tonal"): deep green and coral on a sage ground, white cards, tonal chips
private val Light = lightColorScheme(
    primary = Color(0xFF1F5F4A), onPrimary = Color.White, primaryContainer = Color(0xFFC4E8D6), onPrimaryContainer = Color(0xFF002116),
    secondary = Color(0xFF4C5A52), onSecondary = Color.White, secondaryContainer = Color(0xFFDDE6DC), onSecondaryContainer = Color(0xFF18201C),
    tertiary = Color(0xFFB8432A), onTertiary = Color.White, tertiaryContainer = Color(0xFFFFE1D6), onTertiaryContainer = Color(0xFF4A1606),
    background = Color(0xFFF2F4EE), onBackground = Color(0xFF18201C), surface = Color(0xFFF2F4EE), onSurface = Color(0xFF18201C),
    onSurfaceVariant = Color(0xFF4C5A52), surfaceContainerLowest = Color.White, surfaceContainerLow = Color(0xFFF8FAF5),
    surfaceContainer = Color.White, surfaceContainerHigh = Color.White, surfaceContainerHighest = Color(0xFFE6EBE3),
    outline = Color(0xFF76837B), outlineVariant = Color(0xFFC4CCC5),
)
private val Dark = darkColorScheme(
    primary = Color(0xFF8FD5B5), onPrimary = Color(0xFF003826), primaryContainer = Color(0xFF1F5F4A), onPrimaryContainer = Color(0xFFC4E8D6),
    secondary = Color(0xFFBFC9C0), onSecondary = Color(0xFF29332D), secondaryContainer = Color(0xFF34413A), onSecondaryContainer = Color(0xFFDDE6DC),
    tertiary = Color(0xFFFFB59F), onTertiary = Color(0xFF5E1A07), tertiaryContainer = Color(0xFF7A2B14), onTertiaryContainer = Color(0xFFFFE1D6),
    background = Color(0xFF101512), onBackground = Color(0xFFE0E4DE), surface = Color(0xFF101512), onSurface = Color(0xFFE0E4DE),
    onSurfaceVariant = Color(0xFFC0C9C1), surfaceContainerLowest = Color(0xFF0B0F0D), surfaceContainerLow = Color(0xFF161B18),
    surfaceContainer = Color(0xFF1B211E), surfaceContainerHigh = Color(0xFF1F2622), surfaceContainerHighest = Color(0xFF2A312D),
    outline = Color(0xFF8A948C), outlineVariant = Color(0xFF404943),
)

/** The deep green hero cards (readiness, the run's header) and their content: the same in light and dark. */
@Immutable
data class Hero(val container: Color, val content: Color, val tile: Color)

val LocalHero = staticCompositionLocalOf { Hero(Color(0xFF1F5F4A), Color.White, Color.White.copy(alpha = 0.14f)) }
private val LightHero = Hero(Color(0xFF1F5F4A), Color.White, Color.White.copy(alpha = 0.14f))
private val DarkHero = Hero(Color(0xFF1A4D3C), Color(0xFFF1F7F2), Color.White.copy(alpha = 0.10f))

/** Semantic colours for data viz. Always paired with text/icons so meaning never relies on colour alone. */
@Immutable
data class DataColors(val heartRate: Color, val pace: Color, val attention: Color, val neutral: Color, val band: Color)

val LocalDataColors = staticCompositionLocalOf { DataColors(Color.Red, Color.Blue, Color.Red, Color.Gray, Color.LightGray) }

private fun dataColors(cs: ColorScheme, dark: Boolean) = DataColors(
    heartRate = if (dark) Color(0xFFFFB4AB) else Color(0xFFBA1A1A),
    pace = cs.primary,
    attention = cs.tertiary,
    neutral = cs.outline,
    band = cs.primary.copy(alpha = 0.12f),
)

/** A container/on-container pair for a small accent (icon badges). */
@Immutable
data class Accent(val container: Color, val content: Color)

/** A few soft accent hues so categories are easy to tell apart at a glance. Used sparingly, on icon badges only. */
@Immutable
data class Accents(val training: Accent, val sleep: Accent, val recovery: Accent, val running: Accent, val fitness: Accent, val habits: Accent)

private val LightAccents = Accents(
    training = Accent(Color(0xFFFFDCC2), Color(0xFF6E3900)),
    sleep = Accent(Color(0xFFE0E0FF), Color(0xFF2F3A8C)),
    recovery = Accent(Color(0xFFFFD9E0), Color(0xFF7A2941)),
    running = Accent(Color(0xFFB8F0E6), Color(0xFF00504A)),
    fitness = Accent(Color(0xFFD4EDB0), Color(0xFF2D4F00)),
    habits = Accent(Color(0xFFF6E1A6), Color(0xFF574500)),
)
private val DarkAccents = Accents(
    training = Accent(Color(0xFF5A3010), Color(0xFFFFDCC2)),
    sleep = Accent(Color(0xFF353F7A), Color(0xFFE0E0FF)),
    recovery = Accent(Color(0xFF5E2335), Color(0xFFFFD9E0)),
    running = Accent(Color(0xFF00433D), Color(0xFFB8F0E6)),
    fitness = Accent(Color(0xFF2E4513), Color(0xFFD4EDB0)),
    habits = Accent(Color(0xFF4D3F00), Color(0xFFF6E1A6)),
)

val LocalAccents = staticCompositionLocalOf { LightAccents }

/** Accent for an insight/coach category; unknown categories get null (callers fall back to the theme's own colours). */
@Composable
fun accentFor(category: String): Accent? = LocalAccents.current.let { a ->
    when (category) {
        "training", "intensity", "pacing" -> a.training
        "sleep" -> a.sleep
        "recovery" -> a.recovery
        "running" -> a.running
        "fitness" -> a.fitness
        "habits" -> a.habits
        else -> null
    }
}

private val base = Typography()

@OptIn(ExperimentalTextApi::class)
private fun variable(res: Int, w: FontWeight) = Font(res, w, variationSettings = FontVariation.Settings(FontVariation.weight(w.weight)))

/** Unbounded (wide display face) for numbers and headlines; Plus Jakarta Sans for everything else. Both variable fonts. */
private val Display = FontFamily(variable(R.font.unbounded, FontWeight.Medium), variable(R.font.unbounded, FontWeight.SemiBold),
    variable(R.font.unbounded, FontWeight.Bold))
private val Body = FontFamily(variable(R.font.plus_jakarta_sans, FontWeight.Normal), variable(R.font.plus_jakarta_sans, FontWeight.Medium),
    variable(R.font.plus_jakarta_sans, FontWeight.SemiBold), variable(R.font.plus_jakarta_sans, FontWeight.Bold))

// Unbounded runs wide, so display and headline sizes step down a little from the Material defaults
private val AppTypography = base.copy(
    displayLarge = base.displayLarge.copy(fontFamily = Display, fontWeight = FontWeight.Bold, fontSize = 52.sp, lineHeight = 56.sp),
    displayMedium = base.displayMedium.copy(fontFamily = Display, fontWeight = FontWeight.Bold, fontSize = 40.sp, lineHeight = 46.sp),
    displaySmall = base.displaySmall.copy(fontFamily = Display, fontWeight = FontWeight.Bold, fontSize = 32.sp, lineHeight = 38.sp),
    headlineLarge = base.headlineLarge.copy(fontFamily = Display, fontWeight = FontWeight.SemiBold, fontSize = 26.sp, lineHeight = 32.sp),
    headlineMedium = base.headlineMedium.copy(fontFamily = Display, fontWeight = FontWeight.SemiBold, fontSize = 22.sp, lineHeight = 28.sp),
    headlineSmall = base.headlineSmall.copy(fontFamily = Display, fontWeight = FontWeight.SemiBold, fontSize = 19.sp, lineHeight = 26.sp),
    titleLarge = base.titleLarge.copy(fontFamily = Body, fontWeight = FontWeight.Bold),
    titleMedium = base.titleMedium.copy(fontFamily = Body, fontWeight = FontWeight.Bold),
    titleSmall = base.titleSmall.copy(fontFamily = Body, fontWeight = FontWeight.Bold),
    bodyLarge = base.bodyLarge.copy(fontFamily = Body),
    bodyMedium = base.bodyMedium.copy(fontFamily = Body),
    bodySmall = base.bodySmall.copy(fontFamily = Body),
    labelLarge = base.labelLarge.copy(fontFamily = Body, fontWeight = FontWeight.SemiBold),
    labelMedium = base.labelMedium.copy(fontFamily = Body, fontWeight = FontWeight.SemiBold),
    labelSmall = base.labelSmall.copy(fontFamily = Body, fontWeight = FontWeight.Medium),
)

private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(12.dp), medium = RoundedCornerShape(20.dp),
    large = RoundedCornerShape(28.dp), extraLarge = RoundedCornerShape(36.dp),
)

@Composable
fun RunnerTheme(dark: Boolean = isSystemInDarkTheme(), dynamic: Boolean = false, content: @Composable () -> Unit) {
    val ctx = LocalContext.current
    val cs = when {
        dynamic && dark -> dynamicDarkColorScheme(ctx)
        dynamic -> dynamicLightColorScheme(ctx)
        dark -> Dark
        else -> Light
    }
    androidx.compose.runtime.CompositionLocalProvider(LocalDataColors provides dataColors(cs, dark), LocalAccents provides if (dark) DarkAccents else LightAccents,
        LocalHero provides if (dark) DarkHero else LightHero) {
        @OptIn(ExperimentalMaterial3ExpressiveApi::class)
        MaterialExpressiveTheme(colorScheme = cs, typography = AppTypography, shapes = AppShapes,
            motionScheme = MotionScheme.expressive(), content = content)
    }
}

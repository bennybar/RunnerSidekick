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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

// Fallback palette (used if dynamic color is unavailable): a calm teal-green seed.
private val Light = lightColorScheme(
    primary = Color(0xFF006A60), onPrimary = Color.White, primaryContainer = Color(0xFF9EF2E4), onPrimaryContainer = Color(0xFF00201C),
    secondary = Color(0xFF4A635F), secondaryContainer = Color(0xFFCCE8E2), onSecondaryContainer = Color(0xFF05201C),
    tertiary = Color(0xFF456179), tertiaryContainer = Color(0xFFCCE5FF), onTertiaryContainer = Color(0xFF001E31),
    surface = Color(0xFFF4FBF8), surfaceContainerLow = Color(0xFFEEF5F2), surfaceContainer = Color(0xFFE8EFEC),
    surfaceContainerHigh = Color(0xFFE3EAE7),
)
private val Dark = darkColorScheme(
    primary = Color(0xFF82D5C8), onPrimary = Color(0xFF003731), primaryContainer = Color(0xFF005048), onPrimaryContainer = Color(0xFF9EF2E4),
    secondary = Color(0xFFB1CCC6), secondaryContainer = Color(0xFF334B47), onSecondaryContainer = Color(0xFFCCE8E2),
    tertiary = Color(0xFFADCAE6), tertiaryContainer = Color(0xFF2D4960), onTertiaryContainer = Color(0xFFCCE5FF),
    surface = Color(0xFF0E1513), surfaceContainerLow = Color(0xFF171D1B), surfaceContainer = Color(0xFF1B211F),
    surfaceContainerHigh = Color(0xFF252B2A),
)

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

private val base = Typography()
// Expressive: heavier display/headline weights for hero numerals and headlines, medium-weight titles and labels.
private val AppTypography = base.copy(
    displayLarge = base.displayLarge.copy(fontWeight = FontWeight.Medium),
    displayMedium = base.displayMedium.copy(fontWeight = FontWeight.Medium),
    displaySmall = base.displaySmall.copy(fontWeight = FontWeight.Medium),
    headlineLarge = base.headlineLarge.copy(fontWeight = FontWeight.Medium),
    headlineMedium = base.headlineMedium.copy(fontWeight = FontWeight.Medium),
    headlineSmall = base.headlineSmall.copy(fontWeight = FontWeight.Medium),
    titleLarge = base.titleLarge.copy(fontWeight = FontWeight.Medium),
    titleMedium = base.titleMedium.copy(fontWeight = FontWeight.SemiBold),
    labelLarge = base.labelLarge.copy(fontWeight = FontWeight.SemiBold),
)

private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(12.dp), medium = RoundedCornerShape(20.dp),
    large = RoundedCornerShape(28.dp), extraLarge = RoundedCornerShape(36.dp),
)

@Composable
fun RunnerTheme(dark: Boolean = isSystemInDarkTheme(), dynamic: Boolean = true, content: @Composable () -> Unit) {
    val ctx = LocalContext.current
    val cs = when {
        dynamic && dark -> dynamicDarkColorScheme(ctx)
        dynamic -> dynamicLightColorScheme(ctx)
        dark -> Dark
        else -> Light
    }
    androidx.compose.runtime.CompositionLocalProvider(LocalDataColors provides dataColors(cs, dark)) {
        @OptIn(ExperimentalMaterial3ExpressiveApi::class)
        MaterialExpressiveTheme(colorScheme = cs, typography = AppTypography, shapes = AppShapes,
            motionScheme = MotionScheme.expressive(), content = content)
    }
}

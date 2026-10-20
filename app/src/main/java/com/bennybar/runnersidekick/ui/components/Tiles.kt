package com.bennybar.runnersidekick.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.compositeOver
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.bennybar.runnersidekick.ui.theme.LocalDark
import com.bennybar.runnersidekick.ui.theme.Tint

val TileShape = RoundedCornerShape(26.dp)

/** The tile's fill: an even wash of its hue over the plain card colour (opaque, so it reads the same over anything).
 *  Neutral is the plain card. */
@Composable
fun tileBrush(tint: Tint): Brush {
    val card = MaterialTheme.colorScheme.surfaceContainer
    if (tint == Tint.NEUTRAL) return SolidColor(card)
    return SolidColor(tint.hue.copy(alpha = if (LocalDark.current) 0.18f else 0.20f).compositeOver(card))
}

/** A card: rounded, with a soft tint for its kind of data, a thin bright edge and, in light mode, a faint glow of
 *  its own colour. [onClick] makes the whole tile a button. */
@Composable
fun Tile(
    modifier: Modifier = Modifier,
    tint: Tint = Tint.NEUTRAL,
    onClick: (() -> Unit)? = null,
    contentPadding: PaddingValues = PaddingValues(horizontal = 18.dp, vertical = 16.dp),
    spacing: Dp = 8.dp,
    content: @Composable ColumnScope.() -> Unit,
) {
    val dark = LocalDark.current
    val edge = when {
        dark && tint != Tint.NEUTRAL -> tint.hue.copy(alpha = 0.22f)
        dark -> Color.White.copy(alpha = 0.07f)
        else -> Color.White.copy(alpha = 0.9f)
    }
    val glow = if (tint == Tint.NEUTRAL) Color(0xFF1E2846) else tint.hue
    Column(
        modifier.fillMaxWidth()
            .then(if (dark) Modifier else Modifier.shadow(6.dp, TileShape, ambientColor = glow.copy(alpha = 0.10f), spotColor = glow.copy(alpha = 0.16f)))
            .clip(TileShape).background(tileBrush(tint)).border(1.dp, edge, TileShape)
            .then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
            .padding(contentPadding),
        verticalArrangement = Arrangement.spacedBy(spacing),
        content = content,
    )
}

/** A small uppercase label above a group of tiles ("READINGS", "LAST NIGHT"). */
@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(text.uppercase(), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = modifier.padding(start = 8.dp, top = 10.dp).semantics { heading() })
}

/** A detail screen: a full page over the app with a back arrow (system back works too) and a scrolling column. */
@Composable
fun DetailPage(title: String, onBack: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    Dialog(onDismissRequest = onBack, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        // The page is its own window: give its status and navigation bar icons the app's light/dark too
        val dark = LocalDark.current
        val window = (androidx.compose.ui.platform.LocalView.current.parent as? androidx.compose.ui.window.DialogWindowProvider)?.window
        androidx.compose.runtime.SideEffect {
            window?.let {
                val c = androidx.core.view.WindowCompat.getInsetsController(it, it.decorView)
                c.isAppearanceLightStatusBars = !dark
                c.isAppearanceLightNavigationBars = !dark
            }
        }
        Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            Column(Modifier.systemBarsPadding()) {
                Row(Modifier.fillMaxWidth().padding(start = 4.dp, end = 16.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back") }
                    Text(title, style = MaterialTheme.typography.titleLarge, maxLines = 1)
                }
                Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 12.dp).padding(top = 8.dp, bottom = 32.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp), content = content)
            }
        }
    }
}

/** A big number with an optional unit beside it, as on the tiles. */
@Composable
fun BigValue(value: String, unit: String? = null, modifier: Modifier = Modifier, style: androidx.compose.ui.text.TextStyle = MaterialTheme.typography.displayMedium) {
    Row(modifier, verticalAlignment = Alignment.Bottom) {
        Text(value, style = style, maxLines = 1)
        unit?.let {
            Spacer(Modifier.size(6.dp))
            Text(it, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(bottom = 6.dp))
        }
    }
}

package com.bennybar.runnersidekick.ui.components

import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.toShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.foundation.layout.fillMaxSize
import kotlin.math.roundToInt
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.graphics.shapes.RoundedPolygon

class GroupScope internal constructor() {
    internal val rows = mutableListOf<@Composable (Shape) -> Unit>()

    /** A row in the group. [onClick] makes it a button; [trailing] defaults to a chevron when clickable. */
    fun row(
        headline: String,
        supporting: String? = null,
        overline: String? = null,
        icon: ImageVector? = null,
        iconShape: RoundedPolygon? = null,
        onClick: (() -> Unit)? = null,
        accent: String? = null, // accent category, see accentFor()
        trailing: (@Composable RowScope.() -> Unit)? = null,
    ) {
        rows += { shape -> GroupRow(shape, headline, supporting, overline, icon, iconShape, onClick, accent, trailing) }
    }

    fun custom(content: @Composable ColumnScope.() -> Unit) {
        rows += { _ -> Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 16.dp), content = content) }
    }
}

/** A titled list of rows in one card (tinted with [tint]), rows separated by thin lines. */
@Composable
fun Group(modifier: Modifier = Modifier, title: String? = null, tint: com.bennybar.runnersidekick.ui.theme.Tint = com.bennybar.runnersidekick.ui.theme.Tint.NEUTRAL,
          content: GroupScope.() -> Unit) {
    val scope = GroupScope().apply(content)
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        title?.let { SectionLabel(it) }
        if (scope.rows.isNotEmpty()) Tile(tint = tint, contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 4.dp), spacing = 0.dp) {
            scope.rows.forEachIndexed { i, r ->
                if (i > 0) androidx.compose.material3.HorizontalDivider(Modifier.padding(horizontal = 18.dp),
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.07f))
                r(RoundedCornerShape(0.dp))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun GroupRow(
    shape: Shape, headline: String, supporting: String?, overline: String?, icon: ImageVector?, iconShape: RoundedPolygon?,
    onClick: (() -> Unit)?, accentCategory: String?, trailing: (@Composable RowScope.() -> Unit)?,
) {
    Box(Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth().then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
                .heightIn(min = 56.dp).padding(horizontal = 18.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (icon != null) {
                val accent = accentCategory?.let { com.bennybar.runnersidekick.ui.theme.accentFor(it) }
                ShapeBadge(icon, iconShape ?: MaterialShapes.Circle, Modifier.size(36.dp),
                    container = accent?.container ?: MaterialTheme.colorScheme.primaryContainer,
                    content = accent?.content ?: MaterialTheme.colorScheme.onPrimaryContainer, iconSize = 20.dp)
                Spacer(Modifier.width(14.dp))
            }
            Column(Modifier.weight(1f)) {
                overline?.let { Text(it, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                Text(headline, style = MaterialTheme.typography.bodyLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
                supporting?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
            when {
                trailing != null -> trailing()
                onClick != null -> Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

/** An icon on an Expressive shape (cookie, sunny, burst…), tinted with a container colour. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun ShapeBadge(
    icon: ImageVector,
    polygon: RoundedPolygon,
    modifier: Modifier = Modifier,
    container: Color = MaterialTheme.colorScheme.primaryContainer,
    content: Color = MaterialTheme.colorScheme.onPrimaryContainer,
    iconSize: androidx.compose.ui.unit.Dp = 22.dp,
) {
    Surface(shape = polygon.toShape(), color = container, modifier = modifier) {
        Box(contentAlignment = Alignment.Center) { Icon(icon, null, tint = content, modifier = Modifier.size(iconSize)) }
    }
}

/** Big-numeral tile for a reading, tinted for its kind of data. Colour is never the only signal: the status line has
 *  text and an icon, and a flagged reading also says so in words. */
@Composable
fun MetricTile(
    label: String,
    value: String,
    unit: String?,
    status: String,
    statusIcon: ImageVector?,
    flagged: Boolean,
    modifier: Modifier = Modifier,
    tint: com.bennybar.runnersidekick.ui.theme.Tint = com.bennybar.runnersidekick.ui.theme.Tint.NEUTRAL,
    onClick: () -> Unit,
    chart: (@Composable () -> Unit)? = null,
) {
    val on = MaterialTheme.colorScheme.onSurface
    val sub = MaterialTheme.colorScheme.onSurfaceVariant
    Tile(modifier, tint = if (flagged) com.bennybar.runnersidekick.ui.theme.Tint.ORANGE else tint, onClick = onClick, spacing = 4.dp) {
        Column(Modifier.heightIn(min = 104.dp)) {
            Text(label, style = MaterialTheme.typography.labelLarge, color = on)
            Spacer(Modifier.weight(1f, fill = false))
            Row(verticalAlignment = Alignment.Bottom) {
                Text(value, style = MaterialTheme.typography.headlineMedium, color = on, maxLines = 1)
                unit?.let {
                    Spacer(Modifier.width(4.dp))
                    Text(it, style = MaterialTheme.typography.bodyMedium, color = sub, modifier = Modifier.padding(bottom = 4.dp))
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                statusIcon?.let { Icon(it, null, Modifier.size(16.dp), tint = sub); Spacer(Modifier.width(4.dp)) }
                Text(status, style = MaterialTheme.typography.labelMedium, color = sub, maxLines = 2)
            }
            chart?.let { Spacer(Modifier.padding(top = 8.dp)); it() }
        }
    }
}


/** A lazy-list item that fades in, fades out and moves into place when the list changes (a tab or range switch,
 *  a card appearing), using Material's emphasized timing. */
fun androidx.compose.foundation.lazy.LazyListScope.animatedItem(key: Any, content: @Composable () -> Unit) =
    item(key = key) {
        Box(Modifier.animateItem(fadeInSpec = androidx.compose.animation.core.tween(220, 60),
            fadeOutSpec = androidx.compose.animation.core.tween(90))) { content() }
    }



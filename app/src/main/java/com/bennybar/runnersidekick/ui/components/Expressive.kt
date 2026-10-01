package com.bennybar.runnersidekick.ui.components

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
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.graphics.shapes.RoundedPolygon

/** Corner radii for a segmented group (Android 16 Settings style): outer corners large, inner corners small. */
fun segmentShape(index: Int, count: Int, outer: Int = 24, inner: Int = 6): Shape = when {
    count == 1 -> RoundedCornerShape(outer.dp)
    index == 0 -> RoundedCornerShape(outer.dp, outer.dp, inner.dp, inner.dp)
    index == count - 1 -> RoundedCornerShape(inner.dp, inner.dp, outer.dp, outer.dp)
    else -> RoundedCornerShape(inner.dp)
}

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
        rows += { shape ->
            Surface(shape = shape, color = MaterialTheme.colorScheme.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(20.dp), content = content)
            }
        }
    }
}

@Composable
fun Group(modifier: Modifier = Modifier, title: String? = null, content: GroupScope.() -> Unit) {
    val scope = GroupScope().apply(content)
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        title?.let {
            Text(it, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(start = 20.dp, bottom = 6.dp, top = 4.dp).semantics { heading() })
        }
        scope.rows.forEachIndexed { i, r -> r(segmentShape(i, scope.rows.size)) }
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun GroupRow(
    shape: Shape, headline: String, supporting: String?, overline: String?, icon: ImageVector?, iconShape: RoundedPolygon?,
    onClick: (() -> Unit)?, accentCategory: String?, trailing: (@Composable RowScope.() -> Unit)?,
) {
    Surface(shape = shape, color = MaterialTheme.colorScheme.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
                .heightIn(min = 64.dp).padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (icon != null) {
                val accent = accentCategory?.let { com.bennybar.runnersidekick.ui.theme.accentFor(it) }
                ShapeBadge(icon, iconShape ?: MaterialShapes.Circle, Modifier.size(40.dp),
                    container = accent?.container ?: MaterialTheme.colorScheme.primaryContainer,
                    content = accent?.content ?: MaterialTheme.colorScheme.onPrimaryContainer)
                Spacer(Modifier.width(16.dp))
            }
            Column(Modifier.weight(1f)) {
                overline?.let { Text(it, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                Text(headline, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
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

/** Big-numeral tile for a reading. Colour is never the only signal: the status line has text and an icon. */
@Composable
fun MetricTile(
    label: String,
    value: String,
    unit: String?,
    status: String,
    statusIcon: ImageVector?,
    flagged: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
    chart: (@Composable () -> Unit)? = null,
) {
    val container = if (flagged) MaterialTheme.colorScheme.tertiaryContainer else MaterialTheme.colorScheme.surfaceContainerHigh
    val on = if (flagged) MaterialTheme.colorScheme.onTertiaryContainer else MaterialTheme.colorScheme.onSurface
    Surface(onClick = onClick, shape = MaterialTheme.shapes.large, color = container, modifier = modifier) {
        Column(Modifier.padding(18.dp).heightIn(min = 128.dp)) {
            Text(label, style = MaterialTheme.typography.labelLarge, color = on.copy(alpha = 0.8f))
            Spacer(Modifier.weight(1f, fill = false))
            Row(verticalAlignment = Alignment.Bottom) {
                Text(value, style = MaterialTheme.typography.displaySmall, color = on, maxLines = 1)
                unit?.let {
                    Spacer(Modifier.width(4.dp))
                    Text(it, style = MaterialTheme.typography.titleMedium, color = on.copy(alpha = 0.75f), modifier = Modifier.padding(bottom = 6.dp))
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                statusIcon?.let { Icon(it, null, Modifier.size(16.dp), tint = on.copy(alpha = 0.8f)); Spacer(Modifier.width(4.dp)) }
                Text(status, style = MaterialTheme.typography.labelMedium, color = on.copy(alpha = 0.8f), maxLines = 2)
            }
            chart?.let { Spacer(Modifier.padding(top = 10.dp)); it() }
        }
    }
}

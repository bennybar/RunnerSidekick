package com.bennybar.runnersidekick.ui.insights

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.TrendingUp
import androidx.compose.material.icons.outlined.Bolt
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.Landscape
import androidx.compose.material.icons.outlined.Speed
import androidx.compose.material.icons.outlined.Timer
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.data.remote.NumberItem
import com.bennybar.runnersidekick.data.remote.TrainingNumbers
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.Sparkline

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
private fun iconOf(id: String) = when (id) {
    "threshold" -> Icons.Outlined.Speed to MaterialShapes.Cookie9Sided
    "form" -> Icons.Outlined.Bolt to MaterialShapes.Sunny
    "predictions" -> Icons.Outlined.Timer to MaterialShapes.Cookie4Sided
    "recovery" -> Icons.Outlined.Favorite to MaterialShapes.Flower
    "climbing" -> Icons.Outlined.Landscape to MaterialShapes.Burst
    else -> Icons.AutoMirrored.Outlined.TrendingUp to MaterialShapes.Circle
}

/** One row per training number: its value and what changed. Each opens its history. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun NumbersCard(n: TrainingNumbers, onOpen: (String) -> Unit) {
    Group(title = "Training numbers") {
        // Recovery and climbing appear once there's something to show (sessions with repeats, runs with real climbs)
        n.items.filter { it.status == "ok" || it.id !in setOf("recovery", "climbing") }.forEach { it ->
            val (icon, shape) = iconOf(it.id)
            row(it.title, supporting = listOfNotNull(it.value, it.headline?.takeIf { h -> h.isNotBlank() }).joinToString(" · "),
                icon = icon, iconShape = shape, onClick = { onOpen(it.id) })
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun NumberSheet(item: NumberItem, onOpenRun: (String) -> Unit, onDismiss: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(item.title, style = MaterialTheme.typography.headlineSmall)
            item.value?.let { Text(it, style = MaterialTheme.typography.headlineMedium, color = cs.primary) }
            item.headline?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.titleMedium) }
            item.detail?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
            if (item.series.size >= 2) {
                // Faster paces and times are drawn upward; the load balance has no better or worse direction
                Sparkline(item.series.map { if (item.lowerIsBetter) -it.v else it.v }, Modifier.fillMaxWidth().height(80.dp),
                    description = "${item.title} from ${item.series.first().date} to ${item.series.last().date}")
                Text("${Format.shortDate(item.series.first().date)} – ${Format.shortDate(item.series.last().date)}" +
                    if (item.lowerIsBetter) " · better is up" else "", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
                Group {
                    item.series.takeLast(6).reversed().forEach { p ->
                        row(p.label ?: p.v.toString(), supporting = Format.shortDate(p.date),
                            onClick = p.sourceId?.let { id -> { onOpenRun(id) } })
                    }
                }
            }
            Text(item.basis, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
        }
    }
}

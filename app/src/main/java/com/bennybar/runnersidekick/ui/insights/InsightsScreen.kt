package com.bennybar.runnersidekick.ui.insights

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.outlined.Bedtime
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.FitnessCenter
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material.icons.outlined.TrendingUp
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Icon
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.graphics.shapes.RoundedPolygon
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.bennybar.runnersidekick.data.remote.Insight
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.InsightsVm
import com.bennybar.runnersidekick.ui.components.DemoBadge
import com.bennybar.runnersidekick.ui.components.EmptyState
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.ShapeBadge
import com.bennybar.runnersidekick.ui.factory
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
fun categoryStyle(category: String): Pair<ImageVector, RoundedPolygon> = when (category) {
    "training" -> Icons.Outlined.FitnessCenter to MaterialShapes.Cookie9Sided
    "fitness" -> Icons.Outlined.TrendingUp to MaterialShapes.Sunny
    "running" -> Icons.AutoMirrored.Outlined.DirectionsRun to MaterialShapes.Cookie6Sided
    "sleep" -> Icons.Outlined.Bedtime to MaterialShapes.Clover4Leaf
    "recovery" -> Icons.Outlined.Favorite to MaterialShapes.SoftBurst
    else -> Icons.Outlined.Insights to MaterialShapes.Circle
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun InsightsScreen(vm: InsightsVm = viewModel(factory = factory(::InsightsVm))) {
    val data by vm.insights.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var method by remember { mutableStateOf<Insight?>(null) }
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        topBar = { LargeTopAppBar(title = { Text("Insights") }, scrollBehavior = scroll, actions = { if (data?.value?.synthetic == true) DemoBadge() }) },
    ) { padding ->
        PullToRefreshBox(busy, vm::refresh, Modifier.padding(padding).fillMaxSize()) {
            val items = data?.value?.insights.orEmpty()
            LazyColumn(contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    Text("A fixed set of questions answered from your own data. Every answer is shown, including \"no clear pattern\".",
                        style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (items.isEmpty()) item { EmptyState(Icons.Outlined.Insights, "No insights yet", "Pull down to load them after your first sync.") }
                val patterns = items.filter { it.verdict == "pattern" }
                val nulls = items.filter { it.verdict == "no_clear_pattern" }
                val waiting = items.filter { it.verdict == "not_enough_data" }
                patterns.forEach { i -> item(key = i.id) { InsightCard(i, emphasised = true) { method = i } } }
                if (nulls.isNotEmpty()) item {
                    Text("Checked, nothing notable", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(start = 4.dp, top = 12.dp))
                }
                nulls.forEach { i -> item(key = i.id) { InsightCard(i, emphasised = false) { method = i } } }
                if (waiting.isNotEmpty()) item {
                    Group(title = "Still collecting data") {
                        waiting.forEach { i ->
                            val (icon, shape) = categoryStyle(i.category)
                            row(i.question, supporting = i.detail.ifBlank { i.headline }, icon = icon, iconShape = shape, onClick = { method = i })
                        }
                    }
                }
                data?.value?.let { r ->
                    item {
                        Text("Updated ${Format.shortDate(r.localDate)} · revision ${r.revision} · ${items.firstOrNull()?.algorithmVersion ?: ""}",
                            style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
    method?.let { MethodSheet(it) { method = null } }
}

@Composable
fun InsightCard(i: Insight, emphasised: Boolean, onMethod: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val container = if (emphasised) cs.surfaceContainerHigh else cs.surfaceContainer
    val (icon, shape) = categoryStyle(i.category)
    Surface(shape = MaterialTheme.shapes.extraLarge, color = container, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ShapeBadge(icon, shape, Modifier.size(44.dp),
                    container = if (emphasised) cs.primary else cs.secondaryContainer, content = if (emphasised) cs.onPrimary else cs.onSecondaryContainer)
                Spacer(Modifier.width(12.dp))
                Text(i.question, style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant, modifier = Modifier.weight(1f))
            }
            Text(i.headline, style = if (emphasised) MaterialTheme.typography.headlineSmall else MaterialTheme.typography.titleLarge)
            Text(i.detail, style = MaterialTheme.typography.bodyMedium)
            i.chart?.let { InsightChart(it, Modifier.fillMaxWidth()) }
            i.practical?.let {
                Surface(shape = MaterialTheme.shapes.medium, color = cs.secondaryContainer) {
                    Text(it, style = MaterialTheme.typography.bodyMedium, color = cs.onSecondaryContainer, modifier = Modifier.padding(14.dp))
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(listOfNotNull(i.sampleSize?.let { "n = $it" },
                    when (i.confidence) { "consistent" -> "held on newer data"; "emerging" -> "emerging, not yet re-checked"; else -> null })
                    .joinToString(" · "), style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant, modifier = Modifier.weight(1f))
                TextButton(onClick = onMethod) { Text("How it's worked out") }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MethodSheet(i: Insight, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(i.question, style = MaterialTheme.typography.headlineSmall)
            Text(i.headline, style = MaterialTheme.typography.titleMedium)
            Group(title = "Method") { custom { Text(i.method, style = MaterialTheme.typography.bodyMedium) } }
            if (i.confounders.isNotEmpty()) Group(title = "What else could explain it") {
                i.confounders.forEach { c -> row(c) }
            }
            Text(listOfNotNull(i.sampleSize?.let { "Sample size $it" }, i.evidence.dateRange.takeIf { it.size == 2 }?.let { "${it[0]} – ${it[1]}" },
                i.algorithmVersion, "Associations only, not causes or medical advice").joinToString(" · "),
                style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** Small purpose-built visuals for insight types. Every value is also stated in the card text. */
@Composable
fun InsightChart(chart: JsonObject, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    when (chart["type"]?.jsonPrimitive?.content) {
        "stacked_share" -> {
            val labels = chart["labels"]!!.jsonArray.map { it.jsonPrimitive.content }
            val values = chart["values"]!!.jsonArray.map { it.jsonPrimitive.doubleOrNull ?: 0.0 }
            val colors = listOf(cs.primary.copy(alpha = 0.25f), cs.primary.copy(alpha = 0.45f), cs.primary.copy(alpha = 0.65f), cs.tertiary, cs.error)
            Column(modifier) {
                Canvas(Modifier.fillMaxWidth().height(28.dp).semantics {
                    contentDescription = labels.zip(values).joinToString { (l, v) -> "$l ${(v * 100).toInt()}%" }
                }) {
                    var x = 0f
                    values.forEachIndexed { k, v ->
                        val w = (v * size.width).toFloat()
                        if (w > 0) drawRoundRect(colors[k], Offset(x, 0f), Size((w - 3f).coerceAtLeast(1f), size.height), CornerRadius(10f, 10f))
                        x += w
                    }
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(top = 6.dp)) {
                    labels.zip(values).forEachIndexed { k, (l, v) ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Canvas(Modifier.size(10.dp)) { drawCircle(colors[k]) }
                            Spacer(Modifier.width(4.dp))
                            Text("$l ${(v * 100).toInt()}%", style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant)
                        }
                    }
                }
            }
        }
        "pace_trend" -> {
            val series = chart["series"]!!.jsonArray.map { s ->
                s.jsonObject["points"]!!.jsonArray.map { it.jsonObject["pace_s_per_km"]!!.jsonPrimitive.doubleOrNull ?: 0.0 }
            }
            val all = series.flatten()
            if (all.size < 2) return
            val lo = all.min() - 5
            val hi = all.max() + 5
            val palette = listOf(cs.primary, cs.tertiary, cs.secondary)
            Column(modifier) {
                Row {
                    Text(Format.pace(lo + 5, com.bennybar.runnersidekick.data.local.Units.METRIC) + " (faster)", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
                }
                Canvas(Modifier.fillMaxWidth().height(96.dp).semantics { contentDescription = "Pace at the same heart rate over time, one line per watch" }) {
                    val totalPts = series.sumOf { it.size } + series.size - 1
                    var idx = 0
                    series.forEachIndexed { k, pts ->
                        val path = Path()
                        pts.forEachIndexed { j, p ->
                            val x = (idx + j).toFloat() / (totalPts - 1).coerceAtLeast(1) * size.width
                            val y = ((p - lo) / (hi - lo)).toFloat() * size.height // lower pace (faster) at top
                            if (j == 0) path.moveTo(x, y) else path.lineTo(x, y)
                            drawCircle(palette[k % 3], 4.dp.toPx(), Offset(x, y))
                        }
                        drawPath(path, palette[k % 3].copy(alpha = 0.6f), style = Stroke(2.dp.toPx()))
                        idx += pts.size + 1 // gap between watches: never joined
                    }
                }
                Text(Format.pace(hi - 5, com.bennybar.runnersidekick.data.local.Units.METRIC) + " (slower) · each colour is a different watch",
                    style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            }
        }
        "weekly_bars" -> {
            val pts = chart["points"]!!.jsonArray.map { it.jsonObject["moving_s"]!!.jsonPrimitive.doubleOrNull ?: 0.0 }
            val mx = (pts.maxOrNull() ?: 1.0).coerceAtLeast(1.0)
            val bar = cs.primary
            Canvas(modifier.height(64.dp).semantics { contentDescription = "Weekly running time, last 8 weeks" }) {
                val w = size.width / pts.size
                pts.forEachIndexed { k, v ->
                    val h = (v / mx).toFloat() * size.height
                    drawRoundRect(bar, Offset(k * w + w * 0.15f, size.height - h), Size(w * 0.7f, h.coerceAtLeast(2f)), CornerRadius(8f, 8f))
                }
            }
        }
        else -> Unit
    }
}

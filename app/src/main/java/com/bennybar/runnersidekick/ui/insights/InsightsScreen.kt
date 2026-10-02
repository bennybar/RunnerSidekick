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
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
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
import androidx.compose.runtime.LaunchedEffect
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
import com.bennybar.runnersidekick.ui.components.animatedItem
import com.bennybar.runnersidekick.ui.components.ShapeBadge
import com.bennybar.runnersidekick.ui.factory
import com.bennybar.runnersidekick.ui.theme.accentFor
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

private val REPEATED_ELSEWHERE = setOf("intensity", "efficiency")

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
fun categoryStyle(category: String): Pair<ImageVector, RoundedPolygon> = when (category) {
    "training" -> Icons.Outlined.FitnessCenter to MaterialShapes.Cookie9Sided
    "fitness" -> Icons.Outlined.TrendingUp to MaterialShapes.Sunny
    "running" -> Icons.AutoMirrored.Outlined.DirectionsRun to MaterialShapes.Cookie6Sided
    "sleep" -> Icons.Outlined.Bedtime to MaterialShapes.Clover4Leaf
    "recovery" -> Icons.Outlined.Favorite to MaterialShapes.SoftBurst
    else -> Icons.Outlined.Insights to MaterialShapes.Circle
}

/** Set by links elsewhere (e.g. Today) to open a specific Insights tab: 0 Insights, 1 Compare, 2 Trends. */
object InsightsTab {
    val requested = kotlinx.coroutines.flow.MutableStateFlow<Int?>(null)
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun InsightsScreen(
    onOpenDay: (String) -> Unit, onOpenRun: (String) -> Unit, onOpenReport: (Long) -> Unit, onOpenSettings: () -> Unit,
    vm: InsightsVm = viewModel(factory = factory(::InsightsVm)),
) {
    val data by vm.insights.collectAsStateWithLifecycle()
    val weekly by vm.weekly.collectAsStateWithLifecycle()
    val fitness by vm.fitness.collectAsStateWithLifecycle()
    val trends by vm.trends.collectAsStateWithLifecycle()
    val days by vm.days.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val busy by vm.busy.collectAsStateWithLifecycle()
    val coach by vm.coach.collectAsStateWithLifecycle()
    val coachLoading by vm.coachLoading.collectAsStateWithLifecycle()
    val compare by vm.compare.collectAsStateWithLifecycle()
    val firstDay by vm.weekStart.collectAsStateWithLifecycle()
    val todayReport by vm.today.collectAsStateWithLifecycle()
    val focus by vm.focus.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { vm.loadCoach() }
    LaunchedEffect(tab) { if (tab == 1) vm.loadCompare() }
    val requestedTab by InsightsTab.requested.collectAsStateWithLifecycle()
    LaunchedEffect(requestedTab) { requestedTab?.let { tab = it; InsightsTab.requested.value = null } }
    var method by remember { mutableStateOf<Insight?>(null) }
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        topBar = { LargeTopAppBar(title = { Text("Insights") }, scrollBehavior = scroll, actions = { if (data?.value?.synthetic == true) DemoBadge() }) },
    ) { padding ->
        PullToRefreshBox(busy, vm::refresh, Modifier.padding(padding).fillMaxSize()) {
            val items = data?.value?.insights.orEmpty()
            LazyColumn(contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                animatedItem(key = "tabs") {
                    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                        listOf("Insights", "Compare", "Trends").forEachIndexed { i, l ->
                            SegmentedButton(tab == i, { tab = i }, SegmentedButtonDefaults.itemShape(i, 3), icon = {}) { Text(l) }
                        }
                    }
                }
                if (tab == 1) {
                    animatedItem(key = "compare") { CompareSection(compare?.value, onOpenSettings = onOpenSettings, onOpenRun = onOpenRun) }
                    return@LazyColumn
                }
                if (tab == 2) {
                    animatedItem(key = "trends") {
                        TrendsSection(trends?.value, days, settings?.units ?: com.bennybar.runnersidekick.data.local.Units.METRIC, loading = busy,
                            onDays = vm::setDays, onOpenDay = onOpenDay, onOpenRun = onOpenRun)
                    }
                    return@LazyColumn
                }
                data?.value?.stats?.let { st -> if (st.items.isNotEmpty()) animatedItem(key = "stats") { StatsGrid(st) } }
                coach?.value?.let { c -> animatedItem(key = "coach") { CoachCard(c, coachLoading, items, onOpenRun = onOpenRun, onOpenInsight = { method = it }) } }
                // Your week: the race week (with a race goal) and the weekly focus, moved here from Today
                todayReport?.value?.race?.let { r -> r.week?.let { w -> animatedItem(key = "raceweek") {
                    com.bennybar.runnersidekick.ui.today.RaceWeekCard(r, w, onOpenRun) } } }
                focus?.value?.let { f -> animatedItem(key = "focus") {
                    com.bennybar.runnersidekick.ui.today.FocusCard(f, onChoose = vm::chooseFocus, onOpenRun = onOpenRun) } }
                fitness?.value?.let { f ->
                    animatedItem(key = "fitness") { FitnessSection(f, onOpenRun = onOpenRun) }
                }
                weekly?.value?.let { w -> animatedItem(key = "weekly") { WeeklyCard(w) { onOpenReport(w.id) } } }
                if (items.isEmpty()) animatedItem(key = "empty") { EmptyState(Icons.Outlined.Insights, "No insights yet", "Pull down to load them after your first sync.") }
                // Hard-running share is in the stats grid and the coach; pace at the same heart rate is charted in Trends
                val patterns = items.filter { it.verdict == "pattern" && it.id !in REPEATED_ELSEWHERE }
                val nulls = items.filter { it.verdict == "no_clear_pattern" }
                val waiting = items.filter { it.verdict == "not_enough_data" }
                patterns.forEach { i -> animatedItem(key = i.id) { InsightCard(i, emphasised = i.userState == null, onMethod = { method = i }) } }
                if (nulls.isNotEmpty()) animatedItem(key = "nulls") {
                    Group(title = "Checked, nothing notable") {
                        nulls.forEach { i ->
                            val (icon, shape) = categoryStyle(i.category)
                            row(i.headline, icon = icon, iconShape = shape, onClick = { method = i }, accent = i.category)
                        }
                    }
                }
                if (waiting.isNotEmpty()) animatedItem(key = "waiting") {
                    Group(title = "Still collecting data") {
                        waiting.forEach { i ->
                            val (icon, shape) = categoryStyle(i.category)
                            row(i.question, supporting = i.headline, icon = icon, iconShape = shape, onClick = { method = i }, accent = i.category)
                        }
                    }
                }
            }
        }
    }
    method?.let { m -> MethodSheet(data?.value?.insights?.firstOrNull { it.id == m.id } ?: m, onState = { st -> vm.setInsightState(m.id, st) }) { method = null } }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun WeeklyCard(w: com.bennybar.runnersidekick.data.remote.WeeklyReport, onOpen: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Surface(onClick = onOpen, shape = MaterialTheme.shapes.extraLarge, color = cs.primaryContainer, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ShapeBadge(Icons.Outlined.CalendarMonth, MaterialShapes.Cookie12Sided, Modifier.size(44.dp), container = cs.primary, content = cs.onPrimary)
                Spacer(Modifier.width(12.dp))
                Text("Weekly review · ${Format.shortDate(w.weekStart)} – ${Format.shortDate(w.weekEnd)}", style = MaterialTheme.typography.labelLarge,
                    color = cs.onPrimaryContainer)
            }
            Text(w.headline, style = MaterialTheme.typography.headlineSmall, color = cs.onPrimaryContainer)
            Text("Next week's focus and details", style = MaterialTheme.typography.labelLarge, color = cs.primary)
        }
    }
}

@Composable
fun InsightCard(i: Insight, emphasised: Boolean, onMethod: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val container = if (emphasised) cs.surfaceContainerHigh else cs.surfaceContainer
    val (icon, shape) = categoryStyle(i.category)
    val accent = accentFor(i.category)
    Surface(shape = MaterialTheme.shapes.extraLarge, color = container, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ShapeBadge(icon, shape, Modifier.size(44.dp),
                    container = if (emphasised) accent?.container ?: cs.primary else cs.secondaryContainer,
                    content = if (emphasised) accent?.content ?: cs.onPrimary else cs.onSecondaryContainer)
                Spacer(Modifier.width(12.dp))
                Text(i.question, style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant, modifier = Modifier.weight(1f))
                if (i.verdict == "pattern" && i.novelty in setOf("new", "changed")) {
                    Surface(shape = MaterialTheme.shapes.small, color = cs.tertiaryContainer) {
                        Text(if (i.novelty == "new") "New" else "Changed", style = MaterialTheme.typography.labelMedium,
                            color = cs.onTertiaryContainer, modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp))
                    }
                }
            }
            Text(i.headline, style = if (emphasised) MaterialTheme.typography.headlineSmall else MaterialTheme.typography.titleLarge)
            i.chart?.let { InsightChart(it, Modifier.fillMaxWidth()) }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(listOfNotNull(i.sampleSize?.let { "$it runs" },
                    when (i.confidence) { "consistent" -> "held on newer data"; "emerging" -> "emerging"; else -> null })
                    .joinToString(" · "), style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant, modifier = Modifier.weight(1f))
                TextButton(onClick = onMethod) { Text("Details") }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MethodSheet(i: Insight, onState: (String?) -> Unit, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(i.question, style = MaterialTheme.typography.headlineSmall)
            Text(i.headline, style = MaterialTheme.typography.titleMedium)
            if (i.detail.isNotBlank()) Text(i.detail, style = MaterialTheme.typography.bodyMedium)
            i.practical?.let {
                Surface(shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.secondaryContainer) {
                    Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSecondaryContainer, modifier = Modifier.padding(14.dp))
                }
            }
            Group(title = "Method") { custom { Text(i.method, style = MaterialTheme.typography.bodyMedium) } }
            if (i.confounders.isNotEmpty()) Group(title = "What else could explain it") {
                i.confounders.forEach { c -> row(c) }
            }
            // Marking a pattern lives here, not on the card
            if (i.verdict == "pattern") Row(verticalAlignment = Alignment.CenterVertically) {
                if (i.userState == null) {
                    TextButton(onClick = { onState("working_on") }) { Text("I'm working on it") }
                    TextButton(onClick = { onState("dismissed"); onDismiss() }) { Text("Dismiss") }
                } else {
                    Text(if (i.userState == "working_on") "You're working on this" else "Dismissed", style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(start = 12.dp))
                    TextButton(onClick = { onState(null) }) { Text("Undo") }
                }
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


/** The key numbers of the last 4 weeks, each with its change against the 4 weeks before. */
@Composable
private fun StatsGrid(st: com.bennybar.runnersidekick.data.remote.Stats) {
    val cs = MaterialTheme.colorScheme
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Last 4 weeks", style = MaterialTheme.typography.titleSmall, color = cs.primary, modifier = Modifier.padding(start = 4.dp))
        st.items.chunked(2).forEach { pair ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                pair.forEach { s ->
                    Surface(shape = MaterialTheme.shapes.large, color = cs.surfaceContainer, modifier = Modifier.weight(1f)) {
                        Column(Modifier.padding(14.dp)) {
                            Text(s.label, style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant)
                            Text(s.value, style = MaterialTheme.typography.titleLarge)
                            s.change?.let { c ->
                                // Green when the change is in the better direction (lower pace/HR/hard share), neutral otherwise
                                val good = when (s.higherIs) { "lower" -> c < 0; "higher" -> c > 0; else -> null }
                                Text((if (c > 0) "+" else "") + "$c% vs before", style = MaterialTheme.typography.labelMedium,
                                    color = when (good) { true -> com.bennybar.runnersidekick.ui.theme.LocalDataColors.current.pace; false -> cs.tertiary; else -> cs.onSurfaceVariant })
                            }
                        }
                    }
                }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

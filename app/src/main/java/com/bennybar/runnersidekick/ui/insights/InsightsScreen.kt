package com.bennybar.runnersidekick.ui.insights

import androidx.compose.material.icons.outlined.Psychology

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.Bedtime
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.FitnessCenter
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material.icons.outlined.TrendingUp
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.graphics.shapes.RoundedPolygon
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.bennybar.runnersidekick.data.remote.Insight
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.InsightsVm
import com.bennybar.runnersidekick.ui.components.DemoBadge
import com.bennybar.runnersidekick.ui.components.DetailPage
import com.bennybar.runnersidekick.ui.components.EmptyState
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.SectionLabel
import com.bennybar.runnersidekick.ui.components.Tile
import com.bennybar.runnersidekick.ui.components.animatedItem
import com.bennybar.runnersidekick.ui.factory
import com.bennybar.runnersidekick.ui.theme.Tint
import com.bennybar.runnersidekick.ui.theme.accentFor
import com.bennybar.runnersidekick.ui.theme.ink
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.contentOrNull
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

/** Set by links elsewhere (e.g. Today) to open a specific Trends tab: 0 Summary, 1 Compare, 2 Charts. */
object InsightsTab {
    val requested = kotlinx.coroutines.flow.MutableStateFlow<Int?>(null)
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun InsightsScreen(
    onOpenDay: (String) -> Unit, onOpenRun: (String) -> Unit, onOpenReport: (Long) -> Unit, onOpenSettings: () -> Unit,
    vm: InsightsVm = viewModel(factory = factory(::InsightsVm)),
) {
    com.bennybar.runnersidekick.ui.components.TrackVisible(vm)
    val data by vm.insights.collectAsStateWithLifecycle()
    val weekly by vm.weekly.collectAsStateWithLifecycle()
    val fitness by vm.fitness.collectAsStateWithLifecycle()
    val trends by vm.trends.collectAsStateWithLifecycle()
    val days by vm.days.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val busy by vm.busy.collectAsStateWithLifecycle()
    val coach by vm.coach.collectAsStateWithLifecycle()
    val aiOn = com.bennybar.runnersidekick.ui.components.LocalAiEnabled.current
    val coachLoading by vm.coachLoading.collectAsStateWithLifecycle()
    val unwellPending by vm.unwellPending.collectAsStateWithLifecycle()
    val cardio by vm.cardio.collectAsStateWithLifecycle()
    val numbers by vm.numbers.collectAsStateWithLifecycle()
    var numberOpen by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf<String?>(null) }
    val answers by vm.answers.collectAsStateWithLifecycle()
    var cardioOpen by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf(false) }
    val compare by vm.compare.collectAsStateWithLifecycle()
    val firstDay by vm.weekStart.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { vm.loadCoach() }
    LaunchedEffect(tab) { vm.setTab(tab); if (tab == 1) vm.loadCompare() }
    val requestedTab by InsightsTab.requested.collectAsStateWithLifecycle()
    LaunchedEffect(requestedTab) { requestedTab?.let { tab = it; InsightsTab.requested.value = null } }
    var method by remember { mutableStateOf<Insight?>(null) }
    Scaffold { padding ->
        com.bennybar.runnersidekick.ui.components.RefreshBox(busy, vm::refresh, Modifier.padding(padding).fillMaxSize()) {
            val items = data?.value?.insights.orEmpty()
            LazyColumn(contentPadding = PaddingValues(start = 12.dp, end = 12.dp, bottom = 24.dp + com.bennybar.runnersidekick.ui.components.LocalNavBarPadding.current), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item(key = "title") {
                    Row(Modifier.fillMaxWidth().padding(start = 12.dp, end = 4.dp, top = 40.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Trends", style = MaterialTheme.typography.headlineLarge, modifier = Modifier.weight(1f).semantics { heading() })
                        if (data?.value?.synthetic == true) DemoBadge()
                    }
                }
                animatedItem(key = "tabs") { com.bennybar.runnersidekick.ui.components.ChoiceGroup(listOf("Summary", "Compare", "Charts"), tab, { tab = it }) }
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
                // Advice written before "not feeling well" reached the server is held back until it has (it would say train)
                if (!aiOn) Unit  // AI off: no coach at all
                else if (unwellPending) animatedItem(key = "coach") {
                    com.bennybar.runnersidekick.ui.components.Group(title = "AI coach") {
                        row("Waiting for today's check-in", supporting = "You said you're not feeling well. The coach's advice comes back once the " +
                            "server has your check-in (when you're online). Until then: rest or a short walk.",
                            icon = androidx.compose.material.icons.Icons.Outlined.Psychology, iconShape = androidx.compose.material3.MaterialShapes.Flower)
                    }
                } else coach?.value?.let { c -> animatedItem(key = "coach") { CoachCard(c, coachLoading, items, onOpenRun = onOpenRun, onOpenInsight = { method = it }) } }
                fitness?.value?.let { f ->
                    animatedItem(key = "fitness") { FitnessSection(f, onOpenRun = onOpenRun) }
                }
                numbers?.value?.takeIf { it.items.isNotEmpty() }?.let { n -> animatedItem(key = "numbers") { NumbersCard(n) { numberOpen = it } } }
                cardio?.value?.let { c -> animatedItem(key = "cardio") { CardioCard(c) { vm.loadAnswers(); cardioOpen = true } } }
                weekly?.value?.let { w -> animatedItem(key = "weekly") { WeeklyCard(w) { onOpenReport(w.id) } } }
                if (items.isEmpty()) animatedItem(key = "empty") { EmptyState(Icons.Outlined.Insights, "No insights yet", "Pull down to load them after your first sync.") }
                // Hard-running share is in the stats grid and the coach; pace at the same heart rate is charted in Charts
                val patterns = items.filter { it.verdict == "pattern" && it.id !in REPEATED_ELSEWHERE }
                val nulls = items.filter { it.verdict == "no_clear_pattern" }
                val waiting = items.filter { it.verdict == "not_enough_data" }
                if (patterns.isNotEmpty()) animatedItem(key = "patterns") { SectionLabel("Patterns") }
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
    numberOpen?.let { id -> numbers?.value?.items?.firstOrNull { it.id == id }?.let { item ->
        NumberSheet(item, onOpenRun = { rid -> numberOpen = null; onOpenRun(rid) }, onDismiss = { numberOpen = null })
    } }
    if (cardioOpen) cardio?.value?.let { c ->
        CardioSheet(c, answers, onSave = vm::saveAnswer, onOpenRun = { id -> cardioOpen = false; onOpenRun(id) }, onDismiss = { cardioOpen = false })
    }
    method?.let { m -> MethodSheet(data?.value?.insights?.firstOrNull { it.id == m.id } ?: m, onState = { st -> vm.setInsightState(m.id, st) }) { method = null } }
}

@Composable
fun WeeklyCard(w: com.bennybar.runnersidekick.data.remote.WeeklyReport, onOpen: () -> Unit) {
    Tile(tint = Tint.PURPLE, onClick = onOpen) {
        Text("Weekly review · ${Format.shortDate(w.weekStart)} – ${Format.shortDate(w.weekEnd)}", style = MaterialTheme.typography.titleSmall)
        Text(w.headline, style = MaterialTheme.typography.titleLarge)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Next week's focus and details", style = MaterialTheme.typography.labelLarge, color = ink(Tint.PURPLE), modifier = Modifier.weight(1f))
            Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, null, tint = ink(Tint.PURPLE))
        }
    }
}

@Composable
fun InsightCard(i: Insight, emphasised: Boolean, onMethod: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val (icon, _) = categoryStyle(i.category)
    val accent = accentFor(i.category).takeIf { emphasised }
    Tile(spacing = 10.dp) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Surface(shape = RoundedCornerShape(12.dp), color = accent?.container ?: cs.surfaceContainerHighest) {
                Row(Modifier.padding(horizontal = 10.dp, vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(icon, null, Modifier.size(16.dp), tint = accent?.content ?: cs.onSurface)
                    Spacer(Modifier.width(6.dp))
                    Text(i.category.replaceFirstChar(Char::uppercase), style = MaterialTheme.typography.labelMedium, color = accent?.content ?: cs.onSurface)
                }
            }
            if (i.verdict == "pattern" && i.novelty in setOf("new", "changed")) {
                Surface(shape = RoundedCornerShape(12.dp), color = cs.surfaceContainerHighest) {
                    Text(if (i.novelty == "new") "New" else "Changed", style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp))
                }
            }
        }
        Text(i.question, style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
        Text(i.headline, style = if (emphasised) MaterialTheme.typography.titleLarge else MaterialTheme.typography.titleMedium)
        i.chart?.let { InsightChart(it, Modifier.fillMaxWidth()) }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(listOfNotNull(i.sampleSize?.let { "$it runs" },
                when (i.confidence) { "consistent" -> "held on newer data"; "emerging" -> "emerging"; else -> null })
                .joinToString(" · "), style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant, modifier = Modifier.weight(1f))
            TextButton(onClick = onMethod) { Text("Details") }
        }
    }
}

@Composable
private fun MethodSheet(i: Insight, onState: (String?) -> Unit, onDismiss: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    DetailPage(if (i.verdict == "pattern") "Pattern" else "Details", onDismiss) {
        Column(Modifier.padding(horizontal = 12.dp).padding(top = 4.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(i.question, style = MaterialTheme.typography.headlineSmall)
            Text(i.headline, style = MaterialTheme.typography.bodyLarge)
            if (i.detail.isNotBlank()) Text(i.detail, style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
        }
        i.practical?.let {
            Tile(tint = Tint.GREEN) {
                Text("Try this", style = MaterialTheme.typography.titleSmall)
                Text(it, style = MaterialTheme.typography.bodyMedium)
            }
        }
        Group(title = "Method") { custom { Text(i.method, style = MaterialTheme.typography.bodyMedium) } }
        if (i.confounders.isNotEmpty()) Group(title = "What else could explain it") {
            i.confounders.forEach { c -> row(c) }
        }
        // Marking a pattern lives here, not on the card
        if (i.verdict == "pattern") Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (i.userState == null) {
                OutlinedButton(onClick = { onState("working_on") }, Modifier.weight(1f).heightIn(min = 48.dp)) { Text("I'm working on it") }
                OutlinedButton(onClick = { onState("dismissed"); onDismiss() }, Modifier.weight(1f).heightIn(min = 48.dp)) { Text("Dismiss") }
            } else {
                Text(if (i.userState == "working_on") "You're working on this" else "Dismissed", style = MaterialTheme.typography.labelLarge,
                    color = cs.onSurfaceVariant, modifier = Modifier.weight(1f).padding(start = 12.dp))
                OutlinedButton(onClick = { onState(null) }, Modifier.heightIn(min = 48.dp)) { Text("Undo") }
            }
        }
        Text(listOfNotNull(i.sampleSize?.let { "Sample size $it" }, i.evidence.dateRange.takeIf { it.size == 2 }?.let { "${it[0]} – ${it[1]}" },
            i.algorithmVersion, "Associations only, not causes or medical advice").joinToString(" · "),
            style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp))
    }
}

// Chart data is read defensively: a missing or reshaped field draws less (or nothing), never crashes the screen
internal fun JsonObject.list(k: String): List<kotlinx.serialization.json.JsonElement> = (this[k] as? kotlinx.serialization.json.JsonArray).orEmpty()
internal fun kotlinx.serialization.json.JsonElement.str(): String? = (this as? kotlinx.serialization.json.JsonPrimitive)?.contentOrNull
internal fun kotlinx.serialization.json.JsonElement.dbl(): Double? = (this as? kotlinx.serialization.json.JsonPrimitive)?.doubleOrNull
internal fun kotlinx.serialization.json.JsonElement.obj(): JsonObject? = this as? JsonObject

/** Small purpose-built visuals for insight types. Every value is also stated in the card text. */
@Composable
fun InsightChart(chart: JsonObject, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    when (chart["type"]?.jsonPrimitive?.content) {
        "stacked_share" -> {
            val colors = listOf(cs.primary.copy(alpha = 0.25f), cs.primary.copy(alpha = 0.45f), cs.primary.copy(alpha = 0.65f), cs.tertiary, cs.error)
            val labels = chart.list("labels").map { it.str() ?: "" }.take(colors.size)
            val values = chart.list("values").map { it.dbl() ?: 0.0 }.take(colors.size)
            if (values.isEmpty()) return
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
            val series = chart.list("series").map { s ->
                s.obj()?.list("points").orEmpty().mapNotNull { it.obj()?.get("pace_s_per_km")?.dbl() }
            }.filter { it.isNotEmpty() }
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
            val pts = chart.list("points").map { it.obj()?.get("moving_s")?.dbl() ?: 0.0 }
            if (pts.isEmpty()) return
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

/** Each stat's tile colour, by its kind of data: running volume and intensity orange, pace blue, heart rate pink. */
private fun statTint(id: String) = when (id) {
    "pace_s_per_km" -> Tint.BLUE
    "avg_hr" -> Tint.PINK
    else -> Tint.ORANGE
}

/** The key numbers of the last 4 weeks, each with its change against the 4 weeks before. */
@Composable
private fun StatsGrid(st: com.bennybar.runnersidekick.data.remote.Stats) {
    val cs = MaterialTheme.colorScheme
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionLabel("Last 4 weeks")
        st.items.chunked(2).forEach { pair ->
            Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                pair.forEach { s ->
                    Tile(Modifier.weight(1f).fillMaxHeight(), tint = statTint(s.id), spacing = 2.dp) {
                        Text(s.label, style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant)
                        Text(s.value, style = MaterialTheme.typography.headlineSmall, maxLines = 1)
                        s.change?.let { c ->
                            // Said in words and coloured: green in the better direction (lower pace/HR/hard share), orange the other way
                            val good = if (c == 0) null else when (s.higherIs) { "lower" -> c < 0; "higher" -> c > 0; else -> null }
                            Text(if (c == 0) "Same as before" else (if (c > 0) "+" else "") + "$c% vs before" +
                                when (good) { true -> " · better"; false -> " · worse"; else -> "" },
                                style = MaterialTheme.typography.labelMedium, fontWeight = if (good != null) FontWeight.SemiBold else null,
                                color = when (good) { true -> ink(Tint.GREEN); false -> ink(Tint.ORANGE); else -> cs.onSurfaceVariant })
                        }
                    }
                }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

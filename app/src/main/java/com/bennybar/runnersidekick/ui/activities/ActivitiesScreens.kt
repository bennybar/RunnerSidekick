package com.bennybar.runnersidekick.ui.activities

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material.icons.outlined.Speed
import androidx.compose.material.icons.outlined.Timeline
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.bennybar.runnersidekick.data.local.Units
import com.bennybar.runnersidekick.data.remote.ActivitySummary
import com.bennybar.runnersidekick.data.remote.Finding
import com.bennybar.runnersidekick.data.remote.PostRunReport
import com.bennybar.runnersidekick.ui.ActivitiesVm
import com.bennybar.runnersidekick.ui.ActivityVm
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.components.DemoBadge
import com.bennybar.runnersidekick.ui.components.EmptyState
import com.bennybar.runnersidekick.ui.components.EvidenceSheet
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.SeriesChart
import com.bennybar.runnersidekick.ui.components.ShapeBadge
import com.bennybar.runnersidekick.ui.factory
import com.bennybar.runnersidekick.ui.theme.LocalDataColors
import java.time.LocalDate
import java.time.temporal.WeekFields
import kotlin.math.roundToInt

private val GARMIN_LABELS = mapOf(
    "aerobicTrainingEffect" to "Aerobic training effect",
    "anaerobicTrainingEffect" to "Anaerobic training effect",
    "trainingEffectLabel" to "Training effect",
    "activityTrainingLoad" to "Training load",
    "vO2MaxValue" to "VO₂ max",
    "calories" to "Calories (kcal)",
)

private enum class Filter(val label: String) { ALL("All"), ROAD("Road"), TRAIL("Trail"), TREADMILL("Treadmill") }

/** Garmin names most runs just "Running"; only show names that say something. */
private fun displayName(name: String?) = name?.takeUnless { it.isBlank() || it.equals("Running", true) || it.endsWith(" Running") }

@Composable
private fun BigStat(value: String, unit: String?, label: String, color: Color, modifier: Modifier = Modifier) {
    Column(modifier) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(value, style = MaterialTheme.typography.headlineLarge, color = color)
            unit?.let { Text(" $it", style = MaterialTheme.typography.titleMedium, color = color.copy(alpha = 0.75f), modifier = Modifier.padding(bottom = 4.dp)) }
        }
        Text(label, style = MaterialTheme.typography.labelLarge, color = color.copy(alpha = 0.8f))
    }
}

private fun distanceParts(m: Double?, units: Units): Pair<String, String> = Format.distance(m, units).split(" ").let { it[0] to it.getOrElse(1) { "" } }

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun ActivitiesScreen(onOpen: (String) -> Unit, vm: ActivitiesVm = viewModel(factory = factory(::ActivitiesVm))) {
    val acts by vm.activities.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val units = settings?.units ?: Units.METRIC
    var filter by rememberSaveable { mutableStateOf(Filter.ALL) }
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        topBar = { LargeTopAppBar(title = { Text("Activities") }, scrollBehavior = scroll, actions = { if (acts?.value?.any { it.synthetic } == true) DemoBadge() }) },
    ) { padding ->
        PullToRefreshBox(busy, vm::refresh, Modifier.padding(padding).fillMaxSize()) {
            val all = acts?.value.orEmpty().filter { it.sport != "other" }
            val shown = all.filter {
                when (filter) {
                    Filter.ALL -> true
                    Filter.ROAD -> it.sport == "running"
                    Filter.TRAIL -> it.sport == "trail_running"
                    Filter.TREADMILL -> it.sport == "treadmill_running"
                }
            }
            val wf = WeekFields.ISO
            val weeks = shown.groupBy { LocalDate.parse(it.localDate).with(wf.dayOfWeek(), 1) }
            LazyColumn(contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                weeks.entries.firstOrNull()?.let { (start, runs) -> item { WeekHero(start, runs, units) } }
                item {
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Filter.entries.forEach { f -> FilterChip(selected = filter == f, onClick = { filter = f }, label = { Text(f.label) }) }
                    }
                }
                if (shown.isEmpty()) item {
                    EmptyState(Icons.AutoMirrored.Outlined.DirectionsRun, if (acts == null) "No runs loaded" else "No runs here",
                        if (acts == null) "Pull down to load your runs." else "No runs match this filter in the synced period.")
                }
                weeks.forEach { (weekStart, runs) ->
                    item(key = "w$weekStart") {
                        val dist = runs.sumOf { it.distanceM ?: 0.0 }
                        val time = runs.sumOf { it.movingS ?: 0.0 }
                        Group(title = "Week of ${Format.shortDate(weekStart.toString())} · ${runs.size} ${if (runs.size == 1) "run" else "runs"} · " +
                            "${Format.distance(dist, units)} · ${Format.hoursMinutes(time)}") {
                            runs.forEach { a ->
                                row(
                                    headline = "${Format.distance(a.distanceM, units)} · ${Format.pace(a.paceMovingSPerKm, units)}",
                                    overline = Format.activityTime(a.startUtc, a.utcOffsetS),
                                    supporting = listOfNotNull(displayName(a.name), "${Format.duration(a.movingS)} moving",
                                        a.avgHr?.let { "${it.roundToInt()} bpm" }).joinToString(" · "),
                                    icon = Icons.AutoMirrored.Outlined.DirectionsRun, iconShape = MaterialShapes.Cookie9Sided,
                                    onClick = { onOpen(a.sourceId) },
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun WeekHero(start: LocalDate, runs: List<ActivitySummary>, units: Units) {
    val on = MaterialTheme.colorScheme.onPrimaryContainer
    val (d, du) = distanceParts(runs.sumOf { it.distanceM ?: 0.0 }, units)
    Surface(shape = MaterialTheme.shapes.extraLarge, color = MaterialTheme.colorScheme.primaryContainer, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(if (start == LocalDate.now().with(WeekFields.ISO.dayOfWeek(), 1)) "This week" else "Week of ${Format.shortDate(start.toString())}",
                style = MaterialTheme.typography.titleMedium, color = on)
            Row {
                BigStat(d, du, "distance", on, Modifier.weight(1f))
                BigStat("${runs.size}", null, if (runs.size == 1) "run" else "runs", on, Modifier.weight(0.7f))
                BigStat(Format.hoursMinutes(runs.sumOf { it.movingS ?: 0.0 }).replace(" min", "m").replace(" h ", "h "), null, "moving", on, Modifier.weight(1f))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun ActivityDetailScreen(id: String, onBack: () -> Unit, vm: ActivityVm = viewModel(key = id, factory = factory { ActivityVm(it, id) })) {
    val detail by vm.detail.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val units = settings?.units ?: Units.METRIC
    val snackbar = remember { SnackbarHostState() }
    var evidence by remember { mutableStateOf<Finding?>(null) }
    LaunchedEffect(error) { error?.let { snackbar.showSnackbar(it); vm.clearError() } }
    val r = detail?.value?.report
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(r?.activity?.let { Format.activityTime(it.startUtc, it.utcOffsetS) } ?: "Run", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } },
                actions = { if (r?.synthetic == true) DemoBadge() },
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        PullToRefreshBox(busy, vm::refresh, Modifier.padding(padding).fillMaxSize()) {
            if (r == null) {
                LazyColumn { item { EmptyState(Icons.AutoMirrored.Outlined.DirectionsRun, if (busy) "Loading run" else "Run not cached",
                    if (busy) "Fetching analysis…" else "Connect to the backend to load this run.") } }
                return@PullToRefreshBox
            }
            LazyColumn(contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                item { RunHero(r, units) }
                if (r.story.isNotEmpty()) item {
                    Group(title = "How the run went") {
                        custom {
                            r.story.forEach { line ->
                                Row(Modifier.padding(vertical = 4.dp)) {
                                    Text("•", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.primary)
                                    Spacer(Modifier.width(10.dp))
                                    Text(line, style = MaterialTheme.typography.bodyLarge)
                                }
                            }
                        }
                    }
                }
                val efforts = listOf("1k", "5k", "10k", "half").mapNotNull { r.bestEfforts[it] }
                if (efforts.isNotEmpty()) item {
                    Group(title = "Best efforts in this run") {
                        efforts.forEach { e ->
                            row("${e.label}: ${Format.duration(e.elapsedS)}",
                                supporting = Format.pace(e.paceSPerKm, units) + (e.previousBestS?.let { " · your previous best ${Format.duration(it)}" } ?: " · first one recorded"),
                                icon = Icons.Outlined.EmojiEvents, iconShape = MaterialShapes.Sunny,
                                trailing = if (e.isBest) ({
                                    Surface(shape = MaterialTheme.shapes.small, color = MaterialTheme.colorScheme.tertiaryContainer) {
                                        Text("New best", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onTertiaryContainer,
                                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp))
                                    }
                                }) else null)
                        }
                    }
                }
                detail?.value?.chart?.let { c ->
                    item {
                        val colors = LocalDataColors.current
                        Surface(shape = MaterialTheme.shapes.large, color = MaterialTheme.colorScheme.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
                                SeriesChart("Pace (moving)", c.t, c.speed.map { s -> s?.let { 1000.0 / it } }, colors.pace,
                                    { Format.pace(it, units) }, Modifier.fillMaxWidth(), invert = true,
                                    description = "Pace over time. Gaps are stops or missing data.")
                                SeriesChart("Heart rate (bpm)", c.t, c.hr, colors.heartRate, { "${it.roundToInt()}" }, Modifier.fillMaxWidth(),
                                    description = "Heart rate over time. Gaps are missing sensor data, not zero.")
                                Text("Gaps are stops or missing data. They aren't filled in.", style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
                item {
                    Surface(shape = MaterialTheme.shapes.large, color = MaterialTheme.colorScheme.secondaryContainer, modifier = Modifier.fillMaxWidth()) {
                        Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
                            ShapeBadge(Icons.Outlined.Insights, MaterialShapes.Sunny, Modifier.size(44.dp),
                                container = MaterialTheme.colorScheme.secondary, content = MaterialTheme.colorScheme.onSecondary)
                            Spacer(Modifier.width(16.dp))
                            Column {
                                Text("Next focus", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSecondaryContainer)
                                Text(r.nextFocus, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSecondaryContainer)
                            }
                        }
                    }
                }
                r.narrative?.takeIf { it.status == "ok" }?.let { n ->
                    item {
                        Group(title = "AI summary · ${n.model ?: n.provider}") {
                            custom {
                                Text(n.sentences.joinToString(" ") { it.text }, style = MaterialTheme.typography.bodyLarge)
                                Text("Numbers come from the analysis below.", style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 8.dp))
                            }
                        }
                    }
                }
                item {
                    Group(title = "Analysis") {
                        r.findings.forEach { f -> row(f.title, supporting = f.statement, icon = Icons.Outlined.Timeline, iconShape = MaterialShapes.Pill,
                            onClick = { evidence = f }) }
                        val d = r.decoupling
                        val kind = when (r.classification.kind) { "steady" -> "Steady effort"; "variable" -> "Variable effort / intervals"; else -> "Effort type unknown" }
                        if (!d.eligible) row("Heart-rate drift not calculated", supporting = "$kind. " + d.reasons.joinToString("; "),
                            icon = Icons.Outlined.Favorite, iconShape = MaterialShapes.Pill)
                    }
                }
                item { EffortGroup(r, vm::setEffort) }
                if (r.splits.isNotEmpty()) item { Splits(r, units) }
                if (r.comparable.runs.isNotEmpty()) item {
                    Group(title = "Similar runs (${r.comparable.n}) · distance ±20%, similar climbing, steady") {
                        row("This run", supporting = "${Format.pace(r.paceMovingSPerKm, units)} · ${r.activity.avgHr?.let { "${it.roundToInt()} bpm" } ?: "no HR"}",
                            icon = Icons.Outlined.Speed, iconShape = MaterialShapes.Cookie9Sided)
                        r.comparable.runs.forEach { c ->
                            row("${Format.shortDate(c.localDate)} · ${Format.distance(c.distanceM, units)}",
                                supporting = "${Format.pace(c.paceSPerKm, units)} · ${c.avgHr?.let { "${it.roundToInt()} bpm" } ?: "no HR"}")
                        }
                    }
                }
                val garmin = r.garminMetrics.mapNotNull { (k, v) -> GARMIN_LABELS[k]?.let { it to v.toString().trim('"') } }
                if (garmin.isNotEmpty()) item {
                    Group(title = "From Garmin · shown as supplied") { garmin.forEach { (label, v) -> row(label, trailing = { Text(v, style = MaterialTheme.typography.titleMedium) }) } }
                }
            }
        }
    }
    evidence?.let { EvidenceSheet(it) { evidence = null } }
}

@Composable
private fun RunHero(r: PostRunReport, units: Units) {
    val a = r.activity
    val on = MaterialTheme.colorScheme.onPrimaryContainer
    val (d, du) = distanceParts(a.distanceM, units)
    Surface(shape = MaterialTheme.shapes.extraLarge, color = MaterialTheme.colorScheme.primaryContainer, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            displayName(a.name)?.let { Text(it, style = MaterialTheme.typography.titleMedium, color = on) }
            Row(verticalAlignment = Alignment.Bottom) {
                Text(d, style = MaterialTheme.typography.displayLarge, color = on)
                Text(" $du", style = MaterialTheme.typography.headlineSmall, color = on.copy(alpha = 0.75f), modifier = Modifier.padding(bottom = 10.dp))
            }
            Row {
                BigStat(Format.pace(r.paceMovingSPerKm, units).substringBefore(" "), Format.pace(r.paceMovingSPerKm, units).substringAfter(" "), "moving pace", on, Modifier.weight(1f))
                BigStat(a.avgHr?.roundToInt()?.toString() ?: "—", "bpm", "avg heart rate", on, Modifier.weight(1f))
            }
            Row {
                BigStat(Format.duration(a.movingS), null, "moving", on, Modifier.weight(1f))
                BigStat(Format.duration(a.elapsedS), null, "elapsed", on, Modifier.weight(1f))
                BigStat("+${Format.elevation(a.elevationGainM, units)}", null, "climb", on, Modifier.weight(1f))
            }
            Text("Pace uses moving time (stops excluded). Elapsed includes stops.", style = MaterialTheme.typography.labelSmall, color = on.copy(alpha = 0.75f))
        }
    }
}

@Composable
private fun EffortGroup(r: PostRunReport, onSet: (Int) -> Unit) {
    Group(title = "How hard did it feel?") {
        custom {
            Text("Perceived effort, 1 (very easy) to 10 (max)", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                (1..10).forEach { v -> FilterChip(selected = r.effort?.rpe == v, onClick = { onSet(v) }, label = { Text("$v") }) }
            }
            r.effort?.let {
                Text("Session-RPE load ${it.sessionRpeLoad}. ${it.note}", style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 10.dp))
            }
        }
    }
}

@Composable
private fun Splits(r: PostRunReport, units: Units) {
    Group(title = "Splits") {
        custom {
            Row(Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                listOf("#", "Pace", "Flat-equiv.", "HR", "Zone", "Climb").forEachIndexed { i, h ->
                    Text(h, Modifier.weight(if (i == 0) 0.5f else 1f), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            HorizontalDivider()
            r.splits.forEach { s ->
                Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("${s.idx + 1}", Modifier.weight(0.5f), style = MaterialTheme.typography.bodyMedium)
                    Text(Format.pace(s.paceSPerKm, units).substringBefore(" ") + if (!s.complete) "*" else "", Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                    Text(Format.pace(s.gapPaceSPerKm, units).substringBefore(" "), Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(s.avgHr?.roundToInt()?.toString() ?: "—", Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    Text(s.zone?.takeIf { it > 0 }?.let { "Z$it" } ?: "—", Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    Text("+${Format.elevation(s.elevationGainM, units)}", Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                }
            }
            Text("Flat-equivalent = grade-adjusted pace (Minetti energy-cost model): what the effort would give on flat ground.",
                style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
            if (r.splits.any { !it.complete }) Text("* Partial split, left out of split comparisons", style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
            Spacer(Modifier.height(2.dp))
        }
    }
}

package com.bennybar.runnersidekick.ui.activities

import androidx.compose.foundation.selection.toggleable
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.MoreVert

import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Download

import androidx.compose.animation.animateContentSize

import androidx.compose.material.icons.outlined.Sync

import androidx.compose.material.icons.outlined.AutoAwesome


import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.PlainTooltip
import androidx.compose.material.icons.outlined.Info
import kotlinx.coroutines.launch
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
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
import com.bennybar.runnersidekick.ui.components.BigValue
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.SectionLabel
import com.bennybar.runnersidekick.ui.components.Tile
import com.bennybar.runnersidekick.ui.components.SeriesChart
import com.bennybar.runnersidekick.ui.factory
import com.bennybar.runnersidekick.ui.theme.LocalDataColors
import com.bennybar.runnersidekick.ui.theme.Tint
import com.bennybar.runnersidekick.ui.theme.ink
import java.time.LocalDate
import kotlin.math.roundToInt

// Garmin's training effect is shown with a verdict under "How it went", so it isn't repeated here
private val GARMIN_LABELS = mapOf(
    "activityTrainingLoad" to "Training load",
    "calories" to "Calories (kcal)",
)

/** Garmin's numbers as people read them: whole numbers where decimals mean nothing. */
private fun garminValue(key: String, v: String): String = when (key) {
    "activityTrainingLoad", "calories" -> v.toDoubleOrNull()?.roundToInt()?.toString() ?: v
    else -> v
}

private enum class Filter(val label: String) { ALL("All"), ROAD("Road"), TRAIL("Trail"), TREADMILL("Treadmill") }

/** Garmin names most runs just "Running"; only show names that say something. */
private fun displayName(name: String?) = name?.takeUnless { it.isBlank() || it.equals("Running", true) || it.endsWith(" Running") }

@Composable
private fun BigStat(value: String, label: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(value, style = MaterialTheme.typography.headlineMedium, maxLines = 1)
        Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

private fun distanceParts(m: Double?, units: Units): Pair<String, String> = Format.distance(m, units).split(" ").let { it[0] to it.getOrElse(1) { "" } }

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun ActivitiesScreen(onOpen: (String) -> Unit, onTrophies: () -> Unit = {}, vm: ActivitiesVm = viewModel(factory = factory(::ActivitiesVm))) {
    com.bennybar.runnersidekick.ui.components.TrackVisible(vm)
    val acts by vm.activities.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val firstDay by vm.weekStart.collectAsStateWithLifecycle()
    val units = settings?.units ?: Units.METRIC
    var filter by rememberSaveable { mutableStateOf(Filter.ALL) }
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    val listSnackbar = remember { SnackbarHostState() }
    val syncResult by vm.syncResult.collectAsStateWithLifecycle()
    val listError by vm.error.collectAsStateWithLifecycle()
    LaunchedEffect(syncResult) { syncResult?.let { listSnackbar.showSnackbar(it); vm.clearSyncResult() } }
    val syncStatus by vm.status.collectAsStateWithLifecycle()
    LaunchedEffect(listError) { listError?.let { listSnackbar.showSnackbar(it); vm.clearError() } }
    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        topBar = {
            LargeTopAppBar(title = { Text("Runs") }, scrollBehavior = scroll, actions = {
                if (acts?.value?.any { it.synthetic } == true) DemoBadge()
                androidx.compose.material3.IconButton(onClick = onTrophies) { Icon(Icons.Outlined.EmojiEvents, "Your records") }
                // Fetch a run you just finished from Garmin without waiting for the hourly sync
                val wait = com.bennybar.runnersidekick.ui.components.syncWait(syncStatus?.value?.syncNextAllowedAt)
                androidx.compose.material3.FilledTonalButton(onClick = vm::syncNow, enabled = !busy && wait == null,
                    contentPadding = PaddingValues(horizontal = 14.dp), modifier = Modifier.padding(end = 8.dp)) {
                    if (busy) androidx.compose.material3.LoadingIndicator(Modifier.size(18.dp))
                    else Icon(Icons.Outlined.Sync, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(if (busy) "Syncing…" else wait?.let { "Next sync $it" } ?: "Get new runs")
                }
            })
        },
        snackbarHost = { SnackbarHost(listSnackbar, Modifier.padding(bottom = com.bennybar.runnersidekick.ui.components.LocalNavBarPadding.current)) }  // above the floating bar,
    ) { padding ->
        com.bennybar.runnersidekick.ui.components.RefreshBox(busy, vm::refresh, Modifier.padding(padding).fillMaxSize()) {
            val all = acts?.value.orEmpty().filter { it.sport != "other" }
            val shown = all.filter {
                when (filter) {
                    Filter.ALL -> true
                    Filter.ROAD -> it.sport == "running"
                    Filter.TRAIL -> it.sport == "trail_running"
                    Filter.TREADMILL -> it.sport == "treadmill_running"
                }
            }
            val weeks = shown.groupBy { Format.weekStart(LocalDate.parse(it.localDate), firstDay) }
            LazyColumn(contentPadding = PaddingValues(start = 12.dp, end = 12.dp, top = 4.dp, bottom = 24.dp + com.bennybar.runnersidekick.ui.components.LocalNavBarPadding.current), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                weeks.entries.firstOrNull()?.let { (start, runs) -> item { WeekHero(start, runs, units, firstDay) } }
                item {
                    com.bennybar.runnersidekick.ui.components.ChoiceGroup(Filter.entries.map { it.label }, filter.ordinal, { filter = Filter.entries[it] })
                }
                if (shown.isEmpty()) item {
                    EmptyState(Icons.AutoMirrored.Outlined.DirectionsRun, if (acts == null) "No runs loaded" else "No runs here",
                        if (acts == null) "Pull down to load your runs." else "No runs match this filter in the synced period.")
                }
                weeks.forEach { (weekStart, runs) ->
                    item(key = "w$weekStart") {
                        val dist = runs.sumOf { it.distanceM ?: 0.0 }
                        val time = runs.sumOf { it.movingS ?: 0.0 }
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            SectionLabel("Week of ${Format.shortDate(weekStart.toString())} · ${runs.size} ${if (runs.size == 1) "run" else "runs"} · " +
                                "${Format.distance(dist, units)} · ${Format.hoursMinutes(time)}")
                            Tile(contentPadding = PaddingValues(vertical = 4.dp), spacing = 0.dp) {
                                runs.forEachIndexed { i, a ->
                                    if (i > 0) HorizontalDivider(Modifier.padding(horizontal = 18.dp), color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.07f))
                                    RunRow(a, units) { onOpen(a.sourceId) }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

/** One run in a week's list: when, distance and pace, then name, moving time and heart rate; a run that set a record
 *  says so in words and wears a trophy. */
@Composable
private fun RunRow(a: ActivitySummary, units: Units, onClick: () -> Unit) {
    val sub = MaterialTheme.colorScheme.onSurfaceVariant
    Row(Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onClick).heightIn(min = 56.dp).padding(horizontal = 18.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically) {
        val best = a.records.isNotEmpty()
        com.bennybar.runnersidekick.ui.components.ShapeBadge(
            if (best) Icons.Outlined.EmojiEvents else Icons.AutoMirrored.Outlined.DirectionsRun,
            if (best) androidx.compose.material3.MaterialShapes.Sunny else androidx.compose.material3.MaterialShapes.Cookie6Sided,
            Modifier.size(36.dp).then(if (best) Modifier.semantics { contentDescription = "Set a record" } else Modifier), container = (if (best) Tint.AMBER else Tint.ORANGE).hue.copy(alpha = 0.22f),
            content = ink(if (best) Tint.AMBER else Tint.ORANGE), iconSize = 20.dp)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(Format.activityTime(a.startUtc, a.utcOffsetS), style = MaterialTheme.typography.labelMedium, color = sub)
            Text("${Format.distance(a.distanceM, units)} · ${Format.pace(a.paceMovingSPerKm, units)}", style = MaterialTheme.typography.titleMedium)
            Text(listOfNotNull(displayName(a.name), "${Format.duration(a.movingS)} moving", a.avgHr?.let { "${it.roundToInt()} bpm" }).joinToString(" · "),
                style = MaterialTheme.typography.bodyMedium, color = sub)
            if (a.records.isNotEmpty()) Text("New best: " + a.records.joinToString(", ") { "${it.title.removePrefix("Fastest ")} ${it.value}" },
                style = MaterialTheme.typography.labelLarge, color = ink(Tint.AMBER))
        }
        Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, null, tint = sub)
    }
}

@Composable
private fun WeekHero(start: LocalDate, runs: List<ActivitySummary>, units: Units, firstDay: java.time.DayOfWeek) {
    val (d, du) = distanceParts(runs.sumOf { it.distanceM ?: 0.0 }, units)
    Tile(tint = Tint.ORANGE, spacing = 12.dp) {
        Text(if (start == Format.weekStart(LocalDate.now(), firstDay)) "This week" else "Week of ${Format.shortDate(start.toString())}",
            style = MaterialTheme.typography.titleSmall)
        Row {
            BigStat(d, du, Modifier.weight(1f))
            BigStat("${runs.size}", if (runs.size == 1) "run" else "runs", Modifier.weight(1f))
            BigStat(Format.hoursMinutes(runs.sumOf { it.movingS ?: 0.0 }).replace(" min", "m").replace(" h ", "h "), "moving", Modifier.weight(1f))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun ActivityDetailScreen(id: String, onBack: () -> Unit, onOpenRun: (String) -> Unit = {}, vm: ActivityVm = viewModel(key = id, factory = factory { ActivityVm(it, id) })) {
    com.bennybar.runnersidekick.ui.components.TrackVisible(vm)
    val detail by vm.detail.collectAsStateWithLifecycle()
    val ai by vm.ai.collectAsStateWithLifecycle()
    val routes by vm.routes.collectAsStateWithLifecycle()
    var routeOpen by remember { mutableStateOf(false) }
    val aiOn = com.bennybar.runnersidekick.ui.components.LocalAiEnabled.current
    val aiScroll = remember { mutableStateOf(0) }
    val runList = androidx.compose.foundation.lazy.rememberLazyListState()
    // The AI card comes after the title, the header, the verdict and (when there's one) the decoupling card
    LaunchedEffect(aiScroll.value) {
        val rr = detail?.value?.report
        if (aiScroll.value > 0) runList.animateScrollToItem(2 + (if (rr?.verdict != null) 1 else 0) +
            if (rr?.decoupling?.let { it.decouplingPct != null || it.reasons.isNotEmpty() } == true) 1 else 0)
    }
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val units = settings?.units ?: Units.METRIC
    val snackbar = remember { SnackbarHostState() }
    var evidence by remember { mutableStateOf<Finding?>(null) }
    LaunchedEffect(error) { error?.let { snackbar.showSnackbar(it); vm.clearError() } }
    val notice by vm.notice.collectAsStateWithLifecycle()
    LaunchedEffect(notice) { notice?.let { snackbar.showSnackbar(it); vm.clearNotice() } }
    val context = androidx.compose.ui.platform.LocalContext.current
    val r = detail?.value?.report
    var runMenu by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    // A run from Watchletic can be deleted there too, but only when the runner ticks it, each time
    var alsoWatchletic by remember { mutableStateOf(false) }
    val wl by vm.watchletic.collectAsStateWithLifecycle()
    if (confirmDelete) androidx.compose.material3.AlertDialog(
        onDismissRequest = { confirmDelete = false },
        title = { Text("Delete this run?") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("It leaves your runs, records, trends and reports, and won't come back with the next sync or upload. " +
                    "Use it for test recordings and mistakes.")
                if (detail?.value?.watchletic == true) {
                    val allowed = wl?.canDelete == true
                    Row(Modifier.fillMaxWidth().toggleable(alsoWatchletic && allowed, enabled = allowed, role = androidx.compose.ui.semantics.Role.Checkbox) { alsoWatchletic = it },
                        verticalAlignment = Alignment.CenterVertically) {
                        androidx.compose.material3.Checkbox(alsoWatchletic && allowed, onCheckedChange = null, enabled = allowed)
                        Spacer(Modifier.width(8.dp))
                        Column {
                            Text("Also delete it in Watchletic", style = MaterialTheme.typography.bodyLarge)
                            Text(if (allowed) "Permanently, in Watchletic too" else "Reconnect Watchletic in Me to allow this",
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        },
        confirmButton = { androidx.compose.material3.TextButton(onClick = { confirmDelete = false
            vm.deleteRun(alsoWatchletic && wl?.canDelete == true, onBack) }) { Text("Delete") } },
        dismissButton = { androidx.compose.material3.TextButton(onClick = { confirmDelete = false }) { Text("Cancel") } })
    Scaffold(
        topBar = {
            TopAppBar(
                // The run's name and date are the page's big title, in the list below
                title = {},
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } },
                actions = {
                    if (r?.synthetic == true) DemoBadge()
                    // The whole run (analysis, splits, minute-by-minute data, AI input) as one Markdown file in Downloads
                    if (r != null) IconButton(onClick = {
                        val start = java.time.Instant.parse(r.activity.startUtc).atOffset(java.time.ZoneOffset.ofTotalSeconds(r.activity.utcOffsetS ?: 0))
                        vm.export(context, start.format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd-HHmmss")) + "-running.md")
                    }) { Icon(Icons.Outlined.Download, "Export run to Downloads") }
                    if (r != null && r.synthetic != true) androidx.compose.foundation.layout.Box {
                        IconButton(onClick = { runMenu = true }) { Icon(Icons.Outlined.MoreVert, "More") }
                        androidx.compose.material3.DropdownMenu(runMenu, onDismissRequest = { runMenu = false }) {
                            androidx.compose.material3.DropdownMenuItem(text = { Text("Delete run") },
                                leadingIcon = { Icon(Icons.Outlined.DeleteOutline, null) },
                                onClick = { runMenu = false; confirmDelete = true })
                        }
                    }
                    // AI input sits next to the title: one tap asks for it, then the list scrolls to the card at the top
                    if (r != null && aiOn) {
                        // Any finished AI input for this run counts (also one kept from before the run's data was refreshed)
                        // ...unless you changed the run's type since: then it can be rewritten for the new type
                        val st = ai?.value?.let { v -> if (v.status != "ok" && v.previous?.status == "ok" && !v.stale) "ok" else v.status }
                        androidx.compose.material3.FilledTonalButton(
                            onClick = { vm.askAi(); aiScroll.value++ },
                            // Already written for this run: nothing more to ask for (it's shown at the top)
                            enabled = st !in setOf("ok", "pending", "disabled", "not_configured", "budget_exceeded"),
                            contentPadding = PaddingValues(horizontal = 14.dp), modifier = Modifier.padding(end = 8.dp)) {
                            if (st == "pending") androidx.compose.material3.LoadingIndicator(Modifier.size(18.dp))
                            else Icon(if (st == "ok") Icons.Outlined.CheckCircle else Icons.Outlined.AutoAwesome, null, Modifier.size(18.dp))
                            Spacer(Modifier.width(6.dp))
                            Text(if (st == "ok") "AI input ready" else if (ai?.value?.stale == true) "Update AI input" else "Get AI input")
                        }
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbar, Modifier.padding(bottom = com.bennybar.runnersidekick.ui.components.LocalNavBarPadding.current)) }  // above the floating bar,
    ) { padding ->
        com.bennybar.runnersidekick.ui.components.RefreshBox(busy, vm::refresh, Modifier.padding(padding).fillMaxSize()) {
            if (r == null) {
                LazyColumn { item { EmptyState(Icons.AutoMirrored.Outlined.DirectionsRun, if (busy) "Loading run" else "Run not cached",
                    if (busy) "Fetching analysis…" else "Connect to the backend to load this run.") } }
                return@RefreshBox
            }
            if (routeOpen) detail?.value?.route?.let { rt -> routes?.value?.routes?.firstOrNull { it.id == rt.id }?.let { full ->
                RoutePage(full, routes?.value?.basis.orEmpty(), units, current = id, onOpenRun = { routeOpen = false; onOpenRun(it) },
                    onNotThis = { routeOpen = false; vm.notThisRoute() }, onBack = { routeOpen = false })
            } }
            LazyColumn(state = runList, contentPadding = PaddingValues(start = 12.dp, end = 12.dp, bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { RunTitle(r) }
                item { RunHero(r, units) }
                r.verdict?.let { v -> item(key = "verdict") { VerdictCard(v) } }
                // Shown also when it couldn't be measured, saying why (a short run, missing heart rate), instead of nothing
                if (r.decoupling.decouplingPct != null || r.decoupling.reasons.isNotEmpty()) item { DecouplingCard(r.decoupling) }
                // Shown at the top once asked for (or already written); the button lives in the top bar
                if (aiOn && ai?.value?.let { it.status != "none" || it.previous != null } == true) item(key = "ai") { RunAiCard(ai?.value, onAsk = vm::askAi) }
                item { com.bennybar.runnersidekick.ui.today.IntentPicker(r.intent, vm::setIntent) }
                // The repeat route this run belongs to, recognised from its shape; opens how the route has gone
                detail?.value?.route?.let { rt -> item(key = "route") {
                    Group(title = "Route", tint = Tint.BLUE) {
                        row(routeTitle(rt.name, rt.distanceKm, rt.loop, rt.runs), supporting = rt.progress ?: "Recognised from its shape",
                            onClick = { vm.loadRoutes(); routeOpen = true })
                    }
                } }
                if (r.checks.isNotEmpty()) item {
                    Group(title = "How it went") {
                        r.checks.forEach { c -> row(c.title, supporting = c.say, trailing = { com.bennybar.runnersidekick.ui.components.VerdictChip(c.verdict) }) }
                    }
                } else if (r.story.isNotEmpty()) item {
                    Group(title = "How the run went") {
                        custom {
                            r.story.forEach { line ->
                                Row(Modifier.padding(vertical = 4.dp)) {
                                    Text("•", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
                                trailing = if (e.isBest) ({
                                    Surface(shape = MaterialTheme.shapes.small, color = Tint.AMBER.hue.copy(alpha = 0.22f)) {
                                        Text("New best", style = MaterialTheme.typography.labelLarge, color = ink(Tint.AMBER),
                                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp))
                                    }
                                }) else null)
                        }
                    }
                }
                detail?.value?.chart?.let { c ->
                    item {
                        val colors = LocalDataColors.current
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            SectionLabel("Pace and heart rate")
                            Tile(spacing = 20.dp) {
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
                    Tile(tint = Tint.GREEN, spacing = 4.dp) {
                        Text("Next focus", style = MaterialTheme.typography.titleSmall)
                        Text(r.nextFocus, style = MaterialTheme.typography.bodyLarge)
                    }
                }
                // Only findings that say something; checks that couldn't run aren't listed
                if (r.findings.isNotEmpty()) item {
                    Group(title = "Analysis") {
                        r.findings.forEach { f -> row(f.title, supporting = f.statement, onClick = { evidence = f }) }
                    }
                }
                if (r.splits.isNotEmpty()) item { Splits(r, units) }
                if (r.comparable.runs.isNotEmpty()) item {
                    Group(title = "Similar runs (${r.comparable.n}) · distance ±20%, similar climbing, steady") {
                        row("This run", supporting = "${Format.pace(r.paceMovingSPerKm, units)} · ${r.activity.avgHr?.let { "${it.roundToInt()} bpm" } ?: "no HR"}")
                        r.comparable.runs.forEach { c ->
                            row("${Format.shortDate(c.localDate)} · ${Format.distance(c.distanceM, units)}",
                                supporting = "${Format.pace(c.paceSPerKm, units)} · ${c.avgHr?.let { "${it.roundToInt()} bpm" } ?: "no HR"}")
                        }
                    }
                }
                // The watch's headline VO2 max for that day (one decimal, as the watch shows it); the run's own whole-number
                // estimate only when the day's value is missing, labelled as such. Beside it, Runner Sidekick's from this run.
                val vo2 = r.garminVo2maxDay?.let { listOf("VO₂ max (${r.watch}'s)" to "%.1f".format(it.value)) }
                    ?: r.garminMetrics["vO2MaxValue"]?.let { listOf("VO₂ max (this run's estimate)" to it.toString().trim('"')) }.orEmpty()
                val ours = r.vo2Ours?.let { o -> listOf("VO₂ max (Runner Sidekick, this run${if (o.hillAdjusted) ", hill-adjusted" else ""})" to
                    (o.value?.let { "%.1f".format(it) } ?: "—")) }.orEmpty()
                val fromWatch = vo2 + ours + r.garminMetrics.mapNotNull { (k, v) -> GARMIN_LABELS[k]?.let { it to garminValue(k, v.toString().trim('"')) } }
                if (fromWatch.isNotEmpty()) item {
                    Group(title = "VO₂ max and the watch's numbers", tint = Tint.TEAL) {
                        fromWatch.forEach { (label, v) -> row(label, trailing = { Text(v, style = MaterialTheme.typography.titleMedium) }) }
                        // The runner can leave a run out of our VO2 max (heart rate that looked wrong, say): its own value stays here
                        r.vo2Ours?.takeIf { it.value != null || it.heldOut }?.let { o ->
                            row("Leave out of Runner Sidekick's VO₂ max", supporting = if (o.heldOut) "Held out by you: not in the estimate"
                                else "For a run whose heart rate looked wrong",
                                trailing = { androidx.compose.material3.Switch(checked = o.heldOut, onCheckedChange = { vm.holdOutVo2(it) }) })
                        }
                        r.vo2Ours?.why?.let { why -> custom {
                            Text("No Runner Sidekick VO₂ max from this run: $why. It needs a steady, flat run of 20+ minutes after the warm-up " +
                                "with good heart rate.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        } }
                    }
                }
            }
        }
    }
    evidence?.let { EvidenceSheet(it) { evidence = null } }
}

/** The sensor's connection log in words: each dropout with when it came back, or that it stayed connected. */
private fun sensorLog(s: com.bennybar.runnersidekick.data.remote.HrSensor): String {
    if (!s.logged) return ""
    val drops = s.events.filter { it.event.contains("disconnect", ignoreCase = true) }
    if (drops.isEmpty()) return " · connected the whole run"
    return " · " + drops.joinToString("; ") { d ->
        val back = s.events.firstOrNull { it.atS > d.atS && it.event.contains("connected", ignoreCase = true) && !it.event.contains("disconnect", ignoreCase = true) }
        "dropped out at ${Format.duration(d.atS)}" + (back?.let { ", back at ${Format.duration(it.atS)}" } ?: " and didn't come back")
    }
}

/** The page's big title: the run's day ("Sunday run"), then the date, start time and the run's name. */
@Composable
private fun RunTitle(r: PostRunReport) {
    val a = r.activity
    val day = LocalDate.parse(a.localDate)
    Column(Modifier.padding(horizontal = 12.dp).padding(bottom = 6.dp).semantics(mergeDescendants = true) {}, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(day.dayOfWeek.getDisplayName(java.time.format.TextStyle.FULL, androidx.compose.ui.platform.LocalConfiguration.current.locales[0]) + " run",
            style = MaterialTheme.typography.headlineLarge, modifier = Modifier.semantics { heading() })
        Text(listOfNotNull(day.format(java.time.format.DateTimeFormatter.ofPattern("d MMMM")),
            Format.activityTime(a.startUtc, a.utcOffsetS).substringAfter(" · "), displayName(a.name),
            r.recordedWith?.let { "recorded with $it" }).joinToString(" · "),
            style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        // Where the heart rate came from, when it wasn't the watch's own sensor
        r.hrSensor?.let { s ->
            Text("Heart rate from ${s.name ?: "an external sensor"}" + (if (s.name != null) " (external sensor)" else "") + sensorLog(s),
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** The run's header, in the orange hero tile: distance with the moving pace in a pill beside it, six numbers, then
 *  what the numbers leave out (stops, the watch's VO2 max, doubtful heart rate). */
@Composable
private fun RunHero(r: PostRunReport, units: Units) {
    val a = r.activity
    val sub = MaterialTheme.colorScheme.onSurfaceVariant
    val (d, du) = distanceParts(a.distanceM, units)
    val pace = Format.pace(r.paceMovingSPerKm, units)
    Tile(tint = Tint.ORANGE, spacing = 14.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            BigValue(d, du, Modifier.weight(1f))
            Surface(shape = RoundedCornerShape(14.dp), color = MaterialTheme.colorScheme.surface.copy(alpha = 0.75f)) {
                Text("$pace moving", style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
            }
        }
        val te = r.garminMetrics["aerobicTrainingEffect"]?.toString()?.toDoubleOrNull()
        // The watch's VO2 max on the day of the run (as the watch shows it); the run's own estimate as a fallback
        val vo2 = r.garminVo2maxDay?.value?.let { "%.1f".format(it) } ?: r.garminMetrics["vO2MaxValue"]?.toString()?.trim('"')
        val ours = r.vo2Ours?.value
        val tiles = listOf(
            "Avg heart rate" to (a.avgHr?.roundToInt()?.toString() ?: "—"),
            // Garmin's Training Effect; a watch without it (Samsung) shows the app's own training load for the run
            te?.let { "Aerobic TE" to "%.1f".format(it) } ?: ("Training load" to (r.load?.toString() ?: "—")),
            // Garmin's training readiness on the morning of the run; without it, the run's highest heart rate
            r.garminReadinessDay?.value?.roundToInt()?.let { "Garmin readiness" to it.toString() }
                ?: ("Max heart rate" to (a.maxHr?.roundToInt()?.toString() ?: "—")),
            "Moving time" to Format.duration(a.movingS),
            "Climb" to "+${Format.elevation(a.elevationGainM, units)}",
            // Ours from this run, big; the watch's in the footnote
            if (ours != null) "VO₂ Sidekick" to "%.0f".format(ours) else "VO₂ (${r.watch})" to (vo2 ?: "—"),
        )
        tiles.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { (l, v) ->
                    Column(Modifier.weight(1f).semantics(mergeDescendants = true) {}, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(l, style = MaterialTheme.typography.labelMedium, color = sub, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(v, style = MaterialTheme.typography.titleLarge, maxLines = 1)
                    }
                }
            }
        }
        Text(listOfNotNull(
            // Elapsed only when stops made it differ
            if ((a.elapsedS ?: 0.0) - (a.movingS ?: 0.0) >= 30) "Elapsed ${Format.duration(a.elapsedS)} with stops" else null,
            if (ours != null) vo2?.let { "${r.watch}'s VO₂ max $it" } else if (vo2 != null) "Sidekick VO₂ max: n/a" else null,
        ).joinToString(" · ").let { if (it.isEmpty()) it else "$it. " } +
            "Pace uses moving time (stops excluded). Elapsed includes stops." + (r.hrQuality?.takeIf { it.grade != "good" }?.let { q ->
            " The heart-rate recording looked ${q.grade} in ${q.stretches.size} ${if (q.stretches.size == 1) "stretch" else "stretches"} (" +
                q.stretches.take(3).joinToString { "${Format.duration(it.startS)}–${Format.duration(it.endS)}" } +
                "), so read heart-rate numbers loosely."
        } ?: ""), style = MaterialTheme.typography.labelMedium, color = sub)
    }
}

/** Aerobic decoupling for every run, pace:HR and power:HR (first half against second), in a blue tile. */
@Composable
private fun DecouplingCard(dc: com.bennybar.runnersidekick.data.remote.Decoupling) {
    val cs = MaterialTheme.colorScheme
    Tile(tint = Tint.BLUE, spacing = 12.dp) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            DecouplingTitle(cs.onSurface)
            if (dc.decouplingPct == null) {
                val why = dc.reasons.firstOrNull().orEmpty()
                val short = Regex("""eligible segment (\d+) min < (\d+) min""").find(why)
                Text("Not measured on this run: " + when {
                    short != null -> "it needs ${short.groupValues[2]} minutes of running after the warm-up, and this run had ${short.groupValues[1]}. " +
                        "On shorter runs a few beats of noise would swing it too much."
                    why.contains("heart", ignoreCase = true) -> "too little heart rate was recorded."
                    else -> why.ifBlank { "not enough data." }
                }, style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
                return@Column
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                // power:HR only when the watch records running power (Samsung's doesn't)
                listOfNotNull(dc.decouplingPct to "Pace : heart rate", dc.powerDecouplingPct?.let { it to "Power : heart rate" }).forEach { (v, l) ->
                    Column(Modifier.weight(1f).semantics(mergeDescendants = true) {}, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(l, style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant, maxLines = 1)
                        Text(v?.let { "%.1f%%".format(it) } ?: if (l.startsWith("Power")) "no power" else "—", style = MaterialTheme.typography.headlineMedium)
                    }
                }
            }
            Text(if (!dc.eligible) "Indicative here: " + (if (dc.reasons.any { it.startsWith("run is not steady") }) "the pace wasn't steady"
                else dc.reasons.firstOrNull() ?: "not a steady run") + "."
                else "Under 5% means heart rate kept pace with the effort. Lower is better" +
                    (if (dc.powerDecouplingPct != null) "; on hills, power:HR is the better read." else ".") +
                    (dc.hrCaveat?.let { " $it" } ?: ""),
                style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
        }
    }
}

/** "Aerobic decoupling" with an info button whose tooltip says how to read it. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DecouplingTitle(color: Color) {
    val tip = androidx.compose.material3.rememberTooltipState(isPersistent = true)
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        Text("Aerobic decoupling", style = MaterialTheme.typography.titleSmall, color = color, modifier = Modifier.weight(1f))
        androidx.compose.material3.TooltipBox(
            positionProvider = androidx.compose.material3.TooltipDefaults.rememberTooltipPositionProvider(
                androidx.compose.material3.TooltipAnchorPosition.Above),
            tooltip = {
                PlainTooltip {
                    Text("How much heart rate rose against pace (or power) from the first half to the second, after a "
                        + "10-minute warm-up. Lower is better; under 5% means the effort held steady. On hilly runs, power:HR is "
                        + "the better read.")
                }
            },
            state = tip,
        ) {
            androidx.compose.material3.IconButton(onClick = { scope.launch { tip.show() } }) {
                Icon(Icons.Outlined.Info, contentDescription = "About aerobic decoupling", tint = color.copy(alpha = 0.8f), modifier = Modifier.size(18.dp))
            }
        }
    }
}

@Composable
private fun Splits(r: PostRunReport, units: Units) {
    val cs = MaterialTheme.colorScheme
    val paceColor = LocalDataColors.current.pace
    Group(title = "Splits") {
        // Capsules: taller = faster; the hilliest km in full orange, with its flat-equivalent pace
        val paced = r.splits.filter { it.paceSPerKm != null }
        if (paced.size >= 2) custom {
            val fastest = paced.minOf { it.paceSPerKm!! }
            val slowest = paced.maxOf { it.paceSPerKm!! }
            val hilly = r.splits.filter { it.complete }.maxByOrNull { it.elevationGainM ?: 0.0 }?.takeIf { (it.elevationGainM ?: 0.0) >= 10 && it.gapPaceSPerKm != null }
            Row(Modifier.fillMaxWidth().height(110.dp).semantics(mergeDescendants = true) { contentDescription = "Pace per kilometre, taller is faster" },
                horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.Bottom) {
                r.splits.forEach { s ->
                    val f = s.paceSPerKm?.let { if (slowest > fastest) 0.35f + 0.65f * ((slowest - it) / (slowest - fastest)).toFloat() else 1f } ?: 0.1f
                    Box(Modifier.weight(1f).fillMaxHeight(f).background(
                        if (s.idx == hilly?.idx) paceColor.copy(alpha = if (s.complete) 1f else 0.45f)
                        else Tint.ORANGE.hue.copy(alpha = if (s.complete) 0.45f else 0.2f), RoundedCornerShape(6.dp)))
                }
            }
            Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                r.splits.forEach { s -> Text("${s.idx + 1}", Modifier.weight(1f), style = MaterialTheme.typography.labelSmall,
                    color = cs.onSurfaceVariant, textAlign = androidx.compose.ui.text.style.TextAlign.Center) }
            }
            hilly?.let { h ->
                Surface(shape = RoundedCornerShape(18.dp), color = Tint.ORANGE.hue.copy(alpha = 0.16f), modifier = Modifier.padding(top = 10.dp)) {
                    Text("Km ${h.idx + 1} climbed ${Format.elevation(h.elevationGainM, units)}: ${Format.pace(h.paceSPerKm, units)} actual, " +
                        "${Format.pace(h.gapPaceSPerKm, units)} on the flat.", style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp))
                }
            }
        }
        custom {
            Row(Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                listOf("#", "Pace", "Flat", "HR", "Zone", "Climb").forEachIndexed { i, h ->
                    Text(h, Modifier.weight(if (i == 0) 0.5f else 1f), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1)
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
            Text("Flat = flat-equivalent: the pace this effort would give on flat ground.",
                style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
            if (r.splits.any { !it.complete }) Text("* Partial km", style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
            Spacer(Modifier.height(2.dp))
        }
    }
}


/** AI input on this run, written only when asked. Every number comes from the analysis; every point cites it. */
@OptIn(androidx.compose.material3.ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun RunAiCard(v: com.bennybar.runnersidekick.data.remote.RunAi?, onAsk: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val shown = v?.takeIf { it.status == "ok" } ?: v?.previous?.takeIf { it.status == "ok" }
    Tile {
        Column(Modifier.animateContentSize(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("AI input on this run", style = MaterialTheme.typography.titleSmall)
                    Text("Coaching from this run's analysis, its week and your plan", style = MaterialTheme.typography.labelMedium,
                        color = cs.onSurfaceVariant)
                }
                if (v?.status == "pending") androidx.compose.material3.LoadingIndicator(Modifier.size(28.dp))
            }
            when {
                shown != null -> {
                    // Compact: the one line and the next-time tip; the rest on request
                    var more by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf(false) }
                    shown.tldr?.let { com.bennybar.runnersidekick.ui.insights.Tldr(it) }
                    // Older input has no one-liner: its summary is shown as plain text instead
                    if (more || shown.tldr == null) shown.summary?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                    if (more && shown.wentWell.isNotEmpty()) {
                        Text("Went well", style = MaterialTheme.typography.titleSmall)
                        shown.wentWell.forEach { p -> Bullet(p.text) }
                    }
                    if (more && shown.toWorkOn.isNotEmpty()) {
                        Text("To work on", style = MaterialTheme.typography.titleSmall)
                        shown.toWorkOn.forEach { p -> Bullet(p.text) }
                    }
                    shown.nextTime?.let { n ->
                        Surface(shape = MaterialTheme.shapes.medium, color = cs.surfaceContainerHighest) {
                            Column(Modifier.padding(14.dp)) {
                                Text("Next time · " + when (n.direction) { "easier" -> "easier"; "harder" -> "harder"; else -> "similar effort" },
                                    style = MaterialTheme.typography.labelLarge)
                                Text(n.text, style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                    }
                    if (!more && (shown.wentWell.isNotEmpty() || shown.toWorkOn.isNotEmpty()))
                        androidx.compose.material3.TextButton(onClick = { more = true }) { Text("What went well, what to work on") }
                    Text((if (shown.trigger == "auto") "Written automatically for this new run · " else "") +
                        "AI (${shown.model ?: "OpenAI"})" +
                        (if (shown.keySource == "user") " with your key" else "") +
                        " · numbers come from the app · guidance, not medical advice", style = MaterialTheme.typography.labelSmall,
                        color = cs.onSurfaceVariant)
                }
                v == null || v.status == "none" -> androidx.compose.material3.FilledTonalButton(onClick = onAsk) {
                    Icon(Icons.Outlined.AutoAwesome, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp)); Text("Get AI input")
                }
                v.status == "pending" -> Text("Reading this run…", style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
                v.status == "disabled" -> Text("Turn on the AI coach in Settings to get input on your runs.",
                    style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
                v.status == "not_configured" -> Text("AI input isn't set up on the server yet (or add your own OpenAI key in Settings).",
                    style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
                else -> {
                    Text(when (v.status) {
                        "budget_exceeded" -> "Today's AI limit is reached. Try again tomorrow."
                        "failed" -> v.detail ?: "The AI call failed. Try again in a moment."  // the server says why (e.g. a rejected key)
                        else -> "The AI input didn't pass the app's checks this time."
                    }, style = MaterialTheme.typography.bodyMedium,
                        color = cs.onSurfaceVariant)
                    if (v.status != "budget_exceeded") androidx.compose.material3.TextButton(onClick = onAsk) { Text("Try again") }
                }
            }
        }
    }
}

@Composable
private fun Bullet(text: String) {
    Row {
        Text("•", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.width(10.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium)
    }
}

/** How the run went against what it was meant to be: a verdict for training runs, the age grade for a race. */
@Composable
private fun VerdictCard(v: com.bennybar.runnersidekick.data.remote.RunVerdict) {
    val cs = MaterialTheme.colorScheme
    // On target in green; off it (harder, easier, cut short) in pink, as the mockup; the label says which in words
    val tint = when (v.verdict) {
        "on_target" -> Tint.GREEN
        "harder", "easier", "shortened" -> Tint.PINK
        else -> Tint.NEUTRAL
    }
    Tile(tint = tint, spacing = 6.dp) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            v.ageGrade?.let { ag ->
                Text("Age grade %.1f%%".format(ag.pct), style = MaterialTheme.typography.headlineMedium)
                Text(ag.gradeClass.replaceFirstChar(Char::uppercase), style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
            } ?: Text(v.label, style = MaterialTheme.typography.titleMedium)
            Text(v.say, style = MaterialTheme.typography.bodyMedium)
            Text(listOfNotNull(
                v.judgedAs?.let { k -> "Judged as ${k.replace('_', ' ')}" + (v.basis?.let { " from $it" } ?: "") },
                if (v.verdict == "not_enough_data" && v.judgedAs == null) "Set the run type below" else null,
                v.hrNote, v.note).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
        }
    }
}

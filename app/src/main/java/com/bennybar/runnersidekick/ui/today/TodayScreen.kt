package com.bennybar.runnersidekick.ui.today

import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.automirrored.outlined.TrendingDown
import androidx.compose.material.icons.automirrored.outlined.TrendingFlat
import androidx.compose.material.icons.automirrored.outlined.TrendingUp
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.EventNote
import androidx.compose.material.icons.outlined.HourglassEmpty
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.LinkOff
import androidx.compose.material.icons.outlined.Psychology
import androidx.compose.material.icons.outlined.SelfImprovement
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material.icons.outlined.Watch
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.LoadingIndicator
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.graphics.shapes.RoundedPolygon
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.bennybar.runnersidekick.data.local.Units
import com.bennybar.runnersidekick.data.remote.Finding
import com.bennybar.runnersidekick.data.remote.MorningReport
import com.bennybar.runnersidekick.data.remote.Status
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.TodayVm
import com.bennybar.runnersidekick.ui.components.DemoBadge
import com.bennybar.runnersidekick.ui.components.EmptyState
import com.bennybar.runnersidekick.ui.components.EvidenceSheet
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.animatedItem
import com.bennybar.runnersidekick.ui.components.MetricTile
import com.bennybar.runnersidekick.ui.components.OfflineBanner
import com.bennybar.runnersidekick.ui.components.ShapeBadge
import com.bennybar.runnersidekick.ui.components.Sparkline
import com.bennybar.runnersidekick.ui.factory
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import kotlin.math.roundToInt

private val TILE_METRICS = listOf("sleep_duration", "resting_hr", "hrv_overnight_avg", "running_moving_time_7d")

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun TodayScreen(onOpenRun: (String) -> Unit, onOpenSettings: () -> Unit, onOpenInsights: () -> Unit, vm: TodayVm = viewModel(factory = factory(::TodayVm))) {
    val status by vm.status.collectAsStateWithLifecycle()
    val today by vm.today.collectAsStateWithLifecycle()
    val fitness by vm.fitness.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val offline by vm.offline.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val units = settings?.units ?: Units.METRIC
    val snackbar = remember { SnackbarHostState() }
    var evidence by remember { mutableStateOf<Finding?>(null) }
    var sheet by rememberSaveable { mutableStateOf<String?>(null) } // checkin | why | briefing
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    val listState = rememberLazyListState()
    val coach by vm.coach.collectAsStateWithLifecycle()

    LaunchedEffect(error) { error?.let { snackbar.showSnackbar(it); vm.clearError() } }
    val report = today?.value

    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        topBar = {
            LargeTopAppBar(
                title = { Text(report?.localDate?.let { Format.longDate(it) } ?: "Today", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                actions = {
                    if (status?.value?.synthetic == true) DemoBadge()
                    androidx.compose.material3.TextButton(onClick = vm::syncNow, enabled = !busy) {
                        Icon(Icons.Outlined.Sync, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp))
                        Text(if (busy) "Syncing…" else "Sync Garmin")
                    }
                },
                scrollBehavior = scroll,
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        PullToRefreshBox(isRefreshing = busy && report != null, onRefresh = vm::refresh, modifier = Modifier.padding(padding).fillMaxSize()) {
            if (report == null) {
                NoReport(busy, settings?.hasToken == false, onOpenSettings)
                return@PullToRefreshBox
            }
            LazyColumn(state = listState, contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 112.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                animatedItem(key = "fresh") { Freshness(status?.value, today?.fetchedAt, report, offline) }
                status?.value?.connection?.let { c -> if (c.state != "connected") animatedItem(key = "connection") { ConnectionNotice(c.state, c.detail, onOpenSettings) } }
                // A simple overview: scores, the day's call, the AI's one line, what stands out, readings, the latest run
                report.scores?.takeIf { it.status == "ok" }?.let { sc -> animatedItem(key = "scores") { ScoresCard(sc) { sheet = "scores" } } }
                animatedItem(key = "hero") { Hero(report, onWhy = { sheet = "why" }) }
                val coachShown = coach?.value?.let { c -> if (c.status == "ok") c else c.previous?.takeIf { it.status == "ok" } }
                (coachShown?.tldr ?: coachShown?.summary)?.let { s ->
                    val c = coach!!.value
                    // Older advice is labelled as such, so it never reads as current next to a changed briefing
                    val note = if (coachShown !== c) (if (c.status == "pending") "Updating for today's changes…" else "From an earlier analysis")
                        else "Updated ${Format.ago(runCatching { Instant.parse(coachShown.generatedAt) }.getOrNull())}"
                    animatedItem(key = "coach") { CoachTeaser(s, note, onOpenInsights) }
                }
                if (report.highlights.isNotEmpty()) animatedItem(key = "highlights") {
                    StandsOut(report.highlights.take(3)) { t ->
                        when (t.type) {
                            "run" -> t.id?.let(onOpenRun)
                            "compare" -> { com.bennybar.runnersidekick.ui.insights.InsightsTab.requested.value = 1; onOpenInsights() }
                            else -> onOpenInsights()
                        }
                    }
                }
                animatedItem(key = "readings") { Readings(report, fitness?.value, onOpenFitness = { sheet = "vo2" }) { evidence = it } }
                report.recentRun?.let { run ->
                    animatedItem(key = "lastrun") {
                        Group(title = "Latest run") {
                            row(Format.shortDate(run.localDate) + " · " + Format.distance(run.distanceM, units),
                                supporting = "${Format.duration(run.movingS)} moving · " +
                                    Format.pace(if (run.distanceM != null && run.movingS != null && run.distanceM > 0) run.movingS / (run.distanceM / 1000) else null, units) +
                                    (run.avgHr?.let { " · ${it.roundToInt()} bpm" } ?: ""),
                                icon = Icons.AutoMirrored.Outlined.DirectionsRun, iconShape = MaterialShapes.Cookie9Sided, onClick = { onOpenRun(run.sourceId) },
                                accent = "running")
                        }
                    }
                }
            }
        }
    }
    when (sheet) {
        "scores" -> report?.scores?.let { ScoresSheet(it, onDismiss = { sheet = null }) }
        "vo2" -> report?.let { r ->
            SheetColumn(onDismiss = { sheet = null }) {
                Text("VO₂ max", style = MaterialTheme.typography.headlineSmall)
                r.readingNotes["vo2max"]?.let { com.bennybar.runnersidekick.ui.components.NoteBlock(it) }
                TextButton(onClick = { sheet = null; com.bennybar.runnersidekick.ui.insights.InsightsTab.requested.value = 1; onOpenInsights() }) {
                    Text("Compare with your age group")
                }
            }
        }
        "why" -> report?.let { WhySheet(it, onDismiss = { sheet = null }, onBriefing = { sheet = "briefing" }) { f -> sheet = null; evidence = f } }
        "briefing" -> report?.let { BriefingSheet(it, onDismiss = { sheet = null }) { f -> sheet = null; evidence = f } }
    }
    evidence?.let { f -> EvidenceSheet(f, today?.value?.readingNotes?.get(f.metric)) { evidence = null } }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun NoReport(busy: Boolean, notConnected: Boolean, onOpenSettings: () -> Unit) {
    LazyColumn(Modifier.fillMaxSize()) {
        item {
            when {
                notConnected -> EmptyState(Icons.Outlined.LinkOff, "Connect your backend", "Enter the backend address and device token to load your data.") {
                    Button(onClick = onOpenSettings) { Icon(Icons.Outlined.Settings, null); Spacer(Modifier.width(8.dp)); Text("Open settings") }
                }
                busy -> Column(Modifier.fillMaxWidth().padding(top = 96.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    LoadingIndicator(Modifier.size(72.dp))
                    Spacer(Modifier.height(16.dp))
                    Text("Preparing your briefing…", style = MaterialTheme.typography.titleMedium)
                }
                else -> EmptyState(Icons.Outlined.HourglassEmpty, "No briefing yet", "Pull down to refresh, or check the connection in Settings.")
            }
        }
    }
}

@Composable
private fun Pill(icon: ImageVector, text: String, attention: Boolean = false) {
    val bg = if (attention) MaterialTheme.colorScheme.tertiaryContainer else MaterialTheme.colorScheme.surfaceContainerHigh
    val fg = if (attention) MaterialTheme.colorScheme.onTertiaryContainer else MaterialTheme.colorScheme.onSurfaceVariant
    Surface(shape = MaterialTheme.shapes.small, color = bg) {
        Row(Modifier.padding(horizontal = 10.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, Modifier.size(16.dp), tint = fg)
            Spacer(Modifier.width(6.dp))
            Text(text, style = MaterialTheme.typography.labelLarge, color = fg)
        }
    }
}

@Composable
private fun Freshness(status: Status?, fetchedAt: Instant?, report: MorningReport, offline: Boolean) {
    val lastSource = status?.connection?.lastSuccessAt?.let { runCatching { Instant.parse(it) }.getOrNull() }
    val stale = lastSource == null || Duration.between(lastSource, Instant.now()).toHours() >= 12
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill(if (stale) Icons.Outlined.WarningAmber else Icons.Outlined.CheckCircle,
                (if (status?.synthetic == true) "Demo source " else "Garmin ") + Format.ago(lastSource), attention = stale)
            status?.latestObservationDate?.let { Pill(Icons.Outlined.Watch, "Data through ${Format.shortDate(it)}") }
            if (report.provisional) Pill(Icons.Outlined.HourglassEmpty, "Provisional · sleep not in yet", attention = true)
        }
        if (offline) OfflineBanner("Offline: showing the briefing saved ${Format.ago(fetchedAt)}.")
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun ConnectionNotice(state: String, detail: String?, onOpenSettings: () -> Unit) {
    val (title, body) = when (state) {
        "reauth_required" -> "Garmin needs you to sign in again" to "Run `python -m sidekick garmin-login` on the backend computer. Syncing is paused until then."
        "rate_limited" -> "Garmin asked us to slow down" to "Syncing will retry automatically later."
        "not_configured" -> "Garmin isn't connected" to "Run `python -m sidekick garmin-login` on the backend computer."
        else -> "Last sync failed" to (detail ?: "Will retry later.")
    }
    Group { row(title, supporting = body, icon = Icons.Outlined.LinkOff, iconShape = MaterialShapes.Burst, onClick = onOpenSettings) }
}

private data class StateStyle(val label: String, val icon: ImageVector, val shape: RoundedPolygon)

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
private fun styleFor(state: String) = when (state) {
    "usual_plan" -> StateStyle("Usual plan", Icons.AutoMirrored.Outlined.DirectionsRun, MaterialShapes.Cookie9Sided)
    "consider_easier" -> StateStyle("Consider easier", Icons.Outlined.SelfImprovement, MaterialShapes.SoftBurst)
    else -> StateStyle("Not enough data", Icons.Outlined.Info, MaterialShapes.Clover8Leaf)
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun Hero(r: MorningReport, onWhy: () -> Unit) {
    val rec = r.recommendation
    val easier = rec.state == "consider_easier"
    val cs = MaterialTheme.colorScheme
    val container = if (easier) cs.tertiaryContainer else cs.primaryContainer
    val on = if (easier) cs.onTertiaryContainer else cs.onPrimaryContainer
    val accent = if (easier) cs.tertiary else cs.primary
    val onAccent = if (easier) cs.onTertiary else cs.onPrimary
    // "Usual plan" while intensity is held back would contradict the advice underneath
    val style = if (rec.state == "usual_plan" && rec.suppressIntensity) StateStyle("Go by feel", Icons.Outlined.SelfImprovement, MaterialShapes.Cookie9Sided)
    else styleFor(rec.state)
    Surface(shape = MaterialTheme.shapes.extraLarge, color = container, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ShapeBadge(style.icon, style.shape, Modifier.size(52.dp), container = accent, content = onAccent)
                Spacer(Modifier.width(14.dp))
                Text(style.label, style = MaterialTheme.typography.titleMedium, color = on)
            }
            Text(r.headline, style = MaterialTheme.typography.headlineMedium, color = on)
            Text(rec.suggestion, style = MaterialTheme.typography.bodyLarge, color = on)
            // When the call was made and what moved since yesterday, so a changed call never looks like an old one
            val made = runCatching { Instant.parse(r.generatedAt) }.getOrNull()
            Text(listOfNotNull(made?.let { "Worked out ${Format.ago(it)}" }, r.dataCutoff?.let { c ->
                runCatching { Instant.parse(c) }.getOrNull()?.let { "Garmin data from ${Format.ago(it)}" } }).joinToString(" · "),
                style = MaterialTheme.typography.labelMedium, color = on.copy(alpha = 0.75f))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 4.dp)) {
                OutlinedButton(onClick = onWhy) { Text(if (r.changes.isNotEmpty()) "Why · what changed" else "Why this suggestion?") }
            }
        }
    }
}

private val TONE_ACCENT = mapOf("attention" to "recovery", "positive" to "fitness", "info" to "sleep")

/** What stands out today: Garmin's verdict, load, new bests, VO2 max movement, focus, comparisons. Attention first. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun StandsOut(items: List<com.bennybar.runnersidekick.data.remote.Highlight>,
                      onOpen: (com.bennybar.runnersidekick.data.remote.HighlightTarget) -> Unit) {
    Group(title = "Stands out today") {
        items.forEach { h ->
            val icon = when (h.tone) {
                "attention" -> Icons.Outlined.WarningAmber
                "positive" -> Icons.Outlined.EmojiEvents
                else -> Icons.Outlined.Info
            }
            val shape = when (h.tone) {
                "attention" -> MaterialShapes.SoftBurst
                "positive" -> MaterialShapes.Sunny
                else -> MaterialShapes.Cookie4Sided
            }
            row(h.title, supporting = h.text.ifBlank { null }, icon = icon, iconShape = shape, accent = TONE_ACCENT[h.tone],
                onClick = h.target?.takeIf { it.type in setOf("run", "compare", "insights", "race") }?.let { t -> { onOpen(t) } })
        }
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun CoachTeaser(summary: String, note: String, onOpen: () -> Unit) {
    Group {
        row("From your AI coach", overline = note, supporting = summary, icon = Icons.Outlined.Psychology, iconShape = MaterialShapes.Flower, onClick = onOpen)
    }
}

private fun tileValue(f: Finding): Pair<String, String?> {
    val v = f.observed?.value ?: f.last?.value ?: return "—" to null
    return when (f.metric) {
        "sleep_duration", "running_moving_time_7d" -> { val m = (v / 60).roundToInt(); "${m / 60}h ${"%02d".format(m % 60)}m" to null }
        "resting_hr" -> "${v.roundToInt()}" to "bpm"
        else -> "${v.roundToInt()}" to "ms"
    }
}

private fun tileStatus(f: Finding): String = when {
    f.metric == "running_moving_time_7d" -> if (f.status == "outside") "Well above recent weeks" else "Similar to recent weeks"
    f.status == "learning" -> "Learning · ${f.sampleSize ?: 0}/14 days"
    f.status == "missing" -> f.last?.let { "From ${Format.shortDate(it.date)} · today's not in yet" } ?: "Not recorded"
    f.status == "sustained" -> "Unusual 3 days running"
    f.status == "outside" -> if ((f.delta?.abs ?: 0.0) > 0) "Above your usual" else "Below your usual"
    f.comparison?.median != null -> "Usual · ${Format.signedDelta(f.metric, f.delta?.abs)}"
    else -> "Usual"
}

private fun dailySeries(f: Finding, endDate: String): List<Double?> {
    val byDate = f.sparkline.orEmpty().associate { it.date to it.value }
    val end = LocalDate.parse(endDate)
    return (13 downTo 0).map { byDate[end.minusDays(it.toLong()).toString()] }
}

@Composable
private fun Readings(r: MorningReport, fitness: com.bennybar.runnersidekick.data.remote.Fitness?, onOpenFitness: () -> Unit,
                     onTap: (Finding) -> Unit) {
    val vo2 = fitness?.garmin?.vo2max
    // null marks the VO2 max tile's slot, right after the overnight readings
    val tiles: List<Finding?> = TILE_METRICS.mapNotNull { m -> r.findings.firstOrNull { it.metric == m } } + (if (vo2 != null) listOf(null) else emptyList())
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Readings", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(start = 4.dp, top = 8.dp))
        tiles.chunked(2).forEach { pair ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                pair.forEach { f ->
                    if (f == null) {
                        // Garmin's VO2 max (one decimal, as Garmin shows it), with the change over about four weeks
                        val series = fitness!!.vo2maxSeries
                        val old = series.lastOrNull { java.time.LocalDate.parse(it.date) <= java.time.LocalDate.parse(r.localDate).minusDays(28) }
                        val ch = old?.let { vo2!!.value - it.value }
                        MetricTile(label = "VO₂ max", value = "%.1f".format(vo2!!.value), unit = null,
                            status = ch?.let { if (kotlin.math.abs(it) < 0.05) "Same as 4 weeks ago" else "%+.1f in 4 weeks".format(it) } ?: "Garmin",
                            statusIcon = ch?.let { if (it > 0.05) Icons.AutoMirrored.Outlined.TrendingUp else if (it < -0.05) Icons.AutoMirrored.Outlined.TrendingDown
                                else Icons.AutoMirrored.Outlined.TrendingFlat }, flagged = false,
                            modifier = Modifier.weight(1f).semantics(mergeDescendants = true) { contentDescription = "VO2 max %.1f, Garmin".format(vo2.value) },
                            onClick = onOpenFitness,
                            chart = if (series.size >= 2) {
                                { Sparkline(series.takeLast(14).map { it.value }, Modifier.fillMaxWidth().height(32.dp),
                                    color = MaterialTheme.colorScheme.primary, description = "VO2 max, recent Garmin readings") }
                            } else null)
                        return@forEach
                    }
                    val (value, unit) = tileValue(f)
                    val flagged = f.status == "outside" || f.status == "sustained"
                    val d = f.delta?.abs
                    val icon = when {
                        d == null -> null
                        d > 0 -> Icons.AutoMirrored.Outlined.TrendingUp
                        d < 0 -> Icons.AutoMirrored.Outlined.TrendingDown
                        else -> Icons.AutoMirrored.Outlined.TrendingFlat
                    }
                    val band = f.comparison?.let { c -> if (c.q1 != null && c.q3 != null) c.q1 to c.q3 else null }
                    val lineColor = if (flagged) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.primary
                    MetricTile(
                        label = if (f.metric == "running_moving_time_7d") "Running, 7 days" else f.title,
                        value = value, unit = unit, status = tileStatus(f), statusIcon = icon, flagged = flagged,
                        modifier = Modifier.weight(1f).semantics(mergeDescendants = true) { contentDescription = "${f.title}. ${f.statement}" },
                        onClick = { onTap(f) },
                        chart = if (!f.sparkline.isNullOrEmpty()) {
                            { Sparkline(dailySeries(f, r.localDate), Modifier.fillMaxWidth().height(32.dp), band = band, color = lineColor,
                                description = "${f.title}, last 14 days") }
                        } else null,
                    )
                }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SheetColumn(onDismiss: () -> Unit, content: @Composable () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(14.dp)) { content() }
    }
}

@Composable
private fun WhySheet(r: MorningReport, onDismiss: () -> Unit, onBriefing: () -> Unit, onFinding: (Finding) -> Unit) {
    val rec = r.recommendation
    SheetColumn(onDismiss) {
        Text("Why this suggestion", style = MaterialTheme.typography.headlineSmall)
        if (r.changes.isNotEmpty()) Group(title = "Since yesterday") { r.changes.forEach { c -> row(c) } }
        Text(rec.reason, style = MaterialTheme.typography.bodyLarge)
        rec.uncertainty?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        val evidence = rec.evidenceIds.mapNotNull { id -> r.findings.firstOrNull { it.id == id } }
        if (evidence.isNotEmpty()) Group(title = "Based on") {
            evidence.forEach { f -> row(f.title, supporting = f.statement, onClick = { onFinding(f) }) }
        }
        if ("checkin" in rec.evidenceIds) Text("Also based on your check-in.", style = MaterialTheme.typography.bodyMedium)
        if (rec.suppressIntensity) Text("Hard sessions aren't suggested today: key information is missing, or a signal needs attention.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text("Rule ${rec.ruleId} · ${rec.rulesVersion}. Guidance only, not medical advice.", style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        TextButton(onClick = onBriefing) { Text("Full briefing: all findings and Garmin scores") }
    }
}

@Composable
private fun BriefingSheet(r: MorningReport, onDismiss: () -> Unit, onFinding: (Finding) -> Unit) {
    SheetColumn(onDismiss) {
        Text("Full briefing", style = MaterialTheme.typography.headlineSmall)
        Group(title = "Findings") { r.findings.forEach { f -> row(f.title, supporting = f.statement, onClick = { onFinding(f) }) } }
        if (r.garminContext.isNotEmpty()) {
            Group(title = "From Garmin") {
                r.garminContext.forEach { g -> row(garminName(g.metric), supporting = "${g.value.roundToInt()}" + (g.label?.let { " · $it" } ?: "")) }
            }
            Text("Garmin's own scores, shown for context. They don't feed the suggestion, which avoids counting sleep and HRV twice.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        HorizontalDivider()
        Text("Revision ${r.revision} · generated ${Format.ago(runCatching { Instant.parse(r.generatedAt) }.getOrNull())} · " +
            "rules ${r.recommendation.rulesVersion} (${r.recommendation.ruleId})", style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

private fun garminName(metric: String) = when (metric) {
    "garmin_training_readiness" -> "Training readiness"
    "garmin_sleep_score" -> "Sleep score"
    "body_battery_high" -> "Body Battery high"
    "body_battery_low" -> "Body Battery low"
    "avg_stress" -> "Average stress"
    "garmin_vo2max_running" -> "VO₂ max"
    else -> metric
}


private val SESSION_NAMES = mapOf("easy" to "Easy run", "long" to "Long run", "tempo" to "Tempo", "intervals" to "Intervals",
    "race_pace" to "Race pace", "strides" to "Easy + strides", "race" to "Race day", "rest" to "Rest")

/** The week toward the race: each day's session, ticked off as runs come in. Recomputed daily from what was run. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun RaceWeekCard(race: com.bennybar.runnersidekick.data.remote.RaceStatus, w: com.bennybar.runnersidekick.data.remote.RaceWeek,
                         onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    Group(title = "This week toward ${race.headline.substringBefore(" in ").substringBefore(" today")} · ${race.phase.replace('_', ' ')}") {
        custom {
            Text(w.targetMinutes?.let { "About $it min this week · ${w.doneMinutes} min done" } ?: "${w.doneMinutes} min done this week",
                style = MaterialTheme.typography.titleMedium)
            w.targetMinutes?.let { t ->
                androidx.compose.material3.LinearProgressIndicator(progress = { (w.doneMinutes.toFloat() / t).coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
            }
            w.guardrail?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = cs.tertiary, modifier = Modifier.padding(top = 8.dp)) }
        }
        w.sessions.forEach { s ->
            val day = LocalDate.parse(s.date).let { "${it.dayOfWeek.name.take(3).lowercase().replaceFirstChar(Char::uppercase)} ${it.dayOfMonth}" }
            val status = when (s.status) {
                "done" -> "Done" + (s.ranMinutes?.let { " · $it min" } ?: "")
                "moved" -> "Moved to ${s.movedTo?.let { LocalDate.parse(it).dayOfWeek.name.take(3).lowercase().replaceFirstChar(Char::uppercase) } ?: "another day"}"
                "missed" -> "Missed · not made up"
                "today" -> "Today"
                "extra" -> "Extra run" + (s.ranMinutes?.let { " · $it min" } ?: "")
                else -> null
            }
            if (s.kind == "rest" && s.status == "rest") return@forEach
            val name = SESSION_NAMES[s.kind] ?: s.kind
            row("$day · $name" + (s.minutes?.let { " · ~$it min" } ?: "") + if (s.optional) " (optional)" else "",
                supporting = listOfNotNull(s.text.takeIf { s.kind in setOf("tempo", "intervals", "race_pace", "strides") }, status).joinToString(" · ")
                    .ifBlank { null }, icon = when (s.status) {
                    "done" -> Icons.Outlined.CheckCircle
                    "today" -> Icons.AutoMirrored.Outlined.DirectionsRun
                    else -> Icons.Outlined.EventNote
                }, iconShape = MaterialShapes.Cookie4Sided,
                accent = when (s.status) { "done" -> "fitness"; "missed" -> "recovery"; "today" -> "running"; else -> null },
                onClick = s.sourceId?.let { id -> { onOpenRun(id) } })
        }
        custom { w.basis?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant) } }
    }
}


/** Health and fitness out of 100, judged against your age and sex where a reference exists. Tap for the breakdown. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun ScoresCard(s: com.bennybar.runnersidekick.data.remote.Scores, onOpen: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Surface(onClick = onOpen, shape = MaterialTheme.shapes.extraLarge, color = cs.surfaceContainerHigh, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                ScoreRing("Health", s.health, cs.tertiary, Modifier.weight(1f))
                ScoreRing("Fitness", s.fitness, cs.primary, Modifier.weight(1f))
            }
            Text("For your age (${s.age}) · tap for what's behind each score", style = MaterialTheme.typography.labelMedium,
                color = cs.onSurfaceVariant)
        }
    }
}

@Composable
private fun ScoreRing(title: String, sc: com.bennybar.runnersidekick.data.remote.Score?, color: androidx.compose.ui.graphics.Color, modifier: Modifier) {
    val cs = MaterialTheme.colorScheme
    val v = sc?.score
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        androidx.compose.foundation.layout.Box(Modifier.size(76.dp), contentAlignment = Alignment.Center) {
            androidx.compose.foundation.Canvas(Modifier.fillMaxSize().semantics { contentDescription = "$title score ${v ?: "not available"} out of 100" }) {
                val stroke = androidx.compose.ui.graphics.drawscope.Stroke(9.dp.toPx(), cap = androidx.compose.ui.graphics.StrokeCap.Round)
                drawArc(cs.surfaceContainerHighest, -90f, 360f, false, style = stroke)
                if (v != null) drawArc(color, -90f, 360f * v / 100f, false, style = stroke)
            }
            Text(v?.toString() ?: "–", style = MaterialTheme.typography.headlineMedium)
        }
        Spacer(Modifier.width(12.dp))
        Column {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(sc?.label ?: "Not enough data", style = MaterialTheme.typography.bodyMedium, color = color)
        }
    }
}

@Composable
private fun ScoresSheet(s: com.bennybar.runnersidekick.data.remote.Scores, onDismiss: () -> Unit) {
    SheetColumn(onDismiss) {
        Text("Health and fitness scores", style = MaterialTheme.typography.headlineSmall)
        listOf("Health" to s.health, "Fitness" to s.fitness).forEach { (t, sc) ->
            if (sc == null) return@forEach
            Group(title = "$t ${sc.score?.let { "$it / 100 · ${sc.label}" } ?: "· not enough data"}" +
                (if (sc.used != null && sc.of != null && sc.used < sc.of) " · based on ${sc.used} of ${sc.of}" else "")) {
                sc.components.forEach { c ->
                    row(c.title + (c.value?.let { ": $it" } ?: ""), supporting = c.note,
                        trailing = { Text(c.points?.let { "$it pts · ${c.weightPct}%" } ?: "—", style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant) })
                }
            }
        }
        s.basis?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

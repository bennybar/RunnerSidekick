package com.bennybar.runnersidekick.ui.today

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
import androidx.compose.material.icons.automirrored.outlined.ListAlt
import androidx.compose.material.icons.automirrored.outlined.TrendingDown
import androidx.compose.material.icons.automirrored.outlined.TrendingFlat
import androidx.compose.material.icons.automirrored.outlined.TrendingUp
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.EventNote
import androidx.compose.material.icons.outlined.HourglassEmpty
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.LinkOff
import androidx.compose.material.icons.outlined.MonitorHeart
import androidx.compose.material.icons.outlined.Psychology
import androidx.compose.material.icons.outlined.SelfImprovement
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material.icons.outlined.TaskAlt
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material.icons.outlined.Watch
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.LoadingIndicator
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
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
import com.bennybar.runnersidekick.data.local.CheckinEntity
import com.bennybar.runnersidekick.data.local.Units
import com.bennybar.runnersidekick.data.remote.Finding
import com.bennybar.runnersidekick.data.remote.MorningReport
import com.bennybar.runnersidekick.data.remote.Narrative
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
import com.bennybar.runnersidekick.ui.insights.InsightCard
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
    val checkin by vm.todayCheckin.collectAsStateWithLifecycle()
    val insights by vm.insights.collectAsStateWithLifecycle()
    val fitness by vm.fitness.collectAsStateWithLifecycle()
    val focus by vm.focus.collectAsStateWithLifecycle()
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
                    IconButton(onClick = vm::syncNow, enabled = !busy) { Icon(Icons.Outlined.Sync, "Sync now") }
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
            LazyColumn(state = listState, contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 112.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                animatedItem(key = "fresh") { Freshness(status?.value, today?.fetchedAt, report, offline) }
                status?.value?.connection?.let { c -> if (c.state != "connected") animatedItem(key = "connection") { ConnectionNotice(c.state, c.detail, onOpenSettings) } }
                // Order: the day's call, what stands out, the readings, then commentary
                animatedItem(key = "hero") { Hero(report, onWhy = { sheet = "why" }) }
                if (report.highlights.isNotEmpty()) animatedItem(key = "highlights") {
                    StandsOut(report.highlights) { t ->
                        when (t.type) {
                            "run" -> t.id?.let(onOpenRun)
                            "compare" -> { com.bennybar.runnersidekick.ui.insights.InsightsTab.requested.value = 1; onOpenInsights() }
                            "insights" -> onOpenInsights()
                            "race" -> onOpenSettings()
                        }
                    }
                }
                // The app asks only when an answer would change today's advice
                if (checkin == null && report.checkinPrompt?.ask == true) animatedItem(key = "checkin") {
                    CheckinPromptCard(report.checkinPrompt.reason, onQuick = { rec -> vm.saveCheckin(report.localDate, null, null, rec, false, false, null) },
                        onMore = { sheet = "checkin" })
                }
                animatedItem(key = "readings") { Readings(report) { evidence = it } }
                focus?.value?.let { f -> animatedItem(key = "focus") { FocusCard(f, onChoose = vm::chooseFocus, onOpenRun = onOpenRun) } }
                // One AI voice: the coach's summary when there is one, otherwise the report summary
                val coachShown = coach?.value?.let { c -> if (c.status == "ok") c else c.previous?.takeIf { it.status == "ok" } }
                (coachShown?.tldr ?: coachShown?.summary)?.let { s ->
                    val c = coach!!.value
                    // Older advice is labelled as such, so it never reads as current next to a changed briefing
                    val note = if (coachShown !== c) (if (c.status == "pending") "Updating for today's changes…" else "From an earlier analysis")
                        else "Updated ${Format.ago(runCatching { Instant.parse(coachShown.generatedAt) }.getOrNull())}"
                    animatedItem(key = "coach") { CoachTeaser(s, note, onOpenInsights) }
                } ?: report.narrative?.let { n -> animatedItem(key = "narrative") { NarrativeCard(n, report) { id -> evidence = report.findings.firstOrNull { it.id == id } } } }
                // Prefer what's new or changed; skip what the runner dismissed or is already working on
                insights?.value?.insights?.filter { it.verdict == "pattern" && it.userState == null }
                    ?.sortedBy { if (it.novelty == "continuing") 1 else 0 }?.firstOrNull()?.let { top ->
                    animatedItem(key = "noticed") {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("Something we noticed", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.padding(start = 4.dp, top = 8.dp))
                            InsightCard(top, emphasised = true, onMethod = onOpenInsights)
                        }
                    }
                }
                animatedItem(key = "more") {
                    Group(title = "More") {
                        fitness?.value?.garmin?.let { g ->
                            val parts = listOfNotNull(g.vo2max?.let { "VO₂ max %.1f".format(it.value) },
                                com.bennybar.runnersidekick.ui.insights.trainingStatusLabel(g.trainingStatus?.phrase),
                                g.racePredictions?.k5?.let { "5K ${(it / 60).toInt()}:${"%02d".format(it.toInt() % 60)}" })
                            if (parts.isNotEmpty()) row("Your fitness", supporting = parts.joinToString(" · ") + " (Garmin)",
                                icon = Icons.Outlined.MonitorHeart, iconShape = MaterialShapes.Cookie9Sided, onClick = onOpenInsights,
                                accent = "fitness")
                        }
                        val plan = report.recommendation.plan
                        row("Today's plan", supporting = plan?.let { p -> (PLAN_KINDS.firstOrNull { it.first == p.kind }?.second ?: p.kind) +
                            (p.minutes?.let { " · $it min" } ?: "") } ?: "Optional · the suggestion adapts to it",
                            icon = Icons.Outlined.EventNote, iconShape = MaterialShapes.Cookie4Sided, onClick = { sheet = "plan" },
                            accent = "habits")
                        row(if (checkin == null) "Check in" else "Your check-in", supporting = checkin?.let(::checkinSummary) ?: "Optional",
                            icon = Icons.Outlined.TaskAlt, iconShape = MaterialShapes.Cookie4Sided, onClick = { sheet = "checkin" },
                            accent = "recovery")
                        report.recentRun?.let { run ->
                            row(run.name ?: "Run", overline = "Latest run · ${Format.shortDate(run.localDate)}",
                                supporting = "${Format.distance(run.distanceM, units)} · ${Format.duration(run.movingS)} moving · " +
                                    Format.pace(if (run.distanceM != null && run.movingS != null && run.distanceM > 0) run.movingS / (run.distanceM / 1000) else null, units),
                                icon = Icons.AutoMirrored.Outlined.DirectionsRun, iconShape = MaterialShapes.Cookie9Sided, onClick = { onOpenRun(run.sourceId) },
                                accent = "running")
                        }
                        row("Full briefing", supporting = "All findings, Garmin scores and report details", icon = Icons.AutoMirrored.Outlined.ListAlt,
                            iconShape = MaterialShapes.Clover4Leaf, onClick = { sheet = "briefing" })
                    }
                }
            }
        }
    }
    when (sheet) {
        "checkin" -> report?.let { r ->
            CheckinSheet(r.localDate, checkin, onDismiss = { sheet = null }) { e, s, rec, p, i, n ->
                vm.saveCheckin(r.localDate, e, s, rec, p, i, n); sheet = null
            }
        }
        "plan" -> report?.let { r ->
            SheetColumn(onDismiss = { sheet = null }) {
                PlanCard(r.recommendation.plan) { kind, minutes -> vm.setPlan(r.localDate, kind, minutes) }
            }
        }
        "why" -> report?.let { WhySheet(it, onDismiss = { sheet = null }) { f -> sheet = null; evidence = f } }
        "briefing" -> report?.let { BriefingSheet(it, onDismiss = { sheet = null }) { f -> sheet = null; evidence = f } }
    }
    evidence?.let { EvidenceSheet(it) { evidence = null } }
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
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 4.dp)) {
                OutlinedButton(onClick = onWhy) { Text("Why this suggestion?") }
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

private val QUICK = listOf(4 to "Fresh", 3 to "Okay", 2 to "Tired")

/** Shown only when the backend says an answer matters today; one tap answers "how recovered do you feel?". */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun CheckinPromptCard(reason: String?, onQuick: (Int) -> Unit, onMore: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Surface(shape = MaterialTheme.shapes.large, color = cs.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ShapeBadge(Icons.Outlined.TaskAlt, MaterialShapes.Sunny, Modifier.size(36.dp), container = cs.tertiaryContainer, content = cs.onTertiaryContainer)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("How recovered do you feel?", style = MaterialTheme.typography.titleMedium)
                    reason?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant) }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                QUICK.forEach { (v, l) -> FilledTonalButton(onClick = { onQuick(v) }) { Text(l) } }
                Spacer(Modifier.weight(1f))
                TextButton(onClick = onMore) { Text("More") }
            }
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

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun NarrativeCard(n: Narrative, r: MorningReport, onFinding: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    when (n.status) {
        "ok" -> Surface(shape = MaterialTheme.shapes.large, color = cs.secondaryContainer, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    ShapeBadge(Icons.Outlined.AutoAwesome, MaterialShapes.Flower, Modifier.size(36.dp), container = cs.secondary, content = cs.onSecondary)
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text("Summary", style = MaterialTheme.typography.titleMedium, color = cs.onSecondaryContainer)
                        Text("Written by AI (${n.model ?: n.provider}) from the findings below. Numbers come from the report.",
                            style = MaterialTheme.typography.labelSmall, color = cs.onSecondaryContainer.copy(alpha = 0.75f))
                    }
                }
                Text(n.sentences.joinToString(" ") { it.text }, style = MaterialTheme.typography.bodyLarge, color = cs.onSecondaryContainer)
                n.focus?.let { Text("Focus: ${it.text}", style = MaterialTheme.typography.bodyMedium, color = cs.onSecondaryContainer) }
                val refs = (n.sentences.flatMap { it.findingIds } + n.focus?.findingIds.orEmpty()).distinct()
                    .mapNotNull { id -> r.findings.firstOrNull { it.id == id } }
                if (refs.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    refs.forEach { f -> AssistChip(onClick = { onFinding(f.id) }, label = { Text(f.title) }) }
                }
            }
        }
        "pending" -> Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            LoadingIndicator(Modifier.size(32.dp))
            Spacer(Modifier.width(8.dp))
            Text("Writing an AI summary…", style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
        }
        "rejected", "failed", "budget_exceeded", "not_configured" -> Text(
            "AI summary unavailable for this report" +
                (if (n.status == "not_configured") " (no API key on the backend)." else ". The standard briefing is complete."),
            style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp),
        )
        else -> Unit // disabled: nothing shown
    }
}

private fun tileValue(f: Finding): Pair<String, String?> {
    val v = f.observed?.value ?: return "—" to null
    return when (f.metric) {
        "sleep_duration", "running_moving_time_7d" -> { val m = (v / 60).roundToInt(); "${m / 60}h ${"%02d".format(m % 60)}m" to null }
        "resting_hr" -> "${v.roundToInt()}" to "bpm"
        else -> "${v.roundToInt()}" to "ms"
    }
}

private fun tileStatus(f: Finding): String = when {
    f.metric == "running_moving_time_7d" -> if (f.status == "outside") "Well above recent weeks" else "Similar to recent weeks"
    f.status == "learning" -> "Learning · ${f.sampleSize ?: 0}/14 days"
    f.status == "missing" -> "Not recorded"
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
private fun Readings(r: MorningReport, onTap: (Finding) -> Unit) {
    val tiles = TILE_METRICS.mapNotNull { m -> r.findings.firstOrNull { it.metric == m } }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Readings", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(start = 4.dp, top = 8.dp))
        tiles.chunked(2).forEach { pair ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                pair.forEach { f ->
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

private fun checkinSummary(c: CheckinEntity) =
    "Energy ${c.energy ?: "–"} · Soreness ${c.soreness ?: "–"} · Recovery ${c.recovery ?: "–"}" +
        (if (c.pain) " · Pain" else "") + (if (c.illness) " · Unwell" else "") + (if (c.pendingSync) " · not uploaded yet" else "")

// ---------------------------------------------------------------- sheets

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SheetColumn(onDismiss: () -> Unit, content: @Composable () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(14.dp)) { content() }
    }
}

private val SCALE = listOf(1, 2, 3, 4, 5)

@Composable
private fun ScaleRow(label: String, low: String, high: String, value: Int?, onChange: (Int) -> Unit) {
    Column {
        Text(label, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(6.dp))
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            SCALE.forEachIndexed { i, v ->
                SegmentedButton(selected = value == v, onClick = { onChange(v) }, shape = SegmentedButtonDefaults.itemShape(i, SCALE.size),
                    icon = {}, modifier = Modifier.semantics { contentDescription = "$label $v of 5" }) { Text("$v") }
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 2.dp)) {
            Text(low, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.weight(1f))
            Text(high, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun CheckinSheet(
    date: String, existing: CheckinEntity?, onDismiss: () -> Unit,
    onSave: (Int?, Int?, Int?, Boolean, Boolean, String?) -> Unit,
) {
    var energy by rememberSaveable { mutableStateOf(existing?.energy) }
    var soreness by rememberSaveable { mutableStateOf(existing?.soreness) }
    var recovery by rememberSaveable { mutableStateOf(existing?.recovery) }
    var pain by rememberSaveable { mutableStateOf(existing?.pain ?: false) }
    var illness by rememberSaveable { mutableStateOf(existing?.illness ?: false) }
    var notes by rememberSaveable { mutableStateOf(existing?.notes ?: "") }
    SheetColumn(onDismiss) {
        Text("How do you feel?", style = MaterialTheme.typography.headlineSmall)
        Text(Format.longDate(date), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        ScaleRow("Energy", "Drained", "Great", energy) { energy = it }
        ScaleRow("Soreness", "None", "Very sore", soreness) { soreness = it }
        ScaleRow("Recovery", "Not recovered", "Fully", recovery) { recovery = it }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = pain, onClick = { pain = !pain }, label = { Text("Pain or injury") })
            FilterChip(selected = illness, onClick = { illness = !illness }, label = { Text("Feeling unwell") })
        }
        OutlinedTextField(notes, { notes = it }, label = { Text("Notes (optional, never sent to AI)") }, modifier = Modifier.fillMaxWidth(), maxLines = 3)
        Button(
            onClick = { onSave(energy, soreness, recovery, pain, illness, notes) },
            enabled = energy != null || soreness != null || recovery != null || pain || illness,
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) { Text("Save check-in") }
    }
}

@Composable
private fun WhySheet(r: MorningReport, onDismiss: () -> Unit, onFinding: (Finding) -> Unit) {
    val rec = r.recommendation
    SheetColumn(onDismiss) {
        Text("Why this suggestion", style = MaterialTheme.typography.headlineSmall)
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

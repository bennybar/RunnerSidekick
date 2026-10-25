package com.bennybar.runnersidekick.ui.today

import androidx.compose.material.icons.outlined.Bedtime
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material.icons.outlined.MonitorHeart
import androidx.compose.material.icons.outlined.Speed
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.foundation.background
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Close
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.outlined.TrendingDown
import androidx.compose.material.icons.automirrored.outlined.TrendingFlat
import androidx.compose.material.icons.automirrored.outlined.TrendingUp
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.EventNote
import androidx.compose.material.icons.outlined.HourglassEmpty
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.LinkOff
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.LoadingIndicator
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.bennybar.runnersidekick.data.local.Units
import com.bennybar.runnersidekick.ui.components.VerdictChip
import com.bennybar.runnersidekick.data.remote.Finding
import com.bennybar.runnersidekick.data.remote.MorningReport
import com.bennybar.runnersidekick.data.remote.Status
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.TodayVm
import com.bennybar.runnersidekick.ui.components.BigValue
import com.bennybar.runnersidekick.ui.components.DemoBadge
import com.bennybar.runnersidekick.ui.components.DetailPage
import com.bennybar.runnersidekick.ui.components.EmptyState
import com.bennybar.runnersidekick.ui.components.EvidenceSheet
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.SectionLabel
import com.bennybar.runnersidekick.ui.components.Tile
import com.bennybar.runnersidekick.ui.components.animatedItem
import com.bennybar.runnersidekick.ui.components.MetricTile
import com.bennybar.runnersidekick.ui.components.OfflineBanner
import com.bennybar.runnersidekick.ui.components.Sparkline
import com.bennybar.runnersidekick.ui.factory
import com.bennybar.runnersidekick.ui.theme.Tint
import com.bennybar.runnersidekick.ui.theme.ink
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import kotlin.math.roundToInt

private val TILE_METRICS = listOf("sleep_duration", "resting_hr", "hrv_overnight_avg", "running_moving_time_7d")
private val TILE_BADGES = mapOf(
    "sleep_duration" to (Icons.Outlined.Bedtime to MaterialShapes.Clover4Leaf),
    "resting_hr" to (Icons.Outlined.FavoriteBorder to MaterialShapes.Heart),
    "hrv_overnight_avg" to (Icons.Outlined.MonitorHeart to MaterialShapes.SoftBurst),
    "running_moving_time_7d" to (Icons.AutoMirrored.Outlined.DirectionsRun to MaterialShapes.Cookie6Sided))
private val TILE_TINTS = mapOf("sleep_duration" to Tint.INDIGO, "resting_hr" to Tint.PINK, "hrv_overnight_avg" to Tint.PINK,
    "running_moving_time_7d" to Tint.ORANGE)

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun TodayScreen(onOpenRun: (String) -> Unit, onOpenSettings: () -> Unit, onOpenInsights: () -> Unit, vm: TodayVm = viewModel(factory = factory(::TodayVm))) {
    com.bennybar.runnersidekick.ui.components.TrackVisible(vm)
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
    var sheet by rememberSaveable { mutableStateOf<String?>(null) } // the open detail page: readiness | briefing | health | fitness | vo2 | race | focus
    val listState = rememberLazyListState()
    val coach by vm.coach.collectAsStateWithLifecycle()
    val aiOn = com.bennybar.runnersidekick.ui.components.LocalAiEnabled.current
    val checkins by vm.checkins.collectAsStateWithLifecycle()
    val focus by vm.focus.collectAsStateWithLifecycle()

    LaunchedEffect(error) { error?.let { snackbar.showSnackbar(it); vm.clearError() } }
    val report = today?.value
    val unwellPending by vm.unwellPending.collectAsStateWithLifecycle()
    /** One readiness as shown, for the card and its page alike: rest while "not feeling well" isn't in the briefing yet */
    fun shownReadiness(r: com.bennybar.runnersidekick.data.remote.Score) =
        if (unwellPending) r.copy(score = null, label = "Low", headline = "Take it easy or rest", holdReason = "you're not feeling well", allows = "rest") else r

    // The big title with the sync button above it; it scrolls with the tiles
    val header: @Composable () -> Unit = {
        Header(report, status?.value, today?.fetchedAt, offline, busy) { vm.syncNow() }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar, Modifier.padding(bottom = com.bennybar.runnersidekick.ui.components.LocalNavBarPadding.current)) }  // above the floating bar,
    ) { padding ->
        com.bennybar.runnersidekick.ui.components.RefreshBox(isRefreshing = busy && report != null, onRefresh = vm::refresh, modifier = Modifier.padding(padding).fillMaxSize()) {
            if (report == null) {
                NoReport(busy, settings?.hasToken == false, onOpenSettings, header)
                return@RefreshBox
            }
            LazyColumn(state = listState, contentPadding = PaddingValues(start = 12.dp, end = 12.dp, bottom = 24.dp + com.bennybar.runnersidekick.ui.components.LocalNavBarPadding.current),
                verticalArrangement = Arrangement.spacedBy(10.dp)) {
                animatedItem(key = "header") { header() }
                status?.value?.connection?.let { c -> if (c.state != "connected") animatedItem(key = "connection") { ConnectionNotice(c.state, c.detail, onOpenSettings) } }
                // A simple overview: scores, the day's call, the AI's one line, what stands out, readings, the latest run
                // "How am I and what do I do today" first (readiness, then the next run), then the slower health and fitness scores
                // "Not feeling well" is for the phone's today, whatever day the cached briefing is from. Until the server has
                // it (offline, or still syncing), the phone applies it itself: rest, said as pending.
                val todayDate = LocalDate.now().toString()
                val mark = checkins.firstOrNull { it.localDate == todayDate }
                val unwell = mark?.illness == true
                val pending = unwellPending
                report.readiness?.let { r -> animatedItem(key = "readiness") {
                    ReadinessCard(shownReadiness(r), unwell, pending, onUnwell = { vm.setUnwell(todayDate, !unwell) }) { sheet = "readiness" } } }
                report.nextRun?.let { n -> animatedItem(key = "nextrun") {
                    NextRunCard(if (pending) n.copy(date = todayDate, dayLabel = "Today", kind = "rest", title = "Rest or a short walk", distanceKm = null,
                        minutes = null, hr = null, pace = null, paceSPerKm = null, optional = false, caution = null,
                        why = listOf("you're not feeling well")) else n, units) } }
                // This week: the race week (with a race goal) and the weekly focus, compact; the full cards open as pages
                report.race?.let { r -> r.week?.let { w -> animatedItem(key = "raceweek") { RaceWeekStrip(r, w) { sheet = "race" } } } }
                focus?.value?.let { f -> animatedItem(key = "focus") { FocusLine(f) { sheet = "focus" } } }
                report.scores?.takeIf { it.status == "ok" }?.let { sc -> animatedItem(key = "scores") { ScoresCard(sc) { which -> sheet = which } } }
                // Coach advice written before "not feeling well" reached the server would contradict the rest above: held back
                val coachShown = if (pending || !aiOn) null else coach?.value?.let { c -> if (c.status == "ok") c else c.previous?.takeIf { it.status == "ok" } }
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
                animatedItem(key = "readings") {
                    Readings(report, fitness?.value, onOpenFitness = { sheet = "vo2" }) { evidence = it }
                }
                report.overnight?.let { n -> animatedItem(key = "night") { LastNight(n) } }
                report.recentRun?.let { run -> animatedItem(key = "lastrun") { LastRunCard(run, units) { onOpenRun(run.sourceId) } } }
            }
        }
    }
    // Detail pages; one that leads to another screen closes first, so back from there comes to Today
    when (sheet) {
        "health", "fitness" -> report?.scores?.let { sc -> (if (sheet == "health") sc.health else sc.fitness)?.let {
            ScorePage(if (sheet == "health") "Healthy habits" else "Fitness", if (sheet == "health") Tint.PURPLE else Tint.BLUE,
                sc.scope[sheet!!], it, sc.basis, onBack = { sheet = null }) } }
        "readiness" -> report?.let { r -> r.readiness?.let { ReadinessPage(shownReadiness(it), r.changes, onBack = { sheet = null }, onBriefing = { sheet = "briefing" }) } }
        "vo2" -> report?.let { r ->
            DetailPage("VO₂ max", onBack = { sheet = null }) {
                fitness?.value?.let { f -> chosenVo2(f)?.let { v ->
                    PageHead("%.1f".format(v), "ml/kg/min",
                        if (f.vo2Maker == "Runner Sidekick") "Runner Sidekick's estimate" else "${f.vo2Maker}'s latest reading")
                } }
                fitness?.value?.let { f -> Tile(tint = Tint.TEAL, spacing = 12.dp) { Vo2Progress(f.vo2maxSeries, f.vo2Maker, r.localDate) } }
                r.readingNotes["vo2max"]?.let { com.bennybar.runnersidekick.ui.components.NoteBlock(it) }
                OutlinedButton(onClick = { sheet = null; com.bennybar.runnersidekick.ui.insights.InsightsTab.requested.value = 1; onOpenInsights() },
                    modifier = Modifier.fillMaxWidth().height(48.dp)) { Text("Compare with your age group") }
            }
        }
        // Back from the full briefing returns to readiness, where it opens from; a finding's "Show why" opens over it
        "briefing" -> report?.let { BriefingPage(it, onBack = { sheet = "readiness" }) { f -> evidence = f } }
        "race" -> report?.race?.let { r -> r.week?.let { w -> DetailPage("Race week", onBack = { sheet = null }) {
            RaceWeekCard(r, w) { id -> sheet = null; onOpenRun(id) } } } }
        "focus" -> focus?.value?.let { f -> DetailPage("This week's focus", onBack = { sheet = null }) {
            FocusCard(f, onChoose = { k -> vm.chooseFocus(k) }, onOpenRun = { id -> sheet = null; onOpenRun(id) }) } }
    }
    evidence?.let { f -> EvidenceSheet(f, today?.value?.readingNotes?.get(f.metric)) { evidence = null } }
}

/** "Today", the briefing's date and when the watch last synced, with the sync button top right. */
@Composable
private fun Header(report: MorningReport?, status: Status?, fetchedAt: Instant?, offline: Boolean, busy: Boolean, onSync: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Column {
        Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End),
            verticalAlignment = Alignment.CenterVertically) {
            if (status?.synthetic == true) DemoBadge()
            // Garmin syncs at most every 15 minutes (the server's cooldown); the button says when the next one can run
            val wait = com.bennybar.runnersidekick.ui.components.syncWait(status?.syncNextAllowedAt)
            FilledTonalButton(onClick = onSync, enabled = !busy && wait == null,
                colors = ButtonDefaults.filledTonalButtonColors(containerColor = cs.surfaceContainer, contentColor = cs.onSurface)) {
                Icon(Icons.Outlined.Sync, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp))
                Text(if (busy) "Syncing…" else wait?.let { "Next sync $it" } ?: if (status?.watch == "samsung") "Sync watch" else "Sync Garmin")
            }
        }
        Column(Modifier.padding(start = 12.dp, end = 12.dp, top = 22.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Today", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)
            report?.localDate?.let { Text(Format.longDate(it), style = MaterialTheme.typography.bodyLarge, color = cs.onSurfaceVariant) }
            report?.let { Freshness(status, it) }
        }
        if (offline) OfflineBanner("Offline: showing the briefing saved ${Format.ago(fetchedAt)}.")
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun NoReport(busy: Boolean, notConnected: Boolean, onOpenSettings: () -> Unit, header: @Composable () -> Unit) {
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 12.dp)) {
        item { header() }
        item {
            when {
                notConnected -> EmptyState(Icons.Outlined.LinkOff, "Not signed in", "Sign in to load your data.") {
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

/** A small rounded label on a tile: a distance, a status, a day. */
@Composable
internal fun TagChip(text: String, modifier: Modifier = Modifier, container: Color = MaterialTheme.colorScheme.surface.copy(alpha = 0.75f),
                     content: Color = MaterialTheme.colorScheme.onSurface) {
    Surface(shape = RoundedCornerShape(12.dp), color = container, contentColor = content, modifier = modifier) {
        Text(text, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp))
    }
}

/** A thin rounded progress bar. */
@Composable
private fun ProgressBar(fraction: Float, fill: Brush, modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().height(6.dp).background(MaterialTheme.colorScheme.onSurface.copy(alpha = 0.08f), CircleShape)) {
        Box(Modifier.fillMaxWidth(fraction.coerceIn(0f, 1f)).height(6.dp).background(fill, CircleShape))
    }
}

/** The headline number of a detail page, with a line or two under it. */
@Composable
private fun PageHead(value: String, unit: String?, vararg lines: String?) {
    Column(Modifier.padding(start = 12.dp, end = 12.dp, top = 12.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        BigValue(value, unit, style = MaterialTheme.typography.displayMedium.copy(fontWeight = FontWeight.Bold))
        lines.filterNotNull().forEach { Text(it, style = MaterialTheme.typography.bodyLarge) }
    }
}

/** The sync line under the date: "Samsung synced 2 h ago", flagged in words and with a warning icon after 12 h. */
@Composable
private fun Freshness(status: Status?, report: MorningReport) {
    val lastSource = status?.connection?.lastSuccessAt?.let { runCatching { Instant.parse(it) }.getOrNull() }
    val stale = lastSource == null || Duration.between(lastSource, Instant.now()).toHours() >= 12
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(if (stale) Icons.Outlined.WarningAmber else Icons.Outlined.CheckCircle, null, Modifier.size(16.dp),
            tint = if (stale) ink(Tint.ORANGE) else ink(Tint.GREEN))
        Spacer(Modifier.width(6.dp))
        Text((if (status?.synthetic == true) "Demo source synced " else if (status?.watch == "samsung") "Samsung synced " else "Garmin synced ") + Format.ago(lastSource) +
            (if (report.provisional) " · last night not in yet" else ""), style = MaterialTheme.typography.bodyMedium,
            color = if (stale) ink(Tint.ORANGE) else MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun ConnectionNotice(state: String, detail: String?, onOpenSettings: () -> Unit) {
    val (title, body) = when (state) {
        "reauth_required" -> "Garmin needs connecting again" to "Garmin ended the connection, so syncing is paused. Tap to connect it again in Settings."
        "rate_limited" -> "Garmin asked us to slow down" to "Syncing will retry automatically later."
        "not_configured" -> "Garmin isn't connected" to "Tap to connect Garmin in Settings and download your runs, sleep and health data."
        else -> "Last sync failed" to (detail ?: "Will retry later.")
    }
    Tile(tint = Tint.ORANGE, onClick = onOpenSettings) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.LinkOff, null, tint = ink(Tint.ORANGE))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleSmall)
                Text(body, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// Attention reads orange, as everywhere else; the icon says the tone too
private val TONE_ACCENT = mapOf("attention" to "training", "positive" to "fitness", "info" to "sleep")

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

@Composable
private fun CoachTeaser(summary: String, note: String, onOpen: () -> Unit) {
    Tile(onClick = onOpen) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("From your AI coach", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
            Text(note, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.End,
                modifier = Modifier.padding(start = 8.dp))
        }
        Text(summary, style = MaterialTheme.typography.bodyMedium)
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
    f.status == "missing" -> f.last?.let { if (it.date == java.time.LocalDate.now().minusDays(1).toString()) "Yesterday's" else "From ${Format.shortDate(it.date)}" } ?: "Not in yet"
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

/** The VO2 max chosen in Settings: Runner Sidekick's (its series), else Garmin's current one, or the Samsung watch's latest */
private fun chosenVo2(fitness: com.bennybar.runnersidekick.data.remote.Fitness?): Double? {
    val maker = fitness?.vo2Maker ?: "Garmin"
    return (if (maker == "Runner Sidekick") null else fitness?.garmin?.vo2max?.value) ?: fitness?.vo2maxSeries?.lastOrNull()?.value
}

/** VO2 max progress on the VO2 max page: the chosen source's readings since 3 months, 6 months or a year ago. */
@Composable
private fun Vo2Progress(series: List<com.bennybar.runnersidekick.data.remote.Point>, maker: String, today: String) {
    val cs = MaterialTheme.colorScheme
    var months by rememberSaveable { mutableStateOf(3) }
    val from = java.time.LocalDate.parse(today).minusMonths(months.toLong())
    val pts = series.filter { !java.time.LocalDate.parse(it.date).isBefore(from) }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Progress", style = MaterialTheme.typography.titleSmall)
        val ranges = listOf(3, 6, 12)
        com.bennybar.runnersidekick.ui.components.ChoiceGroup(listOf("3 months", "6 months", "1 year"), ranges.indexOf(months), { months = ranges[it] })
        if (pts.size < 2) {
            Text("Not enough $maker readings in this period yet.", style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
            return@Column
        }
        val ch = pts.last().value - pts.first().value
        Text((if (kotlin.math.abs(ch) < 0.05) "About the same" else "%+.1f".format(ch)) +
            " since ${com.bennybar.runnersidekick.ui.Format.shortDate(pts.first().date)} (%.1f → %.1f)".format(pts.first().value, pts.last().value),
            style = MaterialTheme.typography.bodyLarge)
        val lo = kotlin.math.floor(pts.minOf { it.value } - 0.5)
        val hi = kotlin.math.ceil(pts.maxOf { it.value } + 0.5)
        val d0 = java.time.LocalDate.parse(pts.first().date).toEpochDay().toDouble()
        val span = (java.time.LocalDate.parse(pts.last().date).toEpochDay() - d0).coerceAtLeast(1.0)
        val line = ink(Tint.TEAL)
        val grid = cs.outlineVariant
        Row {
            Column(Modifier.width(36.dp).height(140.dp)) {
                Text("%.0f".format(hi), style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
                Spacer(Modifier.weight(1f))
                Text("%.0f".format(lo), style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            }
            androidx.compose.foundation.Canvas(Modifier.weight(1f).height(140.dp).semantics {
                contentDescription = "VO2 max from %.1f to %.1f over %d readings".format(pts.first().value, pts.last().value, pts.size)
            }) {
                fun x(p: com.bennybar.runnersidekick.data.remote.Point) =
                    ((java.time.LocalDate.parse(p.date).toEpochDay() - d0) / span * size.width).toFloat()
                fun y(v: Double) = (size.height * (1 - (v - lo) / (hi - lo))).toFloat()
                val dash = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(6f, 6f))
                drawLine(grid, androidx.compose.ui.geometry.Offset(0f, 0f), androidx.compose.ui.geometry.Offset(size.width, 0f), pathEffect = dash)
                drawLine(grid, androidx.compose.ui.geometry.Offset(0f, size.height), androidx.compose.ui.geometry.Offset(size.width, size.height), pathEffect = dash)
                val path = androidx.compose.ui.graphics.Path()
                pts.forEachIndexed { i, p -> if (i == 0) path.moveTo(x(p), y(p.value)) else path.lineTo(x(p), y(p.value)) }
                drawPath(path, line, style = Stroke(width = 2.5.dp.toPx(), cap = StrokeCap.Round))
                pts.forEach { p -> drawCircle(line, 3.dp.toPx(), androidx.compose.ui.geometry.Offset(x(p), y(p.value))) }
            }
        }
        Row(Modifier.fillMaxWidth().padding(start = 36.dp)) {
            Text(com.bennybar.runnersidekick.ui.Format.shortDate(pts.first().date), style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            Spacer(Modifier.weight(1f))
            Text(com.bennybar.runnersidekick.ui.Format.shortDate(pts.last().date), style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
        }
        Text(if (maker == "Runner Sidekick") "Runner Sidekick's estimate as it stood after each qualifying run." else "$maker's readings.",
            style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
    }
}

@Composable
private fun Readings(r: MorningReport, fitness: com.bennybar.runnersidekick.data.remote.Fitness?, onOpenFitness: () -> Unit,
                     onTap: (Finding) -> Unit) {
    val maker = fitness?.vo2Maker ?: "Garmin"
    val vo2 = chosenVo2(fitness)
    // null marks the VO2 max tile's slot, right after the overnight readings
    val tiles: List<Finding?> = TILE_METRICS.mapNotNull { m -> r.findings.firstOrNull { it.metric == m } } + (if (vo2 != null) listOf(null) else emptyList())
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionLabel("Readings")
        tiles.chunked(2).forEach { pair ->
            // An odd last tile (usually VO2 max) takes the whole row
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                pair.forEach { f ->
                    if (f == null) {
                        // The chosen VO2 max (one decimal), with the change over about four weeks
                        val series = fitness!!.vo2maxSeries
                        val old = series.lastOrNull { java.time.LocalDate.parse(it.date) <= java.time.LocalDate.parse(r.localDate).minusDays(28) }
                        val ch = old?.let { vo2!! - it.value }
                        MetricTile(label = "VO₂ max", value = "%.1f".format(vo2!!), unit = null,
                            status = ch?.let { if (kotlin.math.abs(it) < 0.05) "Same as 4 weeks ago" else "%+.1f in 4 weeks".format(it) } ?: maker,
                            statusIcon = ch?.let { if (it > 0.05) Icons.AutoMirrored.Outlined.TrendingUp else if (it < -0.05) Icons.AutoMirrored.Outlined.TrendingDown
                                else Icons.AutoMirrored.Outlined.TrendingFlat }, flagged = false, tint = Tint.TEAL,
                            modifier = Modifier.weight(1f).semantics(mergeDescendants = true) { contentDescription = "VO2 max %.1f, %s".format(vo2, maker) },
                            onClick = onOpenFitness, badge = Icons.Outlined.Speed to MaterialShapes.Sunny,
                            chart = if (series.size >= 2) {
                                { Sparkline(series.takeLast(14).map { it.value }, Modifier.fillMaxWidth().height(32.dp),
                                    color = ink(Tint.TEAL), description = "VO2 max, recent $maker readings") }
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
                    val tint = TILE_TINTS[f.metric] ?: Tint.NEUTRAL
                    val lineColor = if (flagged) ink(Tint.ORANGE) else ink(tint)
                    MetricTile(
                        label = if (f.metric == "running_moving_time_7d") "Running, 7 days" else f.title,
                        value = value, unit = unit, status = tileStatus(f), statusIcon = icon, flagged = flagged, tint = tint,
                        modifier = Modifier.weight(1f).semantics(mergeDescendants = true) { contentDescription = "${f.title}. ${f.statement}" },
                        onClick = { onTap(f) }, badge = TILE_BADGES[f.metric],
                        chart = if (!f.sparkline.isNullOrEmpty()) {
                            { Sparkline(dailySeries(f, r.localDate), Modifier.fillMaxWidth().height(32.dp), band = band, color = lineColor,
                                description = "${f.title}, last 14 days") }
                        } else null,
                    )
                }
            }
        }
    }
}

@Composable
private fun BriefingPage(r: MorningReport, onBack: () -> Unit, onFinding: (Finding) -> Unit) {
    val cs = MaterialTheme.colorScheme
    DetailPage("Full briefing", onBack) {
        Group(title = "Findings", tint = Tint.GREEN) { r.findings.forEach { f -> row(f.title, supporting = f.statement, onClick = { onFinding(f) }) } }
        if (r.garminContext.isNotEmpty()) {
            val origins = r.garminContext.map { it.origin }.distinct()
            Group(title = "From " + (origins.singleOrNull() ?: "your watches")) {
                r.garminContext.forEach { g -> row(garminName(g.metric), trailing = {
                    Text("${g.value.roundToInt()}" + (g.label?.let { " · $it" } ?: ""), style = MaterialTheme.typography.titleSmall)
                }) }
            }
            Text("The watch's own scores, shown for context. They don't feed the suggestion, which avoids counting sleep and HRV twice.",
                style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp))
        }
        Text("Revision ${r.revision} · generated ${Format.ago(runCatching { Instant.parse(r.generatedAt) }.getOrNull())} · " +
            "rules ${r.recommendation.rulesVersion} (${r.recommendation.ruleId})", style = MaterialTheme.typography.labelSmall,
            color = cs.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp, vertical = 8.dp))
    }
}

private fun garminName(metric: String) = when (metric) {
    "garmin_training_readiness" -> "Training readiness"
    "garmin_sleep_score", "samsung_sleep_score" -> "Sleep score"
    "body_battery_high" -> "Body Battery high"
    "body_battery_low" -> "Body Battery low"
    "avg_stress" -> "Average stress"
    "garmin_vo2max_running" -> "VO₂ max"
    else -> metric
}


private val SESSION_NAMES = mapOf("easy" to "Easy run", "long" to "Long run", "tempo" to "Tempo", "intervals" to "Intervals",
    "race_pace" to "Race pace", "strides" to "Easy + strides", "race" to "Race day", "rest" to "Rest")

private fun daysToGo(d: Int) = if (d > 0) "$d days" else if (d == 0) "Today" else "Done"

/** The week toward the race: each day's session, ticked off as runs come in. Recomputed daily from what was run. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun RaceWeekCard(race: com.bennybar.runnersidekick.data.remote.RaceStatus, w: com.bennybar.runnersidekick.data.remote.RaceWeek,
                         onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    Tile(tint = Tint.AMBER) {
        Text("This week toward ${race.title ?: race.headline}", style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
        Text("${w.phase.replace('_', ' ').replaceFirstChar(Char::uppercase)} · ${daysToGo(race.daysToGo)}" + if (race.daysToGo > 0) " to go" else "",
            style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(w.targetMinutes?.let { "About $it min this week · ${w.doneMinutes} min done" } ?: "${w.doneMinutes} min done this week",
            style = MaterialTheme.typography.bodyLarge)
        w.targetMinutes?.takeIf { it > 0 }?.let { t ->  // a zero target would be a NaN progress
            ProgressBar(w.doneMinutes.toFloat() / t, Brush.linearGradient(listOf(Tint.AMBER.hue, Tint.AMBER.hue)))
        }
        w.guardrail?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant) }
    }
    Group {
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
                    "done", "extra" -> Icons.Outlined.CheckCircle
                    "today" -> Icons.AutoMirrored.Outlined.DirectionsRun
                    "moved" -> Icons.AutoMirrored.Outlined.ArrowForward
                    "missed" -> Icons.Outlined.Close
                    else -> Icons.Outlined.EventNote
                }, iconShape = MaterialShapes.Circle,
                accent = when (s.status) { "done", "extra" -> "running"; "moved" -> "fitness"; "missed" -> "recovery"; "today" -> "training"; else -> null },
                onClick = s.sourceId?.let { id -> { onOpenRun(id) } })
        }
    }
    w.basis?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp)) }
}


/** Fitness and healthy habits out of 100, as two tinted tiles side by side, each with how it moved in 4 weeks. Tap one for its parts. */
@Composable
private fun ScoresCard(s: com.bennybar.runnersidekick.data.remote.Scores, onOpen: (String) -> Unit) {
    // Equal heights, and a fixed two-line subtitle, so both numbers and rings line up
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.height(androidx.compose.foundation.layout.IntrinsicSize.Min)) {
        ScoreTile("Fitness", s.scope["fitness"], s.horizon["fitness"], s.fitness, Tint.BLUE, Modifier.weight(1f)) { onOpen("fitness") }
        ScoreTile("Healthy habits", s.scope["health"], s.horizon["health"], s.health, Tint.PURPLE, Modifier.weight(1f)) { onOpen("health") }
    }
}

@Composable
private fun ScoreTile(title: String, scope: String?, horizon: String?, sc: com.bennybar.runnersidekick.data.remote.Score?, tint: Tint,
                      modifier: Modifier, onOpen: () -> Unit) {
    val v = sc?.score
    val sub = MaterialTheme.colorScheme.onSurfaceVariant
    Tile(modifier.fillMaxHeight().semantics(mergeDescendants = true) { contentDescription = "$title score ${v ?: "not available"} out of 100" },
        tint = tint, onClick = onOpen, spacing = 6.dp) {
        Text(title, style = MaterialTheme.typography.titleSmall)
        // The time it looks at, so it's clear why Health, Fitness and readiness move differently
        horizon?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = sub) }
        // What the number covers, so Health isn't read as a medical verdict
        Text(scope?.substringBefore(",") ?: "", style = MaterialTheme.typography.labelSmall, color = sub, minLines = 2, maxLines = 2)
        Row(verticalAlignment = Alignment.CenterVertically) {
            // The score as a ring
            val track = tint.hue.copy(alpha = 0.18f)
            val arc = tint.hue
            androidx.compose.foundation.Canvas(Modifier.size(44.dp)) {
                val w = 6.dp.toPx()
                val inset = androidx.compose.ui.geometry.Size(size.width - w, size.height - w)
                val tl = androidx.compose.ui.geometry.Offset(w / 2, w / 2)
                drawArc(track, 0f, 360f, false, tl, inset, style = Stroke(w))
                drawArc(arc, -90f, 360f * ((v ?: 0) / 100f).coerceIn(0f, 1f), false, tl, inset, style = Stroke(w, cap = StrokeCap.Round))
            }
            Spacer(Modifier.width(10.dp))
            Column {
                Text(v?.toString() ?: "—", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                Text(sc?.label ?: "Not enough data", style = MaterialTheme.typography.labelMedium, color = sub)
            }
        }
        Spacer(Modifier.weight(1f))
        val t = sc?.trend
        // Completeness is shown on its own, never hidden behind the trend
        Text(listOfNotNull(
            when {
                t != null && t.delta > 0 -> "↑ ${t.delta} in 4 weeks"
                // A lower Fitness number comes from Garmin's VO2 estimate: labelled as such, not as lost fitness
                t != null && t.delta < 0 -> "↓ ${-t.delta} in 4 weeks" + if (t.note != null) " · estimate" else ""
                t != null -> "Same as 4 weeks ago"
                else -> null
            },
            if (sc?.status == "partial") "partial" else null,
            if (sc?.stale == true) "stale" else null,
        ).joinToString(" · ").ifEmpty { if (sc?.status == "unavailable") "Tap for what's needed" else "Tap for details" },
            style = MaterialTheme.typography.labelMedium)
        sc?.progress?.takeIf { it.verdict != "insufficient" }?.let { p ->
            Text("Progress: ${p.verdict}", style = MaterialTheme.typography.labelMedium, color = sub)
        }
    }
}

@Composable
private fun ScorePage(title: String, tint: Tint, scope: String?, sc: com.bennybar.runnersidekick.data.remote.Score, basis: String?, onBack: () -> Unit) {
    var how by remember { mutableStateOf(false) }
    val cs = MaterialTheme.colorScheme
    DetailPage(title, onBack) {
        Column(Modifier.padding(start = 12.dp, end = 12.dp, top = 12.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            BigValue(sc.score?.toString() ?: "—", "/100", style = MaterialTheme.typography.displayMedium.copy(fontWeight = FontWeight.Bold))
            Text(listOfNotNull(sc.label, sc.trend?.let { t -> (if (t.delta == 0) "same as 4 weeks ago" else "%+d in 4 weeks".format(t.delta)) +
                    (t.detail?.let { " ($it)" } ?: "") }, if (sc.stale) "based on an old VO₂ max" else null)
                .joinToString(" · "), style = MaterialTheme.typography.titleMedium)
            scope?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant) }
            sc.trend?.note?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant) }
            sc.detail?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        }
        Group(title = "What goes into it", tint = tint) {
            sc.components.filter { !it.context }.forEach { c ->
                // "How it's calculated" adds each part's rule and its share of the score under its reading
                row(c.title, supporting = (c.say ?: c.value ?: c.note ?: "") +
                    if (how) "\n" + listOfNotNull(c.note, if (c.weightPct > 0) "${c.weightPct}% of the score" else null).joinToString(" · ") else "",
                    trailing = { VerdictChip(c.verdict) })
            }
        }
        OutlinedButton(onClick = { how = !how }, modifier = Modifier.height(48.dp)) { Text(if (how) "Hide how it's calculated" else "How it's calculated") }
        sc.progress?.let { p ->
            // Is it improving? Separate signals from different data, with how much they agree
            Group(title = "Progress · " + when (p.verdict) { "insufficient" -> "not enough evidence yet"; else -> p.verdict } +
                    (p.agreement?.let { " · $it agree" } ?: p.confidence?.let { " · $it confidence" } ?: "")) {
                p.summary?.let { custom { Text(it, style = MaterialTheme.typography.bodyMedium) } }
                p.signals.forEach { g -> row(g.title, supporting = g.say + if (how) "\n" + (g.note ?: "") else "", trailing = {
                    // Garmin's VO2 max is a device estimate: a dip is an estimate trend, not a decline
                    val dip = g.id == "vo2" && g.direction == "declining"
                    VerdictChip(if (dip) "ok" else when (g.direction) { "improving" -> "good"; "stable" -> "ok"; "declining" -> "low"; else -> null },
                        label = if (dip) "Estimate dipped" else when (g.direction) { "improving" -> "Improving"; "stable" -> "Stable"; "declining" -> "Declining"; else -> null })
                }) }
            }
        }
        sc.components.filter { it.context }.takeIf { it.isNotEmpty() }?.let { ctx ->
            Group(title = "Context · not counted") {
                ctx.forEach { c -> row(c.title, supporting = c.say ?: c.note, trailing = { VerdictChip(c.verdict) }) }
            }
        }
        if (sc.improve.isNotEmpty()) Group(title = "Potential score changes") {
            sc.improve.forEach { x -> row(x.part, supporting = x.text + (x.horizon?.let { " · $it" } ?: ""), trailing = {
                TagChip("+${x.gain}", container = Tint.GREEN.hue.copy(alpha = 0.22f), content = ink(Tint.GREEN))
            }) }
        }
        val notes = listOfNotNull(
            if (sc.improve.isNotEmpty()) "What the score would show if that part reached its target; not a prediction of how much effort it takes." else null,
            if (sc.missing.isNotEmpty() && sc.score != null) "Partial: ${sc.missing.joinToString(", ").lowercase()} not available yet, so the score uses the other parts." else null,
            basis)
        notes.forEach { Text(it, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp)) }
    }
}

/** Our own training readiness out of 100, in the green tile: the number, what it means and what holds it back.
 *  Tap for the breakdown. */
@Composable
private fun ReadinessCard(s: com.bennybar.runnersidekick.data.remote.Score, unwell: Boolean, pending: Boolean, onUnwell: () -> Unit, onOpen: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Tile(Modifier.semantics(mergeDescendants = true) { contentDescription = "Training readiness ${s.score ?: "not available"}. ${s.headline ?: s.label ?: ""}" },
        tint = Tint.GREEN, onClick = onOpen, spacing = 10.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Readiness", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
            Text("Tap for details", style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant)
        }
        Row(verticalAlignment = Alignment.Bottom) {
            BigValue(s.score?.toString() ?: "—", "/100", style = MaterialTheme.typography.displayMedium.copy(fontWeight = FontWeight.Bold))
            Spacer(Modifier.weight(1f))
            Text(s.label ?: "Not known yet", style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.End,
                modifier = Modifier.padding(start = 8.dp, bottom = 6.dp))
        }
        s.score?.let { ProgressBar(it / 100f, Brush.horizontalGradient(listOf(Tint.GREEN.hue, Tint.GREEN.hue))) }
        s.headline?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
        // What decided it: the reason for "easy only" when there is one, else the weakest part
        (s.holdReason?.let { (if (s.allows == "rest") "Rest: " else "Easy only: ") + it }
            ?: s.heldBackBy?.let { "Held back by ${it.lowercase()}" })?.let {
            Text(it, style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
        }
        // Context the watch can't see; one tap for the day, tap again to undo. Never asked for.
        Surface(onClick = onUnwell, shape = CircleShape, color = if (unwell) cs.primary else cs.surface.copy(alpha = 0.8f),
            contentColor = if (unwell) cs.onPrimary else cs.onSurface) {
            Box(Modifier.heightIn(min = 40.dp).padding(horizontal = 16.dp), contentAlignment = Alignment.Center) {
                Text(if (unwell) "Not feeling well today · undo" else "Not feeling well?", style = MaterialTheme.typography.labelLarge)
            }
        }
        if (pending) Text("Saved on your phone; the score updates once it syncs.", style = MaterialTheme.typography.labelMedium,
            color = cs.onSurfaceVariant)
    }
}

@Composable
private fun ReadinessPage(s: com.bennybar.runnersidekick.data.remote.Score, changes: List<String>, onBack: () -> Unit, onBriefing: () -> Unit) {
    DetailPage("Training readiness", onBack) {
        PageHead(s.score?.toString() ?: "—", "/100" + (s.label?.let { " · $it" } ?: ""), s.headline)
        Group(title = "What goes into it", tint = Tint.GREEN) {
            s.components.forEach { c -> row(c.title, supporting = c.say ?: c.value, trailing = { VerdictChip(c.verdict) }) }
        }
        // Garmin's own number, side by side: it weighs its recovery timer much more heavily than ours does
        s.garmin?.let { g ->
            Group(title = "Garmin's training readiness") {
                row("${g.score}" + (g.level?.let { " · $it" } ?: ""), supporting = g.recoveryHours?.let {
                    if (it > 0) "Recovery timer: about $it h left" + if (it >= 24) " · nothing harder than easy until it's under a day" else ""
                    else "Recovery timer: done" } ?: "Calculated by Garmin")
            }
        }
        if (changes.isNotEmpty()) Group(title = "Since yesterday") { changes.forEach { c -> row(c) } }
        OutlinedButton(onClick = onBriefing, modifier = Modifier.fillMaxWidth().height(48.dp)) { Text("All readings and Garmin scores") }
        Text("Calculated from your own data, not Garmin's. A guide, not medical advice.", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp))
    }
}

/** The next run in numbers: kind, distance, heart-rate cap, pace and time as chips, with the reason in one line. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun NextRunCard(n: com.bennybar.runnersidekick.data.remote.NextRun, units: Units) {
    val cs = MaterialTheme.colorScheme
    val dist = n.distanceKm?.let { if (units == Units.IMPERIAL) "%.1f mi".format(it / 1.609344) else "%.1f km".format(it) }
    val orange = Tint.ORANGE.hue.copy(alpha = 0.30f)
    Tile(tint = Tint.ORANGE, spacing = 10.dp) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Next run", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
            if (n.optional) TagChip("Optional")
            TagChip(n.dayLabel, container = orange, content = ink(Tint.ORANGE))
        }
        Text(n.title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        // The pace in the runner's units (the backend's text is per km)
        val pace = n.paceSPerKm?.let { p -> if (n.paceWay == "around") "around ${Format.pace(p, units)}" else "about ${Format.pace(p, units)} or slower" } ?: n.pace
        val chips = listOfNotNull(dist, n.hr?.text, pace, n.minutes?.let { "about $it min" })
        if (chips.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            chips.forEach { TagChip(it) }
        }
        n.caution?.let {
            Surface(shape = RoundedCornerShape(16.dp), color = cs.surface.copy(alpha = 0.75f)) {
                Row(Modifier.padding(horizontal = 12.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.WarningAmber, null, Modifier.size(18.dp), tint = ink(Tint.ORANGE))
                    Spacer(Modifier.width(8.dp))
                    Text(it, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
        if (n.why.isNotEmpty()) Text(n.why.joinToString(" · "), style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
    }
}

/** The latest run as one tile: when, how long, and distance at pace. */
@Composable
private fun LastRunCard(run: com.bennybar.runnersidekick.data.remote.RecentRun, units: Units, onOpen: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val pace = Format.pace(if (run.distanceM != null && run.movingS != null && run.distanceM > 0) run.movingS / (run.distanceM / 1000) else null, units)
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionLabel("Latest run")
        Tile(onClick = onOpen) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                com.bennybar.runnersidekick.ui.components.ShapeBadge(Icons.AutoMirrored.Outlined.DirectionsRun, MaterialShapes.Cookie9Sided,
                    Modifier.size(40.dp), container = Tint.ORANGE.hue.copy(alpha = 0.22f), content = ink(Tint.ORANGE), iconSize = 22.dp)
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text("${Format.shortDate(run.localDate)} · ${Format.duration(run.movingS)}", style = MaterialTheme.typography.labelLarge,
                        color = cs.onSurfaceVariant)
                    Text("${Format.distance(run.distanceM, units)} at $pace", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                }
                run.avgHr?.let { TagChip("${it.roundToInt()} bpm", container = Tint.PINK.hue.copy(alpha = 0.16f)) }
            }
        }
    }
}


/** The race week at a glance: one dot per day (done, missed, today, planned, rest) and the week's minutes. Tap for the
 *  sessions. */
@Composable
private fun RaceWeekStrip(race: com.bennybar.runnersidekick.data.remote.RaceStatus, w: com.bennybar.runnersidekick.data.remote.RaceWeek,
                          onOpen: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Tile(Modifier.semantics(mergeDescendants = true) { contentDescription = "This week toward ${race.title ?: race.headline}: ${w.doneMinutes} minutes done. Tap for the sessions." },
        tint = Tint.AMBER, onClick = onOpen, spacing = 10.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("This week · ${w.phase.replace('_', ' ')}", style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
                Text(race.title ?: race.headline, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }
            TagChip(daysToGo(race.daysToGo))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            w.sessions.forEach { s ->
                val day = LocalDate.parse(s.date).dayOfWeek.name.take(1)
                val done = s.status in setOf("done", "moved", "extra")
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Box(Modifier.size(32.dp).then(
                        when {
                            done -> Modifier.background(cs.primary, CircleShape)
                            s.status == "today" -> Modifier.border(2.dp, cs.primary, CircleShape)
                            s.status == "missed" -> Modifier.background(Tint.PINK.hue.copy(alpha = 0.18f), CircleShape)
                            s.kind == "rest" -> Modifier
                            else -> Modifier.background(cs.surface.copy(alpha = 0.75f), CircleShape)
                        }), contentAlignment = Alignment.Center) {
                        when {
                            done -> Icon(Icons.Outlined.Check, null, tint = cs.onPrimary, modifier = Modifier.size(18.dp))
                            s.status == "missed" -> Icon(Icons.Outlined.Close, null, tint = ink(Tint.PINK), modifier = Modifier.size(16.dp))
                            s.kind == "rest" -> Box(Modifier.size(6.dp).background(cs.outlineVariant, CircleShape))
                            s.kind == "race" -> Icon(Icons.Outlined.EmojiEvents, null, tint = ink(Tint.AMBER), modifier = Modifier.size(18.dp))
                            else -> Unit
                        }
                    }
                    Text(day, style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
                }
            }
        }
        w.targetMinutes?.takeIf { it > 0 }?.let { t ->
            ProgressBar(w.doneMinutes.toFloat() / t, Brush.linearGradient(listOf(Tint.AMBER.hue, Tint.AMBER.hue)))
            Text("${w.doneMinutes} of $t min this week", style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
        }
    }
}

/** This week's focus as one tile with its progress. Tap for the details, or to choose one. */
@Composable
private fun FocusLine(state: com.bennybar.runnersidekick.data.remote.FocusState, onOpen: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val cur = state.current
    Tile(tint = Tint.AMBER, onClick = onOpen) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("This week's focus", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
            cur?.let { FocusStatusChip(it.status) }
        }
        Text(cur?.title ?: "Choose one", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        cur?.summary?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant, maxLines = 2) }
    }
}

/** The focus's status as a chip; "Done" is filled. */
@Composable
internal fun FocusStatusChip(status: String?) {
    val cs = MaterialTheme.colorScheme
    if (status == "achieved") TagChip(statusLabel(status), container = cs.primary, content = cs.onPrimary) else TagChip(statusLabel(status))
}

/** Last night with the Samsung watch: how much was measured, sleeping heart rate, skin temperature and blood oxygen,
 *  each against your own previous nights. Context next to the briefing; none of it feeds the suggestion. */
@Composable
private fun LastNight(n: com.bennybar.runnersidekick.data.remote.Overnight) {
    val cs = MaterialTheme.colorScheme
    val learning = "your usual comes after 5 nights"
    val lines = listOfNotNull(
        n.sleepHr?.let { h ->
            "Sleeping heart rate" to "${h.low?.roundToInt() ?: h.avg.roundToInt()} bpm" + (h.delta?.let { d ->
                if (kotlin.math.abs(d) < 1) ", as usual" else ", ${kotlin.math.abs(d).roundToInt()} ${if (d > 0) "above" else "below"} your usual"
            } ?: " · $learning")
        },
        n.skinTemp?.let { s ->
            "Skin temperature" to (s.delta?.let { d -> if (kotlin.math.abs(d) < 0.1) "as usual" else "%+.1f °C vs your usual".format(d) }
                ?: "%.1f °C · $learning".format(s.value))
        },
        n.spo2?.let { o ->
            "Blood oxygen" to "${o.avg.roundToInt()}%" + (o.min?.let { " (lowest ${it.roundToInt()}%)" } ?: "") +
                (o.usual?.let { u -> " · usual ${u[0].roundToInt()}–${u[1].roundToInt()}%" } ?: "")
        },
    )
    val covered = n.asleepS?.takeIf { it > 0 }?.let { (n.measuredS / it).coerceAtMost(1.0) }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionLabel("Last night · Samsung")
        Tile(tint = Tint.INDIGO, spacing = 10.dp) {
            lines.forEach { (label, value) ->
                Row(Modifier.semantics(mergeDescendants = true) {}) {
                    Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
                    Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.End,
                        modifier = Modifier.weight(1f).padding(start = 8.dp))
                }
            }
            Text(
                (covered?.let { c -> if (c >= 0.9) "Measured through the night" else "Measured ${Format.duration(n.measuredS)} of ${Format.duration(n.asleepS)} asleep, so read it loosely" }
                    ?: "Measured ${Format.duration(n.measuredS)}") +
                    ". From your Samsung watch; context only, not part of the suggestion. Skin temperature isn't body temperature.",
                style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
        }
    }
}

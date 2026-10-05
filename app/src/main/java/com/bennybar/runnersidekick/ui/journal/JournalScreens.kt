package com.bennybar.runnersidekick.ui.journal

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.ui.input.nestedscroll.nestedScroll
import com.bennybar.runnersidekick.data.remote.InsightsReport
import com.bennybar.runnersidekick.data.remote.WeeklyReport
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.insights.InsightCard
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.outlined.EditNote
import androidx.compose.material.icons.outlined.MenuBook
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.Badge
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.bennybar.runnersidekick.data.remote.Finding
import com.bennybar.runnersidekick.data.remote.MorningReport
import com.bennybar.runnersidekick.data.remote.PostRunReport
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.JournalVm
import com.bennybar.runnersidekick.ui.ReportVm
import com.bennybar.runnersidekick.ui.components.DemoBadge
import com.bennybar.runnersidekick.ui.components.EmptyState
import com.bennybar.runnersidekick.ui.components.EvidenceSheet
import com.bennybar.runnersidekick.ui.components.SectionHeader
import com.bennybar.runnersidekick.ui.factory
import kotlinx.serialization.json.Json

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun JournalScreen(onOpenReport: (Long) -> Unit, vm: JournalVm = viewModel(factory = factory(::JournalVm))) {
    val reports by vm.reports.collectAsStateWithLifecycle()
    val checkins by vm.checkins.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        topBar = { LargeTopAppBar(title = { Text("Journal") }, scrollBehavior = scroll) },
    ) { padding ->
        com.bennybar.runnersidekick.ui.components.RefreshBox(busy, vm::refresh, Modifier.padding(padding).fillMaxSize()) {
            LazyColumn(contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 24.dp + com.bennybar.runnersidekick.ui.components.LocalNavBarPadding.current), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                // The app no longer asks for check-ins; the tab only stays for people who logged some earlier
                if (checkins.isNotEmpty()) item {
                    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                        listOf("Reports", "Check-ins").forEachIndexed { i, l ->
                            SegmentedButton(tab == i, { tab = i }, SegmentedButtonDefaults.itemShape(i, 2), icon = {}) { Text(l) }
                        }
                    }
                }
                if (tab == 0 || checkins.isEmpty()) {
                    if (reports.isEmpty()) item { EmptyState(Icons.Outlined.MenuBook, "No reports yet", "Reports appear here after your first sync.") }
                    reports.groupBy { it.localDate.take(7) }.forEach { (month, rs) ->
                        item(key = "m$month") {
                            Group(title = java.time.YearMonth.parse(month).format(java.time.format.DateTimeFormatter.ofPattern("MMMM yyyy"))) {
                                rs.forEach { r ->
                                    val (icon, shape, kind) = when (r.type) {
                                        "morning" -> Triple(Icons.Outlined.WbSunny, MaterialShapes.Sunny, "Morning briefing")
                                        "post_run" -> Triple(Icons.AutoMirrored.Outlined.DirectionsRun, MaterialShapes.Cookie9Sided, "Run report")
                                        "weekly" -> Triple(Icons.Outlined.CalendarMonth, MaterialShapes.Cookie12Sided, "Weekly review")
                                        else -> Triple(Icons.Outlined.Insights, MaterialShapes.Flower, "Insights update")
                                    }
                                    row(r.title ?: kind, overline = "$kind · ${Format.shortDate(r.localDate)}" + if (r.revision > 1) " · revised" else "",
                                        icon = icon, iconShape = shape, onClick = { onOpenReport(r.id) })
                                }
                            }
                        }
                    }
                } else {
                    item {
                        Group {
                            checkins.forEach { c ->
                                val flags = listOfNotNull("Pain".takeIf { c.pain }, "Unwell".takeIf { c.illness }, "Not uploaded yet".takeIf { c.pendingSync })
                                row("Energy ${c.energy ?: "–"} · Soreness ${c.soreness ?: "–"} · Recovery ${c.recovery ?: "–"}",
                                    overline = Format.shortDate(c.localDate),
                                    supporting = listOfNotNull(flags.joinToString(" · ").ifEmpty { null }, c.notes).joinToString("\n").ifEmpty { null },
                                    icon = Icons.Outlined.EditNote, iconShape = MaterialShapes.Cookie4Sided)
                            }
                        }
                    }
                }
            }
        }
    }
}

private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

/** Shows a report exactly as generated at the time (its own revision), not recomputed with today's baselines. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReportScreen(
    id: Long, onBack: () -> Unit, onOpenRun: (String) -> Unit, onOpenReport: (Long) -> Unit,
    vm: ReportVm = viewModel(key = "r$id", factory = factory { ReportVm(it, id) }),
) {
    val entity by vm.report.collectAsStateWithLifecycle()
    val revisions by vm.revisions.collectAsStateWithLifecycle()
    var evidence by remember { mutableStateOf<Finding?>(null) }
    val body = entity?.json
    val morning = remember(body) { if (entity?.type == "morning" && body != null) runCatching { json.decodeFromString<MorningReport>(body) }.getOrNull() else null }
    val run = remember(body) { if (entity?.type == "post_run" && body != null) runCatching { json.decodeFromString<PostRunReport>(body) }.getOrNull() else null }
    val ins = remember(body) { if (entity?.type == "insights" && body != null) runCatching { json.decodeFromString<InsightsReport>(body) }.getOrNull() else null }
    val wk = remember(body) { if (entity?.type == "weekly" && body != null) runCatching { json.decodeFromString<WeeklyReport>(body) }.getOrNull() else null }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text(entity?.let { Format.shortDate(it.localDate) } ?: "Report") },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } },
            actions = { if (morning?.synthetic == true || run?.synthetic == true) DemoBadge() },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            ins?.let { r ->
                item { Text("Insights as they stood on ${Format.shortDate(r.localDate)}", style = MaterialTheme.typography.titleMedium) }
                items(r.insights, key = { it.id }) { i -> InsightCard(i, emphasised = i.verdict == "pattern", onMethod = {}) }
            }
            wk?.let { w ->
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer), shape = MaterialTheme.shapes.extraLarge) {
                        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("Week of ${Format.shortDate(w.weekStart)} – ${Format.shortDate(w.weekEnd)}", style = MaterialTheme.typography.labelLarge,
                                color = MaterialTheme.colorScheme.onPrimaryContainer)
                            Text(w.headline, style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                            Text("Next week: ${w.nextWeekFocus.text}", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onPrimaryContainer)
                        }
                    }
                }
                items(w.findings, key = { it.id }) { f -> FindingCard(f) { evidence = f } }
                item { Meta("Revision ${w.revision} · generated ${w.generatedAt} · focus rule ${w.nextWeekFocus.rule}") }
            }
            if (morning == null && run == null && ins == null && wk == null) {
                item { EmptyState(Icons.Outlined.MenuBook, "Report not cached", "Connect to the backend once to save this report for offline reading.") }
            }
            morning?.let { m ->
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer), shape = MaterialTheme.shapes.extraLarge) {
                        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(m.headline, style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                            Text(m.recommendation.suggestion, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onPrimaryContainer)
                            Text(m.recommendation.reason, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
                        }
                    }
                }
                item { SectionHeader("Findings") }
                items(m.findings, key = { it.id }) { f -> FindingCard(f) { evidence = f } }
                item { Meta("Revision ${m.revision} · generated ${m.generatedAt} · data through ${m.dataCutoff ?: "unknown"} · ${m.algorithmVersion.values.joinToString()}") }
            }
            run?.let { r ->
                item {
                    Text(r.activity.name ?: "Run", style = MaterialTheme.typography.headlineSmall)
                    Text(r.nextFocus, style = MaterialTheme.typography.bodyLarge)
                }
                items(r.findings, key = { it.id }) { f -> FindingCard(f) { evidence = f } }
                item { OutlinedButton(onClick = { onOpenRun(r.activity.sourceId) }) { Text("Open run details") } }
                item { Meta("Revision ${r.revision} · generated ${r.generatedAt}") }
            }
            if (revisions.size > 1) item {
                Group(title = "Versions") {
                    revisions.forEach { v ->
                        row("Revision ${v.revision}" + if (v.id == id) " · showing" else "",
                            supporting = "Generated ${v.generatedAt.replace('T', ' ').removeSuffix("Z")} UTC",
                            onClick = if (v.id == id) null else ({ vm.open(v) { onOpenReport(v.id) } }))
                    }
                }
            }
        }
    }
    evidence?.let { EvidenceSheet(it) { evidence = null } }
}

@Composable
private fun FindingCard(f: Finding, onWhy: () -> Unit) {
    OutlinedCard(shape = MaterialTheme.shapes.large, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp).fillMaxWidth()) {
            Text(f.title, style = MaterialTheme.typography.titleMedium)
            Text(f.statement, style = MaterialTheme.typography.bodyMedium)
            TextButton(onClick = onWhy, contentPadding = PaddingValues(0.dp)) { Text("Show why") }
        }
    }
}

@Composable
private fun Meta(text: String) =
    Text(text, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)


/** One day's morning briefing, opened from a trend chart. Rendered from the report for that date. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DayScreen(date: String, onBack: () -> Unit, vm: com.bennybar.runnersidekick.ui.DayVm = viewModel(key = "d$date", factory = factory { com.bennybar.runnersidekick.ui.DayVm(it, date) })) {
    val day by vm.day.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var evidence by remember { mutableStateOf<Finding?>(null) }
    Scaffold(topBar = {
        TopAppBar(title = { Text(Format.longDate(date)) },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } },
            actions = { if (day?.value?.synthetic == true) DemoBadge() })
    }) { padding ->
        val m = day?.value
        LazyColumn(Modifier.padding(padding), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (m == null) {
                item { EmptyState(Icons.Outlined.MenuBook, if (busy) "Loading day" else "Day not cached", if (busy) "Fetching…" else "Connect to the backend to load this day.") }
            } else {
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer), shape = MaterialTheme.shapes.extraLarge) {
                        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(m.headline, style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                            Text(m.recommendation.suggestion, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onPrimaryContainer)
                        }
                    }
                }
                items(m.findings, key = { it.id }) { f -> FindingCard(f) { evidence = f } }
                m.checkin?.let { c -> item { Meta("Check-in: energy ${c.energy ?: "–"}, soreness ${c.soreness ?: "–"}, recovery ${c.recovery ?: "–"}") } }
                item { Meta("Report revision ${m.revision} · generated ${m.generatedAt}") }
            }
        }
    }
    evidence?.let { EvidenceSheet(it) { evidence = null } }
}

package com.bennybar.runnersidekick.ui.journal

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.EditNote
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material.icons.outlined.MenuBook
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.bennybar.runnersidekick.data.remote.Finding
import com.bennybar.runnersidekick.data.remote.InsightsReport
import com.bennybar.runnersidekick.data.remote.MorningReport
import com.bennybar.runnersidekick.data.remote.PostRunReport
import com.bennybar.runnersidekick.data.remote.WeeklyReport
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.JournalVm
import com.bennybar.runnersidekick.ui.ReportVm
import com.bennybar.runnersidekick.ui.components.DemoBadge
import com.bennybar.runnersidekick.ui.components.EmptyState
import com.bennybar.runnersidekick.ui.components.EvidenceSheet
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.SectionLabel
import com.bennybar.runnersidekick.ui.components.Tile
import com.bennybar.runnersidekick.ui.factory
import com.bennybar.runnersidekick.ui.insights.InsightCard
import com.bennybar.runnersidekick.ui.theme.Tint
import com.bennybar.runnersidekick.ui.theme.ink
import kotlinx.serialization.json.Json

/** What a report of [type] is called. */
private fun kindOf(type: String?) = when (type) {
    "morning" -> "Morning briefing"
    "post_run" -> "Run report"
    "weekly" -> "Weekly review"
    else -> "Insights update"
}

/** A page's top: back arrow, title, and anything on the right (the demo badge). */
@Composable
private fun PageTop(title: String, onBack: () -> Unit, demo: Boolean = false) {
    Row(Modifier.fillMaxWidth().padding(start = 4.dp, end = 16.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back") }
        Text(title, style = MaterialTheme.typography.titleLarge, maxLines = 1, modifier = Modifier.weight(1f).semantics { heading() })
        if (demo) DemoBadge()
    }
}

private val PageList = PaddingValues(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 32.dp)

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun JournalScreen(onOpenReport: (Long) -> Unit, onBack: () -> Unit, vm: JournalVm = viewModel(factory = factory(::JournalVm))) {
    val reports by vm.reports.collectAsStateWithLifecycle()
    val checkins by vm.checkins.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    Column(Modifier.fillMaxSize().systemBarsPadding()) {
        PageTop("Reports", onBack)
        com.bennybar.runnersidekick.ui.components.RefreshBox(busy, vm::refresh, Modifier.fillMaxSize()) {
            LazyColumn(contentPadding = PageList, verticalArrangement = Arrangement.spacedBy(10.dp)) {
                // The app no longer asks for check-ins; the tab only stays for people who logged some earlier
                if (checkins.isNotEmpty()) item {
                    com.bennybar.runnersidekick.ui.components.ChoiceGroup(listOf("Reports", "Check-ins"), tab, { tab = it })
                }
                if (tab == 0 || checkins.isEmpty()) {
                    if (reports.isEmpty()) item { EmptyState(Icons.Outlined.MenuBook, "No reports yet", "Reports appear here after your first sync.") }
                    reports.groupBy { it.localDate.take(7) }.forEach { (month, rs) ->
                        item(key = "m$month") {
                            Group(title = java.time.YearMonth.parse(month).format(java.time.format.DateTimeFormatter.ofPattern("MMMM yyyy"))) {
                                rs.forEach { r ->
                                    val (icon, shape) = when (r.type) {
                                        "morning" -> Icons.Outlined.WbSunny to MaterialShapes.Sunny
                                        "post_run" -> Icons.AutoMirrored.Outlined.DirectionsRun to MaterialShapes.Cookie9Sided
                                        "weekly" -> Icons.Outlined.CalendarMonth to MaterialShapes.Cookie12Sided
                                        else -> Icons.Outlined.Insights to MaterialShapes.Flower
                                    }
                                    val kind = kindOf(r.type)
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
    Column(Modifier.fillMaxSize().systemBarsPadding()) {
        PageTop(entity?.let { "${kindOf(it.type)} · ${Format.shortDate(it.localDate)}" } ?: "Report", onBack,
            demo = morning?.synthetic == true || run?.synthetic == true)
        LazyColumn(contentPadding = PageList, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            ins?.let { r ->
                item { Text("Insights as they stood on ${Format.shortDate(r.localDate)}", style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(horizontal = 8.dp)) }
                items(r.insights, key = { it.id }) { i -> InsightCard(i, emphasised = i.verdict == "pattern", onMethod = {}) }
            }
            wk?.let { w ->
                item {
                    Headline(w.headline, label = "Week of ${Format.shortDate(w.weekStart)} – ${Format.shortDate(w.weekEnd)}",
                        lines = listOf("Next week: ${w.nextWeekFocus.text}"))
                }
                if (w.findings.isNotEmpty()) item { SectionLabel("Findings") }
                items(w.findings, key = { it.id }) { f -> FindingTile(f) { evidence = f } }
                item { Meta("Revision ${w.revision} · generated ${w.generatedAt} · focus rule ${w.nextWeekFocus.rule}") }
            }
            if (morning == null && run == null && ins == null && wk == null) {
                item { EmptyState(Icons.Outlined.MenuBook, "Report not cached", "Connect to the backend once to save this report for offline reading.") }
            }
            morning?.let { m ->
                item { Headline(m.headline, lines = listOf(m.recommendation.suggestion, m.recommendation.reason)) }
                item { SectionLabel("Findings") }
                items(m.findings, key = { it.id }) { f -> FindingTile(f) { evidence = f } }
                item { Meta("Revision ${m.revision} · generated ${m.generatedAt} · data through ${m.dataCutoff ?: "unknown"} · ${m.algorithmVersion.values.joinToString()}") }
            }
            run?.let { r ->
                item { Headline(r.activity.name ?: "Run", lines = listOf(r.nextFocus)) }
                if (r.findings.isNotEmpty()) item { SectionLabel("Findings") }
                items(r.findings, key = { it.id }) { f -> FindingTile(f) { evidence = f } }
                item { FilledTonalButton(onClick = { onOpenRun(r.activity.sourceId) }, modifier = Modifier.fillMaxWidth()) { Text("Open run details") } }
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

/** The report's headline tile: an optional small label, the headline, then its sentences. */
@Composable
private fun Headline(headline: String, label: String? = null, lines: List<String>) {
    Tile(tint = Tint.PURPLE) {
        label?.let { Text(it, style = MaterialTheme.typography.labelLarge, color = ink(Tint.PURPLE)) }
        Text(headline, style = MaterialTheme.typography.headlineSmall)
        lines.forEach { Text(it, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

@Composable
private fun FindingTile(f: Finding, onWhy: () -> Unit) {
    Tile(spacing = 4.dp, contentPadding = PaddingValues(start = 18.dp, end = 18.dp, top = 16.dp, bottom = 4.dp)) {
        Text(f.title, style = MaterialTheme.typography.titleMedium)
        Text(f.statement, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        TextButton(onClick = onWhy, contentPadding = PaddingValues(0.dp)) { Text("Show why") }
    }
}

@Composable
private fun Meta(text: String) =
    Text(text, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp))


/** One day's morning briefing, opened from a trend chart. Rendered from the report for that date. */
@Composable
fun DayScreen(date: String, onBack: () -> Unit, vm: com.bennybar.runnersidekick.ui.DayVm = viewModel(key = "d$date", factory = factory { com.bennybar.runnersidekick.ui.DayVm(it, date) })) {
    val day by vm.day.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var evidence by remember { mutableStateOf<Finding?>(null) }
    Column(Modifier.fillMaxSize().systemBarsPadding()) {
        PageTop(Format.longDate(date), onBack, demo = day?.value?.synthetic == true)
        val m = day?.value
        LazyColumn(contentPadding = PageList, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (m == null) {
                item { EmptyState(Icons.Outlined.MenuBook, if (busy) "Loading day" else "Day not cached", if (busy) "Fetching…" else "Connect to the backend to load this day.") }
            } else {
                item { Headline(m.headline, lines = listOf(m.recommendation.suggestion)) }
                if (m.findings.isNotEmpty()) item { SectionLabel("Findings") }
                items(m.findings, key = { it.id }) { f -> FindingTile(f) { evidence = f } }
                m.checkin?.let { c -> item { Meta("Check-in: energy ${c.energy ?: "–"}, soreness ${c.soreness ?: "–"}, recovery ${c.recovery ?: "–"}") } }
                item { Meta("Report revision ${m.revision} · generated ${m.generatedAt}") }
            }
        }
    }
    evidence?.let { EvidenceSheet(it) { evidence = null } }
}

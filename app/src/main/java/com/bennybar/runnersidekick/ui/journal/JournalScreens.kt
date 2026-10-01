package com.bennybar.runnersidekick.ui.journal

import androidx.compose.foundation.clickable
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
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JournalScreen(onOpenReport: (Long) -> Unit, vm: JournalVm = viewModel(factory = factory(::JournalVm))) {
    val reports by vm.reports.collectAsStateWithLifecycle()
    val checkins by vm.checkins.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    Scaffold(topBar = { TopAppBar(title = { Text("Journal") }) }) { padding ->
        Column(Modifier.padding(padding)) {
            PrimaryTabRow(selectedTabIndex = tab) {
                Tab(tab == 0, { tab = 0 }, text = { Text("Reports") })
                Tab(tab == 1, { tab = 1 }, text = { Text("Check-ins") })
            }
            PullToRefreshBox(busy, vm::refresh, Modifier.fillMaxSize()) {
                LazyColumn(contentPadding = PaddingValues(vertical = 8.dp)) {
                    if (tab == 0) {
                        if (reports.isEmpty()) item { EmptyState(Icons.Outlined.MenuBook, "No reports yet", "Reports appear here after your first sync.") }
                        items(reports, key = { it.id }) { r ->
                            ListItem(
                                modifier = Modifier.clickable { onOpenReport(r.id) },
                                leadingContent = {
                                    Icon(if (r.type == "morning") Icons.Outlined.WbSunny else Icons.AutoMirrored.Outlined.DirectionsRun, null,
                                        tint = MaterialTheme.colorScheme.primary)
                                },
                                overlineContent = { Text((if (r.type == "morning") "Morning briefing" else "Run report") + " · " + Format.shortDate(r.localDate)) },
                                headlineContent = { Text(r.title ?: "Report") },
                                trailingContent = {
                                    if (r.revision > 1) Badge(containerColor = MaterialTheme.colorScheme.secondaryContainer,
                                        contentColor = MaterialTheme.colorScheme.onSecondaryContainer) { Text("Revised") }
                                },
                            )
                        }
                    } else {
                        if (checkins.isEmpty()) item { EmptyState(Icons.Outlined.EditNote, "No check-ins yet", "Your daily check-ins from the Today screen appear here.") }
                        items(checkins, key = { it.id }) { c ->
                            ListItem(
                                overlineContent = { Text(Format.shortDate(c.localDate)) },
                                headlineContent = { Text("Energy ${c.energy ?: "–"} · Soreness ${c.soreness ?: "–"} · Recovery ${c.recovery ?: "–"}") },
                                supportingContent = {
                                    val flags = listOfNotNull("Pain".takeIf { c.pain }, "Unwell".takeIf { c.illness }, "Not uploaded yet".takeIf { c.pendingSync })
                                    val text = listOfNotNull(flags.joinToString(" · ").ifEmpty { null }, c.notes).joinToString("\n")
                                    if (text.isNotEmpty()) Text(text)
                                },
                            )
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
fun ReportScreen(id: Long, onBack: () -> Unit, onOpenRun: (String) -> Unit, vm: ReportVm = viewModel(key = "r$id", factory = factory { ReportVm(it, id) })) {
    val entity by vm.report.collectAsStateWithLifecycle()
    var evidence by remember { mutableStateOf<Finding?>(null) }
    val body = entity?.json
    val morning = remember(body) { if (entity?.type == "morning" && body != null) runCatching { json.decodeFromString<MorningReport>(body) }.getOrNull() else null }
    val run = remember(body) { if (entity?.type == "post_run" && body != null) runCatching { json.decodeFromString<PostRunReport>(body) }.getOrNull() else null }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text(entity?.let { Format.shortDate(it.localDate) } ?: "Report") },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } },
            actions = { if (morning?.synthetic == true || run?.synthetic == true) DemoBadge() },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (morning == null && run == null) {
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

package com.bennybar.runnersidekick.ui.activities

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.TrophiesVm
import com.bennybar.runnersidekick.ui.components.DetailPage
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.Tile
import com.bennybar.runnersidekick.ui.theme.Tint
import com.bennybar.runnersidekick.ui.theme.ink
import com.bennybar.runnersidekick.ui.factory

/** Your records: fastest times, longest runs and biggest weeks, heart and fitness bests, steps and streaks. Garmin's
 *  all-time records next to the app's own bests, each with where it comes from, and how it compares with people of your
 *  age and sex where there's a published reference. A record from a run the app has opens that run. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TrophiesScreen(onBack: () -> Unit, onOpenRun: (String) -> Unit, vm: TrophiesVm = viewModel(factory = factory(::TrophiesVm))) {
    val trophies by vm.trophies.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    var open by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf<com.bennybar.runnersidekick.data.remote.Trophy?>(null) }
    val routes by vm.routes.collectAsStateWithLifecycle()
    val units by vm.settings.collectAsStateWithLifecycle()
    var routeOpen by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf<String?>(null) }
    Scaffold(topBar = {
        TopAppBar(title = { Text("Your records") },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } })
    }) { padding ->
        val t = trophies?.value
        LazyColumn(Modifier.padding(padding).fillMaxSize(), contentPadding = PaddingValues(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (t == null) {
                item { Text(error ?: "Loading your records…", style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 16.dp, start = 8.dp)) }
            } else if (t.groups.isEmpty()) {
                item { Text("No records yet. They appear once your runs have synced.", style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 16.dp, start = 8.dp)) }
            }
            t?.groups?.forEach { g ->
                item(key = g.id) {
                    val tint = when (g.id) {
                        "fastest" -> Tint.AMBER
                        "longest" -> Tint.ORANGE
                        else -> Tint.GREEN  // body, steps and streaks
                    }
                    Group(title = g.title, tint = tint) {
                        g.items.forEach { r ->
                            val when_ = r.date?.let { d -> runCatching { Format.shortDate(d) }.getOrDefault(d) }
                            row(r.title,
                                trailing = { Text(r.value, style = MaterialTheme.typography.titleLarge) },
                                supporting = listOfNotNull(
                                    listOfNotNull(when_, r.source.takeIf { it.isNotBlank() }).joinToString(" · ").ifBlank { null },
                                    r.comparison?.headline).joinToString("\n"),
                                onClick = { open = r })
                        }
                    }
                }
            }
            routes?.value?.routes?.takeIf { it.isNotEmpty() }?.let { rs ->
                item(key = "routes") {
                    Group(title = "Your routes") {
                        rs.forEach { rt ->
                            row(routeTitle(rt.name, rt.distanceKm, rt.loop, rt.runs), supporting = rt.progress ?: "Run ${rt.runs} times since ${
                                rt.first?.let { Format.shortDate(it) } ?: "—"}",
                                onClick = { routeOpen = rt.id })
                        }
                    }
                }
            }
            t?.basis?.takeIf { it.isNotBlank() }?.let { b ->
                item { Text(b, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 8.dp)) }
            }
        }
    }
    open?.let { r -> TrophyPage(r, onBack = { open = null }) { id -> open = null; onOpenRun(id) } }
    routeOpen?.let { rid -> routes?.value?.routes?.firstOrNull { it.id == rid }?.let { rt ->
        RoutePage(rt, routes?.value?.basis.orEmpty(), units?.units, current = null, onOpenRun = { routeOpen = null; onOpenRun(it) },
            onNotThis = null, onBack = { routeOpen = null })
    } }
}

/** One record, as a full page: its value and comparison, and how it got there (each improvement, oldest first; a run opens). */
@Composable
private fun TrophyPage(r: com.bennybar.runnersidekick.data.remote.Trophy, onBack: () -> Unit, onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    DetailPage(r.title, onBack) {
        Column(Modifier.padding(horizontal = 12.dp).padding(top = 8.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(r.value, style = MaterialTheme.typography.displayMedium)
            Text(listOfNotNull(r.date?.let { runCatching { Format.longDate(it) }.getOrDefault(it) }, r.source.takeIf { it.isNotBlank() })
                .joinToString(" · "), style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
            r.comparison?.let { c ->
                Text(listOfNotNull(c.headline, c.detail).joinToString("\n"), style = MaterialTheme.typography.bodyMedium)
            }
        }
        if (r.history.size >= 2) Tile(tint = Tint.AMBER) {
            Text("How it got here", style = MaterialTheme.typography.titleSmall)
            // Drawn so better is always up (a faster time is a lower number)
            com.bennybar.runnersidekick.ui.components.Sparkline(r.history.map { if (r.lowerIsBetter) -it.v else it.v },
                Modifier.fillMaxWidth().height(72.dp), color = ink(Tint.AMBER),
                description = "${r.title}: ${r.history.joinToString(", ") { "${it.value} on ${it.date}" }}")
        }
        if (r.history.isNotEmpty()) Group {
            r.history.reversed().forEachIndexed { i, pt ->
                row(pt.value, supporting = listOfNotNull(runCatching { Format.longDate(pt.date) }.getOrDefault(pt.date),
                        when {
                            pt.garmin -> "Garmin's record, before the app's history"
                            i == r.history.size - 1 -> "where the history starts"
                            i == 0 -> "the record now"
                            else -> null
                        }).joinToString(" · "),
                    onClick = pt.sourceId?.let { id -> { onOpenRun(id) } })
            }
        }
        if (r.history.size < 2) Text("No earlier best in the app's history yet: the next run that beats it shows up here.",
            style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp))
    }
}

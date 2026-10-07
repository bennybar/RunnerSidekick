package com.bennybar.runnersidekick.ui.activities

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.DirectionsWalk
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material.icons.outlined.Straighten
import androidx.compose.material.icons.outlined.Route
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialShapes
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
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.factory

/** Your records: fastest times, longest runs and biggest weeks, heart and fitness bests, steps and streaks. Garmin's
 *  all-time records next to the app's own bests, each with where it comes from, and how it compares with people of your
 *  age and sex where there's a published reference. A record from a run the app has opens that run. */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
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
        LazyColumn(Modifier.padding(padding).fillMaxSize(), contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp)) {
            if (t == null) {
                item { Text(error ?: "Loading your records…", style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 16.dp)) }
            } else if (t.groups.isEmpty()) {
                item { Text("No records yet. They appear once your runs have synced.", style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 16.dp)) }
            }
            t?.groups?.forEach { g ->
                item(key = g.id) {
                    val (icon, shape) = when (g.id) {
                        "fastest" -> Icons.Outlined.EmojiEvents to MaterialShapes.Sunny
                        "longest" -> Icons.Outlined.Straighten to MaterialShapes.Cookie9Sided
                        "body" -> Icons.Outlined.FavoriteBorder to MaterialShapes.Flower
                        else -> Icons.AutoMirrored.Outlined.DirectionsWalk to MaterialShapes.Cookie4Sided
                    }
                    Group(title = g.title) {
                        g.items.forEach { r ->
                            val when_ = r.date?.let { d -> runCatching { Format.shortDate(d) }.getOrDefault(d) }
                            row(r.title,
                                trailing = { Text(r.value, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary) },
                                supporting = listOfNotNull(
                                    listOfNotNull(when_, r.source.takeIf { it.isNotBlank() }).joinToString(" · ").ifBlank { null },
                                    r.comparison?.headline).joinToString("\n"),
                                icon = icon, iconShape = shape,
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
                                rt.first?.let { Format.shortDate(it) } ?: "—"}", icon = Icons.Outlined.Route, iconShape = MaterialShapes.Cookie9Sided,
                                onClick = { routeOpen = rt.id })
                        }
                    }
                }
            }
            t?.basis?.takeIf { it.isNotBlank() }?.let { b ->
                item { Text(b, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 4.dp)) }
            }
        }
    }
    open?.let { r -> TrophySheet(r, onDismiss = { open = null }) { id -> open = null; onOpenRun(id) } }
    routeOpen?.let { rid -> routes?.value?.routes?.firstOrNull { it.id == rid }?.let { rt ->
        RouteSheet(rt, routes?.value?.basis.orEmpty(), units?.units, current = null, onOpenRun = { routeOpen = null; onOpenRun(it) },
            onNotThis = null, onDismiss = { routeOpen = null })
    } }
}

/** One record: its value and comparison, and how it got there (each improvement, oldest first; a run opens). */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun TrophySheet(r: com.bennybar.runnersidekick.data.remote.Trophy, onDismiss: () -> Unit, onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    androidx.compose.material3.ModalBottomSheet(onDismissRequest = onDismiss,
        sheetState = androidx.compose.material3.rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        androidx.compose.foundation.layout.Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp)
            .verticalScroll(androidx.compose.foundation.rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(r.title, style = MaterialTheme.typography.headlineSmall)
            Text(r.value, style = MaterialTheme.typography.displaySmall, color = cs.primary)
            Text(listOfNotNull(r.date?.let { runCatching { Format.longDate(it) }.getOrDefault(it) }, r.source.takeIf { it.isNotBlank() })
                .joinToString(" · "), style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
            r.comparison?.let { c ->
                Text(listOfNotNull(c.headline, c.detail).joinToString("\n"), style = MaterialTheme.typography.bodyMedium)
            }
            if (r.history.size >= 2) {
                Text("How it got here", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 6.dp))
                // Drawn so better is always up (a faster time is a lower number)
                com.bennybar.runnersidekick.ui.components.Sparkline(r.history.map { if (r.lowerIsBetter) -it.v else it.v },
                    Modifier.fillMaxWidth().height(72.dp),
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
                style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
        }
    }
}

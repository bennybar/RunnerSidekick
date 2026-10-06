package com.bennybar.runnersidekick.ui.activities

import androidx.compose.foundation.layout.Arrangement
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
                                onClick = r.sourceId?.let { id -> { onOpenRun(id) } })
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
}

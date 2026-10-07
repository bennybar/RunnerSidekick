package com.bennybar.runnersidekick.ui.activities

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.data.local.Units
import com.bennybar.runnersidekick.data.remote.RouteSummary
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.components.Group
import kotlin.math.roundToInt

fun routeTitle(name: String, km: Double, loop: Boolean, runs: Int) = "$name · ${"%.1f".format(km)} km${if (loop) " loop" else ""} · $runs runs"

/** A repeat route: how it has gone (same kind, same conditions, similar heart rate), its runs with their conditions,
 *  how it's recognised and what's kept. [onNotThis]: the run being looked at isn't this route (a correction). */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun RouteSheet(route: RouteSummary, basis: String, units: Units?, current: String?, onOpenRun: (String) -> Unit,
               onNotThis: (() -> Unit)?, onDismiss: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(routeTitle(route.name, route.distanceKm, route.loop, route.runs), style = MaterialTheme.typography.headlineSmall)
            Text(route.progress ?: "Not enough comparable runs yet: progress needs runs of the same kind, in the same conditions, " +
                "at a similar heart rate.", style = MaterialTheme.typography.bodyLarge)
            Group(title = "Its runs") {
                route.rows.reversed().forEach { r ->
                    row("${Format.pace(r.paceSPerKm, units ?: Units.METRIC)} · ${r.avgHr?.roundToInt()?.let { "$it bpm" } ?: "no HR"}",
                        overline = Format.shortDate(r.date) + if (r.sourceId == current) " · this run" else "",
                        supporting = listOfNotNull(if (r.kind == "easy") "easy or steady" else "harder",
                            r.temperatureC?.let { "${it.roundToInt()}°C" + if (r.hot) ", hot and humid" else "" }).joinToString(" · "),
                        onClick = if (r.sourceId == current) null else ({ onOpenRun(r.sourceId) }))
                }
            }
            onNotThis?.let {
                OutlinedButton(onClick = it, modifier = Modifier.fillMaxWidth()) { Text("This run is a different route") }
            }
            Text(basis, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
        }
    }
}

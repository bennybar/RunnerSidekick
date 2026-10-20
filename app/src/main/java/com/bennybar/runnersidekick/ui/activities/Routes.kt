package com.bennybar.runnersidekick.ui.activities

import androidx.compose.foundation.layout.heightIn
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.data.local.Units
import com.bennybar.runnersidekick.data.remote.RouteSummary
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.components.DetailPage
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.Tile
import com.bennybar.runnersidekick.ui.theme.Tint
import com.bennybar.runnersidekick.ui.theme.ink
import kotlin.math.roundToInt

/** The route's shape, drawn from its outline (a unit box, no map): enough to recognise it, or to spot a wrong match. */
@Composable
fun RouteOutline(outline: List<List<Double>>, modifier: Modifier = Modifier) {
    val line = ink(Tint.BLUE)
    val dot = Tint.ORANGE.hue
    androidx.compose.foundation.Canvas(modifier.semantics { contentDescription = "The route's shape" }) {
        val pad = 12.dp.toPx()
        val side = minOf(size.width, size.height) - 2 * pad
        val ox = (size.width - side) / 2
        val oy = (size.height - side) / 2
        fun at(p: List<Double>) = androidx.compose.ui.geometry.Offset(ox + p[0].toFloat() * side, oy + p[1].toFloat() * side)
        val path = androidx.compose.ui.graphics.Path().apply {
            moveTo(at(outline[0]).x, at(outline[0]).y)
            outline.drop(1).forEach { lineTo(at(it).x, at(it).y) }
        }
        drawPath(path, line, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 4.dp.toPx(),
            cap = androidx.compose.ui.graphics.StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round))
        drawCircle(dot, radius = 6.dp.toPx(), center = at(outline[0]))  // where it starts
    }
}

fun routeTitle(name: String, km: Double, loop: Boolean, runs: Int) = "$name · ${"%.1f".format(km)} km${if (loop) " loop" else ""} · $runs runs"

/** A repeat route, as a full page: how it has gone (same kind, same conditions, similar heart rate), its runs with
 *  their conditions, how it's recognised and what's kept. [onNotThis]: the run being looked at isn't this route (a correction). */
@Composable
fun RoutePage(route: RouteSummary, basis: String, units: Units?, current: String?, onOpenRun: (String) -> Unit,
              onNotThis: (() -> Unit)?, onBack: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    DetailPage(route.name, onBack) {
        Tile(tint = Tint.BLUE, spacing = 10.dp) {
            if (route.outline.size >= 2) RouteOutline(route.outline, Modifier.fillMaxWidth().height(160.dp))
            Text(routeTitle(route.name, route.distanceKm, route.loop, route.runs).substringAfter(" · "),
                style = MaterialTheme.typography.titleSmall)
            Text(route.progress ?: "Not enough comparable runs yet: progress needs runs of the same kind, in the same conditions, " +
                "at a similar heart rate.", style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
        }
        Group(title = "Its runs") {
            route.rows.reversed().forEach { r ->
                row("${Format.pace(r.paceSPerKm, units ?: Units.METRIC)} · ${r.avgHr?.roundToInt()?.let { "$it bpm" } ?: "no HR"}",
                    supporting = listOf(Format.shortDate(r.date) + if (r.sourceId == current) " · this run" else "",
                        r.temperatureC?.let { "${it.roundToInt()}°C" + if (r.hot == true) ", hot and humid" else "" } ?: "weather not known")
                        .joinToString(" · "),
                    onClick = if (r.sourceId == current) null else ({ onOpenRun(r.sourceId) }),
                    trailing = {
                        Surface(shape = MaterialTheme.shapes.small, color = cs.surfaceContainerHighest) {
                            Text(when (r.kind) { "easy" -> "easy or steady"; "hard" -> "harder"; else -> "kind not known" },
                                style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp))
                        }
                    })
            }
        }
        onNotThis?.let {
            OutlinedButton(onClick = it, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Text("This run is a different route") }
        }
        Text(basis, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp))
    }
}

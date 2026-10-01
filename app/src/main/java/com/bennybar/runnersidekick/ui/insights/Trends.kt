package com.bennybar.runnersidekick.ui.insights

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.outlined.Watch
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.data.local.Units
import com.bennybar.runnersidekick.data.remote.TrendMetric
import com.bennybar.runnersidekick.data.remote.Trends
import com.bennybar.runnersidekick.data.remote.WeekVolume
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.components.Group
import kotlin.math.roundToInt

private val RANGES = listOf(7, 28, 90)

/** Trends section: daily series with personal-range band, gaps and watch changes; each point opens its source. */
@Composable
fun TrendsSection(t: Trends?, days: Int, units: Units, loading: Boolean, onDays: (Int) -> Unit, onOpenDay: (String) -> Unit, onOpenRun: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            RANGES.forEachIndexed { i, d ->
                SegmentedButton(days == d, { onDays(d) }, SegmentedButtonDefaults.itemShape(i, RANGES.size), icon = {}) { Text("$d days") }
            }
        }
        if (t == null) {
            Text(if (loading) "Loading trends…" else "Couldn't load trends. Pull down to try again.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            return@Column
        }
        ScreenSummaryCard(t.aiSummary)
        if (t.deviceChanges.isNotEmpty()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.Watch, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.width(8.dp))
                Text("Watch changed on ${t.deviceChanges.joinToString { Format.shortDate(it) }}. Shown as a dashed line; ranges restart there.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        t.metrics.forEach { m -> MetricTrendCard(m, t, onOpenDay) }
        WeeklyVolumeCard(t.weeklyRunning, units, onOpenRun)
        PaceCard(t, units, onOpenRun)
    }
}

private fun valueText(metric: String, v: Double?) = Format.metricValue(metric, v)

@Composable
private fun MetricTrendCard(m: TrendMetric, t: Trends, onOpenDay: (String) -> Unit) {
    var selected by rememberSaveable(m.metric, t.days) { mutableStateOf<Int?>(null) }
    val cs = MaterialTheme.colorScheme
    val s = m.summary
    Surface(shape = MaterialTheme.shapes.extraLarge, color = cs.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(m.title, style = MaterialTheme.typography.titleMedium)
            Row(verticalAlignment = Alignment.Bottom) {
                Text(valueText(m.metric, s.median), style = MaterialTheme.typography.headlineMedium)
                Spacer(Modifier.width(8.dp))
                Text("median, ${s.n} of ${t.days} days", style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant,
                    modifier = Modifier.padding(bottom = 4.dp))
            }
            Text(
                if (s.enough && s.change != null)
                    "${Format.signedDelta(m.metric, s.change)} vs the previous ${t.days} days (${s.previousN} days of data)" +
                        if (s.meaningful) ". A notable change." else ", within normal variation."
                else "Not enough data in the previous ${t.days} days to compare.",
                style = MaterialTheme.typography.bodyMedium, color = if (s.meaningful) cs.tertiary else cs.onSurfaceVariant,
            )
            TrendChart(m, t, selected, onSelect = { selected = it },
                description = "${m.title} over ${t.days} days. Shaded band is your usual range; gaps are days without data.")
            val sel = selected?.let { m.points.getOrNull(it) }
            if (sel != null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("${Format.shortDate(sel.date)} · ${sel.value?.let { valueText(m.metric, it) } ?: "no data"}",
                        style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                    FilledTonalButton(onClick = { onOpenDay(sel.date) }) { Text("Open day") }
                }
            } else {
                Text("Tap the chart to see a day.", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun TrendChart(m: TrendMetric, t: Trends, selected: Int?, onSelect: (Int) -> Unit, description: String) {
    val cs = MaterialTheme.colorScheme
    val values = m.points.map { it.value }
    val present = values.filterNotNull() + m.band.mapNotNull { it.q1 } + m.band.mapNotNull { it.q3 }
    if (present.size < 2) {
        Text("No data in this period.", style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
        return
    }
    val lo = present.min()
    val hi = present.max().let { if (it == lo) lo + 1 else it }
    val eraIdx = t.deviceChanges.mapNotNull { d -> m.points.indexOfFirst { it.date == d }.takeIf { it >= 0 } }
    val line = cs.primary
    val band = cs.primary.copy(alpha = 0.14f)
    val grid = cs.outlineVariant
    Column {
        Row {
            Column(Modifier.width(64.dp).height(140.dp)) {
                Text(valueText(m.metric, hi), style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
                Spacer(Modifier.weight(1f))
                Text(valueText(m.metric, lo), style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            }
            Canvas(Modifier.weight(1f).height(140.dp).semantics { contentDescription = description }.pointerInput(values.size) {
                detectTapGestures { o -> onSelect(((o.x / size.width) * (values.size - 1)).roundToInt().coerceIn(0, values.size - 1)) }
            }) {
                val n = values.size
                fun x(i: Int) = if (n <= 1) 0f else i * size.width / (n - 1)
                fun y(v: Double) = (size.height * (1 - (v - lo) / (hi - lo))).toFloat()
                // personal range band, drawn per contiguous run of days that have one
                var i = 0
                while (i < n) {
                    if (m.band[i].q1 == null) { i++; continue }
                    var j = i
                    while (j + 1 < n && m.band[j + 1].q1 != null) j++
                    val p = Path()
                    p.moveTo(x(i), y(m.band[i].q3!!))
                    for (k in i..j) p.lineTo(x(k), y(m.band[k].q3!!))
                    for (k in j downTo i) p.lineTo(x(k), y(m.band[k].q1!!))
                    p.close()
                    drawPath(p, band)
                    i = j + 1
                }
                eraIdx.forEach { e ->
                    drawLine(grid, Offset(x(e), 0f), Offset(x(e), size.height), strokeWidth = 2f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 8f)))
                }
                val path = Path()
                var pen = false
                values.forEachIndexed { k, v ->
                    if (v == null) { pen = false; return@forEachIndexed }
                    if (pen) path.lineTo(x(k), y(v)) else path.moveTo(x(k), y(v))
                    pen = true
                    if (n <= 31) drawCircle(line, 3.dp.toPx(), Offset(x(k), y(v)))
                }
                drawPath(path, line, style = Stroke(2.dp.toPx(), join = StrokeJoin.Round))
                selected?.let { s ->
                    drawLine(cs.onSurface.copy(alpha = 0.4f), Offset(x(s), 0f), Offset(x(s), size.height), strokeWidth = 2f)
                    values.getOrNull(s)?.let { drawCircle(cs.tertiary, 6.dp.toPx(), Offset(x(s), y(it))) }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(start = 64.dp)) {
            Text(Format.shortDate(t.start), style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            Spacer(Modifier.weight(1f))
            Text(Format.shortDate(t.end), style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
        }
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun WeeklyVolumeCard(weeks: List<WeekVolume>, units: Units, onOpenRun: (String) -> Unit) {
    var selected by rememberSaveable { mutableStateOf<Int?>(null) }
    val cs = MaterialTheme.colorScheme
    if (weeks.isEmpty()) return
    val mx = weeks.maxOf { it.movingS }.coerceAtLeast(1.0)
    Surface(shape = MaterialTheme.shapes.extraLarge, color = cs.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Running per week", style = MaterialTheme.typography.titleMedium)
            Text("Moving time per calendar week. The lighter bar is the current, unfinished week.", style = MaterialTheme.typography.bodySmall,
                color = cs.onSurfaceVariant)
            Canvas(Modifier.fillMaxWidth().height(110.dp).semantics { contentDescription = "Weekly running time" }.pointerInput(weeks.size) {
                detectTapGestures { o -> selected = (o.x / size.width * weeks.size).toInt().coerceIn(0, weeks.size - 1) }
            }) {
                val w = size.width / weeks.size
                weeks.forEachIndexed { k, wk ->
                    val h = (wk.movingS / mx).toFloat() * size.height
                    val c: Color = if (selected == k) cs.tertiary else if (wk.partial) cs.primary.copy(alpha = 0.45f) else cs.primary
                    drawRoundRect(c, Offset(k * w + w * 0.18f, size.height - h.coerceAtLeast(3f)), Size(w * 0.64f, h.coerceAtLeast(3f)), CornerRadius(10f, 10f))
                }
            }
            val sel = selected?.let { weeks.getOrNull(it) } ?: weeks.last()
            Text("Week of ${Format.shortDate(sel.weekStart)}: ${sel.runs} ${if (sel.runs == 1) "run" else "runs"} · " +
                "${Format.distance(sel.distanceM, units)} · ${Format.hoursMinutes(sel.movingS)}" + if (sel.partial) " (so far)" else "",
                style = MaterialTheme.typography.titleSmall)
            if (sel.activityIds.isNotEmpty()) Group {
                sel.activityIds.forEach { id -> row("Open run", supporting = id.removePrefix("fx-run-"), icon = Icons.AutoMirrored.Outlined.DirectionsRun,
                    iconShape = MaterialShapes.Cookie9Sided, onClick = { onOpenRun(id) }) }
            }
        }
    }
}

@Composable
private fun PaceCard(t: Trends, units: Units, onOpenRun: (String) -> Unit) {
    val p = t.paceAtHr
    val pts = p.series.flatMap { s -> s.points.map { s.device to it } }
    if (pts.isEmpty() || p.bandBpm == null) return
    var selected by rememberSaveable(t.days) { mutableStateOf<Int?>(null) }
    val cs = MaterialTheme.colorScheme
    val palette = listOf(cs.primary, cs.tertiary, cs.secondary)
    val devices = p.series.map { it.device }
    val lo = pts.minOf { it.second.paceSPerKm } - 5
    val hi = pts.maxOf { it.second.paceSPerKm } + 5
    Surface(shape = MaterialTheme.shapes.extraLarge, color = cs.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Pace at ${p.bandBpm[0]}–${p.bandBpm[1]} bpm", style = MaterialTheme.typography.titleMedium)
            Text(p.headline, style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
            Text("${Format.pace(lo + 5, units)} (faster)", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            Canvas(Modifier.fillMaxWidth().height(110.dp).semantics { contentDescription = "Pace at the same heart rate, per run; colours are watches" }
                .pointerInput(pts.size) { detectTapGestures { o -> selected = ((o.x / size.width) * (pts.size - 1)).roundToInt().coerceIn(0, pts.size - 1) } }) {
                pts.forEachIndexed { k, (dev, pt) ->
                    val x = if (pts.size == 1) size.width / 2 else k * size.width / (pts.size - 1)
                    val y = ((pt.paceSPerKm - lo) / (hi - lo)).toFloat() * size.height
                    drawCircle(if (selected == k) cs.onSurface else palette[devices.indexOf(dev) % 3], (if (selected == k) 7 else 5).dp.toPx(), Offset(x, y))
                }
            }
            Text("${Format.pace(hi - 5, units)} (slower) · each colour is a different watch", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            selected?.let { pts.getOrNull(it) }?.let { (_, pt) ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("${Format.shortDate(pt.date)} · ${Format.pace(pt.paceSPerKm, units)}", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                    pt.sourceId?.let { sid -> FilledTonalButton(onClick = { onOpenRun(sid) }) { Text("Open run") } }
                }
            }
        }
    }
}

package com.bennybar.runnersidekick.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.ui.theme.LocalDataColors

/**
 * Tiny trend line. [band] draws the personal reference range (q1..q3) behind it.
 * Missing days are not drawn as zero: points are placed by date index, and a missing day breaks the line.
 */
@Composable
fun Sparkline(
    values: List<Double?>,
    modifier: Modifier = Modifier,
    band: Pair<Double, Double>? = null,
    color: Color = MaterialTheme.colorScheme.primary,
    description: String,
) {
    val bandColor = LocalDataColors.current.band
    Canvas(modifier.semantics { contentDescription = description }) {
        val present = values.filterNotNull()
        if (present.size < 2) return@Canvas
        var lo = present.min()
        var hi = present.max()
        band?.let { lo = minOf(lo, it.first); hi = maxOf(hi, it.second) }
        if (hi == lo) { hi += 1; lo -= 1 }
        fun y(v: Double) = (size.height * (1 - (v - lo) / (hi - lo))).toFloat()
        val step = size.width / (values.size - 1).coerceAtLeast(1)
        band?.let { drawRect(bandColor, Offset(0f, y(it.second)), androidx.compose.ui.geometry.Size(size.width, y(it.first) - y(it.second))) }
        val path = Path()
        var pen = false
        values.forEachIndexed { i, v ->
            if (v == null) { pen = false; return@forEachIndexed }
            val p = Offset(i * step, y(v))
            if (pen) path.lineTo(p.x, p.y) else path.moveTo(p.x, p.y)
            pen = true
        }
        drawPath(path, color, style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        values.lastOrNull()?.let { drawCircle(color, 3.5.dp.toPx(), Offset((values.size - 1) * step, y(it))) }
    }
}

/**
 * Time-series chart with labelled y-axis (min/max) and x-axis in minutes. Nulls break the line (gaps stay gaps).
 * [invert] puts lower values at the top (used for pace, where faster = lower s/km).
 */
@Composable
fun SeriesChart(
    title: String,
    t: List<Double>,
    values: List<Double?>,
    color: Color,
    formatY: (Double) -> String,
    modifier: Modifier = Modifier,
    invert: Boolean = false,
    description: String,
) {
    val present = values.filterNotNull()
    val onVar = MaterialTheme.colorScheme.onSurfaceVariant
    val grid = MaterialTheme.colorScheme.outlineVariant
    Column(modifier) {
        Text(title, style = MaterialTheme.typography.labelLarge, color = onVar)
        if (present.size < 2 || t.size < 2) {
            Text("No data recorded", style = MaterialTheme.typography.bodySmall, color = onVar, modifier = Modifier.padding(vertical = 24.dp))
            return@Column
        }
        // Scale to the 2nd–98th percentile so start-up sensor readings don't flatten the trace; outliers are clamped.
        val sorted = present.sorted()
        val lo = sorted[(sorted.size * 0.02).toInt()]
        val hi = sorted[((sorted.size - 1) * 0.98).toInt()].let { if (it <= lo) lo + 1 else it }
        Row {
            Column(Modifier.width(56.dp).height(120.dp)) {
                Text(formatY(if (invert) lo else hi), style = MaterialTheme.typography.labelSmall, color = onVar)
                Spacer(Modifier.weight(1f))
                Text(formatY(if (invert) hi else lo), style = MaterialTheme.typography.labelSmall, color = onVar)
            }
            Canvas(Modifier.weight(1f).height(120.dp).semantics { contentDescription = description }) {
                val t0 = t.first()
                val span = (t.last() - t0).coerceAtLeast(1.0)
                fun x(v: Double) = ((v - t0) / span * size.width).toFloat()
                fun y(v: Double): Float {
                    val f = ((v.coerceIn(lo, hi) - lo) / (hi - lo)).toFloat()
                    return size.height * (if (invert) f else 1 - f)
                }
                val dash = PathEffect.dashPathEffect(floatArrayOf(6f, 6f))
                drawLine(grid, Offset(0f, 0f), Offset(size.width, 0f), pathEffect = dash)
                drawLine(grid, Offset(0f, size.height), Offset(size.width, size.height), pathEffect = dash)
                val path = Path()
                var pen = false
                for (i in t.indices) {
                    val v = values.getOrNull(i)
                    if (v == null) { pen = false; continue }
                    if (pen) path.lineTo(x(t[i]), y(v)) else path.moveTo(x(t[i]), y(v))
                    pen = true
                }
                drawPath(path, color, style = Stroke(width = 1.75.dp.toPx(), join = StrokeJoin.Round))
            }
        }
        Row(Modifier.fillMaxWidth().padding(start = 56.dp)) {
            Text("0 min", style = MaterialTheme.typography.labelSmall, color = onVar)
            Spacer(Modifier.weight(1f))
            Text("${((t.last() - t.first()) / 60).toInt()} min", style = MaterialTheme.typography.labelSmall, color = onVar)
        }
    }
}

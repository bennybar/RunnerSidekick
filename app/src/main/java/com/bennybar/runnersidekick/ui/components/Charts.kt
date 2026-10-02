package com.bennybar.runnersidekick.ui.components

import androidx.compose.ui.graphics.drawscope.clipRect
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
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
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
import androidx.compose.ui.text.drawText
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
    val ring = MaterialTheme.colorScheme.surface
    // Draws itself left to right once, when it first appears
    var shown by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf(false) }
    androidx.compose.runtime.LaunchedEffect(Unit) { shown = true }
    val reveal by androidx.compose.animation.core.animateFloatAsState(if (shown) 1f else 0f,
        androidx.compose.animation.core.tween(700, easing = androidx.compose.animation.core.FastOutSlowInEasing), label = "spark")
    Canvas(modifier.semantics { contentDescription = description }) {
        val present = values.filterNotNull()
        if (present.size < 2) return@Canvas
        var lo = present.min()
        var hi = present.max()
        band?.let { lo = minOf(lo, it.first); hi = maxOf(hi, it.second) }
        if (hi == lo) { hi += 1; lo -= 1 }
        val pad = 5.dp.toPx()  // room for the end dot's halo
        val h = size.height - 2 * pad
        fun y(v: Double) = (pad + h * (1 - (v - lo) / (hi - lo))).toFloat()
        val step = (size.width - pad) / (values.size - 1).coerceAtLeast(1)
        band?.let {
            drawRoundRect(bandColor, Offset(0f, y(it.second)), androidx.compose.ui.geometry.Size(size.width, y(it.first) - y(it.second)),
                androidx.compose.ui.geometry.CornerRadius(4.dp.toPx()))
        }
        // Each unbroken run of values: a smooth curve (midpoint quadratic segments) with a soft fill underneath
        val runs = mutableListOf<MutableList<Offset>>()
        values.forEachIndexed { i, v ->
            if (v == null) { runs.add(mutableListOf()); return@forEachIndexed }
            if (runs.isEmpty()) runs.add(mutableListOf())
            runs.last().add(Offset(i * step, y(v)))
        }
        clipRect(right = size.width * reveal) {
            runs.filter { it.size >= 2 }.forEach { pts ->
                val line = Path().apply {
                    moveTo(pts[0].x, pts[0].y)
                    for (k in 1 until pts.size) {
                        val m = Offset((pts[k - 1].x + pts[k].x) / 2, (pts[k - 1].y + pts[k].y) / 2)
                        quadraticTo(pts[k - 1].x, pts[k - 1].y, m.x, m.y)
                    }
                    lineTo(pts.last().x, pts.last().y)
                }
                val area = Path().apply { addPath(line); lineTo(pts.last().x, size.height); lineTo(pts[0].x, size.height); close() }
                drawPath(area, androidx.compose.ui.graphics.Brush.verticalGradient(listOf(color.copy(alpha = 0.36f), color.copy(alpha = 0f))))
                drawPath(line, color, style = Stroke(width = 2.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            }
        }
        // Today's value: a dot with a soft halo, once the line has reached it
        values.lastOrNull()?.let {
            val c = Offset((values.size - 1) * step, y(it))
            val a = ((reveal - 0.85f) / 0.15f).coerceIn(0f, 1f)
            drawCircle(color.copy(alpha = 0.22f * a), 7.dp.toPx(), c)
            drawCircle(ring.copy(alpha = a), 4.5.dp.toPx(), c)
            drawCircle(color.copy(alpha = a), 3.dp.toPx(), c)
        }
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


data class WeekPoint(val week: java.time.LocalDate, val value: Double, val newWatch: Boolean = false)

/**
 * Weekly values as labelled dots on a zoomed scale with gridlines every [step] (position encodes the value, so a narrow
 * range isn't exaggerated as bar lengths would be). Weeks without a value are marked "gap" and a watch change
 * "new watch"; the line is never drawn across either. [band] shades a personal range (e.g. your usual HRV).
 */
@Composable
fun WeeklyDotChart(points: List<WeekPoint>, decimals: Int, step: Double, caption: String, description: String,
                   band: Pair<Double, Double>? = null) {
    if (points.size < 2) return
    val cs = MaterialTheme.colorScheme
    val locale = androidx.compose.ui.platform.LocalConfiguration.current.locales[0]
    val fmt = "%.${decimals}f"
    // Slots in order: a week, or a marker ("gap" for missing weeks, "new watch" for a device change)
    val slots = buildList<Any> {
        points.forEachIndexed { i, p ->
            if (i > 0 && p.newWatch) add("new watch")
            else if (i > 0 && p.week.minusWeeks(1) != points[i - 1].week) add("gap")
            add(p)
        }
    }
    val weights = slots.map { if (it is String) 0.7f else 1f }
    val values = points.map { it.value } + listOfNotNull(band?.first, band?.second)
    val lo = kotlin.math.floor((values.min() - step / 2) / step) * step
    val hi = kotlin.math.ceil((values.max() + step / 2) / step) * step
    val measurer = androidx.compose.ui.text.rememberTextMeasurer()
    val small = MaterialTheme.typography.labelSmall.copy(color = cs.onSurfaceVariant)
    val strong = MaterialTheme.typography.labelLarge.copy(color = cs.primary)
    val marker = MaterialTheme.typography.labelSmall.copy(color = cs.outline)
    val gap = 6.dp
    Column {
        Canvas(Modifier.fillMaxWidth().height(120.dp).semantics {
            contentDescription = "$description: " + points.joinToString { "${it.week} ${fmt.format(it.value)}" }
        }) {
            val spacing = gap.toPx()
            val axis = 28.dp.toPx()  // right margin for gridline labels, outside the plot
            val plotW = size.width - axis
            val unit = (plotW - spacing * (slots.size - 1)) / weights.sum()
            var x0 = 0f
            val centers = weights.map { w -> (x0 + w * unit / 2).also { x0 += w * unit + spacing } }
            val top = 26.dp.toPx()
            val bottom = size.height - 8.dp.toPx()
            fun y(v: Double) = (bottom - (v - lo) / (hi - lo) * (bottom - top)).toFloat()
            band?.let { (a, b) -> drawRect(cs.primary.copy(alpha = 0.08f), Offset(0f, y(b)), androidx.compose.ui.geometry.Size(plotW, y(a) - y(b))) }
            var g = lo
            while (g <= hi + 1e-9) {
                drawLine(cs.outlineVariant, Offset(0f, y(g)), Offset(plotW, y(g)), strokeWidth = 1.dp.toPx())
                val t = measurer.measure("%.0f".format(g), small)
                drawText(t, topLeft = Offset(size.width - t.size.width, y(g) - t.size.height / 2))
                g += step
            }
            slots.forEachIndexed { k, sl ->
                if (sl is String) {
                    val t = measurer.measure(sl.replace(" ", "\n"), marker)
                    drawText(t, topLeft = Offset(centers[k] - t.size.width / 2, bottom - t.size.height))
                } else if (k > 0 && slots[k - 1] is WeekPoint) {
                    drawLine(cs.primary.copy(alpha = 0.45f), Offset(centers[k - 1], y((slots[k - 1] as WeekPoint).value)),
                        Offset(centers[k], y((sl as WeekPoint).value)), strokeWidth = 2.dp.toPx())
                }
            }
            slots.forEachIndexed { k, sl ->
                if (sl !is WeekPoint) return@forEachIndexed
                val last = k == slots.lastIndex
                val c = Offset(centers[k], y(sl.value))
                drawCircle(if (last) cs.primary else cs.primary.copy(alpha = 0.7f), (if (last) 7 else 5).dp.toPx(), c)
                val t = measurer.measure(fmt.format(sl.value), if (last) strong else small)
                drawText(t, topLeft = Offset(c.x - t.size.width / 2, c.y - t.size.height - 8.dp.toPx()))
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 4.dp, end = 28.dp), horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(gap)) {
            // The month is named only where it changes (6 Jul, 13, 20, … 3 Aug), so the labels fit
            var shownMonth: java.time.Month? = null
            slots.forEachIndexed { k, sl ->
                val label = (sl as? WeekPoint)?.week?.let { d ->
                    (if (d.month != shownMonth) "${d.dayOfMonth} ${d.month.getDisplayName(java.time.format.TextStyle.SHORT, locale)}"
                    else "${d.dayOfMonth}").also { shownMonth = d.month }
                } ?: ""
                Text(label, style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant, maxLines = 1,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.weight(weights[k]))
            }
        }
        Text(caption + (if (slots.any { it == "gap" }) " · gap = weeks without a reading" else "") +
            (if (band != null) " · shaded = your usual range" else ""),
            style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
    }
}

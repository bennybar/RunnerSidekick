package com.bennybar.runnersidekick.ui.insights

import androidx.compose.foundation.Canvas
import androidx.compose.ui.text.drawText
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.Handshake
import androidx.compose.material.icons.outlined.MonitorHeart
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.data.remote.Fitness
import com.bennybar.runnersidekick.data.remote.TrainingStatus
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.ShapeBadge

/** Garmin's training-status phrases (e.g. "OVERREACHING_3") as Garmin names them in its app. */
fun trainingStatusLabel(phrase: String?): String? = phrase?.substringBefore('_')?.let {
    when (it) {
        "NO" -> "No status"
        else -> it.lowercase().replaceFirstChar(Char::uppercase)
    }
}

/** Garmin's load-balance feedback, e.g. "AEROBIC_LOW_SHORTAGE" -> "Low aerobic shortage". */
fun loadBalanceLabel(phrase: String?): String? = when (phrase) {
    null -> null
    "AEROBIC_LOW_SHORTAGE" -> "Low aerobic shortage"
    "AEROBIC_HIGH_SHORTAGE" -> "High aerobic shortage"
    "ANAEROBIC_SHORTAGE" -> "Anaerobic shortage"
    "AEROBIC_LOW_FOCUS" -> "Low aerobic focus"
    "AEROBIC_HIGH_FOCUS" -> "High aerobic focus"
    "ANAEROBIC_FOCUS" -> "Anaerobic focus"
    "BALANCED" -> "Balanced"
    else -> phrase.lowercase().replace('_', ' ').replaceFirstChar(Char::uppercase)
}

private fun clock(s: Double?): String {
    if (s == null) return "—"
    val t = s.toInt()
    return if (t >= 3600) "%d:%02d:%02d".format(t / 3600, (t % 3600) / 60, t % 60) else "%d:%02d".format(t / 60, t % 60)
}

/**
 * The fitness overview: Garmin's numbers (labelled as Garmin's), your records, and an explicit note when
 * Garmin's verdict and Runner Sidekick's own analysis point the same way.
 */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun FitnessSection(f: Fitness, mostlyHard: Boolean, onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    val g = f.garmin
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (g != null) {
            Surface(shape = MaterialTheme.shapes.extraLarge, color = cs.surfaceContainerHigh, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        ShapeBadge(Icons.Outlined.MonitorHeart, MaterialShapes.Cookie9Sided, Modifier.size(44.dp), container = cs.primary, content = cs.onPrimary)
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text("Your fitness", style = MaterialTheme.typography.titleLarge)
                            Text("Numbers calculated by Garmin, shown as Garmin supplies them", style = MaterialTheme.typography.labelSmall,
                                color = cs.onSurfaceVariant)
                        }
                    }
                    Row(verticalAlignment = Alignment.Bottom) {
                        g.vo2max?.let { v ->
                            Column(Modifier.weight(1f)) {
                                Text("VO₂ max", style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
                                Text("%.1f".format(v.value), style = MaterialTheme.typography.displayMedium)
                                v.date?.let { Text("as of ${Format.shortDate(it)}", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant) }
                            }
                        }
                        g.trainingStatus?.let { st -> StatusBlock(st, Modifier.weight(1f)) }
                    }
                    if (f.vo2maxSeries.size >= 2) {
                        Vo2Chart(f.vo2maxSeries)
                        Text("VO₂ max: ${f.vo2maxSeries.size} Garmin measurements since ${Format.shortDate(f.vo2maxSeries.first().date)} " +
                            "(%.1f → %.1f)".format(f.vo2maxSeries.first().value, f.vo2maxSeries.last().value),
                            style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
                    }
                    g.trainingStatus?.let { st -> LoadBar(st) }
                    g.racePredictions?.let { r ->
                        Text("Garmin race predictions", style = MaterialTheme.typography.titleSmall)
                        Row {
                            listOf("5K" to r.k5, "10K" to r.k10, "Half" to r.half, "Marathon" to r.marathon).forEach { (l, v) ->
                                Column(Modifier.weight(1f)) {
                                    Text(clock(v), style = MaterialTheme.typography.titleLarge)
                                    Text(l, style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant)
                                }
                            }
                        }
                    }
                    listOfNotNull(
                        loadBalanceLabel(g.loadBalance?.phrase)?.let { "Load balance: $it" },
                        g.heatAcclimationPct?.let { "Heat acclimation: ${it.toInt()}%" },
                    ).takeIf { it.isNotEmpty() }?.let {
                        Text(it.joinToString(" · ") + " (Garmin)", style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
                    }
                }
            }
            // Agreement: Garmin's status/balance and our own intensity analysis come from the same runs, so this is
            // consistency, not independent confirmation.
            val strained = trainingStatusLabel(g.trainingStatus?.phrase) in setOf("Overreaching", "Strained", "Unproductive")
            val shortEasy = g.loadBalance?.phrase == "AEROBIC_LOW_SHORTAGE"
            if (mostlyHard && (strained || shortEasy)) {
                Surface(shape = MaterialTheme.shapes.large, color = cs.tertiaryContainer, modifier = Modifier.fillMaxWidth()) {
                    Row(Modifier.padding(18.dp), verticalAlignment = Alignment.Top) {
                        ShapeBadge(Icons.Outlined.Handshake, MaterialShapes.SoftBurst, Modifier.size(40.dp), container = cs.tertiary, content = cs.onTertiary)
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text("Garmin and your own data agree", style = MaterialTheme.typography.titleMedium, color = cs.onTertiaryContainer)
                            Text(
                                listOfNotNull(
                                    if (strained) "Garmin rates your training as ${trainingStatusLabel(g.trainingStatus?.phrase)?.lowercase()}" else null,
                                    if (shortEasy) "Garmin sees too little low-intensity aerobic work" else null,
                                ).joinToString(", and ") + ". That matches what Runner Sidekick finds: most of your running is in zones 4–5. " +
                                    "Both views come from the same runs, so this is consistency rather than independent proof.",
                                style = MaterialTheme.typography.bodyMedium, color = cs.onTertiaryContainer,
                            )
                        }
                    }
                }
            }
        }
        val recs = listOf("1k", "5k", "10k", "half").mapNotNull { k -> f.records[k]?.takeIf { it.best != null } }
        if (recs.isNotEmpty()) {
            Group(title = "Personal records · fastest segment inside any synced run") {
                recs.forEach { r ->
                    val b = r.best!!
                    row("${r.label}: ${clock(b.elapsedS)}", supporting = "Set ${Format.shortDate(b.date)} · improved ${r.progression.size - 1} times",
                        icon = Icons.Outlined.EmojiEvents, iconShape = MaterialShapes.Sunny, onClick = { onOpenRun(b.sourceId) })
                }
            }
        }
    }
}

@Composable
private fun StatusBlock(st: TrainingStatus, modifier: Modifier) {
    val cs = MaterialTheme.colorScheme
    val label = trainingStatusLabel(st.phrase) ?: return
    val warn = label in setOf("Overreaching", "Strained", "Unproductive", "Detraining")
    Column(modifier) {
        Text("Training status", style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
        Surface(shape = MaterialTheme.shapes.small, color = if (warn) cs.errorContainer else cs.primaryContainer) {
            Text(label, style = MaterialTheme.typography.titleLarge, color = if (warn) cs.onErrorContainer else cs.onPrimaryContainer,
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
        }
        st.since?.let { Text("since ${Format.shortDate(it)}", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant) }
    }
}

/** Garmin's acute load against Garmin's own optimal range for you. The ratio between them is not shown. */
@Composable
private fun LoadBar(st: TrainingStatus) {
    val acute = st.acuteLoad ?: return
    val lo = st.chronicMin ?: return
    val hi = st.chronicMax ?: return
    val cs = MaterialTheme.colorScheme
    val top = maxOf(acute, hi) * 1.15
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Acute load ${acute.toInt()} · Garmin's optimal range ${lo.toInt()}–${hi.toInt()}",
            style = MaterialTheme.typography.titleSmall)
        Canvas(Modifier.fillMaxWidth().height(18.dp).semantics {
            contentDescription = "Acute load ${acute.toInt()}, Garmin optimal range ${lo.toInt()} to ${hi.toInt()}"
        }) {
            fun x(v: Double) = (v / top * size.width).toFloat()
            drawRoundRect(cs.surfaceVariant, Offset.Zero, size, CornerRadius(20f, 20f))
            drawRoundRect(cs.primary.copy(alpha = 0.35f), Offset(x(lo), 0f), Size(x(hi) - x(lo), size.height), CornerRadius(20f, 20f))
            drawCircle(if (acute > hi) cs.error else cs.primary, size.height * 0.7f, Offset(x(acute), size.height / 2))
        }
        Text(if (acute > hi) "Above Garmin's optimal range" else if (acute < lo) "Below Garmin's optimal range" else "Inside Garmin's optimal range",
            style = MaterialTheme.typography.labelMedium, color = if (acute > hi) cs.error else cs.onSurfaceVariant)
    }
}

/** VO2 max by week (Garmin's latest reading each week, last 8 weeks) as labelled dots. A dot's height is its value on
 *  a zoomed scale with whole-number gridlines, so small changes stay visible without the length distortion of bars.
 *  Weeks without a reading break the line and are marked as a gap. */
@Composable
private fun Vo2Chart(series: List<com.bennybar.runnersidekick.data.remote.Point>) {
    val cs = MaterialTheme.colorScheme
    val locale = androidx.compose.ui.platform.LocalConfiguration.current.locales[0]
    val weeks = series.groupBy { java.time.LocalDate.parse(it.date).let { d -> d.minusDays(d.dayOfWeek.value - 1L) } }
        .mapValues { (_, pts) -> pts.maxBy { it.date }.value }.toSortedMap().entries.toList().takeLast(8)
    if (weeks.size < 2) return
    // Slots in order: a week, or a gap where weeks have no reading (narrower, never joined by the line)
    val slots = buildList<Pair<java.time.LocalDate, Double>?> {
        weeks.forEachIndexed { i, e ->
            if (i > 0 && e.key.minusWeeks(1) != weeks[i - 1].key) add(null)
            add(e.key to e.value)
        }
    }
    val weights = slots.map { if (it == null) 0.6f else 1f }
    val lo = kotlin.math.floor(weeks.minOf { it.value } * 2 - 1) / 2
    val hi = kotlin.math.ceil(weeks.maxOf { it.value } * 2 + 1) / 2
    val measurer = androidx.compose.ui.text.rememberTextMeasurer()
    val small = MaterialTheme.typography.labelSmall.copy(color = cs.onSurfaceVariant)
    val strong = MaterialTheme.typography.labelLarge.copy(color = cs.primary)
    val grid = cs.outlineVariant
    val line = cs.primary.copy(alpha = 0.45f)
    val dot = cs.primary.copy(alpha = 0.7f)
    val gapLabel = MaterialTheme.typography.labelSmall.copy(color = cs.outline)
    val gap = 6.dp
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Canvas(Modifier.fillMaxWidth().height(120.dp).semantics {
            contentDescription = "VO2 max by week: " + weeks.joinToString { "${Format.shortDate(it.key.toString())} %.1f".format(it.value) }
        }) {
            val spacing = gap.toPx()
            val axis = 28.dp.toPx()  // right margin for the gridline labels, outside the plot
            val plotW = size.width - axis
            val unit = (plotW - spacing * (slots.size - 1)) / weights.sum()
            var x0 = 0f
            val centers = weights.map { w -> (x0 + w * unit / 2).also { x0 += w * unit + spacing } }
            val top = 26.dp.toPx()
            val bottom = size.height - 8.dp.toPx()
            fun y(v: Double) = (bottom - (v - lo) / (hi - lo) * (bottom - top)).toFloat()
            // Whole-number gridlines, labelled at the right edge
            var g = kotlin.math.ceil(lo)
            while (g <= hi) {
                drawLine(grid, Offset(0f, y(g)), Offset(plotW, y(g)), strokeWidth = 1.dp.toPx())
                val t = measurer.measure("%.0f".format(g), small)
                drawText(t, topLeft = Offset(size.width - t.size.width, y(g) - t.size.height / 2))
                g += 1
            }
            slots.forEachIndexed { k, sl ->
                if (sl == null) {
                    val t = measurer.measure("gap", gapLabel)
                    drawText(t, topLeft = Offset(centers[k] - t.size.width / 2, bottom - t.size.height))
                } else if (k > 0 && slots[k - 1] != null) {
                    drawLine(line, Offset(centers[k - 1], y(slots[k - 1]!!.second)), Offset(centers[k], y(sl.second)), strokeWidth = 2.dp.toPx())
                }
            }
            slots.forEachIndexed { k, sl ->
                if (sl == null) return@forEachIndexed
                val last = k == slots.lastIndex
                val c = Offset(centers[k], y(sl.second))
                drawCircle(if (last) cs.primary else dot, (if (last) 7 else 5).dp.toPx(), c)
                val t = measurer.measure("%.1f".format(sl.second), if (last) strong else small)
                drawText(t, topLeft = Offset(c.x - t.size.width / 2, c.y - t.size.height - 8.dp.toPx()))
            }
        }
        Row(Modifier.fillMaxWidth().padding(end = 28.dp), horizontalArrangement = Arrangement.spacedBy(gap)) {
            // The month is named only where it changes (6 Jul, 13, 20, … 3 Aug), so the labels fit
            var shownMonth: java.time.Month? = null
            slots.forEachIndexed { k, sl ->
                val label = sl?.first?.let { d ->
                    (if (d.month != shownMonth) "${d.dayOfMonth} ${d.month.getDisplayName(java.time.format.TextStyle.SHORT, locale)}"
                    else "${d.dayOfMonth}").also { shownMonth = d.month }
                } ?: ""
                Text(label,
                    style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant, maxLines = 1,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.weight(weights[k]))
            }
        }
        Text("By week (latest Garmin reading)" + if (slots.any { it == null }) " · gap = weeks without a reading" else "",
            style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
    }
}

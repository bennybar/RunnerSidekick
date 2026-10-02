package com.bennybar.runnersidekick.ui.insights

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.outlined.Cake
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.MonitorHeart
import androidx.compose.material.icons.outlined.Speed
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.graphics.shapes.RoundedPolygon
import com.bennybar.runnersidekick.data.remote.AgeGradeRow
import com.bennybar.runnersidekick.data.remote.CompareItem
import com.bennybar.runnersidekick.data.remote.CompareReport
import com.bennybar.runnersidekick.ui.components.ShapeBadge
import com.bennybar.runnersidekick.ui.theme.accentFor
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

private fun JsonObject.num(k: String): Double? = this[k]?.jsonPrimitive?.doubleOrNull
private fun JsonObject.nums(k: String): List<Double> = this[k]?.jsonArray?.mapNotNull { it.jsonPrimitive.doubleOrNull }.orEmpty()

private fun clock(s: Double): String {
    val t = s.toInt()
    return if (t >= 3600) "%d:%02d:%02d".format(t / 3600, (t % 3600) / 60, t % 60) else "%d:%02d".format(t / 60, t % 60)
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
private fun style(id: String): Triple<ImageVector, RoundedPolygon, String> = when (id) {
    "vo2max" -> Triple(Icons.Outlined.Speed, MaterialShapes.Cookie9Sided, "fitness")
    "fitness_age" -> Triple(Icons.Outlined.Cake, MaterialShapes.Sunny, "habits")
    "resting_hr" -> Triple(Icons.Outlined.Favorite, MaterialShapes.SoftBurst, "recovery")
    "age_grade" -> Triple(Icons.AutoMirrored.Outlined.DirectionsRun, MaterialShapes.Cookie6Sided, "running")
    else -> Triple(Icons.Outlined.MonitorHeart, MaterialShapes.Clover4Leaf, "sleep")
}

/** You against people of your sex and age. Every card says which reference it uses and what limits the comparison. */
@Composable
fun CompareSection(r: CompareReport?, onOpenSettings: () -> Unit, onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    if (r == null) return
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val p = r.profile
        if (r.missing.isNotEmpty()) {
            Surface(shape = MaterialTheme.shapes.large, color = cs.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(20.dp)) {
                    Text("Comparisons need your ${r.missing.joinToString(" and ")}", style = MaterialTheme.typography.titleMedium)
                    Text("Garmin didn't provide ${if (r.missing.size > 1) "them" else "it"}. Add it in Settings; nothing is guessed.",
                        style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant)
                    TextButton(onClick = onOpenSettings) { Text("Open Settings") }
                }
            }
            return
        }
        ScreenSummaryCard(r.aiSummary)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Compared with ${if (p.sex == "female") "women" else "men"} of your age (${p.age})" +
                if (p.source == "settings") " · your settings" else " · from Garmin",
                style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant, modifier = Modifier.weight(1f))
            TextButton(onClick = onOpenSettings) { Text("Change") }
        }
        r.items.forEach { CompareCard(it, onOpenRun) }
        Text("Population comparisons describe where you sit among others; they aren't health assessments or medical advice.",
            style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun CompareCard(i: CompareItem, onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    val (icon, shape, cat) = style(i.id)
    val accent = accentFor(cat)
    var more by remember { mutableStateOf(false) }
    Surface(shape = MaterialTheme.shapes.extraLarge, color = cs.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.animateContentSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ShapeBadge(icon, shape, Modifier.size(40.dp), container = accent?.container ?: cs.secondaryContainer,
                    content = accent?.content ?: cs.onSecondaryContainer)
                Spacer(Modifier.width(12.dp))
                Text(i.title, style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
            }
            i.headline?.let { Text(it, style = MaterialTheme.typography.titleLarge) }
            i.chart?.let { c ->
                when (c["type"]?.jsonPrimitive?.content) {
                    "bands" -> BandsChart(c)
                    "ages" -> AgesChart(c)
                    "distribution" -> DistributionChart(c)
                    "age_grade" -> AgeGradeChart(i.rows, onOpenRun)
                    "weekly_dots" -> com.bennybar.runnersidekick.ui.components.WeeklyDotChart(
                        c["points"]!!.jsonArray.map { it.jsonObject }.map { p ->
                            com.bennybar.runnersidekick.ui.components.WeekPoint(java.time.LocalDate.parse(p["week"]!!.jsonPrimitive.content),
                                p.num("value") ?: 0.0, p["new_watch"]?.jsonPrimitive?.content == "true")
                        },
                        decimals = c.num("decimals")?.toInt() ?: 0, step = c.num("step") ?: 5.0, caption = "Weekly median (${c["unit"]?.jsonPrimitive?.content})",
                        description = i.title,
                        band = c["band"]?.takeIf { it !is kotlinx.serialization.json.JsonNull }?.jsonArray?.let { b ->
                            b[0].jsonPrimitive.doubleOrNull!! to b[1].jsonPrimitive.doubleOrNull!! })
                }
            }
            if (i.detail != null || i.method != null || i.caveats.isNotEmpty()) {
                if (more) {
                    i.detail?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                    i.method?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant) }
                    i.caveats.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant) }
                    i.source?.let { Text("Reference: $it", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant) }
                }
                TextButton(onClick = { more = !more }) { Text(if (more) "Less" else "Details") }
            }
        }
    }
}

/** VO2 max: the rating bands for your group with your value marked. */
@Composable
private fun BandsChart(c: JsonObject) {
    val cs = MaterialTheme.colorScheme
    val bands = c["bands"]!!.jsonArray.map { it.jsonObject }
    val value = c.num("value") ?: return
    val lo = bands.first().num("from")!!
    val hi = bands.last().num("to")!!
    val colors = listOf(cs.surfaceContainerHighest, cs.primary.copy(alpha = 0.25f), cs.primary.copy(alpha = 0.45f),
        cs.primary.copy(alpha = 0.7f), cs.primary)
    Column {
        Canvas(Modifier.fillMaxWidth().height(36.dp).semantics {
            contentDescription = "Your value ${"%.1f".format(value)} on the rating scale " + bands.joinToString { it["label"]!!.jsonPrimitive.content }
        }) {
            fun x(v: Double) = ((v.coerceIn(lo, hi) - lo) / (hi - lo) * size.width).toFloat()
            bands.forEachIndexed { k, b ->
                val x0 = x(b.num("from")!!)
                val x1 = x(b.num("to")!!)
                drawRoundRect(colors[k % colors.size], Offset(x0 + 1f, 10f), Size((x1 - x0 - 2f).coerceAtLeast(1f), size.height - 20f), CornerRadius(8f, 8f))
            }
            val mx = x(value)
            drawCircle(cs.onSurface, 9.dp.toPx(), Offset(mx, size.height / 2))
            drawCircle(cs.surface, 5.dp.toPx(), Offset(mx, size.height / 2))
        }
        Row(Modifier.fillMaxWidth()) {
            bands.forEach { b ->
                Text(b["label"]!!.jsonPrimitive.content, style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant,
                    textAlign = TextAlign.Center, modifier = Modifier.weight(((b.num("to")!! - b.num("from")!!) / (hi - lo)).toFloat()))
            }
        }
    }
}

/** Fitness age: your real age, Garmin's fitness age, what Garmin says is achievable, and the age your VO2 max is typical for. */
@Composable
private fun AgesChart(c: JsonObject) {
    val cs = MaterialTheme.colorScheme
    val marks = listOfNotNull(
        c.num("age")?.let { Triple("Your age", it, cs.onSurfaceVariant) },
        c.num("fitness_age")?.let { Triple("Fitness age", it, cs.primary) },
        c.num("achievable")?.let { Triple("Achievable", it, cs.tertiary) },
        c.num("vo2_age")?.let { Triple("VO₂ max typical for", it, cs.secondary) },
    )
    if (marks.size < 2) return
    val lo = marks.minOf { it.second } - 3
    val hi = marks.maxOf { it.second } + 3
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Canvas(Modifier.fillMaxWidth().height(28.dp).semantics { contentDescription = marks.joinToString { "${it.first} ${"%.1f".format(it.second)}" } }) {
            fun x(v: Double) = ((v - lo) / (hi - lo) * size.width).toFloat()
            drawRoundRect(cs.surfaceContainerHighest, Offset(0f, size.height / 2 - 4f), Size(size.width, 8f), CornerRadius(4f, 4f))
            marks.forEach { (_, v, col) -> drawCircle(col, 8.dp.toPx(), Offset(x(v), size.height / 2)) }
        }
        marks.forEach { (label, v, col) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Canvas(Modifier.size(10.dp)) { drawCircle(col) }
                Spacer(Modifier.width(8.dp))
                Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
                Text("%.1f".format(v).removeSuffix(".0"), style = MaterialTheme.typography.titleMedium)
            }
        }
    }
}

/** Resting heart rate: the population's spread (2.5th–97.5th, middle half darker, median tick) with your value. */
@Composable
private fun DistributionChart(c: JsonObject) {
    val cs = MaterialTheme.colorScheme
    val pts = c.nums("points")
    val value = c.num("value") ?: return
    if (pts.size < 9) return
    val lo = minOf(pts.first(), value) - 4
    val hi = maxOf(pts.last(), value) + 4
    Column {
        Canvas(Modifier.fillMaxWidth().height(40.dp).semantics {
            contentDescription = "Your ${value.toInt()} bpm; population middle ${pts[4].toInt()} bpm, typical range ${pts[0].toInt()} to ${pts[8].toInt()}"
        }) {
            fun x(v: Double) = ((v - lo) / (hi - lo) * size.width).toFloat()
            val mid = size.height / 2
            drawRoundRect(cs.primary.copy(alpha = 0.18f), Offset(x(pts[0]), mid - 10f), Size(x(pts[8]) - x(pts[0]), 20f), CornerRadius(10f, 10f))
            drawRoundRect(cs.primary.copy(alpha = 0.4f), Offset(x(pts[3]), mid - 10f), Size(x(pts[5]) - x(pts[3]), 20f), CornerRadius(10f, 10f))
            drawLine(cs.primary, Offset(x(pts[4]), mid - 16f), Offset(x(pts[4]), mid + 16f), strokeWidth = 3.dp.toPx())
            drawCircle(cs.onSurface, 9.dp.toPx(), Offset(x(value), mid))
            drawCircle(cs.surface, 5.dp.toPx(), Offset(x(value), mid))
        }
        Row(Modifier.fillMaxWidth()) {
            Text("${pts[0].toInt()} bpm", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            Spacer(Modifier.weight(1f))
            Text("middle ${pts[4].toInt()}", style = MaterialTheme.typography.labelSmall, color = cs.primary)
            Spacer(Modifier.weight(1f))
            Text("${pts[8].toInt()} bpm", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
        }
        Text("You: ${value.toInt()} bpm · darker band = middle half of people", style = MaterialTheme.typography.labelSmall,
            color = cs.onSurfaceVariant)
    }
}

/** Age grade per distance on a 40–100% scale with the class thresholds marked. */
@Composable
private fun AgeGradeChart(rows: List<AgeGradeRow>, onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    val lo = 40.0
    val hi = 100.0
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        rows.sortedWith(compareBy({ it.kind != "best" }, { it.timeS })).forEach { r ->
            Column {
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(r.label + if (r.kind == "prediction") " · Garmin prediction" else " · your best", style = MaterialTheme.typography.labelLarge,
                        modifier = Modifier.weight(1f))
                    Text("${clock(r.timeS)} → ${"%.0f".format(r.ageGradePct)}%", style = MaterialTheme.typography.titleSmall)
                }
                Box {
                    Canvas(Modifier.fillMaxWidth().height(14.dp).padding(top = 4.dp).semantics {
                        contentDescription = "${r.label} ${"%.0f".format(r.ageGradePct)} percent age grade, ${r.gradeClass}"
                    }) {
                        fun x(v: Double) = ((v.coerceIn(lo, hi) - lo) / (hi - lo) * size.width).toFloat()
                        drawRoundRect(cs.surfaceContainerHighest, Offset.Zero, size, CornerRadius(6f, 6f))
                        drawRoundRect(if (r.kind == "best") cs.primary else cs.primary.copy(alpha = 0.45f), Offset.Zero,
                            Size(x(r.ageGradePct), size.height), CornerRadius(6f, 6f))
                        listOf(60.0, 70.0, 80.0, 90.0).forEach { t ->
                            drawLine(Color.Black.copy(alpha = 0.25f), Offset(x(t), 0f), Offset(x(t), size.height), strokeWidth = 1.dp.toPx())
                        }
                    }
                }
                Row {
                    Text(r.gradeClass.replaceFirstChar(Char::uppercase) + " · open-age equivalent ${clock(r.ageGradedTimeS)}",
                        style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant, modifier = Modifier.weight(1f))
                    if (r.sourceId != null) TextButton(onClick = { onOpenRun(r.sourceId) }) { Text("Run") }
                }
            }
        }
        Text("Scale 40–100%. Lines mark 60% local, 70% regional, 80% national and 90% world class.",
            style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
    }
}

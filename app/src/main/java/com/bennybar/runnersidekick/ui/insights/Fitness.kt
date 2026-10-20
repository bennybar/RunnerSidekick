package com.bennybar.runnersidekick.ui.insights

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.MonitorHeart
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Icon
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
import com.bennybar.runnersidekick.ui.components.SectionLabel
import com.bennybar.runnersidekick.ui.components.Tile
import com.bennybar.runnersidekick.ui.theme.LocalDataColors
import com.bennybar.runnersidekick.ui.theme.Tint
import com.bennybar.runnersidekick.ui.theme.ink

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
 * Garmin's view of your training (status, load against its range, race predictions) and your records.
 */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun FitnessSection(f: Fitness, onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    val g = f.garmin
    val recs = listOf("1k", "5k", "10k", "half").mapNotNull { k -> f.records[k]?.takeIf { it.best != null } }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (g != null || recs.isNotEmpty()) SectionLabel("Fitness")
        if (g != null) {
            Tile(tint = Tint.BLUE, spacing = 14.dp) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.MonitorHeart, null, Modifier.size(22.dp), tint = ink(Tint.BLUE))
                    Spacer(Modifier.width(10.dp))
                    Column {
                        Text("Garmin training status", style = MaterialTheme.typography.titleSmall)
                        Text("Calculated by Garmin", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
                    }
                }
                // VO2 max lives on Today and in Compare; this card is Garmin's view of your training
                g.trainingStatus?.let { st -> StatusBlock(st, Modifier.fillMaxWidth()) }
                g.trainingStatus?.let { st -> LoadBar(st) }
                g.racePredictions?.let { r ->
                    Text("Garmin race predictions", style = MaterialTheme.typography.titleSmall)
                    Row {
                        listOf("5K" to r.k5, "10K" to r.k10, "Half" to r.half, "Marathon" to r.marathon).forEach { (l, v) ->
                            Column(Modifier.weight(1f)) {
                                Text(l, style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant)
                                Text(clock(v), style = MaterialTheme.typography.titleLarge)
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
        if (recs.isNotEmpty()) {
            Group(tint = Tint.AMBER) {
                custom {
                    Text("Personal records", style = MaterialTheme.typography.titleSmall)
                    Text("Fastest segment inside any synced run", style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant)
                }
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
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Training status", style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Surface(shape = RoundedCornerShape(12.dp),
                color = if (warn) Tint.ORANGE.hue.copy(alpha = 0.28f) else cs.surfaceContainer.copy(alpha = 0.75f)) {
                Text(label, style = MaterialTheme.typography.titleLarge, color = if (warn) ink(Tint.ORANGE) else cs.onSurface,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
            }
            Spacer(Modifier.width(10.dp))
            st.since?.let { Text("since ${Format.shortDate(it)}", style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant) }
        }
    }
}

/** Garmin's acute load against Garmin's own optimal range for you. The ratio between them is not shown. */
@Composable
private fun LoadBar(st: TrainingStatus) {
    val acute = st.acuteLoad ?: return
    val lo = st.chronicMin ?: return
    val hi = st.chronicMax ?: return
    val cs = MaterialTheme.colorScheme
    val accent = ink(Tint.BLUE)
    val attention = LocalDataColors.current.attention
    val top = maxOf(acute, hi) * 1.15
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Acute load ${acute.toInt()} · Garmin's optimal range ${lo.toInt()}–${hi.toInt()}",
            style = MaterialTheme.typography.titleSmall)
        Canvas(Modifier.fillMaxWidth().height(18.dp).semantics {
            contentDescription = "Acute load ${acute.toInt()}, Garmin optimal range ${lo.toInt()} to ${hi.toInt()}"
        }) {
            fun x(v: Double) = (v / top * size.width).toFloat()
            drawRoundRect(cs.onSurface.copy(alpha = 0.08f), Offset.Zero, size, CornerRadius(20f, 20f))
            drawRoundRect(accent.copy(alpha = 0.35f), Offset(x(lo), 0f), Size(x(hi) - x(lo), size.height), CornerRadius(20f, 20f))
            drawCircle(if (acute > hi) attention else accent, size.height * 0.7f, Offset(x(acute), size.height / 2))
        }
        Text(if (acute > hi) "Above Garmin's optimal range" else if (acute < lo) "Below Garmin's optimal range" else "Inside Garmin's optimal range",
            style = MaterialTheme.typography.labelMedium, color = if (acute > hi) attention else cs.onSurfaceVariant)
    }
}

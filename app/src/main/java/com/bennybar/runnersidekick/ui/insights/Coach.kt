package com.bennybar.runnersidekick.ui.insights

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Bedtime
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.FitnessCenter
import androidx.compose.material.icons.outlined.Psychology
import androidx.compose.material.icons.outlined.Repeat
import androidx.compose.material.icons.outlined.Speed
import androidx.compose.material3.AssistChip
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LoadingIndicator
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.data.remote.CoachView
import com.bennybar.runnersidekick.data.remote.Insight
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.components.ShapeBadge
import com.bennybar.runnersidekick.ui.theme.accentFor

/** AI coach: cross-domain insights and recommendations written from the deterministic data. Every item cites its evidence. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun CoachCard(view: CoachView, loading: Boolean, insights: List<Insight>, onOpenRun: (String) -> Unit, onOpenInsight: (Insight) -> Unit) {
    val cs = MaterialTheme.colorScheme
    val shown = if (view.status == "ok") view else view.previous?.takeIf { it.status == "ok" }
    when {
        view.status == "disabled" -> return
        shown == null && (view.status == "pending" || loading) -> Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            LoadingIndicator(Modifier.size(32.dp))
            Spacer(Modifier.width(8.dp))
            Text("Your AI coach is reading your data…", style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
        }
        shown == null -> Text(
            when (view.status) {
                "not_configured" -> "AI coach is off: add your own OpenAI key in Settings to turn it on."
                "budget_exceeded" -> "AI coach has reached today's limit. The deterministic insights below are complete."
                else -> "AI coach couldn't produce a checked analysis this time. The insights below are complete."
            },
            style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant, modifier = Modifier.padding(horizontal = 4.dp),
        )
        else -> Surface(shape = MaterialTheme.shapes.extraLarge, color = cs.surfaceContainerHigh, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    ShapeBadge(Icons.Outlined.Psychology, MaterialShapes.Flower, Modifier.size(44.dp), container = cs.tertiary, content = cs.onTertiary)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("AI coach", style = MaterialTheme.typography.titleMedium)
                        Text(when {
                            view.status == "pending" || loading -> "Updating with your latest data…"
                            shown !== view -> "From an earlier analysis · ${Format.ago(runCatching { java.time.Instant.parse(shown.generatedAt) }.getOrNull())}"
                            else -> "Across running, sleep, recovery and habits"
                        },
                            style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant)
                    }
                    if (view.status == "pending" || loading) LoadingIndicator(Modifier.size(28.dp))
                }
                shown.tldr?.let { Tldr(it) }
                // Compact by default: the one line plus point titles; the full analysis on request
                var full by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf(false) }
                if (!full) {
                    // Two findings and the first thing to try; the rest is under "Show full analysis"
                    (shown.insights.take(2).map { it.title } + shown.recommendations.take(1).map { "Try: ${it.title}" }).forEach { t ->
                        Text("• $t", style = MaterialTheme.typography.bodyMedium)
                    }
                    androidx.compose.material3.TextButton(onClick = { full = true }) { Text("Show full analysis") }
                }
                if (full) shown.summary?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
                if (full && shown.insights.isNotEmpty()) {
                    HorizontalDivider()
                    Text("What stands out", style = MaterialTheme.typography.titleSmall, color = cs.primary)
                    shown.insights.forEach { i ->
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(i.title, style = MaterialTheme.typography.titleMedium)
                            Text(i.text, style = MaterialTheme.typography.bodyMedium)
                            Text("${i.confidence.replaceFirstChar(Char::uppercase)} confidence", style = MaterialTheme.typography.labelSmall,
                                color = cs.onSurfaceVariant)
                            EvidenceChips(i.evidenceIds, shown, insights, onOpenRun, onOpenInsight)
                        }
                    }
                }
                if (full && shown.recommendations.isNotEmpty()) {
                    HorizontalDivider()
                    Text("Try this", style = MaterialTheme.typography.titleSmall, color = cs.primary)
                    shown.recommendations.forEach { r ->
                        val accent = accentFor(r.category)
                        Row(verticalAlignment = Alignment.Top) {
                            ShapeBadge(recIcon(r.category), MaterialShapes.Cookie6Sided, Modifier.size(36.dp), iconSize = 18.dp,
                                container = accent?.container ?: cs.secondaryContainer, content = accent?.content ?: cs.onSecondaryContainer)
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text(r.title, style = MaterialTheme.typography.titleMedium)
                                Text(r.text, style = MaterialTheme.typography.bodyMedium)
                                Text("Why: ${r.why}", style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
                                EvidenceChips(r.evidenceIds, shown, insights, onOpenRun, onOpenInsight)
                            }
                        }
                    }
                }
                Text(listOfNotNull("Written by AI (${shown.model ?: "OpenAI"}) from your data", if (shown.keySource == "user") "your key" else null,
                    "numbers come from the app", "guidance, not medical advice").joinToString(" · "),
                    style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            }
        }
    }
}

private fun recIcon(category: String) = when (category) {
    "sleep" -> Icons.Outlined.Bedtime
    "recovery" -> Icons.Outlined.Favorite
    "pacing" -> Icons.Outlined.Speed
    "habits" -> Icons.Outlined.Repeat
    else -> Icons.Outlined.FitnessCenter
}

/** Chips only for evidence the app can open: runs and deterministic insights. */
@Composable
private fun EvidenceChips(ids: List<String>, v: CoachView, insights: List<Insight>, onOpenRun: (String) -> Unit, onOpenInsight: (Insight) -> Unit) {
    val chips = ids.distinct().mapNotNull { id ->
        val t = v.targets[id] ?: return@mapNotNull null
        when (t.type) {
            "run" -> t.id?.let { rid -> ("Run" + (t.date?.let { " · ${Format.shortDate(it)}" } ?: "")) to { onOpenRun(rid) } }
            "insight" -> insights.firstOrNull { it.id == t.id }?.let { i -> i.question to { onOpenInsight(i) } }
            else -> null
        }
    }.take(3)
    if (chips.isEmpty()) return
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        chips.forEach { (label, open) ->
            AssistChip(onClick = open, label = { Text(label, maxLines = 1, overflow = TextOverflow.Ellipsis) }, modifier = Modifier.widthIn(max = 280.dp))
        }
    }
}

/** The one line to read if you read nothing else. */
@Composable
fun Tldr(text: String) {
    val cs = MaterialTheme.colorScheme
    Surface(shape = MaterialTheme.shapes.medium, color = cs.tertiaryContainer, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("TL;DR", style = MaterialTheme.typography.labelLarge, color = cs.tertiary)
            Spacer(Modifier.width(10.dp))
            Text(text, style = MaterialTheme.typography.titleMedium, color = cs.onTertiaryContainer)
        }
    }
}

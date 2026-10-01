package com.bennybar.runnersidekick.ui.today

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CenterFocusStrong
import androidx.compose.material.icons.outlined.EventNote
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.data.remote.DayPlan
import com.bennybar.runnersidekick.data.remote.FocusState
import com.bennybar.runnersidekick.data.remote.RunIntent
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.ShapeBadge

val PLAN_KINDS = listOf("rest" to "Rest", "easy" to "Easy", "long" to "Long", "tempo" to "Tempo", "intervals" to "Intervals", "race" to "Race")
private val MINUTES = listOf(20, 30, 45, 60, 90)

/** "What's the plan today?": the suggestion above it speaks to whatever is chosen here. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun PlanCard(plan: DayPlan?, onSet: (String?, Int?) -> Unit) {
    val cs = MaterialTheme.colorScheme
    Surface(shape = MaterialTheme.shapes.large, color = cs.surfaceContainer, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ShapeBadge(Icons.Outlined.EventNote, MaterialShapes.Cookie4Sided, Modifier.size(36.dp))
                Spacer(Modifier.width(12.dp))
                Text(if (plan == null) "What's the plan today?" else "Today's plan", style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f))
                if (plan != null) TextButton(onClick = { onSet(null, null) }) { Text("Clear") }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                PLAN_KINDS.forEach { (k, l) -> FilterChip(selected = plan?.kind == k, onClick = { onSet(k, plan?.minutes) }, label = { Text(l) }) }
            }
            if (plan != null && plan.kind != "rest") {
                Text("About how long?", style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    MINUTES.forEach { m -> FilterChip(selected = plan.minutes == m, onClick = { onSet(plan.kind, if (plan.minutes == m) null else m) },
                        label = { Text("$m min") }) }
                }
            }
        }
    }
}

private fun statusLabel(s: String?) = when (s) {
    "achieved" -> "Done"
    "partly" -> "Partly"
    "missed" -> "Not this time"
    "over" -> "Above target"
    "off_track" -> "Off track"
    "unavailable" -> "Can't measure"
    else -> "In progress"
}

/** One focus for the week, chosen from data-based suggestions, then measured on the week's runs. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun FocusCard(state: FocusState, onChoose: (String) -> Unit, onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    val cur = state.current
    var changing by remember { mutableStateOf(false) }
    if (cur == null || changing) {
        Group(title = "Choose this week's focus") {
            state.lastWeek?.let { lw -> row("Last week: ${lw.title}", supporting = "${statusLabel(lw.status)}. ${lw.summary ?: ""}") }
            state.options.forEach { o ->
                row(o.title, supporting = o.reason, icon = Icons.Outlined.CenterFocusStrong, iconShape = MaterialShapes.Sunny,
                    onClick = { changing = false; onChoose(o.kind) })
            }
        }
        return
    }
    Surface(shape = MaterialTheme.shapes.extraLarge, color = cs.secondaryContainer, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ShapeBadge(Icons.Outlined.CenterFocusStrong, MaterialShapes.Sunny, Modifier.size(40.dp), container = cs.secondary, content = cs.onSecondary)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (cur.auto) "This week's focus · picked for you" else "This week's focus", style = MaterialTheme.typography.labelLarge,
                        color = cs.onSecondaryContainer)
                    Text(cur.title, style = MaterialTheme.typography.titleLarge, color = cs.onSecondaryContainer)
                }
                Surface(shape = MaterialTheme.shapes.small, color = if (cur.status == "achieved") cs.primary else cs.surface) {
                    Text(statusLabel(cur.status), style = MaterialTheme.typography.labelLarge,
                        color = if (cur.status == "achieved") cs.onPrimary else cs.onSurface, modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp))
                }
            }
            cur.summary?.let { Text(it, style = MaterialTheme.typography.bodyLarge, color = cs.onSecondaryContainer) }
            cur.target?.let { Text("Target: $it", style = MaterialTheme.typography.bodySmall, color = cs.onSecondaryContainer.copy(alpha = 0.8f)) }
            cur.felt?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = cs.onSecondaryContainer.copy(alpha = 0.8f)) }
            val runs = cur.runs.filter { it.sourceId != null }
            if (runs.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                runs.forEach { r ->
                    FilterChip(selected = r.met, onClick = { r.sourceId?.let(onOpenRun) },
                        label = { Text(java.time.LocalDate.parse(r.date).dayOfWeek.name.take(3).lowercase().replaceFirstChar(Char::uppercase) +
                            if (r.met) " ✓" else "") })
                }
            }
            state.lastWeek?.let { lw ->
                Text("Last week (${lw.title.lowercase()}): ${statusLabel(lw.status).lowercase()}. ${lw.summary ?: ""}",
                    style = MaterialTheme.typography.bodySmall, color = cs.onSecondaryContainer.copy(alpha = 0.8f))
            }
            if (state.options.size > 1) TextButton(onClick = { changing = true }) { Text("Change") }
        }
    }
}

val INTENT_KINDS = listOf("easy" to "Easy", "recovery" to "Recovery", "long" to "Long", "tempo" to "Tempo", "intervals" to "Intervals",
    "race" to "Race", "other" to "Other")

/** "What was this run meant to be?" plus a private note (never sent to AI). */
@Composable
fun IntentPicker(intent: RunIntent?, onSave: (String, String?) -> Unit) {
    var note by remember(intent?.note) { mutableStateOf(intent?.note ?: "") }
    var kind by remember(intent?.kind) { mutableStateOf(intent?.kind) }
    // An inferred kind needs no answer; it stays a one-line summary unless the runner wants to correct it
    var open by remember(intent?.source) { mutableStateOf(intent?.source != "inferred") }
    if (!open) {
        Group(title = "Run type") {
            row("Looks like: ${INTENT_KINDS.firstOrNull { it.first == intent?.kind }?.second ?: intent?.kind}",
                supporting = "Inferred from pace and heart rate · tap to change", onClick = { open = true })
        }
        return
    }
    Group(title = "What was this run meant to be?") {
        custom {
            if (intent?.source == "plan") Text("Pre-filled from today's plan. Change it if it was something else.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp),
                modifier = Modifier.padding(top = 4.dp)) {
                INTENT_KINDS.forEach { (k, l) -> FilterChip(selected = kind == k, onClick = { kind = k }, label = { Text(l) }) }
            }
            OutlinedTextField(note, { note = it }, label = { Text("Note (private, never sent to AI)") }, maxLines = 3,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
            val changed = kind != null && (kind != intent?.kind || note != (intent?.note ?: "") || intent?.source in setOf("plan", "inferred"))
            FilledTonalButton(onClick = { kind?.let { onSave(it, note) } }, enabled = changed, modifier = Modifier.padding(top = 8.dp)) {
                Text(if (intent?.source == "user" && !changed) "Saved" else "Save")
            }
        }
    }
}

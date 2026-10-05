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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.rememberModalBottomSheetState
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

internal fun statusLabel(s: String?) = when (s) {
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

val INTENT_KINDS = listOf("recovery" to "Recovery", "easy" to "Easy", "steady" to "Steady aerobic", "long" to "Long run",
    "tempo" to "Tempo", "threshold" to "Threshold", "intervals" to "Intervals", "race" to "Race", "progression" to "Progression",
    "free" to "Free run", "other" to "Other")
private val EFFORTS = listOf("very_easy" to "Very easy", "easy" to "Easy", "easy_moderate" to "Easy-moderate", "moderate" to "Moderate",
    "moderate_hard" to "Moderate-hard", "hard" to "Hard", "very_hard" to "Very hard")
private val FEELS = listOf("great" to "Great", "good" to "Good", "okay" to "Okay", "poor" to "Poor", "very_poor" to "Very poor")
private val LIMITERS = listOf("none" to "None", "cardio" to "Cardio", "breathing" to "Breathing", "legs" to "Legs", "feet" to "Feet",
    "muscular_fatigue" to "Muscular fatigue", "heat" to "Heat", "humidity" to "Humidity", "hills" to "Hills", "illness" to "Illness",
    "pain" to "Pain", "gi" to "Stomach", "motivation" to "Motivation", "other" to "Other")
private val HEALTH = listOf("normal" to "Normal", "recovering" to "Recovering from illness", "mild_symptoms" to "Mild symptoms",
    "poor_sleep" to "Poor sleep", "fatigued" to "Fatigued", "sore" to "Sore", "other" to "Other")

private fun label(options: List<Pair<String, String>>, key: String?) = options.firstOrNull { it.first == key }?.second ?: key

/** The run's type as one line; tapping opens an optional sheet for what it was meant to be and how it went. Never asked for. */
@Composable
fun IntentPicker(intent: RunIntent?, onSave: (RunIntent) -> Unit) {
    var open by remember { mutableStateOf(false) }
    val stated = intent?.source == "user"
    val said = if (stated) listOfNotNull(intent?.feel?.let { "felt ${label(FEELS, it)?.lowercase()}" },
        intent?.limiter?.takeIf { it != "none" }?.let { "limited by ${label(LIMITERS, it)?.lowercase()}" }) else emptyList()
    Group(title = "Run type") {
        row(if (intent == null) "Not set" else (if (stated) "" else "Looks like: ") + label(INTENT_KINDS, intent.kind),
            supporting = when (intent?.source) {
                "user" -> (said.joinToString(" · ").replaceFirstChar { it.uppercase() }.ifEmpty { "Your run type" }) + " · tap to edit"
                "plan" -> "From today's plan · tap to change or add how it went"
                else -> "Inferred from pace and heart rate · tap to set it or add how it went"
            }, onClick = { open = true })
    }
    if (open) RunContextSheet(intent, onDismiss = { open = false }) { onSave(it); open = false }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RunContextSheet(intent: RunIntent?, onDismiss: () -> Unit, onSave: (RunIntent) -> Unit) {
    val stated = intent?.source == "user"
    var kind by remember { mutableStateOf(intent?.kind) }
    var target by remember { mutableStateOf(if (stated) intent?.target ?: "" else "") }
    var effort by remember { mutableStateOf(if (stated) intent?.effort else null) }
    var feel by remember { mutableStateOf(if (stated) intent?.feel else null) }
    var limiter by remember { mutableStateOf(if (stated) intent?.limiter else null) }
    var limiter2 by remember { mutableStateOf(if (stated) intent?.limiter2 else null) }
    var health by remember { mutableStateOf(if (stated) intent?.health else null) }
    var note by remember { mutableStateOf(if (stated) intent?.note ?: "" else "") }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("This run", style = MaterialTheme.typography.headlineSmall)
            Text("All optional. What you say here comes first in the run's advice, AI input and export; blanks are left out.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Choice("Meant to be", INTENT_KINDS, kind, optional = false) { kind = it }
            OutlinedTextField(target, { target = it.take(100) }, label = { Text("Target (e.g. HR ≤ 160, 5:30 /km)") }, singleLine = true,
                modifier = Modifier.fillMaxWidth())
            Choice("Perceived effort", EFFORTS, effort) { effort = it }
            Choice("Overall feel", FEELS, feel) { feel = it }
            Choice("What limited you", LIMITERS, limiter) { limiter = it }
            if (limiter != null && limiter != "none") Choice("Anything else", LIMITERS.filter { it.first != limiter }, limiter2) { limiter2 = it }
            Choice("Health", HEALTH, health) { health = it }
            OutlinedTextField(note, { note = it.take(500) }, label = { Text("Notes (private, never sent to AI)") }, maxLines = 4,
                modifier = Modifier.fillMaxWidth())
            FilledTonalButton(onClick = {
                kind?.let { onSave(RunIntent(it, note, "user", target, effort, feel, limiter, limiter2.takeIf { limiter != null && limiter != "none" }, health)) }
            }, enabled = kind != null) { Text("Save") }
        }
    }
}

/** One labelled row of chips; tapping the selected chip again clears an optional answer. */
@Composable
private fun Choice(title: String, options: List<Pair<String, String>>, selected: String?, optional: Boolean = true, onPick: (String?) -> Unit) {
    Column {
        Text(title, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 4.dp)) {
            options.forEach { (k, l) ->
                FilterChip(selected = selected == k, onClick = { onPick(if (selected == k && optional) null else k) }, label = { Text(l) })
            }
        }
    }
}

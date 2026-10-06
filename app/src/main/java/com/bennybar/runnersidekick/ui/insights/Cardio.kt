package com.bennybar.runnersidekick.ui.insights

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.MonitorHeart
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.data.remote.Cardio
import com.bennybar.runnersidekick.data.remote.CardioPart
import com.bennybar.runnersidekick.data.remote.SettingsDto
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.components.Group

/** One line per piece of evidence, in the Fitness details; the sheet has the rest. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun CardioCard(c: Cardio, onOpen: () -> Unit) {
    val parts = listOf(c.runs, c.garmin, c.questionnaire).filter { it.value != null }
    Group(title = "Cardio fitness (experimental)") {
        row(parts.joinToString(" · ") { "${short(it)} ${it.value!!.toInt()}" }.ifEmpty { "Not enough evidence yet" },
            supporting = listOfNotNull(c.runs.comparison?.headline ?: c.garmin.comparison?.headline,
                c.performance.value?.let { "Running performance: VDOT ${it.toInt()}" },
                "VO₂ max estimates side by side, each with its method").joinToString("\n"),
            icon = Icons.Outlined.MonitorHeart, iconShape = MaterialShapes.Flower, onClick = onOpen)
    }
}

private fun short(p: CardioPart) = when (p.id) { "runs" -> "Your runs"; "garmin" -> "Garmin"; "questionnaire" -> "Questionnaire"; else -> p.title }

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun CardioSheet(c: Cardio, answers: SettingsDto?, onSave: ((SettingsDto) -> SettingsDto) -> Unit, onOpenRun: (String) -> Unit,
                onDismiss: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    var editing by remember { mutableStateOf<String?>(null) }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("Cardio fitness", style = MaterialTheme.typography.headlineSmall)
            Text(c.basis, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
            listOf(c.runs, c.garmin, c.questionnaire, c.performance).forEach { p -> Evidence(p, onOpenRun) }
            if (c.notes.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("How they relate", style = MaterialTheme.typography.titleMedium)
                c.notes.forEach { Text(it, style = MaterialTheme.typography.bodyMedium) }
            }
            // The answers these estimates use, each with the day it was given
            Group(title = "Your answers") {
                val a = answers
                row("Activity level, last month", supporting = a?.activityPar?.let { "$it of 7" + (a.activityParAt?.let { d -> " · answered ${Format.shortDate(d)}" } ?: "") }
                    ?: "Not answered", onClick = { editing = "par" })
                row("Weight", supporting = c.inputs.weightKg?.let { "${fmt(it)} kg · " + from(c.inputs.weightFrom) } ?: "Not set",
                    onClick = { editing = "weight" })
                row("Height", supporting = c.inputs.heightCm?.let { "${fmt(it)} cm · " + from(c.inputs.heightFrom) } ?: "Not set",
                    onClick = { editing = "height" })
                row("Maximum heart rate", supporting = c.hrMax.value?.let { "${it.toInt()} bpm · ${c.hrMax.source}" } ?: "Not known yet",
                    onClick = { editing = "hrmax" })
            }
        }
    }
    when (editing) {
        "par" -> ParDialog(c, answers?.activityPar, onDismiss = { editing = null }) { v -> onSave { it.copy(activityPar = v) }; editing = null }
        "weight" -> NumberDialog("Weight (kg)", answers?.profileWeightKg, 30.0..250.0, "Clear (use Garmin's)",
            onDismiss = { editing = null }) { v -> onSave { it.copy(profileWeightKg = v) }; editing = null }
        "height" -> NumberDialog("Height (cm)", answers?.profileHeightCm, 100.0..250.0, "Clear (use Garmin's)",
            onDismiss = { editing = null }) { v -> onSave { it.copy(profileHeightCm = v) }; editing = null }
        "hrmax" -> NumberDialog("Maximum heart rate (bpm)", answers?.hrMax?.toDouble(), 120.0..230.0, "Clear (work it out from your runs)",
            hint = "Only if you know it from an all-out race finish or a test. Otherwise leave it: the app uses the higher of Garmin's setting " +
                "and the highest you've held for a minute.",
            onDismiss = { editing = null }) { v -> onSave { it.copy(hrMax = v?.toInt()) }; editing = null }
    }
}

private fun from(src: String?) = when {
    src == null -> "set by you"
    src.startsWith("from") -> src
    else -> "set ${runCatching { Format.shortDate(src) }.getOrDefault(src)}"
}

private fun fmt(v: Double) = if (v % 1.0 == 0.0) v.toInt().toString() else "%.1f".format(v)

@Composable
private fun Evidence(p: CardioPart, onOpenRun: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(p.title, style = MaterialTheme.typography.titleMedium)
        Row(verticalAlignment = Alignment.Bottom) {
            p.value?.let { Text("${it.toInt()}", style = MaterialTheme.typography.headlineMedium, color = cs.primary); Spacer(Modifier.width(10.dp)) }
            Text(p.headline ?: "", style = MaterialTheme.typography.bodyLarge)
        }
        p.comparison?.let { Text(listOfNotNull(it.headline, it.detail).joinToString(". "), style = MaterialTheme.typography.bodyMedium) }
        p.detail?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant) }
        p.sensitivity?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant) }
        p.leftOut?.takeIf { it.isNotEmpty() }?.let { lo ->
            Text("Left out: " + lo.entries.joinToString(", ") { (why, n) -> "$n $why" }, style = MaterialTheme.typography.bodySmall,
                color = cs.onSurfaceVariant)
        }
        if (p.points.isNotEmpty()) Text("Runs used: " + p.points.takeLast(8).joinToString(", ") { "${Format.shortDate(it.date)} ${it.value.toInt()}" },
            style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
        p.caveat?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant) }
        p.comparison?.source?.let { Text("Reference: $it", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant) }
        p.sourceId?.let { id -> TextButton(onClick = { onOpenRun(id) }, contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) { Text("Open the run") } }
    }
}

/** The NASA/JSC activity rating, with its published wording, for the previous month. */
@Composable
private fun ParDialog(c: Cardio, current: Int?, onDismiss: () -> Unit, onPick: (Int?) -> Unit) {
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Your activity, last month") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            c.parScale.forEach { o ->
                Row(Modifier.fillMaxWidth().selectable(o.value == current, role = Role.RadioButton) { onPick(o.value) }.padding(vertical = 6.dp),
                    verticalAlignment = Alignment.Top) {
                    RadioButton(selected = o.value == current, onClick = null)
                    Spacer(Modifier.width(10.dp))
                    Text("${o.value}. ${o.text}", style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }, confirmButton = { if (current != null) TextButton(onClick = { onPick(null) }) { Text("Clear") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Close") } })
}

@Composable
private fun NumberDialog(title: String, current: Double?, range: ClosedFloatingPointRange<Double>, clearLabel: String,
                         hint: String? = null, onDismiss: () -> Unit, onSave: (Double?) -> Unit) {
    var text by remember { mutableStateOf(current?.let { fmt(it) } ?: "") }
    val v = text.replace(',', '.').toDoubleOrNull()
    AlertDialog(onDismissRequest = onDismiss, title = { Text(title) }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            hint?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            OutlinedTextField(text, { text = it.take(5) }, singleLine = true, isError = text.isNotBlank() && (v == null || v !in range),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth())
            if (current != null) TextButton(onClick = { onSave(null) }) { Text(clearLabel) }
        }
    }, confirmButton = { TextButton(onClick = { onSave(v) }, enabled = v != null && v in range) { Text("Save") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
}

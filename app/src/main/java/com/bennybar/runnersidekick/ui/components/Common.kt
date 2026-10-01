package com.bennybar.runnersidekick.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.Science
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.data.remote.Finding
import com.bennybar.runnersidekick.ui.Format

@Composable
fun DemoBadge() {
    AssistChip(
        onClick = {}, enabled = true,
        label = { Text("Demo data") },
        leadingIcon = { Icon(Icons.Outlined.Science, null, Modifier.size(AssistChipDefaults.IconSize)) },
        colors = AssistChipDefaults.assistChipColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
            labelColor = MaterialTheme.colorScheme.onErrorContainer,
            leadingIconContentColor = MaterialTheme.colorScheme.onErrorContainer,
        ),
        border = null,
    )
}

@Composable
fun SectionHeader(text: String, modifier: Modifier = Modifier) {
    Text(
        text, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface,
        modifier = modifier.padding(top = 8.dp, bottom = 4.dp).semantics { heading() },
    )
}

@Composable
fun EmptyState(icon: ImageVector, title: String, body: String, modifier: Modifier = Modifier, action: @Composable (() -> Unit)? = null) {
    Column(modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Icon(icon, null, Modifier.size(48.dp), tint = MaterialTheme.colorScheme.primary)
        Text(title, style = MaterialTheme.typography.titleLarge, textAlign = TextAlign.Center)
        Text(body, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
        action?.invoke()
    }
}

@Composable
fun OfflineBanner(message: String) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Outlined.CloudOff, null, Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.width(8.dp))
        Text(message, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun StatTile(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.titleLarge)
    }
}

/** "Show why": the evidence behind a finding — value, personal range, sample size, dates, limitations, version. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EvidenceSheet(finding: Finding, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(finding.title, style = MaterialTheme.typography.headlineSmall)
            Text(finding.statement, style = MaterialTheme.typography.bodyLarge)
            finding.interpretation?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            HorizontalDivider()
            EvidenceRows {
                finding.observed?.value?.let { Row("Observed", Format.metricValue(finding.metric, it) + (finding.observed.date?.let { d -> " on ${Format.shortDate(d)}" } ?: "")) }
                finding.observed?.label?.let { Row("Garmin status", "$it (Garmin)") }
                finding.comparison?.let { c ->
                    if (c.median != null) {
                        Row("Your usual (median)", Format.metricValue(finding.metric, c.median))
                        if (c.q1 != null && c.q3 != null) Row("Typical range (middle 50%)", "${Format.metricValue(finding.metric, c.q1)} – ${Format.metricValue(finding.metric, c.q3)}")
                    }
                    if (c.kind == "prior_4_week_weekly_mean" && c.value != null) Row("Prior 4-week weekly average", Format.metricValue(finding.metric, c.value))
                    c.window?.takeIf { it.size == 2 }?.let { Row("Compared with", "${Format.shortDate(it[0])} – ${Format.shortDate(it[1])}") }
                }
                finding.delta?.abs?.let { if (finding.comparison?.median != null) Row("Difference", Format.signedDelta(finding.metric, it) + (finding.delta.pct?.let { p -> " (%+.0f%%)".format(p) } ?: "")) }
                finding.sampleSize?.let { Row("Sample size", "$it ${if (finding.category == "running") "records" else "days"}") }
                Row("Derived", if (finding.derived) "Yes — calculated by Runner Sidekick" else "No — as reported by the source")
                Row("Algorithm", finding.algorithmVersion)
            }
            if (finding.limitations.isNotEmpty()) {
                Text("Limitations", style = MaterialTheme.typography.titleSmall)
                finding.limitations.forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

class EvidenceRowsScope(private val col: ColumnScope) {
    @Composable
    fun Row(label: String, value: String) {
        androidx.compose.foundation.layout.Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
            Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
fun EvidenceRows(content: @Composable EvidenceRowsScope.() -> Unit) {
    Column { EvidenceRowsScope(this).content() }
}

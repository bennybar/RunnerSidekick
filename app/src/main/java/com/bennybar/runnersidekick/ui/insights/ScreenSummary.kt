package com.bennybar.runnersidekick.ui.insights

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.LoadingIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.data.remote.ScreenSummary
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.components.Tile

/** Today's AI summary of a screen (Compare, Trends). Hidden when AI is off; earlier summaries are labelled as such. */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun ScreenSummaryCard(s: ScreenSummary?) {
    val cs = MaterialTheme.colorScheme
    if (s == null || s.status in setOf("disabled", "not_configured") || !com.bennybar.runnersidekick.ui.components.LocalAiEnabled.current) return
    val shown = if (s.status == "ok") s else s.previous?.takeIf { it.status == "ok" }
    if (shown == null) {
        if (s.status == "pending") Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            LoadingIndicator(Modifier.size(28.dp))
            Spacer(Modifier.width(8.dp))
            Text("Writing today's AI summary…", style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
        }
        return
    }
    Tile {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.AutoAwesome, null, Modifier.size(20.dp))
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text("Today's summary · AI", style = MaterialTheme.typography.titleSmall)
                Text(if (shown !== s) "From ${shown.localDate?.let { Format.shortDate(it) } ?: "earlier"} · updating…"
                    else "Written by AI from this screen · numbers come from the app",
                    style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant)
            }
            if (s.status == "pending") LoadingIndicator(Modifier.size(24.dp))
        }
        // The takeaway on its own; the rest on tap
        var more by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf(false) }
        val lines = if (more) shown.sentences else shown.sentences.take(1)
        Text(lines.joinToString(" ") { it.text }, style = MaterialTheme.typography.bodyLarge)
        if (shown.sentences.size > 1) androidx.compose.material3.TextButton(onClick = { more = !more }) { Text(if (more) "Less" else "More") }
    }
}

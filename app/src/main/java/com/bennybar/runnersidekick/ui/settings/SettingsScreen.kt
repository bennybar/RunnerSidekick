package com.bennybar.runnersidekick.ui.settings

import android.Manifest
import androidx.compose.ui.Alignment
import androidx.compose.foundation.layout.Spacer
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Key
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.EventNote
import androidx.compose.material.icons.outlined.Palette
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.material3.OutlinedButton
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.border
import androidx.compose.foundation.background
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material3.Icon
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Watch
import androidx.compose.material.icons.outlined.CloudDone
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.FileDownload
import androidx.compose.material.icons.outlined.History
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material.icons.outlined.Straighten
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.bennybar.runnersidekick.data.Repository
import com.bennybar.runnersidekick.data.local.Units
import com.bennybar.runnersidekick.data.remote.SettingsDto
import com.bennybar.runnersidekick.ui.BaseVm
import com.bennybar.runnersidekick.ui.Format
import com.bennybar.runnersidekick.ui.components.DemoBadge
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.factory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant

class SettingsVm(repo: Repository) : BaseVm(repo) {
    val status = repo.status.state(null)
    val me = repo.me.state(null)

    fun signOut() = launchIo { repo.signOut() }
    fun deleteAccount() = launchIo { repo.deleteAccount() }
    fun disconnectGarmin() = launchIo { repo.disconnectGarmin(); message.value = "Garmin disconnected" }
    fun connectGarmin(ctx: android.content.Context) = launchIo {
        val url = repo.garminAuthorizeUrl()
        androidx.browser.customtabs.CustomTabsIntent.Builder().build().launchUrl(ctx, android.net.Uri.parse(url))
    }
    val remote = MutableStateFlow<SettingsDto?>(null)
    val message = MutableStateFlow<String?>(null)

    init { loadRemote() }

    fun loadRemote() = launchIo { remote.value = repo.remoteSettings() }

    fun saveBackend(url: String, token: String) = launchIo {
        repo.settings.setBackend(url, token)
        repo.refreshAll()
        remote.value = repo.remoteSettings()
        message.value = "Connected"
    }

    fun saveRemote(s: SettingsDto) = launchIo {
        remote.value = repo.saveRemoteSettings(s)
        repo.refreshAll()
        message.value = "Saved"
    }

    fun setOwnAiKey(key: String?) = launchIo {
        repo.settings.setOwnAiKey(key)
        message.value = if (key.isNullOrBlank()) "Your key was removed" else "Key saved on this phone"
    }

    fun setUnits(u: Units) = viewModelScope.launch { repo.settings.setUnits(u) }
    fun setTheme(t: com.bennybar.runnersidekick.ui.theme.ThemeChoice) = viewModelScope.launch { repo.settings.setTheme(t.name) }
    fun setAppearance(a: com.bennybar.runnersidekick.ui.theme.Appearance) = viewModelScope.launch { repo.settings.setAppearance(a.name) }
    fun setNotifications(on: Boolean) = viewModelScope.launch { repo.settings.setNotificationsEnabled(on) }
    fun setBackgroundRefresh(on: Boolean) = viewModelScope.launch { repo.settings.setBackgroundRefresh(on) }

    fun export(ctx: android.content.Context, uri: Uri) = launchIo {
        val body = repo.exportJson()
        withContext(Dispatchers.IO) { ctx.contentResolver.openOutputStream(uri)?.use { it.write(body.toByteArray()) } }
        message.value = "Exported"
    }

    fun deleteRemote(scope: String) = launchIo { repo.deleteRemote(scope); message.value = "Deleted" }
    fun clearLocal() = launchIo { repo.clearLocal(includeCheckins = false); message.value = "Local cache cleared" }
}

private val DAYS = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
private val GOALS = listOf("consistency" to "Consistency", "distance" to "Go longer", "performance" to "Get faster", "health" to "Health")
private val RACES = listOf("5k" to "5K", "10k" to "10K", "half" to "Half", "marathon" to "Marathon")
private fun hms(s: Int) = if (s >= 3600) "%d:%02d:%02d".format(s / 3600, s % 3600 / 60, s % 60) else "%d:%02d".format(s / 60, s % 60)

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun SettingsScreen(vm: SettingsVm = viewModel(factory = factory(::SettingsVm))) {
    val local by vm.settings.collectAsStateWithLifecycle()
    val me by vm.me.collectAsStateWithLifecycle()
    val status by vm.status.collectAsStateWithLifecycle()
    val remote by vm.remote.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val message by vm.message.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val ctx = LocalContext.current
    var confirm by remember { mutableStateOf<String?>(null) }
    var open by rememberSaveable { mutableStateOf<String?>(null) }  // which section sheet is open
    val exporter = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let { vm.export(ctx, it) } }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        vm.setNotifications(granted)
        if (!granted) vm.message.value = "Notifications permission denied"
    }
    LaunchedEffect(error) { error?.let { snackbar.showSnackbar(it); vm.clearError() } }
    LaunchedEffect(message) { message?.let { snackbar.showSnackbar(it); vm.message.value = null } }
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        topBar = { LargeTopAppBar(title = { Text("Settings") }, scrollBehavior = scroll, actions = { if (status?.value?.synthetic == true) DemoBadge() }) },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        LazyColumn(Modifier.padding(padding).fillMaxSize(), contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp + com.bennybar.runnersidekick.ui.components.LocalNavBarPadding.current),
            verticalArrangement = Arrangement.spacedBy(20.dp)) {
            // Only a Garmin problem is shown up here; everything else lives in its own section
            status?.value?.connection?.state?.takeIf { it == "reauth_required" || it == "not_configured" || it == "error" }?.let { st ->
                item {
                    Group {
                        row(if (st == "error") "Garmin sync failing" else "Garmin sign-in needed",
                            supporting = if (st == "error") (status?.value?.connection?.detail ?: "The last sync failed; it retries on its own.")
                                else "The server's Garmin sign-in has expired and has to be renewed there. Syncing is paused until then.",
                            icon = Icons.Outlined.CloudOff, iconShape = MaterialShapes.Burst)
                    }
                }
            }
            item {
                val m = me?.value
                val s = status?.value
                val g = s?.garminOfficial
                Group(title = "Account") {
                    row(m?.email ?: if (m?.role == "owner") "Owner (signed in with a device token)" else "Signed in",
                        supporting = when (m?.role) { "owner" -> "Server owner"; null -> null; else -> "Member" },
                        icon = Icons.Outlined.AccountCircle, iconShape = MaterialShapes.Circle)
                    row("Garmin", supporting = when {
                        s?.synthetic == true -> "Demo data source"
                        g?.connected == true -> "Connected with Garmin's official sign-in. " + (g.dataImport ?: "")
                        s?.connection?.state == "connected" -> "Connected · last fetch ${Format.ago(s.connection.lastSuccessAt?.let { t -> runCatching { Instant.parse(t) }.getOrNull() })}" +
                            (s.backfill?.oldestDone?.let { d -> " · history from $d" } ?: "")
                        g?.available == true -> "Not connected"
                        else -> "Garmin sign-in for members opens once Garmin approves this app"
                    }, icon = Icons.Outlined.Watch, iconShape = MaterialShapes.Cookie9Sided,
                        trailing = when {
                            g?.connected == true -> ({ TextButton(onClick = vm::disconnectGarmin) { Text("Disconnect") } })
                            g?.available == true -> ({ FilledTonalButton(onClick = { vm.connectGarmin(ctx) }) { Text("Connect") } })
                            else -> null
                        })
                    row("Server", supporting = local?.backendUrl ?: "", icon = if (s?.connection?.state == "connected") Icons.Outlined.CloudDone else Icons.Outlined.CloudOff,
                        iconShape = MaterialShapes.Cookie4Sided, onClick = { open = "backend" })
                    row("Sign out", supporting = "Removes the token and cached data from this phone", icon = Icons.AutoMirrored.Outlined.Logout,
                        iconShape = MaterialShapes.Cookie4Sided, onClick = { confirm = "signout" })
                    if (m?.role == "member") row("Delete my account", supporting = "Deletes all your data on the server and disconnects Garmin",
                        icon = Icons.Outlined.DeleteOutline, iconShape = MaterialShapes.Burst, onClick = { confirm = "account" })
                }
            }
            item {
                Group(title = "Appearance") {
                    row("Theme", supporting = com.bennybar.runnersidekick.ui.theme.ThemeChoice.of(local?.theme).label + " · " +
                        com.bennybar.runnersidekick.ui.theme.Appearance.of(local?.appearance).label,
                        icon = Icons.Outlined.Palette, iconShape = MaterialShapes.Flower, onClick = { open = "theme" })
                    custom {
                        Text("Units", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(bottom = 8.dp))
                        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                            Units.entries.forEachIndexed { i, u ->
                                SegmentedButton(local?.units == u, { vm.setUnits(u) }, SegmentedButtonDefaults.itemShape(i, 2),
                                    icon = {}) { Text(if (u == Units.METRIC) "Metric (km)" else "Imperial (mi)") }
                            }
                        }
                    }
                }
            }
            remote?.let { r ->
                item {
                    Group(title = "Training") {
                        row("Training", supporting = listOfNotNull(
                                r.runningDays.sorted().joinToString(", ") { DAYS[it] }.ifEmpty { "No running days" },
                                GOALS.firstOrNull { it.first == r.goalType }?.second?.let { "goal: ${it.lowercase()}" },
                                r.availableMinutes?.let { "$it min a run" }).joinToString(" · "),
                            icon = Icons.Outlined.EventNote, iconShape = MaterialShapes.Cookie9Sided, onClick = { open = "training" })
                        row("Race", supporting = r.raceDate?.let { d ->
                                listOfNotNull(r.raceName, RACES.firstOrNull { it.first == r.raceDistance }?.second, Format.shortDate(d),
                                    r.raceTargetS?.let { "target ${hms(it)}" }).joinToString(" · ") } ?: "No race set",
                            icon = Icons.Outlined.EmojiEvents, iconShape = MaterialShapes.Sunny, onClick = { open = "race" })
                        row("About you", supporting = listOfNotNull(
                                (r.profileSex ?: r.profileDetected?.sex)?.replaceFirstChar(Char::uppercase),
                                (r.profileBirthDate ?: r.profileDetected?.birthDate)?.let { "born $it" },
                                if (r.profileSex == null && r.profileBirthDate == null) "from Garmin" else null).joinToString(" · ").ifEmpty { "Not set" },
                            icon = Icons.Outlined.AccountCircle, iconShape = MaterialShapes.Circle, onClick = { open = "about" })
                    }
                }
                item {
                    Group(title = "Notifications") {
                        row("Morning briefing and run reports", supporting = "Best effort: Android decides exact timing.",
                            icon = Icons.Outlined.Notifications, iconShape = MaterialShapes.Sunny,
                            trailing = {
                                Switch(checked = local?.notificationsEnabled == true, onCheckedChange = { on ->
                                    if (on) permission.launch(Manifest.permission.POST_NOTIFICATIONS) else vm.setNotifications(false)
                                })
                            })
                        row("Background refresh", supporting = if (local?.notificationsEnabled == true)
                                "Already on with notifications (about hourly)."
                            else "Keeps today's briefing and your runs ready offline, about every 3 hours. Garmin itself syncs on the server either way.",
                            icon = Icons.Outlined.Sync, iconShape = MaterialShapes.Cookie9Sided,
                            trailing = {
                                Switch(checked = local?.notificationsEnabled == true || local?.backgroundRefresh == true,
                                    enabled = local?.notificationsEnabled != true, onCheckedChange = vm::setBackgroundRefresh)
                            })
                        row("Morning window", supporting = "${r.morningWindowStart}–${r.morningWindowEnd} · the briefing comes once your sleep has synced, " +
                            "or at the end of the window as provisional", icon = Icons.Outlined.Schedule, iconShape = MaterialShapes.Cookie4Sided,
                            onClick = { open = "window" })
                    }
                }
                item {
                    val ownKey = local?.hasOwnAiKey == true
                    Group(title = "AI coach (optional)") {
                        row("AI coach and summaries", icon = Icons.Outlined.AutoAwesome, iconShape = MaterialShapes.Flower,
                            supporting = when {
                                ownKey -> "Uses OpenAI with your own key."
                                r.aiAvailable -> "Uses OpenAI. Off by default."
                                else -> "Add your own OpenAI key to use it."
                            },
                            trailing = { Switch(checked = r.aiEnabled, enabled = !busy && (r.aiAvailable || ownKey || r.aiEnabled),
                                onCheckedChange = { vm.saveRemote(r.copy(aiEnabled = it)) }) })
                        if (r.aiEnabled) row("Model", supporting = r.aiModel, icon = Icons.Outlined.Tune, iconShape = MaterialShapes.Cookie4Sided,
                            onClick = { open = "model" })
                        row("Your own OpenAI key", supporting = if (ownKey) "Saved on this phone" else "Optional", icon = Icons.Outlined.Key,
                            iconShape = MaterialShapes.Cookie4Sided, onClick = { open = "key" })
                        row("What's sent to the AI", supporting = "Findings and numbers only; never your notes, run names or routes",
                            icon = Icons.Outlined.Info, iconShape = MaterialShapes.Circle, onClick = { open = "ai_info" })
                    }
                }
            }
            item {
                Group(title = "Your data") {
                    row("Export all data", supporting = "JSON file with records, check-ins and reports", icon = Icons.Outlined.FileDownload,
                        iconShape = MaterialShapes.Cookie4Sided, onClick = { exporter.launch("runner-sidekick-export.json") })
                    row("Clear this phone's cache", supporting = "Unsent check-ins are kept", icon = Icons.Outlined.History,
                        iconShape = MaterialShapes.Cookie4Sided, onClick = { confirm = "local" })
                    row("Delete raw Garmin payloads", supporting = "On the backend. Records and reports stay.", icon = Icons.Outlined.DeleteOutline,
                        iconShape = MaterialShapes.Cookie4Sided, onClick = { confirm = "raw" })
                    row("Delete everything on the backend", supporting = "Records, reports, check-ins and settings", icon = Icons.Outlined.DeleteOutline,
                        iconShape = MaterialShapes.Burst, onClick = { confirm = "all" })
                    custom {
                        Text("Health data lives on your backend and in this phone's cache. Android backup and device transfer are turned off for this app; " +
                            "your server's own backups may still include its data folder.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            item {
                Group(title = "About") {
                    row("Runner Sidekick", supporting = "Guidance only, not medical advice. Garmin data via an unofficial, read-only connector.",
                        icon = Icons.Outlined.Straighten, iconShape = MaterialShapes.Circle)
                }
            }
        }
    }
    val r = remote
    when (open) {
        "backend" -> BackendSheet(local?.backendUrl ?: "", local?.hasToken == true, busy, onClose = { open = null }) { url, token ->
            vm.saveBackend(url, token); open = null }
        "theme" -> SectionSheet("Theme", dirty = false, canSave = false, onSave = {}, onClose = { open = null }) {
            ThemePicker(local?.theme, local?.appearance, vm::setTheme, vm::setAppearance) }
        "training" -> r?.let { TrainingSheet(it, busy, onClose = { open = null }) { s -> vm.saveRemote(s); open = null } }
        "race" -> r?.let { RaceSheet(it, busy, onClose = { open = null }) { s -> vm.saveRemote(s); open = null } }
        "about" -> r?.let { AboutYouSheet(it, busy, onClose = { open = null }) { s -> vm.saveRemote(s); open = null } }
        "window" -> r?.let { WindowSheet(it, busy, onClose = { open = null }) { s -> vm.saveRemote(s); open = null } }
        "model" -> r?.let { ModelDialog(it, local?.hasOwnAiKey == true, onClose = { open = null }) { m -> vm.saveRemote(it.copy(aiModel = m)); open = null } }
        "key" -> KeySheet(local?.hasOwnAiKey == true, onClose = { open = null }) { k -> vm.setOwnAiKey(k); open = null }
        "ai_info" -> SectionSheet("What's sent to the AI", dirty = false, canSave = false, onSave = {}, onClose = { open = null }) {
            Text("New runs get AI input automatically after a sync: only runs from the last 36 hours, at most 2 per sync, never for older " +
                "history, and never using the last 5 AI calls of the day. Older runs: tap Get AI input. This uses the server's key; with only " +
                "your own key, input is written when you ask.", style = MaterialTheme.typography.bodyMedium)
            Text("What is sent: finding titles, statuses, values and ranges. Never your notes, run names, routes or identifiers. Numbers in " +
                "summaries are filled in from the report, not written by the AI. If its output doesn't pass checks, nothing is shown.",
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    confirm?.let { scope ->
        AlertDialog(
            onDismissRequest = { confirm = null },
            title = { Text(when (scope) { "signout" -> "Sign out?"; "account" -> "Delete your account?"; else -> "Delete data?" }) },
            text = {
                Text(when (scope) {
                    "local" -> "Removes cached reports and runs from this phone. Unsent check-ins are kept."
                    "raw" -> "Removes stored Garmin source payloads. Normalised records and reports stay."
                    "signout" -> "You can sign in again any time. Unsent check-ins stay on this phone."
                    "account" -> "Permanently deletes all your health data, reports and check-ins on the server, and disconnects Garmin. This can't be undone."
                    else -> "Removes all records, reports, check-ins and settings from the backend and this phone. Garmin sign-in tokens aren't affected. This can't be undone."
                })
            },
            confirmButton = {
                TextButton(onClick = {
                    when (scope) {
                        "local" -> vm.clearLocal()
                        "signout" -> vm.signOut()
                        "account" -> vm.deleteAccount()
                        else -> vm.deleteRemote(scope)
                    }
                    confirm = null
                }) { Text(if (scope == "signout") "Sign out" else "Delete") }
            },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("Cancel") } },
        )
    }
}


/** Colour theme as swatches (each drawn from its own scheme), and light, dark or system. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun ThemePicker(theme: String?, appearance: String?, onTheme: (com.bennybar.runnersidekick.ui.theme.ThemeChoice) -> Unit,
                        onAppearance: (com.bennybar.runnersidekick.ui.theme.Appearance) -> Unit) {
    val current = com.bennybar.runnersidekick.ui.theme.ThemeChoice.of(theme)
    val cs = MaterialTheme.colorScheme
    Text("Theme", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(bottom = 10.dp))
    androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        com.bennybar.runnersidekick.ui.theme.ThemeChoice.entries.forEach { c ->
            val selected = c == current
            Column(horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
                modifier = Modifier.width(56.dp).selectable(selected, role = androidx.compose.ui.semantics.Role.RadioButton) { onTheme(c) }) {
                androidx.compose.foundation.layout.Box(Modifier.size(52.dp)
                    .border(if (selected) 3.dp else 0.dp, if (selected) cs.onSurface else androidx.compose.ui.graphics.Color.Transparent, androidx.compose.foundation.shape.CircleShape)
                    .padding(5.dp)
                    .background(c.seed?.let { androidx.compose.ui.graphics.Brush.linearGradient(listOf(it, it.copy(alpha = 0.55f))) }
                        ?: androidx.compose.ui.graphics.Brush.sweepGradient(listOf(cs.primary, cs.tertiary, cs.secondary, cs.primary)),
                        androidx.compose.foundation.shape.CircleShape),
                    contentAlignment = androidx.compose.ui.Alignment.Center) {
                    if (selected) Icon(Icons.Outlined.Check, null, tint = androidx.compose.ui.graphics.Color.White, modifier = Modifier.size(22.dp))
                }
                Text(c.label, style = MaterialTheme.typography.labelSmall, maxLines = 1, modifier = Modifier.padding(top = 4.dp))
            }
        }
    }
    if (current == com.bennybar.runnersidekick.ui.theme.ThemeChoice.DYNAMIC) Text("Uses your wallpaper's colours (Material You).",
        style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 8.dp))
    Text("Appearance", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 16.dp, bottom = 8.dp))
    val now = com.bennybar.runnersidekick.ui.theme.Appearance.of(appearance)
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        com.bennybar.runnersidekick.ui.theme.Appearance.entries.forEachIndexed { i, a ->
            SegmentedButton(now == a, { onAppearance(a) }, SegmentedButtonDefaults.itemShape(i, 3), icon = {}) { Text(a.label) }
        }
    }
}


/** One section's sheet with its own Save. Closing it with unsaved edits asks first, so nothing is lost silently. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SectionSheet(title: String, dirty: Boolean, canSave: Boolean, onSave: () -> Unit, onClose: () -> Unit,
                         content: @Composable ColumnScope.() -> Unit) {
    var ask by remember { mutableStateOf(false) }
    val dirtyNow by androidx.compose.runtime.rememberUpdatedState(dirty)
    val state = androidx.compose.material3.rememberModalBottomSheetState(skipPartiallyExpanded = true, confirmValueChange = { v ->
        if (v == androidx.compose.material3.SheetValue.Hidden && dirtyNow) { ask = true; false } else true
    })
    androidx.compose.material3.ModalBottomSheet(onDismissRequest = { if (dirtyNow) ask = true else onClose() }, sheetState = state) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(title, style = MaterialTheme.typography.headlineSmall)
            content()
            if (canSave || dirty) Button(onClick = onSave, enabled = canSave && dirty, modifier = Modifier.fillMaxWidth()) {
                Text(if (dirty) "Save" else "Saved")
            }
        }
    }
    if (ask) AlertDialog(onDismissRequest = { ask = false }, title = { Text("Discard changes?") },
        text = { Text("Your edits in $title haven't been saved.") },
        confirmButton = { TextButton(onClick = { ask = false; onClose() }) { Text("Discard") } },
        dismissButton = { TextButton(onClick = { ask = false }) { Text("Keep editing") } })
}

@Composable
private fun Label(text: String, hint: String? = null) {
    Column {
        Text(text, style = MaterialTheme.typography.titleMedium)
        hint?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

@Composable
private fun BackendSheet(current: String, hasToken: Boolean, busy: Boolean, onClose: () -> Unit, onSave: (String, String) -> Unit) {
    var url by remember { mutableStateOf(current) }
    var token by remember { mutableStateOf("") }
    SectionSheet("Server", dirty = url != current || token.isNotBlank(), canSave = !busy && url.isNotBlank() && (token.isNotBlank() || hasToken),
        onSave = { onSave(url, token) }, onClose = onClose) {
        OutlinedTextField(url, { url = it }, label = { Text("Backend URL") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, autoCorrectEnabled = false))
        OutlinedTextField(token, { token = it }, label = { Text(if (hasToken) "Device token (saved, enter to replace)" else "Device token") },
            singleLine = true, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false))
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun TrainingSheet(r: SettingsDto, busy: Boolean, onClose: () -> Unit, onSave: (SettingsDto) -> Unit) {
    var days by remember { mutableStateOf(r.runningDays.toSet()) }
    var goalType by remember { mutableStateOf(r.goalType) }
    var goal by remember { mutableStateOf(r.goal ?: "") }
    var minutes by remember { mutableStateOf(r.availableMinutes?.toString() ?: "") }
    var weekStart by remember { mutableStateOf(r.weekStartDay) }
    var zones by remember { mutableStateOf(r.hrZoneSource) }
    var tz by remember { mutableStateOf(r.timezone) }
    val phoneTz = java.time.ZoneId.systemDefault().id
    val tzOk = runCatching { java.time.ZoneId.of(tz.trim()) }.isSuccess
    val edited = r.copy(runningDays = days.sorted(), goalType = goalType, goal = goal.ifBlank { null }, availableMinutes = minutes.toIntOrNull(),
        weekStartDay = weekStart, hrZoneSource = zones, timezone = tz.trim())
    SectionSheet("Training", dirty = edited != r, canSave = !busy && tzOk, onSave = { onSave(edited) }, onClose = onClose) {
        Label("Running days")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            DAYS.forEachIndexed { i, d -> FilterChip(i in days, { days = if (i in days) days - i else days + i }, { Text(d) }) }
        }
        Label("Main goal", "Orders the weekly focus suggestions.")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            GOALS.forEach { (k, l) -> FilterChip(goalType == k, { goalType = if (goalType == k) null else k }, { Text(l) }) }
        }
        OutlinedTextField(goal, { goal = it.take(200) }, label = { Text("Goal in your words (optional)") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(minutes, { minutes = it.filter(Char::isDigit).take(3) }, label = { Text("Usual time per run (min)") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
        Label("Week starts on", if (weekStart == null) "Now: ${r.weekStartEffective.replaceFirstChar(Char::uppercase)} (from Garmin, or Monday)."
            else "Used for weekly reviews, the weekly focus, Activities and charts.")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf(null to "As in Garmin", "monday" to "Monday", "sunday" to "Sunday", "saturday" to "Saturday")
                .forEach { (k, l) -> FilterChip(weekStart == k, { weekStart = k }, { Text(l) }) }
        }
        Label("Heart-rate zones")
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            listOf("garmin" to "From Garmin", "none" to "Don't use").forEachIndexed { i, (k, l) ->
                SegmentedButton(zones == k, { zones = k }, SegmentedButtonDefaults.itemShape(i, 2), icon = {}) { Text(l) }
            }
        }
        Label("Time zone", "Decides when your day starts and ends.")
        OutlinedTextField(tz, { tz = it }, singleLine = true, isError = !tzOk, modifier = Modifier.fillMaxWidth(),
            supportingText = { if (!tzOk) Text("Not a time zone name, e.g. Europe/London") })
        if (tz.trim() != phoneTz) TextButton(onClick = { tz = phoneTz }) { Text("Use this phone's ($phoneTz)") }
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
private fun RaceSheet(r: SettingsDto, busy: Boolean, onClose: () -> Unit, onSave: (SettingsDto) -> Unit) {
    var dist by remember { mutableStateOf(r.raceDistance) }
    var date by remember { mutableStateOf(r.raceDate) }
    var name by remember { mutableStateOf(r.raceName ?: "") }
    val t0 = r.raceTargetS ?: 0
    var h by remember { mutableStateOf(if (r.raceTargetS != null) "${t0 / 3600}" else "") }
    var m by remember { mutableStateOf(if (r.raceTargetS != null) "%02d".format(t0 % 3600 / 60) else "") }
    var s by remember { mutableStateOf(if (r.raceTargetS != null) "%02d".format(t0 % 60) else "") }
    var picking by remember { mutableStateOf(false) }
    val target = if (h.isBlank() && m.isBlank() && s.isBlank()) null
        else ((h.toIntOrNull() ?: 0) * 3600 + (m.toIntOrNull() ?: 0) * 60 + (s.toIntOrNull() ?: 0)).takeIf { (m.toIntOrNull() ?: 0) < 60 && (s.toIntOrNull() ?: 0) < 60 && it in 600..36000 }
    val targetOk = (h.isBlank() && m.isBlank() && s.isBlank()) || target != null
    val edited = r.copy(raceDistance = dist, raceDate = date, raceName = name.trim().ifBlank { null }, raceTargetS = target)
    SectionSheet("Race", dirty = edited != r, canSave = !busy && targetOk && ((date == null) == (dist == null)), onSave = { onSave(edited) }, onClose = onClose) {
        Text("The weekly focus, Today and the AI coach plan backwards from it: base, build, sharpen, taper, race week.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Label("Distance")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            RACES.forEach { (k, l) -> FilterChip(dist == k, { dist = if (dist == k) null else k }, { Text(l) }) }
        }
        Label("Date")
        OutlinedButton(onClick = { picking = true }, modifier = Modifier.fillMaxWidth()) {
            Text(date?.let { Format.longDate(it) } ?: "Choose the race date")
        }
        if ((date == null) != (dist == null)) Text("Set both a distance and a date, or neither", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.error)
        Label("Target time (optional)")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            listOf(Triple(h, "h") { v: String -> h = v }, Triple(m, "min") { v: String -> m = v }, Triple(s, "s") { v: String -> s = v })
                .forEach { (v, l, set) ->
                    OutlinedTextField(v, { set(it.filter(Char::isDigit).take(2)) }, label = { Text(l) }, singleLine = true, isError = !targetOk,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.weight(1f))
                }
        }
        OutlinedTextField(name, { name = it.take(60) }, label = { Text("Race name (optional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        if (dist != null || date != null) TextButton(onClick = { dist = null; date = null; h = ""; m = ""; s = ""; name = "" }) { Text("Remove race") }
    }
    if (picking) DateDialog(date, future = true, onClose = { picking = false }) { date = it; picking = false }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun AboutYouSheet(r: SettingsDto, busy: Boolean, onClose: () -> Unit, onSave: (SettingsDto) -> Unit) {
    var sex by remember { mutableStateOf(r.profileSex) }
    var birth by remember { mutableStateOf(r.profileBirthDate) }
    var picking by remember { mutableStateOf(false) }
    val edited = r.copy(profileSex = sex, profileBirthDate = birth)
    SectionSheet("About you", dirty = edited != r, canSave = !busy, onSave = { onSave(edited) }, onClose = onClose) {
        val det = r.profileDetected
        Text(if (det?.sex != null || det?.birthDate != null) "From Garmin: ${listOfNotNull(det.sex, det.birthDate).joinToString(", ")}. Set these only to override Garmin."
            else "Garmin didn't provide these; set them to see age and sex comparisons.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Label("Sex")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf(null to "As in Garmin", "male" to "Male", "female" to "Female").forEach { (k, l) -> FilterChip(sex == k, { sex = k }, { Text(l) }) }
        }
        Label("Birth date")
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(onClick = { picking = true }, modifier = Modifier.weight(1f)) { Text(birth?.let { Format.longDate(it) } ?: "As in Garmin") }
            if (birth != null) TextButton(onClick = { birth = null }) { Text("Use Garmin's") }
        }
    }
    if (picking) DateDialog(birth ?: "1985-01-01", future = false, onClose = { picking = false }) { birth = it; picking = false }
}

@Composable
private fun WindowSheet(r: SettingsDto, busy: Boolean, onClose: () -> Unit, onSave: (SettingsDto) -> Unit) {
    var start by remember { mutableStateOf(r.morningWindowStart) }
    var end by remember { mutableStateOf(r.morningWindowEnd) }
    var picking by remember { mutableStateOf<String?>(null) }
    val edited = r.copy(morningWindowStart = start, morningWindowEnd = end)
    SectionSheet("Morning window", dirty = edited != r, canSave = !busy && start < end, onSave = { onSave(edited) }, onClose = onClose) {
        Text("The briefing is sent once your sleep has synced, or at the end of the window as provisional.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { picking = "start" }, modifier = Modifier.weight(1f)) { Text("From $start") }
            OutlinedButton(onClick = { picking = "end" }, modifier = Modifier.weight(1f)) { Text("Until $end") }
        }
        if (start >= end) Text("The window has to end after it starts", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
    }
    picking?.let { which ->
        TimeDialog(if (which == "start") start else end, onClose = { picking = null }) { v -> if (which == "start") start = v else end = v; picking = null }
    }
}

@Composable
private fun ModelDialog(r: SettingsDto, ownKey: Boolean, onClose: () -> Unit, onPick: (String) -> Unit) {
    var other by remember { mutableStateOf(if (r.aiModel !in r.aiModels) r.aiModel else "") }
    AlertDialog(onDismissRequest = onClose, title = { Text("AI model") }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            r.aiModels.ifEmpty { listOf(r.aiModel) }.forEach { mm ->
                Row(Modifier.fillMaxWidth().selectable(mm == r.aiModel, role = androidx.compose.ui.semantics.Role.RadioButton) { onPick(mm) }.padding(vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    androidx.compose.material3.RadioButton(selected = mm == r.aiModel, onClick = null)
                    Spacer(Modifier.width(12.dp)); Text(mm)
                }
            }
            // Any other model only runs on your own key; the server's key runs the list above
            if (ownKey) OutlinedTextField(other, { other = it.trim() }, label = { Text("Another model (your key)") }, singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
            else Text("Add your own OpenAI key to use other models.", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }, confirmButton = { if (ownKey) TextButton(onClick = { onPick(other) }, enabled = Regex("^[A-Za-z0-9._:\\-]{1,64}$").matches(other)) { Text("Use") } },
        dismissButton = { TextButton(onClick = onClose) { Text("Close") } })
}

@Composable
private fun KeySheet(ownKey: Boolean, onClose: () -> Unit, onSave: (String?) -> Unit) {
    var key by remember { mutableStateOf("") }
    SectionSheet("Your own OpenAI key", dirty = key.isNotBlank(), canSave = key.startsWith("sk-"), onSave = { onSave(key) }, onClose = onClose) {
        Text("Encrypted on this phone and sent only with AI requests. The server uses it for that request and never stores it.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        OutlinedTextField(key, { key = it.trim() }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            label = { Text(if (ownKey) "Saved · enter a new key to replace" else "sk-…") }, visualTransformation = PasswordVisualTransformation())
        if (ownKey) TextButton(onClick = { onSave(null) }) { Text("Remove saved key") }
    }
}

/** A Material date picker for a "YYYY-MM-DD" value. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DateDialog(value: String?, future: Boolean, onClose: () -> Unit, onPick: (String) -> Unit) {
    val start = value?.let { runCatching { java.time.LocalDate.parse(it) }.getOrNull() }
    val today = java.time.LocalDate.now()
    val state = androidx.compose.material3.rememberDatePickerState(
        initialSelectedDateMillis = start?.atStartOfDay(java.time.ZoneOffset.UTC)?.toInstant()?.toEpochMilli(),
        selectableDates = object : androidx.compose.material3.SelectableDates {
            override fun isSelectableDate(utcTimeMillis: Long): Boolean {
                val d = Instant.ofEpochMilli(utcTimeMillis).atZone(java.time.ZoneOffset.UTC).toLocalDate()
                return if (future) !d.isBefore(today.minusDays(30)) else d.isBefore(today)
            }
        })
    androidx.compose.material3.DatePickerDialog(onDismissRequest = onClose,
        confirmButton = { TextButton(onClick = { state.selectedDateMillis?.let { ms ->
            onPick(Instant.ofEpochMilli(ms).atZone(java.time.ZoneOffset.UTC).toLocalDate().toString()) } }, enabled = state.selectedDateMillis != null) { Text("OK") } },
        dismissButton = { TextButton(onClick = onClose) { Text("Cancel") } }) {
        androidx.compose.material3.DatePicker(state)
    }
}

/** A Material time picker for an "HH:MM" value. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TimeDialog(value: String, onClose: () -> Unit, onPick: (String) -> Unit) {
    val (h0, m0) = value.split(":").let { (it.getOrNull(0)?.toIntOrNull() ?: 6) to (it.getOrNull(1)?.toIntOrNull() ?: 0) }
    val state = androidx.compose.material3.rememberTimePickerState(initialHour = h0, initialMinute = m0, is24Hour = true)
    AlertDialog(onDismissRequest = onClose, text = { androidx.compose.material3.TimePicker(state) },
        confirmButton = { TextButton(onClick = { onPick("%02d:%02d".format(state.hour, state.minute)) }) { Text("OK") } },
        dismissButton = { TextButton(onClick = onClose) { Text("Cancel") } })
}

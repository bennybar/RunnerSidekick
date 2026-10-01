package com.bennybar.runnersidekick.ui.settings

import android.Manifest
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
    fun setNotifications(on: Boolean) = viewModelScope.launch { repo.settings.setNotificationsEnabled(on) }

    fun export(ctx: android.content.Context, uri: Uri) = launchIo {
        val body = repo.exportJson()
        withContext(Dispatchers.IO) { ctx.contentResolver.openOutputStream(uri)?.use { it.write(body.toByteArray()) } }
        message.value = "Exported"
    }

    fun deleteRemote(scope: String) = launchIo { repo.deleteRemote(scope); message.value = "Deleted" }
    fun clearLocal() = launchIo { repo.clearLocal(includeCheckins = false); message.value = "Local cache cleared" }
}

private val DAYS = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
private val TIME = Regex("^([01]\\d|2[0-3]):[0-5]\\d$")
private val BIRTH = Regex("^(19|20)\\d{2}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])$")

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
    var editBackend by remember { mutableStateOf(false) }
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
        LazyColumn(Modifier.padding(padding).fillMaxSize(), contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp)) {
            item {
                val s = status?.value
                val ok = s?.connection?.state == "connected"
                Group(title = "Connection") {
                    row(
                        if (s == null) "Not connected" else if (s.synthetic) "Demo data source" else "Garmin (unofficial connector)",
                        supporting = s?.let {
                            "${it.connection.state.replace('_', ' ').replaceFirstChar(Char::uppercase)} · last fetch ${Format.ago(it.connection.lastSuccessAt?.let { t -> runCatching { Instant.parse(t) }.getOrNull() })}" +
                                (it.backfill?.oldestDone?.let { d -> " · history from $d" } ?: "")
                        } ?: "Enter the backend address and device token.",
                        icon = if (ok) Icons.Outlined.CloudDone else Icons.Outlined.CloudOff, iconShape = MaterialShapes.Cookie9Sided,
                    )
                    if (s?.connection?.state == "reauth_required" || s?.connection?.state == "not_configured") {
                        row("Garmin sign-in needed", supporting = "Run `python -m sidekick garmin-login` on the backend computer.")
                    }
                    row("Backend", supporting = local?.backendUrl ?: "", onClick = { editBackend = !editBackend })
                    if (editBackend || local?.hasToken == false) custom {
                        var url by remember(local?.backendUrl) { mutableStateOf(local?.backendUrl ?: "") }
                        var token by remember { mutableStateOf("") }
                        OutlinedTextField(url, { url = it }, label = { Text("Backend URL") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
                        OutlinedTextField(token, { token = it }, label = { Text(if (local?.hasToken == true) "Device token (saved, enter to replace)" else "Device token") },
                            singleLine = true, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
                        FilledTonalButton(onClick = { vm.saveBackend(url, token); token = ""; editBackend = false },
                            enabled = !busy && url.isNotBlank() && (token.isNotBlank() || local?.hasToken == true),
                            modifier = Modifier.padding(top = 12.dp)) { Text("Save and test") }
                    }
                }
            }
            item {
                val m = me?.value
                val g = status?.value?.garminOfficial
                Group(title = "Account") {
                    row(m?.email ?: if (m?.role == "owner") "Owner (signed in with a device token)" else "Signed in",
                        supporting = when (m?.role) { "owner" -> "Server owner"; null -> null; else -> "Member" },
                        icon = Icons.Outlined.AccountCircle, iconShape = MaterialShapes.Circle)
                    row("Garmin", supporting = when {
                        g?.connected == true -> "Connected with Garmin's official sign-in. " + (g.dataImport ?: "")
                        status?.value?.connection?.state == "connected" && m?.role == "owner" -> "Connected (owner's direct connection)"
                        g?.available == true -> "Not connected"
                        else -> "Garmin sign-in for members opens once Garmin approves this app"
                    }, icon = Icons.Outlined.Watch, iconShape = MaterialShapes.Cookie9Sided,
                        trailing = when {
                            g?.connected == true -> ({ TextButton(onClick = vm::disconnectGarmin) { Text("Disconnect") } })
                            g?.available == true -> ({ FilledTonalButton(onClick = { vm.connectGarmin(ctx) }) { Text("Connect") } })
                            else -> null
                        })
                    row("Sign out", supporting = "Removes the token and cached data from this phone", icon = Icons.AutoMirrored.Outlined.Logout,
                        iconShape = MaterialShapes.Cookie4Sided, onClick = { confirm = "signout" })
                    if (m?.role == "member") row("Delete my account", supporting = "Deletes all your data on the server and disconnects Garmin",
                        icon = Icons.Outlined.DeleteOutline, iconShape = MaterialShapes.Burst, onClick = { confirm = "account" })
                }
            }
            item {
                Group(title = "Display") {
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
                    var tz by remember(r) { mutableStateOf(r.timezone) }
                    var days by remember(r) { mutableStateOf(r.runningDays.toSet()) }
                    var goal by remember(r) { mutableStateOf(r.goal ?: "") }
                    var minutes by remember(r) { mutableStateOf(r.availableMinutes?.toString() ?: "") }
                    var zones by remember(r) { mutableStateOf(r.hrZoneSource) }
                    var goalType by remember(r) { mutableStateOf(r.goalType) }
                    var start by remember(r) { mutableStateOf(r.morningWindowStart) }
                    var end by remember(r) { mutableStateOf(r.morningWindowEnd) }
                    var aiOn by remember(r) { mutableStateOf(r.aiEnabled) }
                    var model by remember(r) { mutableStateOf(r.aiModel) }
                    var sex by remember(r) { mutableStateOf(r.profileSex) }
                    var birth by remember(r) { mutableStateOf(r.profileBirthDate ?: "") }
                    val birthOk = birth.isEmpty() || BIRTH.matches(birth)
                    val valid = TIME.matches(start) && TIME.matches(end) && start < end && model.isNotBlank() && birthOk
                    val edited = SettingsDto(tz.trim(), days.sorted(), goal.ifBlank { null }, minutes.toIntOrNull(), zones, goalType, aiOn, model.trim(),
                        r.aiAvailable, start, end, profileSex = sex, profileBirthDate = birth.ifBlank { null }, profileDetected = r.profileDetected)
                    val dirty = edited != r
                    Column(verticalArrangement = Arrangement.spacedBy(20.dp)) {
                        Group(title = "Training profile") {
                            custom {
                                Text("Main goal", style = MaterialTheme.typography.titleMedium)
                                Text("Orders the weekly focus suggestions.", style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(top = 8.dp, bottom = 12.dp)) {
                                    listOf("consistency" to "Consistency", "distance" to "Go longer", "performance" to "Get faster", "health" to "Health")
                                        .forEach { (k, l) -> FilterChip(goalType == k, { goalType = if (goalType == k) null else k }, { Text(l) }) }
                                }
                                Text("Running days", style = MaterialTheme.typography.titleMedium)
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(top = 8.dp)) {
                                    DAYS.forEachIndexed { i, d -> FilterChip(i in days, { days = if (i in days) days - i else days + i }, { Text(d) }) }
                                }
                                OutlinedTextField(goal, { goal = it }, label = { Text("Goal in your words (optional)") },
                                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp))
                                OutlinedTextField(minutes, { minutes = it.filter(Char::isDigit) }, label = { Text("Usual time per run (min)") }, singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
                                OutlinedTextField(tz, { tz = it }, label = { Text("Time zone (e.g. Asia/Jerusalem)") }, singleLine = true,
                                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
                                Text("For age and sex comparisons", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 16.dp))
                                val det = r.profileDetected
                                Text(if (det?.sex != null || det?.birthDate != null)
                                    "From Garmin: ${listOfNotNull(det.sex, det.birthDate).joinToString(", ")}. Set these only to override Garmin."
                                    else "Garmin didn't provide these; set them to see comparisons.",
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(top = 8.dp)) {
                                    listOf(null to "As in Garmin", "male" to "Male", "female" to "Female")
                                        .forEach { (k, l) -> FilterChip(sex == k, { sex = k }, { Text(l) }) }
                                }
                                OutlinedTextField(birth, { birth = it.filter { c -> c.isDigit() || c == '-' }.take(10) },
                                    label = { Text("Birth date (YYYY-MM-DD, optional)") }, singleLine = true, isError = !birthOk,
                                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
                                Text("Heart-rate zones", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 16.dp, bottom = 8.dp))
                                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                                    listOf("garmin" to "From Garmin", "none" to "Don't use").forEachIndexed { i, (k, l) ->
                                        SegmentedButton(zones == k, { zones = k }, SegmentedButtonDefaults.itemShape(i, 2), icon = {}) { Text(l) }
                                    }
                                }
                            }
                        }
                        Group(title = "Notifications") {
                            row("Morning briefing and run reports", supporting = "Best effort: Android decides exact timing.",
                                icon = Icons.Outlined.Notifications, iconShape = MaterialShapes.Sunny,
                                trailing = {
                                    Switch(checked = local?.notificationsEnabled == true, onCheckedChange = { on ->
                                        if (on) permission.launch(Manifest.permission.POST_NOTIFICATIONS) else vm.setNotifications(false)
                                    })
                                })
                            custom {
                                Text("Morning window", style = MaterialTheme.typography.titleMedium)
                                Text("The briefing is sent once your sleep has synced, or at the end of the window as provisional.",
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
                                    OutlinedTextField(start, { start = it.take(5) }, label = { Text("From") }, singleLine = true, isError = !TIME.matches(start),
                                        modifier = Modifier.weight(1f))
                                    OutlinedTextField(end, { end = it.take(5) }, label = { Text("Until") }, singleLine = true, isError = !TIME.matches(end) || start >= end,
                                        modifier = Modifier.weight(1f))
                                }
                            }
                        }
                        val ownKey = local?.hasOwnAiKey == true
                        Group(title = "AI coach and summaries (optional)") {
                            row("AI coach and report summaries", icon = Icons.Outlined.AutoAwesome, iconShape = MaterialShapes.Flower,
                                supporting = when {
                                    ownKey -> "Uses OpenAI with your own key."
                                    r.aiAvailable -> "Uses OpenAI. Off by default."
                                    else -> "Add your own OpenAI key below to use it."
                                },
                                trailing = { Switch(checked = aiOn, enabled = r.aiAvailable || ownKey || aiOn, onCheckedChange = { aiOn = it }) })
                            custom {
                                Text("What is sent: finding titles, statuses, values and ranges. Never your notes, run names, routes or identifiers. " +
                                    "Numbers in the summary are filled in from the report, not written by the AI. If its output doesn't pass checks, " +
                                    "no summary is shown and the report is unchanged.",
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                OutlinedTextField(model, { model = it }, label = { Text("Model") }, singleLine = true, enabled = aiOn,
                                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp))
                            }
                            custom {
                                var key by remember { mutableStateOf("") }
                                Text("Your own OpenAI key (optional)", style = MaterialTheme.typography.titleSmall)
                                Text("Encrypted on this phone and sent only with AI requests. The server uses it for that request and never stores it.",
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                OutlinedTextField(key, { key = it.trim() }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                                    label = { Text(if (ownKey) "Saved · enter a new key to replace" else "sk-…") },
                                    visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation())
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
                                    FilledTonalButton(onClick = { vm.setOwnAiKey(key); key = "" }, enabled = key.startsWith("sk-")) { Text("Save key") }
                                    if (ownKey) TextButton(onClick = { vm.setOwnAiKey(null) }) { Text("Remove") }
                                }
                            }
                        }
                        Button(
                            enabled = !busy && valid && dirty, modifier = Modifier.fillMaxWidth(),
                            onClick = { vm.saveRemote(edited) },
                        ) { Text(if (dirty) "Save changes" else "Saved") }
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

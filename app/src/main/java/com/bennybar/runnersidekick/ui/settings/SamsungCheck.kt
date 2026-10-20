package com.bennybar.runnersidekick.ui.settings

import android.content.ClipData
import androidx.activity.compose.LocalActivity
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.ClipEntry
import androidx.compose.ui.platform.LocalClipboard
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.bennybar.runnersidekick.ui.components.Group
import com.bennybar.runnersidekick.ui.components.Tile
import com.bennybar.runnersidekick.ui.theme.Tint
import com.samsung.android.sdk.health.data.HealthDataService
import com.samsung.android.sdk.health.data.HealthDataStore
import com.samsung.android.sdk.health.data.data.HealthDataPoint
import com.samsung.android.sdk.health.data.error.HealthDataException
import com.samsung.android.sdk.health.data.error.ResolvablePlatformException
import com.samsung.android.sdk.health.data.permission.AccessType
import com.samsung.android.sdk.health.data.permission.Permission
import com.samsung.android.sdk.health.data.request.DataType
import com.samsung.android.sdk.health.data.request.DataTypes
import com.samsung.android.sdk.health.data.request.LocalDateFilter
import com.samsung.android.sdk.health.data.request.LocalTimeFilter
import com.samsung.android.sdk.health.data.request.Ordering
import kotlinx.coroutines.launch
import java.time.Duration
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** A one-off check of what Samsung Health on this phone lets the app read from a Galaxy Watch (Samsung Health Data SDK):
 *  how detailed the latest run is (heart rate, speed, cadence and power every few seconds? a GPS route?), sleep stages and
 *  score, all-day heart rate, skin temperature, blood oxygen and Energy Score. Read only; nothing leaves the phone unless you
 *  copy the report. Until Samsung approves the app as a partner, Samsung Health needs its developer mode on for this. */
private val TYPES: List<Pair<String, DataType>> = listOf(
    "Workouts" to DataTypes.EXERCISE, "Workout routes" to DataTypes.EXERCISE_LOCATION, "Heart rate" to DataTypes.HEART_RATE,
    "Sleep" to DataTypes.SLEEP, "Skin temperature" to DataTypes.SKIN_TEMPERATURE, "Blood oxygen" to DataTypes.BLOOD_OXYGEN,
    "Energy Score" to DataTypes.ENERGY_SCORE)
private val PERMISSIONS = TYPES.map { Permission.of(it.second, AccessType.READ) }.toSet()
private val WHEN = DateTimeFormatter.ofPattern("d MMM HH:mm").withZone(ZoneId.systemDefault())

private class Finding(val title: String, val detail: String)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SamsungCheckScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val activity = LocalActivity.current
    val clipboard = LocalClipboard.current
    val scope = rememberCoroutineScope()
    val store = remember { HealthDataService.getStore(ctx.applicationContext) }
    var granted by remember { mutableStateOf<Set<Permission>?>(null) }
    var findings by remember { mutableStateOf<List<Finding>?>(null) }
    var problem by remember { mutableStateOf<String?>(null) }
    var fix by remember { mutableStateOf<ResolvablePlatformException?>(null) }  // Samsung Health missing or too old: it can fix that
    var round by remember { mutableIntStateOf(0) }
    fun failed(e: Throwable) {
        fix = (e as? ResolvablePlatformException)?.takeIf { it.hasResolution }
        problem = (e as? HealthDataException)?.let { "Samsung Health said: ${it.errorMessage ?: it.message} (code ${it.errorCode})" }
            ?: "Couldn't reach Samsung Health: ${e.message}"
    }
    LaunchedEffect(round) {
        problem = null; fix = null
        runCatching {
            granted = store.getGrantedPermissions(PERMISSIONS)
            if (granted!!.isNotEmpty()) findings = check(store, granted!!)
        }.onFailure(::failed)
    }
    val report = remember(findings, granted, problem) {
        buildString {
            appendLine("Samsung Health check · ${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL} · Android ${android.os.Build.VERSION.RELEASE}")
            appendLine("Access: ${granted?.size ?: 0} of ${PERMISSIONS.size} allowed")
            problem?.let { appendLine(it) }
            findings?.forEach { appendLine("${it.title}: ${it.detail}") }
        }
    }

    Scaffold(topBar = {
        TopAppBar(title = { Text("Samsung Health check") },
            navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } })
    }) { padding ->
        LazyColumn(Modifier.padding(padding).fillMaxSize(), contentPadding = PaddingValues(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Tile { Text("Shows what Samsung Health lets this app read from your Galaxy Watch, mostly over the last 30 days. Read only; " +
                    "nothing is sent anywhere unless you copy the report. For now Samsung Health needs developer mode: ⋮ › Settings › " +
                    "About Samsung Health, tap the version 10 times, then turn on Developer Mode for Data Read.",
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
            item {
                Row(Modifier.padding(horizontal = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = {
                        val a = activity ?: return@Button
                        scope.launch { runCatching { store.requestPermissions(PERMISSIONS, a) }.onFailure(::failed); round++ }
                    }) { Text(if (granted.isNullOrEmpty()) "Allow reading" else "Allow more") }
                    if (findings != null || problem != null) OutlinedButton(onClick = {
                        scope.launch { clipboard.setClipEntry(ClipEntry(ClipData.newPlainText("Samsung Health check", report))) }
                    }) { Text("Copy report") }
                }
            }
            problem?.let { p ->
                item {
                    Group(tint = Tint.ORANGE) {
                        row("Something's in the way", supporting = p + (fix?.let { "\nTap to let Samsung Health fix it." } ?: ""),
                            onClick = fix?.let { e -> { activity?.let { e.resolve(it) }; Unit } })
                    }
                }
            }
            findings?.let { fs -> item { Group(title = "What the app can read") { fs.forEach { f -> row(f.title, supporting = f.detail) } } } }
        }
    }
}

/** Every data point of a type in the range, newest first, at most 10 pages. */
private suspend fun read(store: HealthDataStore, type: DataType, from: LocalDateTime, to: LocalDateTime): List<HealthDataPoint> {
    val out = mutableListOf<HealthDataPoint>()
    var token: String? = null
    repeat(10) {
        val b = when (type) {
            is DataType.ExerciseType -> type.readDataRequestBuilder
            is DataType.HeartRateType -> type.readDataRequestBuilder
            is DataType.SleepType -> type.readDataRequestBuilder
            is DataType.SkinTemperatureType -> type.readDataRequestBuilder
            is DataType.BloodOxygenType -> type.readDataRequestBuilder
            else -> null
        }
        val req = if (b != null) b.setLocalTimeFilter(LocalTimeFilter.of(from, to)).setOrdering(Ordering.DESC).setPageToken(token).build()
        else DataTypes.ENERGY_SCORE.readDataRequestBuilder.setLocalDateFilter(LocalDateFilter.of(from.toLocalDate(), to.toLocalDate()))
            .setOrdering(Ordering.DESC).setPageToken(token).build()
        val page = store.readData(req)
        out += page.dataList
        token = page.pageToken ?: return out
    }
    return out
}

/** Median gap between consecutive times, as ", one every N s". */
private fun spacing(times: List<Instant>): String = times.sorted().zipWithNext { a, b -> Duration.between(a, b).seconds }
    .filter { it > 0 }.sorted().let { if (it.isEmpty()) "" else ", one every ${it[it.size / 2]} s" }

/** One finding per kind of data, with the latest run and night in detail. */
private suspend fun check(store: HealthDataStore, granted: Set<Permission>): List<Finding> {
    val now = LocalDateTime.now()
    val month = now.minusDays(30)
    val out = mutableListOf<Finding>()
    val has = { t: DataType -> Permission.of(t, AccessType.READ) in granted }
    fun device(p: HealthDataPoint) = listOfNotNull(p.dataSource?.appId, p.dataSource?.deviceId?.take(8)?.let { "device $it…" }).joinToString(", ")

    if (has(DataTypes.EXERCISE)) runCatching {
        val all = read(store, DataTypes.EXERCISE, month, now)
        val types = all.groupingBy { it.getValue(DataType.ExerciseType.EXERCISE_TYPE)?.name?.lowercase() ?: "other" }.eachCount()
        out += Finding("Workouts, last 30 days", if (all.isEmpty()) "none" else "${all.size} · " + types.entries.joinToString { "${it.key} ${it.value}" })
        val running = setOf(DataType.ExerciseType.PredefinedExerciseType.RUNNING, DataType.ExerciseType.PredefinedExerciseType.TREADMILL,
            DataType.ExerciseType.PredefinedExerciseType.TRACK_RUNNING)
        val p = all.firstOrNull { it.getValue(DataType.ExerciseType.EXERCISE_TYPE) in running } ?: all.firstOrNull()
        val s = p?.getValue(DataType.ExerciseType.SESSIONS)?.firstOrNull()
        if (p != null && s != null) {
            val log = s.log.orEmpty()
            val route = s.route.orEmpty()
            out += Finding("Latest run (${p.getValue(DataType.ExerciseType.EXERCISE_TYPE)?.name?.lowercase()}, ${WHEN.format(s.startTime)})", listOf(
                "${s.duration.toMinutes()} min, %.2f km".format((s.distance ?: 0f) / 1000f), "from ${device(p)}",
                "${p.getValue(DataType.ExerciseType.SESSIONS)?.size} part(s)",
                "log ${log.size} points" + spacing(log.map { it.timestamp }),
                "heart rate in ${log.count { it.heartRate != null }}, speed in ${log.count { it.speed != null }}, " +
                    "cadence in ${log.count { it.cadence != null }}, power in ${log.count { it.power != null }}",
                "route ${route.size} points" + spacing(route.map { it.timestamp }) +
                    (if (route.any { it.altitude != null }) " with altitude" else ""),
                "climb ${s.altitudeGain?.let { "%.0f m".format(it) } ?: "—"}",
                "HR avg/max ${s.meanHeartRate?.toInt() ?: "—"}/${s.maxHeartRate?.toInt() ?: "—"}",
                "cadence avg ${s.meanCadence?.toInt() ?: "—"}", "power avg ${s.meanPower?.toInt() ?: "—"}",
                "VO2 max ${s.vo2Max?.let { "%.1f".format(it) } ?: "—"}").joinToString(" · "))
        }
    }.onFailure { out += Finding("Workouts", "can't read: ${it.message}") } else out += Finding("Workouts", "not allowed")

    if (!has(DataTypes.EXERCISE_LOCATION)) out += Finding("Workout routes", "not allowed (routes stay empty without it)")

    if (has(DataTypes.HEART_RATE)) runCatching {
        val day = read(store, DataTypes.HEART_RATE, now.minusDays(1), now)
        val series = day.flatMap { it.getValue(DataType.HeartRateType.SERIES_DATA).orEmpty() }
        out += Finding("Heart rate, last 24 h", if (day.isEmpty()) "none" else "${day.size} readings" + spacing(day.map { it.startTime }) +
            " · ${series.size} series points" + spacing(series.map { it.startTime }) + " · from ${device(day.first())}")
    }.onFailure { out += Finding("Heart rate", "can't read: ${it.message}") } else out += Finding("Heart rate", "not allowed")

    if (has(DataTypes.SLEEP)) runCatching {
        val nights = read(store, DataTypes.SLEEP, now.minusDays(7), now)
        val last = nights.firstOrNull()
        val stages = last?.getValue(DataType.SleepType.SESSIONS).orEmpty().flatMap { it.stages.orEmpty() }
        out += Finding("Sleep, last 7 days", if (last == null) "none" else "${nights.size} nights · latest ${WHEN.format(last.startTime)}, " +
            "${last.getValue(DataType.SleepType.DURATION)?.toMinutes()?.let { "%.1f h".format(it / 60.0) } ?: "—"}, " +
            "${stages.size} stages (${stages.map { it.stage.name.lowercase() }.distinct().joinToString("/")}), " +
            "score ${last.getValue(DataType.SleepType.SLEEP_SCORE) ?: "—"} · from ${device(last)}")
    }.onFailure { out += Finding("Sleep", "can't read: ${it.message}") } else out += Finding("Sleep", "not allowed")

    for ((label, type) in listOf("Skin temperature" to DataTypes.SKIN_TEMPERATURE, "Blood oxygen" to DataTypes.BLOOD_OXYGEN,
        "Energy Score" to DataTypes.ENERGY_SCORE)) {
        if (!has(type)) { out += Finding(label, "not allowed"); continue }
        runCatching {
            val ps = read(store, type, now.minusDays(7), now)
            val latest = ps.firstOrNull()
            val value = latest?.let { p -> when (type) {
                is DataType.SkinTemperatureType -> p.getValue(DataType.SkinTemperatureType.SKIN_TEMPERATURE)?.let { "%.1f °C".format(it) }
                is DataType.BloodOxygenType -> p.getValue(DataType.BloodOxygenType.OXYGEN_SATURATION)?.let { "%.0f%%".format(it) }
                else -> p.getValue(DataType.EnergyScoreType.ENERGY_SCORE)?.let { "%.0f".format(it) }
            } }
            out += Finding("$label, last 7 days", if (latest == null) "none" else "${ps.size} · latest ${value ?: "—"} on ${WHEN.format(latest.startTime)}")
        }.onFailure { out += Finding(label, "can't read: ${it.message}") }
    }
    // How far back workouts go
    if (has(DataTypes.EXERCISE)) runCatching {
        val year = read(store, DataTypes.EXERCISE, now.minusDays(365), now)
        out += Finding("Workouts, past year", "${year.size}" + (year.lastOrNull()?.let { " · oldest ${WHEN.format(it.startTime)}" } ?: ""))
    }
    return out
}


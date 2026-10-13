package com.bennybar.runnersidekick.data

import android.app.Activity
import android.content.Context
import com.samsung.android.sdk.health.data.HealthDataService
import com.samsung.android.sdk.health.data.data.HealthDataPoint
import com.samsung.android.sdk.health.data.permission.AccessType
import com.samsung.android.sdk.health.data.permission.Permission
import com.samsung.android.sdk.health.data.request.DataType
import com.samsung.android.sdk.health.data.request.DataTypes
import com.samsung.android.sdk.health.data.request.InstantTimeFilter
import com.samsung.android.sdk.health.data.request.ReadDataRequest
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant

/** Reads the Galaxy Watch's data from Samsung Health on this phone (Samsung Health Data SDK), shaped for the server's
 *  /v1/samsung upload (backend samsung.py): workouts with their per-second log and GPS route, sleep with its stages, and
 *  all-day heart rate, and overnight skin temperature and blood oxygen. Read only. Samsung has no cloud API, so this is how the watch's data reaches the server. */
class SamsungHealth(context: Context) {
    private val store by lazy { HealthDataService.getStore(context.applicationContext) }
    private val types = listOf(DataTypes.EXERCISE, DataTypes.EXERCISE_LOCATION, DataTypes.HEART_RATE, DataTypes.SLEEP,
        DataTypes.SKIN_TEMPERATURE, DataTypes.BLOOD_OXYGEN)
    private val permissions = types.map { Permission.of(it, AccessType.READ) }.toSet()

    /** What Samsung Health lets the app read. Each kind works on its own: without routes, runs still come (no map). */
    data class Allowed(val workouts: Boolean, val routes: Boolean, val heartRate: Boolean, val sleep: Boolean,
                       val skinTemp: Boolean, val spo2: Boolean) {
        val missing get() = listOfNotNull("workouts".takeIf { !workouts }, "routes".takeIf { !routes },
            "heart rate".takeIf { !heartRate }, "sleep".takeIf { !sleep }, "skin temperature".takeIf { !skinTemp },
            "blood oxygen".takeIf { !spo2 })
    }

    private fun allowedOf(granted: Set<Permission>) = Allowed(
        workouts = Permission.of(DataTypes.EXERCISE, AccessType.READ) in granted,
        routes = Permission.of(DataTypes.EXERCISE_LOCATION, AccessType.READ) in granted,
        heartRate = Permission.of(DataTypes.HEART_RATE, AccessType.READ) in granted,
        sleep = Permission.of(DataTypes.SLEEP, AccessType.READ) in granted,
        skinTemp = Permission.of(DataTypes.SKIN_TEMPERATURE, AccessType.READ) in granted,
        spo2 = Permission.of(DataTypes.BLOOD_OXYGEN, AccessType.READ) in granted)

    suspend fun allowed(): Allowed = allowedOf(store.getGrantedPermissions(permissions))

    /** Samsung Health's own screen asking to allow reading; what was allowed afterwards. */
    suspend fun ask(activity: Activity): Allowed = allowedOf(store.requestPermissions(permissions, activity))

    /** Every data point a request pages through. */
    private suspend fun read(request: (String?) -> ReadDataRequest<HealthDataPoint>): List<HealthDataPoint> {
        val out = mutableListOf<HealthDataPoint>()
        var token: String? = null
        do {
            val page = store.readData(request(token))
            out += page.dataList
            token = page.pageToken
        } while (token != null)
        return out
    }

    private fun num(v: Number?) = v?.let { JsonPrimitive(it) } ?: JsonPrimitive(null as Number?)

    /** Workouts that started in [from, to): the summary, the log [ms, hr, speed, cadence, power] and the route
     *  [ms, lat, lon, altitude]. A workout in several parts is sent as one workout per part. */
    suspend fun workouts(from: Instant, to: Instant): List<JsonObject> =
        read { DataTypes.EXERCISE.readDataRequestBuilder.setInstantTimeFilter(InstantTimeFilter.of(from, to)).setPageToken(it).build() }
            .flatMap { p ->
                p.getValue(DataType.ExerciseType.SESSIONS).orEmpty().mapIndexed { i, s ->
                    buildJsonObject {
                        put("uid", p.uid + if (i > 0) "-$i" else "")
                        put("type", (s.exerciseType ?: p.getValue(DataType.ExerciseType.EXERCISE_TYPE))?.name)  // each part its own
                        put("title", s.customTitle ?: p.getValue(DataType.ExerciseType.CUSTOM_TITLE))
                        put("start", s.startTime.toEpochMilli())
                        put("end", s.endTime.toEpochMilli())
                        put("offset_s", p.zoneOffset?.totalSeconds)
                        put("device", p.dataSource?.deviceId)
                        put("duration_s", s.duration.seconds)
                        put("distance_m", s.distance)
                        put("climb_m", s.altitudeGain)
                        put("descent_m", s.altitudeLoss)
                        put("avg_hr", s.meanHeartRate)
                        put("max_hr", s.maxHeartRate)
                        put("avg_cadence", s.meanCadence)
                        put("vo2max", s.vo2Max)
                        put("log", JsonArray(s.log.orEmpty().map { e ->
                            JsonArray(listOf(num(e.timestamp.toEpochMilli()), num(e.heartRate), num(e.speed), num(e.cadence), num(e.power)))
                        }))
                        put("route", JsonArray(s.route.orEmpty().map { r ->
                            JsonArray(listOf(num(r.timestamp.toEpochMilli()), num(r.latitude), num(r.longitude), num(r.altitude)))
                        }))
                    }
                }
            }

    /** Nights (and naps) that started in [from, to), with their stages [start ms, end ms, stage]. */
    suspend fun sleep(from: Instant, to: Instant): List<JsonObject> =
        read { DataTypes.SLEEP.readDataRequestBuilder.setInstantTimeFilter(InstantTimeFilter.of(from, to)).setPageToken(it).build() }
            .mapNotNull { p ->
                val parts = p.getValue(DataType.SleepType.SESSIONS).orEmpty()
                if (parts.isEmpty()) return@mapNotNull null
                buildJsonObject {
                    put("uid", p.uid)
                    put("start", parts.minOf { it.startTime }.toEpochMilli())
                    put("end", parts.maxOf { it.endTime }.toEpochMilli())
                    put("offset_s", p.zoneOffset?.totalSeconds)
                    put("duration_s", p.getValue(DataType.SleepType.DURATION)?.seconds)
                    put("score", p.getValue(DataType.SleepType.SLEEP_SCORE))
                    put("stages", JsonArray(parts.flatMap { it.stages.orEmpty() }.map { st ->
                        JsonArray(listOf(num(st.startTime.toEpochMilli()), num(st.endTime.toEpochMilli()), JsonPrimitive(st.stage.name)))
                    }))
                }
            }

    /** All-day heart rate in [from, to) as [ms, bpm, UTC offset s]: each reading's series when it has one, else the
     *  reading itself, each with its own offset (a day's readings belong to the time zone they were taken in). */
    suspend fun heartRate(from: Instant, to: Instant): List<JsonArray> =
        read { DataTypes.HEART_RATE.readDataRequestBuilder.setInstantTimeFilter(InstantTimeFilter.of(from, to)).setPageToken(it).build() }
            .flatMap { p ->
                val off = num(p.zoneOffset?.totalSeconds)
                val series = p.getValue(DataType.HeartRateType.SERIES_DATA).orEmpty()
                if (series.isNotEmpty()) series.map { JsonArray(listOf(num(it.startTime.toEpochMilli()), num(it.heartRate), off)) }
                else listOfNotNull(p.getValue(DataType.HeartRateType.HEART_RATE)?.let { JsonArray(listOf(num(p.startTime.toEpochMilli()), num(it), off)) })
            }

    /** Skin temperature in [from, to) as [ms, °C, UTC offset s] (the watch measures it during sleep). */
    suspend fun skinTemperature(from: Instant, to: Instant): List<JsonArray> =
        read { DataTypes.SKIN_TEMPERATURE.readDataRequestBuilder.setInstantTimeFilter(InstantTimeFilter.of(from, to)).setPageToken(it).build() }
            .flatMap { p ->
                val off = num(p.zoneOffset?.totalSeconds)
                val series = p.getValue(DataType.SkinTemperatureType.SERIES_DATA).orEmpty()
                if (series.isNotEmpty()) series.map { JsonArray(listOf(num(it.startTime.toEpochMilli()), num(it.skinTemperature), off)) }
                else listOfNotNull(p.getValue(DataType.SkinTemperatureType.SKIN_TEMPERATURE)?.let { JsonArray(listOf(num(p.startTime.toEpochMilli()), num(it), off)) })
            }

    /** Blood oxygen in [from, to) as [ms, %, UTC offset s] (overnight when the watch is set to measure it in sleep). */
    suspend fun bloodOxygen(from: Instant, to: Instant): List<JsonArray> =
        read { DataTypes.BLOOD_OXYGEN.readDataRequestBuilder.setInstantTimeFilter(InstantTimeFilter.of(from, to)).setPageToken(it).build() }
            .flatMap { p ->
                val off = num(p.zoneOffset?.totalSeconds)
                val series = p.getValue(DataType.BloodOxygenType.SERIES_DATA).orEmpty()
                if (series.isNotEmpty()) series.map { JsonArray(listOf(num(it.startTime.toEpochMilli()), num(it.oxygenSaturation), off)) }
                else listOfNotNull(p.getValue(DataType.BloodOxygenType.OXYGEN_SATURATION)?.let { JsonArray(listOf(num(p.startTime.toEpochMilli()), num(it), off)) })
            }
}

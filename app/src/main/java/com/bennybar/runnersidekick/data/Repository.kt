package com.bennybar.runnersidekick.data

import com.bennybar.runnersidekick.data.local.CachedBlob
import com.bennybar.runnersidekick.data.local.CheckinEntity
import com.bennybar.runnersidekick.data.local.ReportEntity
import com.bennybar.runnersidekick.data.local.SettingsStore
import com.bennybar.runnersidekick.data.local.SidekickDb
import com.bennybar.runnersidekick.data.remote.ActivityDetail
import com.bennybar.runnersidekick.data.remote.ActivitySummary
import com.bennybar.runnersidekick.data.remote.ApiClient
import com.bennybar.runnersidekick.data.remote.CheckinDto
import com.bennybar.runnersidekick.data.remote.EffortIn
import com.bennybar.runnersidekick.data.remote.InsightsReport
import com.bennybar.runnersidekick.data.remote.MorningReport
import com.bennybar.runnersidekick.data.remote.ReportListItem
import com.bennybar.runnersidekick.data.remote.SettingsDto
import com.bennybar.runnersidekick.data.remote.Status
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.encodeToString
import java.time.Instant
import java.util.UUID

/** A cached value plus when this device last fetched it, so the UI can be honest about staleness. */
data class Cached<T>(val value: T, val fetchedAt: Instant)

class Repository(
    private val db: SidekickDb,
    private val api: ApiClient,
    val settings: SettingsStore,
) {
    private val json = api.json

    private fun <T> observe(key: String, decode: (String) -> T): Flow<Cached<T>?> =
        settings.settings.map { it.currentMode }.flatMapLatest { mode ->
            if (mode == null) flowOf(null)
            else db.cache().observe(key, mode).map { b ->
                b?.let { runCatching { Cached(decode(it.json), Instant.ofEpochMilli(it.fetchedAt)) }.getOrNull() }
            }
        }.flowOn(Dispatchers.Default) // decoding large reports must not block the main thread

    val status: Flow<Cached<Status>?> = observe("status") { json.decodeFromString<Status>(it) }
    val today: Flow<Cached<MorningReport>?> = observe("today") { json.decodeFromString<MorningReport>(it) }
    val activities: Flow<Cached<List<ActivitySummary>>?> =
        observe("activities") { json.decodeFromString(ListSerializer(ActivitySummary.serializer()), it) }

    val insights: Flow<Cached<InsightsReport>?> = observe("insights") { json.decodeFromString<InsightsReport>(it) }

    fun activity(id: String): Flow<Cached<ActivityDetail>?> = observe("activity:$id") { json.decodeFromString<ActivityDetail>(it) }

    val journal: Flow<List<ReportEntity>> = settings.settings.map { it.currentMode }.flatMapLatest { mode ->
        if (mode == null) flowOf(emptyList()) else db.reports().observeAll(mode)
    }
    val checkins: Flow<List<CheckinEntity>> = db.checkins().observeAll()

    fun report(id: Long): Flow<ReportEntity?> = db.reports().observe(id)
    fun checkinFor(date: String): Flow<CheckinEntity?> = db.checkins().observeForDate(date)

    private suspend fun put(key: String, body: String) {
        val mode = settings.settings.first().currentMode ?: return
        db.cache().put(CachedBlob(key, mode, body, System.currentTimeMillis()))
    }

    /** Status first: it tells us the backend mode, and a mode change wipes the other mode's cache. */
    suspend fun refreshStatus(): Status {
        val body = api.getRaw("/v1/status")
        val s = json.decodeFromString<Status>(body)
        val current = settings.settings.first().currentMode
        if (current != s.mode) {
            db.cache().deleteOtherModes(s.mode)
            db.reports().deleteOtherModes(s.mode)
            settings.setMode(s.mode)
        }
        put("status", body)
        return s
    }

    suspend fun refreshAll() {
        refreshStatus()
        pushPendingCheckins()
        val todayBody = api.getRaw("/v1/today")
        put("today", todayBody)
        val r = json.decodeFromString<MorningReport>(todayBody)
        cacheReport(r.id, "morning", r.localDate, r.localDate, r.revision, r.headline, r.recommendation.state, todayBody)
        put("activities", api.getRaw("/v1/activities"))
        put("insights", api.getRaw("/v1/insights"))
        refreshJournal()
    }

    suspend fun refreshInsights() = put("insights", api.getRaw("/v1/insights"))

    /** Re-fetch today's briefing (used to pick up an AI summary that was still being written). */
    suspend fun refreshToday() {
        val body = api.getRaw("/v1/today")
        put("today", body)
    }

    suspend fun refreshJournal() {
        val list = json.decodeFromString(ListSerializer(ReportListItem.serializer()), api.getRaw("/v1/reports", mapOf("limit" to "200")))
        list.forEach { cacheReport(it.id, it.type, it.subjectKey, it.localDate, it.revision, it.title, it.state, null) }
    }

    private suspend fun cacheReport(id: Long, type: String, key: String, date: String, rev: Int, title: String?, state: String?, body: String?) {
        val mode = settings.settings.first().currentMode ?: return
        val existing = db.reports().get(id)
        db.reports().upsert(ReportEntity(id, type, key, date, rev, title, state, mode, body ?: existing?.json, System.currentTimeMillis()))
    }

    suspend fun loadReport(id: Long) {
        val existing = db.reports().get(id) ?: return
        if (existing.json != null) return
        db.reports().upsert(existing.copy(json = api.getRaw("/v1/reports/$id")))
    }

    suspend fun refreshActivity(id: String) = put("activity:$id", api.getRaw("/v1/activities/$id"))

    /** Starts a backend sync and waits (bounded) for it to finish, then refreshes the cache. */
    suspend fun syncNow() {
        api.post("/v1/sync")
        for (attempt in 0 until 90) {
            delay(2000)
            if (!refreshStatus().syncRunning) break
        }
        refreshAll()
    }

    suspend fun saveCheckin(
        date: String, energy: Int?, soreness: Int?, recovery: Int?, pain: Boolean, illness: Boolean, notes: String?, tags: List<String>,
    ) {
        val existing = db.checkins().observeForDate(date).first()
        val c = CheckinEntity(
            id = existing?.id ?: UUID.randomUUID().toString(), localDate = date, energy = energy, soreness = soreness,
            recovery = recovery, pain = pain, illness = illness, notes = notes?.takeIf { it.isNotBlank() },
            tagsJson = json.encodeToString(ListSerializer(String.serializer()), tags),
            clientUpdatedAt = Instant.now().toString(), pendingSync = true,
        )
        db.checkins().put(c)
    }

    suspend fun pushPendingCheckins() {
        for (c in db.checkins().pending()) {
            val dto = CheckinDto(
                localDate = c.localDate, energy = c.energy, soreness = c.soreness, recovery = c.recovery, pain = c.pain,
                illness = c.illness, notes = c.notes, tags = json.decodeFromString(ListSerializer(String.serializer()), c.tagsJson),
                clientUpdatedAt = c.clientUpdatedAt,
            )
            api.putRaw("/v1/checkins/${c.id}", json.encodeToString(dto))
            db.checkins().markSynced(c.id, c.clientUpdatedAt)
        }
    }

    suspend fun setEffort(activityId: String, rpe: Int) {
        api.putRaw("/v1/activities/$activityId/effort", json.encodeToString(EffortIn(rpe, Instant.now().toString())))
        refreshActivity(activityId)
    }

    suspend fun remoteSettings(): SettingsDto = json.decodeFromString(api.getRaw("/v1/settings"))

    suspend fun saveRemoteSettings(s: SettingsDto): SettingsDto =
        json.decodeFromString(api.putRaw("/v1/settings", json.encodeToString(s)))

    suspend fun exportJson(): String = api.getRaw("/v1/export")

    suspend fun deleteRemote(scope: String) {
        api.delete("/v1/data", mapOf("scope" to scope))
        clearLocal(includeCheckins = scope == "all")
    }

    suspend fun clearLocal(includeCheckins: Boolean) {
        db.cache().clear()
        db.reports().clear()
        if (includeCheckins) db.checkins().clear()
    }
}

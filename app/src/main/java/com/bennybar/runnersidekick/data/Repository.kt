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
import com.bennybar.runnersidekick.data.remote.AuthResult
import com.bennybar.runnersidekick.data.remote.CoachView
import com.bennybar.runnersidekick.data.remote.DayPlanIn
import com.bennybar.runnersidekick.data.remote.Fitness
import com.bennybar.runnersidekick.data.remote.FocusState
import com.bennybar.runnersidekick.data.remote.RunIntentIn
import com.bennybar.runnersidekick.data.remote.GoogleSignInBody
import com.bennybar.runnersidekick.data.remote.InsightsReport
import com.bennybar.runnersidekick.data.remote.Me
import com.bennybar.runnersidekick.data.remote.RevisionInfo
import com.bennybar.runnersidekick.data.remote.Trends
import com.bennybar.runnersidekick.data.remote.WeeklyReport
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
    val weekly: Flow<Cached<WeeklyReport>?> = observe("weekly") { json.decodeFromString<WeeklyReport>(it) }
    val fitness: Flow<Cached<Fitness>?> = observe("fitness") { json.decodeFromString<Fitness>(it) }
    val me: Flow<Cached<Me>?> = observe("me") { json.decodeFromString<Me>(it) }

    suspend fun refreshFitness() = put("fitness", api.getRaw("/v1/fitness"))

    val focus: Flow<Cached<FocusState>?> = observe("focus") { json.decodeFromString<FocusState>(it) }
    val coach: Flow<Cached<CoachView>?> = observe("coach") { json.decodeFromString<CoachView>(it) }

    /** Fetches the coach analysis. A "pending" answer keeps showing the previous analysis until the new one exists. */
    suspend fun refreshCoach(): String {
        val body = api.getRaw("/v1/coach")
        val v = json.decodeFromString<CoachView>(body)
        if (v.status != "pending" || db.cache().get("coach") == null) put("coach", body)
        return v.status
    }

    suspend fun refreshFocus() = put("focus", api.getRaw("/v1/focus"))

    suspend fun chooseFocus(kind: String) = put("focus", api.putRaw("/v1/focus", """{"kind":"$kind"}"""))

    /** Today's intended session; the backend answers with the revised briefing. */
    suspend fun setPlan(date: String, kind: String?, minutes: Int?) {
        val body = if (kind == null) api.delete("/v1/plan/$date", emptyMap())
        else api.putRaw("/v1/plan/$date", json.encodeToString(DayPlanIn(kind, minutes, Instant.now().toString())))
        put("today", body)
    }

    suspend fun setIntent(activityId: String, kind: String, note: String?) {
        api.putRaw("/v1/activities/$activityId/intent", json.encodeToString(RunIntentIn(kind, note?.takeIf { it.isNotBlank() }, Instant.now().toString())))
        refreshActivity(activityId)
        refreshFocus()
    }

    suspend fun setInsightState(id: String, state: String?) {
        put("insights", api.putRaw("/v1/insights/$id/state", if (state == null) """{"state":null}""" else """{"state":"$state"}"""))
    }

    /** Exchanges a Google ID token for an app token; stores it. Returns an error message, or null on success. */
    suspend fun signInWithGoogle(idToken: String, backendUrl: String): String? {
        val (code, body) = api.postPublic(backendUrl, "/v1/auth/google",
            json.encodeToString(GoogleSignInBody(idToken, android.os.Build.MODEL ?: "android")))
        return when (code) {
            200 -> {
                val r = json.decodeFromString<AuthResult>(body)
                settings.setBackend(backendUrl, r.token)
                refreshAll()
                null
            }
            403 -> "This Google account hasn't been invited yet. Ask the server owner to run: sidekick invite add <your email>"
            503 -> "Google sign-in isn't set up on this server yet."
            else -> "Sign-in failed (HTTP $code)."
        }
    }

    suspend fun garminAuthorizeUrl(): String =
        json.parseToJsonElement(api.post("/v1/garmin/oauth/start")).let { (it as kotlinx.serialization.json.JsonObject)["authorize_url"]!!.toString().trim('"') }

    suspend fun disconnectGarmin() { api.delete("/v1/garmin/connection", emptyMap()); refreshStatus() }

    suspend fun deleteAccount() {
        api.delete("/v1/account", emptyMap())
        clearLocal(includeCheckins = true)
        settings.clearToken()
    }

    suspend fun signOut() {
        clearLocal(includeCheckins = false)
        settings.clearToken()
    }

    fun trends(days: Int): Flow<Cached<Trends>?> = observe("trends:$days") { json.decodeFromString<Trends>(it) }
    fun day(date: String): Flow<Cached<MorningReport>?> = observe("day:$date") { json.decodeFromString<MorningReport>(it) }

    suspend fun refreshTrends(days: Int) = put("trends:$days", api.getRaw("/v1/trends", mapOf("days" to "$days")))
    suspend fun refreshDay(date: String) = put("day:$date", api.getRaw("/v1/today", mapOf("date" to date)))
    suspend fun refreshWeekly() {
        val body = runCatching { api.getRaw("/v1/weekly/latest") }.getOrElse { if (it is com.bennybar.runnersidekick.data.remote.ApiException.Http && it.code == 404) return else throw it }
        put("weekly", body)
    }

    /** Earlier revisions of a report, newest first. Opening one caches it like any other report. */
    suspend fun revisions(type: String, key: String): List<RevisionInfo> =
        json.decodeFromString(ListSerializer(RevisionInfo.serializer()), api.getRaw("/v1/reports/$type/$key/revisions"))

    suspend fun cacheRevision(id: Long, type: String, key: String, date: String, revision: Int) {
        if (db.reports().get(id)?.json != null) return
        cacheReport(id, type, key, date, revision, null, null, api.getRaw("/v1/reports/$id"))
    }

    fun activity(id: String): Flow<Cached<ActivityDetail>?> = observe("activity:$id") { json.decodeFromString<ActivityDetail>(it) }

    val journal: Flow<List<ReportEntity>> = settings.settings.map { it.currentMode }.flatMapLatest { mode ->
        if (mode == null) flowOf(emptyList()) else db.reports().observeAll(mode)
    }
    private val account: Flow<String?> = settings.settings.map { it.account }

    val checkins: Flow<List<CheckinEntity>> = account.flatMapLatest { a -> if (a == null) flowOf(emptyList()) else db.checkins().observeAll(a) }

    fun report(id: Long): Flow<ReportEntity?> = db.reports().observe(id)
    fun checkinFor(date: String): Flow<CheckinEntity?> =
        account.flatMapLatest { a -> if (a == null) flowOf(null) else db.checkins().observeForDate(date, a) }

    /**
     * Identifies the signed-in account and scopes local data to it. A different account than last time clears the
     * cached reports (never another account's check-ins, which stay hidden and are never uploaded under this account).
     */
    private suspend fun establishAccount(): String {
        val body = api.getRaw("/v1/me")
        val me = json.decodeFromString<Me>(body)
        val key = "${settings.settings.first().backendUrl.trimEnd('/')}#${me.id}"
        val previous = settings.settings.first().account
        if (previous != key) {
            db.cache().clear()
            db.reports().clear()
            if (previous == null) db.checkins().adoptLegacy(key)
            settings.setAccount(key)
        }
        put("me", body)
        return key
    }

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
        establishAccount()
        pushPendingCheckins()
        val todayBody = api.getRaw("/v1/today")
        put("today", todayBody)
        val r = json.decodeFromString<MorningReport>(todayBody)
        cacheReport(r.id, "morning", r.localDate, r.localDate, r.revision, r.headline, r.recommendation.state, todayBody)
        put("activities", api.getRaw("/v1/activities"))
        put("insights", api.getRaw("/v1/insights"))
        refreshWeekly()
        refreshFitness()
        refreshFocus()
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
        val acct = settings.settings.first().account ?: ""
        val existing = db.checkins().observeForDate(date, acct).first()
        val c = CheckinEntity(
            id = existing?.id ?: UUID.randomUUID().toString(), localDate = date, energy = energy, soreness = soreness,
            recovery = recovery, pain = pain, illness = illness, notes = notes?.takeIf { it.isNotBlank() },
            tagsJson = json.encodeToString(ListSerializer(String.serializer()), tags),
            clientUpdatedAt = Instant.now().toString(), pendingSync = true, account = acct,
        )
        db.checkins().put(c)
    }

    suspend fun pushPendingCheckins() {
        val acct = settings.settings.first().account ?: return  // unknown account: upload nothing
        for (c in db.checkins().pending(acct)) {
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

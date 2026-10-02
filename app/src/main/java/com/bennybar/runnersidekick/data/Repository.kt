package com.bennybar.runnersidekick.data

import androidx.room.withTransaction

import com.bennybar.runnersidekick.data.local.CachedBlob
import com.bennybar.runnersidekick.data.local.CheckinEntity
import com.bennybar.runnersidekick.data.local.ReportEntity
import com.bennybar.runnersidekick.data.local.SettingsStore
import com.bennybar.runnersidekick.data.local.SidekickDb
import com.bennybar.runnersidekick.data.remote.ActivityDetail
import com.bennybar.runnersidekick.data.remote.ActivitySummary
import com.bennybar.runnersidekick.data.remote.ApiClient
import com.bennybar.runnersidekick.data.remote.CheckinDto
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
    // encodeDefaults: without it, a value equal to its default (ai_enabled = false, a cleared goal = null) is left out of
    // the request, so the server could never turn AI off or clear a field
    private val withNulls = kotlinx.serialization.json.Json { ignoreUnknownKeys = true; explicitNulls = true; encodeDefaults = true }

    private fun <T> observe(key: String, decode: (String) -> T): Flow<Cached<T>?> =
        settings.settings.map { it.currentMode }.flatMapLatest { mode ->
            if (mode == null) flowOf(null)
            else db.cache().observe(key, mode).map { b ->
                b?.let { runCatching { Cached(decode(it.json), Instant.ofEpochMilli(it.fetchedAt)) }.getOrNull() }
            }
        }.flowOn(Dispatchers.Default) // decoding large reports must not block the main thread

    val status: Flow<Cached<Status>?> = observe("status") { json.decodeFromString<Status>(it) }
    /** The day weeks start on (Settings, else Garmin's profile, else Monday), as the backend reports it. */
    val weekStart: Flow<java.time.DayOfWeek> = status.map { com.bennybar.runnersidekick.ui.Format.firstDay(it?.value?.weekStartDay) }
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
    val compare: Flow<Cached<com.bennybar.runnersidekick.data.remote.CompareReport>?> =
        observe("compare") { json.decodeFromString<com.bennybar.runnersidekick.data.remote.CompareReport>(it) }

    /** The runner's own OpenAI key, sent only with requests that may call the AI (coach, screen summaries). */
    private suspend fun aiHeaders() = settings.ownAiKey()?.let { mapOf("X-OpenAI-Key" to it) } ?: emptyMap()

    /** Returns true while the screen's AI summary is still being written. */
    suspend fun refreshCompare(): Boolean {
        val body = api.getRaw("/v1/compare", headers = aiHeaders())
        put("compare", body)
        return json.decodeFromString<com.bennybar.runnersidekick.data.remote.CompareReport>(body).aiSummary?.status == "pending"
    }

    /** Fetches the coach analysis, polling (bounded) while the backend writes a new one for changed inputs. */
    suspend fun pollCoach(pause: suspend (Int) -> Unit) {
        for (attempt in 0 until 20) {
            if (runCatching { refreshCoach() }.getOrDefault("failed") != "pending") return
            pause(attempt)
        }
    }

    /** A "pending" answer carries the previous analysis, which the UI shows marked as updating. */
    suspend fun refreshCoach(): String {
        // The runner's own key goes only with this request, never with any other call
        val body = api.getRaw("/v1/coach", headers = aiHeaders())
        put("coach", body)
        return json.decodeFromString<CoachView>(body).status
    }

    suspend fun refreshFocus() = put("focus", api.getRaw("/v1/focus"))

    suspend fun chooseFocus(kind: String) = put("focus", api.putRaw("/v1/focus", """{"kind":"$kind"}"""))

    /** Today's intended session; the backend answers with the revised briefing. */
    suspend fun setPlan(date: String, kind: String?, minutes: Int?) {
        val body = if (kind == null) api.delete("/v1/plan/$date", emptyMap())
        else api.putRaw("/v1/plan/$date", json.encodeToString(DayPlanIn(kind, minutes, Instant.now().toString())))
        put("today", body)
        val r = json.decodeFromString<MorningReport>(body)
        cacheReport(r.id, "morning", r.localDate, r.localDate, r.revision, r.headline, r.recommendation.state, body)
    }

    suspend fun setIntent(activityId: String, kind: String, note: String?) {
        api.putRaw("/v1/activities/$activityId/intent", json.encodeToString(RunIntentIn(kind, note?.takeIf { it.isNotBlank() }, Instant.now().toString())))
        refreshActivity(activityId)
        refreshFocus()
        // The AI input was written for the old type: refresh its state so "Update AI input" shows straight away
        runCatching { refreshRunAi(activityId) }
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

    suspend fun refreshTrends(days: Int): Boolean {
        val body = api.getRaw("/v1/trends", mapOf("days" to "$days"), aiHeaders())
        put("trends:$days", body)
        return json.decodeFromString<Trends>(body).aiSummary?.status == "pending"
    }
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
            val status = db.cache().get("status")  // fetched just before; keep it
            db.cache().clear()
            db.reports().clear()
            status?.let { db.cache().put(it) }
            if (previous == null) db.checkins().adoptLegacy(key) else settings.setOwnAiKey(null)  // a key belongs to one account
            settings.setAccount(key)
        }
        put("me", body)
        return key
    }

    private suspend fun put(key: String, body: String) {
        val mode = settings.settings.first().currentMode ?: return
        // Unchanged content isn't rewritten: no disk write and no needless refresh of every screen observing it
        val existing = db.cache().get(key)
        if (existing != null && existing.mode == mode && existing.json == body) return
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
        pullCheckins()
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
        // One transaction for the whole list; rows that didn't change are skipped in cacheReport
        db.withTransaction { list.forEach { cacheReport(it.id, it.type, it.subjectKey, it.localDate, it.revision, it.title, it.state, null) } }
    }

    private suspend fun cacheReport(id: Long, type: String, key: String, date: String, rev: Int, title: String?, state: String?, body: String?) {
        val mode = settings.settings.first().currentMode ?: return
        val existing = db.reports().get(id)
        if (body == null && existing != null && existing.mode == mode && existing.revision == rev && existing.title == title &&
            existing.state == state) return
        db.reports().upsert(ReportEntity(id, type, key, date, rev, title, state, mode, body ?: existing?.json, System.currentTimeMillis()))
    }

    suspend fun loadReport(id: Long) {
        val existing = db.reports().get(id) ?: return
        if (existing.json != null) return
        db.reports().upsert(existing.copy(json = api.getRaw("/v1/reports/$id")))
    }

    suspend fun refreshActivity(id: String) = put("activity:$id", api.getRaw("/v1/activities/$id"))

    fun runAi(id: String): Flow<Cached<com.bennybar.runnersidekick.data.remote.RunAi>?> =
        observe("runai:$id") { json.decodeFromString<com.bennybar.runnersidekick.data.remote.RunAi>(it) }

    /** The run's AI input; [request] asks for it to be written (only then does it cost an AI call). Returns the status. */
    suspend fun refreshRunAi(id: String, request: Boolean = false): String {
        val body = if (request) api.postRaw("/v1/activities/$id/ai", aiHeaders()) else api.getRaw("/v1/activities/$id/ai", headers = aiHeaders())
        put("runai:$id", body)
        return json.decodeFromString<com.bennybar.runnersidekick.data.remote.RunAi>(body).status
    }

    /** Syncs with Garmin now and says how many new runs arrived. */
    suspend fun syncRunsNow(pause: suspend (Int) -> Unit): Int {
        val before = activities.first()?.value.orEmpty().map { it.sourceId }.toSet()
        syncNow(pause)
        return activities.first()?.value.orEmpty().count { it.sourceId !in before }
    }

    /** The background worker's small refresh: what the notifications read, nothing else. */
    suspend fun backgroundRefresh() {
        refreshStatus()
        pushPendingCheckins()
        put("today", api.getRaw("/v1/today"))
        put("activities", api.getRaw("/v1/activities"))
        refreshWeekly()
        refreshFocus()
    }

    /** Starts a backend sync and waits (bounded) for it to finish, then refreshes the cache. For an explicit tap only. */
    suspend fun syncNow(pause: suspend (Int) -> Unit) {
        api.post("/v1/sync")
        for (attempt in 0 until 40) {
            pause(attempt)
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
            val stored = json.decodeFromString<CheckinDto>(api.putRaw("/v1/checkins/${c.id}", json.encodeToString(dto)))
            // A newer version on the server wins; keep that one instead of ours
            if (stored.clientUpdatedAt != c.clientUpdatedAt) mergeServerCheckin(stored, acct) else db.checkins().markSynced(c.id, c.clientUpdatedAt)
        }
    }

    /** Pulls the account's check-ins so a reinstall or second phone shows the same history. Last write wins. */
    suspend fun pullCheckins() {
        val acct = settings.settings.first().account ?: return
        json.decodeFromString(ListSerializer(CheckinDto.serializer()), api.getRaw("/v1/checkins")).forEach { mergeServerCheckin(it, acct) }
    }

    private suspend fun mergeServerCheckin(s: CheckinDto, acct: String) {
        val id = s.id ?: return
        val local = db.checkins().get(id)
        if (local != null && local.clientUpdatedAt >= s.clientUpdatedAt) return
        if (s.deleted) { if (local != null) db.checkins().delete(id); return }
        db.checkins().put(CheckinEntity(
            id = id, localDate = s.localDate, energy = s.energy, soreness = s.soreness, recovery = s.recovery, pain = s.pain,
            illness = s.illness, notes = s.notes, tagsJson = json.encodeToString(ListSerializer(String.serializer()), s.tags),
            clientUpdatedAt = s.clientUpdatedAt, pendingSync = false, account = acct,
        ))
    }

    suspend fun remoteSettings(): SettingsDto = json.decodeFromString(api.getRaw("/v1/settings"))

    suspend fun saveRemoteSettings(s: SettingsDto): SettingsDto =
        // Nulls are sent on purpose: a cleared goal or usual time must clear it on the server too
        json.decodeFromString(api.putRaw("/v1/settings", withNulls.encodeToString(s)))

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

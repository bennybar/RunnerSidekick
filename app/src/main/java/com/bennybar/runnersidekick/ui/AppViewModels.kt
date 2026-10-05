package com.bennybar.runnersidekick.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.CreationExtras
import com.bennybar.runnersidekick.RunnerApp
import com.bennybar.runnersidekick.data.Repository
import com.bennybar.runnersidekick.data.remote.ApiException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/** Shared plumbing: a busy flag and a human-readable error for the last failed network action. */
open class BaseVm(val repo: Repository) : ViewModel() {
    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()
    private val _offline = MutableStateFlow(false)
    /** True while the last network action could not reach the backend; the UI keeps showing cached data. */
    val offline: StateFlow<Boolean> = _offline.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    val settings = repo.settings.settings.stateIn(viewModelScope, SharingStarted.Eagerly, null)

    fun <T> kotlinx.coroutines.flow.Flow<T>.state(initial: T) = stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), initial)

    fun launchIo(block: suspend () -> Unit): kotlinx.coroutines.Job = viewModelScope.launch { runIo(block) }

    /** Runs [block] in the caller's own coroutine with the loading flag and error handling, so cancelling the caller
     * cancels the work too. */
    suspend fun runIo(block: suspend () -> Unit) {
        _busy.value = true
        _error.value = null
        try {
            block()
            _offline.value = false
        } catch (e: ApiException) {
            _offline.value = e is ApiException.Network
            _error.value = when (e) {
                is ApiException.NotConfigured -> "Backend not set up. Open Settings to connect."
                is ApiException.Unauthorized -> "The backend rejected this device's token. Enter a new one in Settings."
                is ApiException.Network -> "Can't reach the backend. Showing saved data."
                is ApiException.Http -> "Backend error (${e.code}). Showing saved data."
                is ApiException.Sync -> e.detail
            }
        } catch (e: kotlinx.serialization.SerializationException) {
            // A contract mismatch must never crash the app or replace cached data
            android.util.Log.e("RunnerSidekick", "Unexpected backend response", e)
            _error.value = "Unexpected response from the backend. Showing saved data."
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e  // leaving the screen cancels its work; that isn't an error
        } catch (e: Exception) {
            // Anything else (storage, the database, opening a page): a message, never a crash
            android.util.Log.e("RunnerSidekick", "Unexpected error", e)
            _error.value = "Something went wrong: ${e.message ?: e.javaClass.simpleName}"
        } finally {
            _busy.value = false
        }
    }

    fun clearError() { _error.value = null }

    // Polls only run while their screen is visible (see TrackVisible); true until a screen says otherwise
    private val visible = MutableStateFlow(true)
    fun setVisible(v: Boolean) { visible.value = v }

    /** The wait between polls: 3 s, growing ×1.5 to at most 15 s, and no requests at all while the screen is hidden. */
    suspend fun pause(attempt: Int) = pause(attempt, 3_000.0, 15_000.0)
    suspend fun pause(attempt: Int, firstMs: Double, maxMs: Double) {
        kotlinx.coroutines.delay(kotlin.math.min(maxMs, firstMs * Math.pow(1.5, attempt.toDouble())).toLong())
        visible.first { it }
    }
}

class TodayVm(repo: Repository) : BaseVm(repo) {
    val status = repo.status.state(null)
    val today = repo.today.state(null)
    val fitness = repo.fitness.state(null)
    val coach = repo.coach.state(null)

    // New data changes the evidence, so the coach is asked again rather than left showing older advice
    private var coachJob: kotlinx.coroutines.Job? = null
    private fun updateCoach() {
        if (coachJob?.isActive == true) return  // one coach poll at a time, however often Today refreshes
        coachJob = viewModelScope.launch { repo.pollCoach(::pause) }
    }

    init { refresh() }

    fun refresh() = launchIo {
        repo.refreshAll()
        updateCoach()
    }
    fun syncNow() = launchIo { repo.syncNow { pause(it, 2_000.0, 8_000.0) } }
    val checkins = repo.checkins.state(emptyList())
    // The coach's advice was written before this: ask again so it can't sit next to a changed recommendation
    fun setUnwell(date: String, on: Boolean) = launchIo { repo.setUnwell(date, on); updateCoach() }
}

class InsightsVm(repo: Repository) : BaseVm(repo) {
    val insights = repo.insights.state(null)
    val coach = repo.coach.state(null)
    private val _coachLoading = MutableStateFlow(false)
    val coachLoading: StateFlow<Boolean> = _coachLoading.asStateFlow()

    private var coachJob: kotlinx.coroutines.Job? = null
    // One coach poll at a time: opening Insights asks from both the ViewModel and the screen
    fun loadCoach() {
        if (coachJob?.isActive == true) return
        coachJob = pollCoachJob()
    }
    private fun pollCoachJob() = viewModelScope.launch {
        _coachLoading.value = true
        try {
            repo.pollCoach(::pause)
        } finally {
            _coachLoading.value = false
        }
    }
    val weekly = repo.weekly.state(null)
    val fitness = repo.fitness.state(null)
    val compare = repo.compare.state(null)
    val today = repo.today.state(null)
    val focus = repo.focus.state(null)
    fun chooseFocus(kind: String) = launchIo { repo.chooseFocus(kind) }
    val weekStart = repo.weekStart.state(java.time.DayOfWeek.MONDAY)
    // The visible sub-tab (0 Insights, 1 Compare, 2 Trends): Compare and Trends poll only while they're shown
    private val tab = MutableStateFlow(0)
    // Trends (and its AI summary) load only once that tab is opened
    fun setTab(t: Int) { tab.value = t; if (t == 2 && trendsJob == null) loadTrends(_days.value) }
    private var compareJob: kotlinx.coroutines.Job? = null
    fun loadCompare() {
        if (compareJob?.isActive == true) return
        compareJob = fetchThenPoll(1, repo::refreshCompare)
    }

    /** Re-fetch (bounded, without the busy indicator) while a screen's AI summary is written in the background. */
    /** The first fetch shows the refresh indicator and errors; the follow-up poll runs quietly. One job owns both, so
     * cancelling it means no poll starts afterwards. */
    private fun fetchThenPoll(onTab: Int, fetch: suspend () -> Boolean) = viewModelScope.launch {
        var pending = false
        runIo { pending = fetch() }  // inside this job: a new range cancels the old fetch too, not just its poll
        if (pending) pollQuietly(onTab, fetch)
    }
    private suspend fun pollQuietly(onTab: Int, fetch: suspend () -> Boolean) {
        for (attempt in 0 until 10) {
            pause(attempt)
            tab.first { it == onTab }
            if (!runCatching { fetch() }.getOrDefault(false)) return
        }
    }
    // One trends job (first fetch and its poll together): a new range cancels the old one, so a slow answer for the
    // previous range can't restart its poll
    private var trendsJob: kotlinx.coroutines.Job? = null
    private fun loadTrends(d: Int) {
        trendsJob?.cancel()
        trendsJob = fetchThenPoll(2) { repo.refreshTrends(d) }
    }
    private val _days = MutableStateFlow(28)
    val days: StateFlow<Int> = _days.asStateFlow()

    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    val trends = _days.flatMapLatest { repo.trends(it) }.state(null)

    init { refresh() }
    fun refresh() = launchIo { repo.refreshInsights(); repo.refreshWeekly(); repo.refreshFitness(); if (tab.value == 2) loadTrends(_days.value) }
        .also { loadCoach() }
    fun setDays(d: Int) { _days.value = d; loadTrends(d) }
    fun setInsightState(id: String, state: String?) = launchIo { repo.setInsightState(id, state) }
}

class DayVm(repo: Repository, val date: String) : BaseVm(repo) {
    val day = repo.day(date).state(null)
    init { launchIo { repo.refreshDay(date) } }
}

class ActivitiesVm(repo: Repository) : BaseVm(repo) {
    val activities = repo.activities.state(null)
    val status = repo.status.state(null)
    private val _syncResult = MutableStateFlow<String?>(null)
    /** One-off message after a manual sync ("2 new runs", "No new runs"). */
    val syncResult: StateFlow<String?> = _syncResult.asStateFlow()
    fun syncNow() = launchIo {
        val n = repo.syncRunsNow { pause(it, 2_000.0, 8_000.0) }
        _syncResult.value = "Synced with Garmin · " + when (n) { 0 -> "no new runs"; 1 -> "1 new run"; else -> "$n new runs" }
    }
    fun clearSyncResult() { _syncResult.value = null }
    val weekStart = repo.weekStart.state(java.time.DayOfWeek.MONDAY)
    fun refresh() = launchIo { repo.refreshAll() }
}

class ActivityVm(repo: Repository, val id: String) : BaseVm(repo) {
    val detail = repo.activity(id).state(null)
    val ai = repo.runAi(id).state(null)
    init { refresh() }
    fun refresh() = launchIo { repo.refreshActivity(id); runCatching { repo.refreshRunAi(id) } }

    private val _notice = MutableStateFlow<String?>(null)
    /** One-off confirmation, e.g. where an export was saved. */
    val notice: StateFlow<String?> = _notice.asStateFlow()
    fun clearNotice() { _notice.value = null }

    /** Saves the run as one Markdown file in the phone's Downloads folder (not the app's own folder). */
    fun export(context: android.content.Context, fileName: String) = launchIo {
        val text = repo.exportRun(id)
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            com.bennybar.runnersidekick.data.Downloads.saveText(context.applicationContext, fileName, "text/markdown", text)
        }
        _notice.value = "Saved to Downloads: $fileName"
    }

    /** Asks for the AI input, then follows it (bounded) while it is written in the background. */
    fun askAi() = launchIo {
        if (repo.refreshRunAi(id, request = true) != "pending") return@launchIo
        viewModelScope.launch {
            for (attempt in 0 until 20) {
                pause(attempt)
                if (runCatching { repo.refreshRunAi(id) }.getOrDefault("failed") != "pending") break
            }
        }
    }
    fun setIntent(i: com.bennybar.runnersidekick.data.remote.RunIntent) = launchIo { repo.setIntent(id, i) }
}

class JournalVm(repo: Repository) : BaseVm(repo) {
    val reports = repo.journal.state(emptyList())
    val checkins = repo.checkins.state(emptyList())
    init { launchIo { repo.refreshJournal() } }
    fun refresh() = launchIo { repo.refreshJournal() }
}

class ReportVm(repo: Repository, val id: Long) : BaseVm(repo) {
    val report = repo.report(id).state(null)
    val revisions = MutableStateFlow<List<com.bennybar.runnersidekick.data.remote.RevisionInfo>>(emptyList())
    init {
        launchIo {
            repo.loadReport(id)
            repo.report(id).first()?.let { r -> revisions.value = repo.revisions(r.type, r.subjectKey) }
        }
    }
    fun open(rev: com.bennybar.runnersidekick.data.remote.RevisionInfo, onReady: () -> Unit) = launchIo {
        val r = report.value ?: return@launchIo
        repo.cacheRevision(rev.id, r.type, r.subjectKey, r.localDate, rev.revision)
        onReady()
    }
}

@Suppress("UNCHECKED_CAST")
fun <T : ViewModel> factory(create: (Repository) -> T) = object : ViewModelProvider.Factory {
    override fun <V : ViewModel> create(modelClass: Class<V>, extras: CreationExtras): V {
        val app = extras[ViewModelProvider.AndroidViewModelFactory.APPLICATION_KEY] as RunnerApp
        return create(app.repository) as V
    }
}

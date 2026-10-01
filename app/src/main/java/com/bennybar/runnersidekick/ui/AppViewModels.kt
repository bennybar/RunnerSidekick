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
import kotlinx.coroutines.flow.flowOf
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

    fun launchIo(block: suspend () -> Unit) {
        viewModelScope.launch {
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
                }
            } catch (e: kotlinx.serialization.SerializationException) {
                // A contract mismatch must never crash the app or replace cached data
                android.util.Log.e("RunnerSidekick", "Unexpected backend response", e)
                _error.value = "Unexpected response from the backend. Showing saved data."
            } finally {
                _busy.value = false
            }
        }
    }

    fun clearError() { _error.value = null }
}

class TodayVm(repo: Repository) : BaseVm(repo) {
    val status = repo.status.state(null)
    val today = repo.today.state(null)
    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    val todayCheckin = repo.status.flatMapLatest { s -> s?.let { repo.checkinFor(it.value.today) } ?: flowOf(null) }.state(null)

    val insights = repo.insights.state(null)

    init { refresh() }

    fun refresh() = launchIo {
        repo.refreshAll()
        // An AI summary may still be in progress; check back a few times (bounded).
        for (attempt in 0 until 6) {
            if (today.value?.value?.narrative?.status != "pending") break
            kotlinx.coroutines.delay(5000)
            repo.refreshToday()
        }
    }
    fun syncNow() = launchIo { repo.syncNow() }

    fun saveCheckin(date: String, energy: Int?, soreness: Int?, recovery: Int?, pain: Boolean, illness: Boolean, notes: String?) =
        launchIo {
            repo.saveCheckin(date, energy, soreness, recovery, pain, illness, notes, emptyList())
            repo.refreshAll() // pushes the check-in and fetches the revised briefing; offline it stays pending
        }
}

class InsightsVm(repo: Repository) : BaseVm(repo) {
    val insights = repo.insights.state(null)
    val weekly = repo.weekly.state(null)
    private val _days = MutableStateFlow(28)
    val days: StateFlow<Int> = _days.asStateFlow()

    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    val trends = _days.flatMapLatest { repo.trends(it) }.state(null)

    init { refresh() }
    fun refresh() = launchIo { repo.refreshInsights(); repo.refreshWeekly(); repo.refreshTrends(_days.value) }
    fun setDays(d: Int) { _days.value = d; launchIo { repo.refreshTrends(d) } }
}

class DayVm(repo: Repository, val date: String) : BaseVm(repo) {
    val day = repo.day(date).state(null)
    init { launchIo { repo.refreshDay(date) } }
}

class ActivitiesVm(repo: Repository) : BaseVm(repo) {
    val activities = repo.activities.state(null)
    fun refresh() = launchIo { repo.refreshAll() }
}

class ActivityVm(repo: Repository, val id: String) : BaseVm(repo) {
    val detail = repo.activity(id).state(null)
    init { refresh() }
    fun refresh() = launchIo { repo.refreshActivity(id) }
    fun setEffort(rpe: Int) = launchIo { repo.setEffort(id, rpe) }
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

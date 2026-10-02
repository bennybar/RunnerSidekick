package com.bennybar.runnersidekick

import android.app.Application
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.bennybar.runnersidekick.data.Repository
import com.bennybar.runnersidekick.data.local.SettingsStore
import com.bennybar.runnersidekick.data.local.SidekickDb
import com.bennybar.runnersidekick.data.remote.ApiClient
import com.bennybar.runnersidekick.work.Notifier
import com.bennybar.runnersidekick.work.RefreshWorker
import java.util.concurrent.TimeUnit

class RunnerApp : Application() {
    lateinit var repository: Repository
        private set

    override fun onCreate() {
        super.onCreate()
        val settings = SettingsStore(this)
        repository = Repository(SidekickDb.create(this), ApiClient { settings.credentials() }, settings)
        Notifier.createChannels(this)
        // Best-effort background refresh, only while signed in; timing is up to the OS (hourly at most, so the morning
        // window can be met). The server syncs Garmin itself, so this only fetches what notifications need.
        val wm = WorkManager.getInstance(this)
        kotlinx.coroutines.MainScope().launch {
            settings.settings.map { it.hasToken }.distinctUntilChanged().collect { signedIn ->
                if (signedIn) wm.enqueueUniquePeriodicWork(
                    "refresh",
                    ExistingPeriodicWorkPolicy.UPDATE,
                    PeriodicWorkRequestBuilder<RefreshWorker>(1, TimeUnit.HOURS)
                        .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).setRequiresBatteryNotLow(true).build())
                        .build(),
                ) else wm.cancelUniqueWork("refresh")
            }
        }
    }
}

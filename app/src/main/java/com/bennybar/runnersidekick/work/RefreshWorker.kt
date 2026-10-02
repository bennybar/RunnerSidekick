package com.bennybar.runnersidekick.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.bennybar.runnersidekick.RunnerApp
import com.bennybar.runnersidekick.data.remote.ApiException
import kotlinx.coroutines.flow.first

/** Fetches what notifications (and the offline copy) need. The server syncs Garmin hourly by itself, so the phone doesn't start a sync
 * or wait on one in the background (that was up to ~100 requests and minutes of radio time per run). */
class RefreshWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val repo = (applicationContext as RunnerApp).repository
        val s = repo.settings.settings.first()
        if (!s.notificationsEnabled && !s.backgroundRefresh) return Result.success()  // nothing to serve: no reads
        return try {
            repo.backgroundRefresh()
            if (s.notificationsEnabled) Notifier.check(applicationContext, repo)
            Result.success()
        } catch (_: ApiException.NotConfigured) {
            Result.success()
        } catch (_: ApiException.Unauthorized) {
            Result.failure() // a rejected token will not fix itself; avoid retry storms
        } catch (_: ApiException) {
            if (runAttemptCount < 3) Result.retry() else Result.failure()
        }
    }
}

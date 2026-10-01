package com.bennybar.runnersidekick.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.bennybar.runnersidekick.RunnerApp
import com.bennybar.runnersidekick.data.remote.ApiException

/** Pushes offline check-ins, asks the backend to sync, and refreshes the local cache. */
class RefreshWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val repo = (applicationContext as RunnerApp).repository
        return try {
            repo.syncNow()
            Notifier.check(applicationContext, repo)
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

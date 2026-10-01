package com.bennybar.runnersidekick.work

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.bennybar.runnersidekick.MainActivity
import com.bennybar.runnersidekick.R
import com.bennybar.runnersidekick.data.Repository
import com.bennybar.runnersidekick.ui.Format
import kotlinx.coroutines.flow.first
import java.time.Duration
import java.time.Instant
import java.time.LocalTime

/**
 * Best-effort local notifications, de-duplicated on the phone:
 *  - morning briefing: once per date, inside the morning window; when the window ends a provisional briefing is
 *    posted as provisional. A later change of suggestion silently updates the same notification.
 *  - run report: once per new run that started in the last 24 h. Runs already known at first use are never notified.
 */
object Notifier {
    private const val CH_MORNING = "morning"
    private const val CH_RUNS = "runs"
    private const val ID_MORNING = 1

    fun createChannels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_MORNING, "Morning briefing", NotificationManager.IMPORTANCE_DEFAULT))
        nm.createNotificationChannel(NotificationChannel(CH_RUNS, "Run reports", NotificationManager.IMPORTANCE_LOW))
    }

    private fun allowed(ctx: Context) =
        ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private fun openApp(ctx: Context) = PendingIntent.getActivity(
        ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
        PendingIntent.FLAG_IMMUTABLE,
    )

    suspend fun check(ctx: Context, repo: Repository, now: Instant = Instant.now()) {
        val settings = repo.settings.settings.first()
        if (!settings.notificationsEnabled || !allowed(ctx)) return
        val state = repo.settings.notifyState.first()
        val nm = NotificationManagerCompat.from(ctx)
        val remote = runCatching { repo.remoteSettings() }.getOrNull()
        val zone = java.time.ZoneId.of(remote?.timezone ?: java.time.ZoneId.systemDefault().id)
        val local = now.atZone(zone)
        val start = LocalTime.parse(remote?.morningWindowStart ?: "06:00")
        val end = LocalTime.parse(remote?.morningWindowEnd ?: "10:00")

        repo.today.first()?.value?.let { r ->
            val isToday = r.localDate == local.toLocalDate().toString()
            val inWindow = local.toLocalTime() >= start
            val ready = !r.provisional || local.toLocalTime() >= end
            val stateKey = r.recommendation.state
            if (isToday && inWindow && ready && (state.morningDate != r.localDate || state.morningState != stateKey)) {
                val firstToday = state.morningDate != r.localDate
                val n = NotificationCompat.Builder(ctx, CH_MORNING)
                    .setSmallIcon(R.drawable.ic_stat_pulse)
                    .setContentTitle((if (r.provisional) "Provisional · " else "") + r.headline)
                    .setContentText(r.recommendation.suggestion)
                    .setStyle(NotificationCompat.BigTextStyle().bigText(r.recommendation.suggestion))
                    .setContentIntent(openApp(ctx)).setAutoCancel(true)
                    .setOnlyAlertOnce(true).setSilent(!firstToday) // a revision updates quietly
                    .build()
                @Suppress("MissingPermission") nm.notify(ID_MORNING, n)
                repo.settings.markMorningNotified(r.localDate, stateKey)
            }
        }

        val acts = repo.activities.first()?.value.orEmpty()
        if (!state.runsSeeded) {
            repo.settings.markRunsSeen(acts.map { it.sourceId }) // first use: history is not news
            return
        }
        val fresh = acts.filter { it.sourceId !in state.runsSeen && Duration.between(Instant.parse(it.startUtc), now).toHours() < 24 }
        val units = settings.units
        fresh.forEach { a ->
            val n = NotificationCompat.Builder(ctx, CH_RUNS)
                .setSmallIcon(R.drawable.ic_stat_pulse)
                .setContentTitle("Run report ready")
                .setContentText("${Format.distance(a.distanceM, units)} · ${Format.pace(a.paceMovingSPerKm, units)} · ${Format.shortDate(a.localDate)}")
                .setContentIntent(openApp(ctx)).setAutoCancel(true)
                .build()
            @Suppress("MissingPermission") nm.notify(a.sourceId.hashCode(), n)
        }
        if (acts.isNotEmpty()) repo.settings.markRunsSeen(acts.map { it.sourceId })
    }
}

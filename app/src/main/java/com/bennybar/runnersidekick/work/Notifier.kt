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
    private const val CH_WEEKLY = "weekly"
    private const val ID_MORNING = 1
    private const val ID_WEEKLY = 2

    fun createChannels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_MORNING, "Morning briefing", NotificationManager.IMPORTANCE_DEFAULT))
        nm.createNotificationChannel(NotificationChannel(CH_RUNS, "Run reports", NotificationManager.IMPORTANCE_LOW))
        nm.createNotificationChannel(NotificationChannel(CH_WEEKLY, "Weekly digest", NotificationManager.IMPORTANCE_DEFAULT))
    }

    private fun allowed(ctx: Context) =
        ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private fun openApp(ctx: Context, run: String? = null, report: Long? = null) = PendingIntent.getActivity(
        ctx, run?.hashCode() ?: report?.toInt() ?: 0,
        Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .apply { run?.let { putExtra(MainActivity.EXTRA_OPEN_RUN, it) }; report?.let { putExtra(MainActivity.EXTRA_OPEN_REPORT, it) } },
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
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
            // The same one decision Today shows: readiness and the next run. A changed decision updates the notification.
            val rd = r.readiness?.takeIf { it.status == "ok" }
            val nr = r.nextRun
            val title = rd?.let { "Readiness ${it.score} · ${it.headline ?: it.label}" } ?: r.headline
            val text = nr?.let { n -> listOfNotNull("${n.title} ${n.dayLabel.lowercase()}", n.distanceKm?.let { Format.distance(it * 1000, settings.units) }, n.hr?.text)
                .joinToString(" · ") } ?: r.recommendation.suggestion
            val stateKey = "${rd?.score}|${title.hashCode()}|${text.hashCode()}"
            if (isToday && inWindow && ready && (state.morningDate != r.localDate || state.morningState != stateKey)) {
                val firstToday = state.morningDate != r.localDate
                val body = text + (nr?.why?.takeIf { it.isNotEmpty() }?.let { "\n" + it.joinToString(" · ") } ?: "")
                val n = NotificationCompat.Builder(ctx, CH_MORNING)
                    .setSmallIcon(R.drawable.ic_stat_pulse)
                    .setContentTitle(title)
                    .setContentText(text)
                    .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                    .setContentIntent(openApp(ctx)).setAutoCancel(true)
                    .setOnlyAlertOnce(true).setSilent(!firstToday) // a revision updates quietly
                    .build()
                @Suppress("MissingPermission") nm.notify(ID_MORNING, n)
                repo.settings.markMorningNotified(r.localDate, stateKey)
            }
        }

        // Weekly digest: on the first day of the week, from the start of the morning window, once per week
        val firstDay = repo.weekStart.first()
        val weekStart = Format.weekStart(local.toLocalDate(), firstDay)
        if (local.dayOfWeek == firstDay && local.toLocalTime() >= start && state.weeklyWeek != weekStart.toString()) {
            val w = repo.weekly.first()?.value
            if (w != null && w.weekStart == weekStart.minusWeeks(1).toString()) {
                val focus = repo.focus.first()?.value?.current?.title
                val body = "This week's focus: ${focus ?: "pick one in Today"}" + "\n" + "Next week from the review: ${w.nextWeekFocus.text}"
                val n = NotificationCompat.Builder(ctx, CH_WEEKLY)
                    .setSmallIcon(R.drawable.ic_stat_pulse)
                    .setContentTitle("Last week: ${w.headline}")
                    .setContentText("This week's focus: ${focus ?: "pick one in Today"}")
                    .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                    .setContentIntent(openApp(ctx, report = w.id)).setAutoCancel(true)
                    .build()
                @Suppress("MissingPermission") nm.notify(ID_WEEKLY, n)
                repo.settings.markWeeklyNotified(weekStart.toString())
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
                .setContentIntent(openApp(ctx, a.sourceId)).setAutoCancel(true)
                .build()
            @Suppress("MissingPermission") nm.notify(a.sourceId.hashCode(), n)
        }
        if (acts.isNotEmpty()) repo.settings.markRunsSeen(acts.map { it.sourceId })
    }
}

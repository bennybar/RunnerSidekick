package com.bennybar.runnersidekick.ui

import com.bennybar.runnersidekick.data.local.Units
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import kotlin.math.roundToInt

/** Display-boundary conversions. Storage and API stay in canonical metric units. */
object Format {
    private const val M_PER_MILE = 1609.344

    fun distance(m: Double?, units: Units): String = when {
        m == null -> "—"
        units == Units.IMPERIAL -> "%.2f mi".format(m / M_PER_MILE)
        else -> "%.2f km".format(m / 1000.0)
    }

    /** Pace from seconds per km. */
    fun pace(sPerKm: Double?, units: Units): String {
        if (sPerKm == null || sPerKm <= 0 || sPerKm.isNaN()) return "—"
        val s = if (units == Units.IMPERIAL) sPerKm * M_PER_MILE / 1000.0 else sPerKm
        var total = s.roundToInt()
        val min = total / 60
        total %= 60
        return "%d:%02d %s".format(min, total, if (units == Units.IMPERIAL) "/mi" else "/km")
    }

    fun paceFromSpeed(mps: Double?, units: Units): String = pace(mps?.takeIf { it > 0 }?.let { 1000.0 / it }, units)

    fun duration(s: Double?): String {
        if (s == null) return "—"
        val t = s.roundToInt()
        val h = t / 3600
        val m = (t % 3600) / 60
        val sec = t % 60
        return if (h > 0) "%d:%02d:%02d".format(h, m, sec) else "%d:%02d".format(m, sec)
    }

    fun hoursMinutes(s: Double?): String {
        if (s == null) return "—"
        val m = (s / 60).roundToInt()
        return if (m >= 60) "${m / 60} h ${"%02d".format(m % 60)} min" else "$m min"
    }

    fun elevation(m: Double?, units: Units): String = when {
        m == null -> "—"
        units == Units.IMPERIAL -> "${(m * 3.28084).roundToInt()} ft"
        else -> "${m.roundToInt()} m"
    }

    fun metricValue(metric: String, v: Double?): String = when {
        v == null -> "—"
        metric == "sleep_duration" -> hoursMinutes(v)
        metric == "resting_hr" -> "${v.roundToInt()} bpm"
        metric.startsWith("hrv") -> "${v.roundToInt()} ms"
        metric == "running_moving_time_7d" -> hoursMinutes(v)
        else -> "%.0f".format(v)
    }

    fun signedDelta(metric: String, d: Double?): String {
        if (d == null) return ""
        val sign = if (d > 0) "+" else if (d < 0) "−" else "±"
        return sign + metricValue(metric, kotlin.math.abs(d))
    }

    fun longDate(iso: String): String =
        LocalDate.parse(iso).format(DateTimeFormatter.ofPattern("EEEE, d MMMM"))

    fun shortDate(iso: String): String =
        LocalDate.parse(iso).format(DateTimeFormatter.ofPattern("EEE d MMM"))

    /** Activity start in the activity's own offset (not the phone's current zone), so travel history stays true. */
    fun activityTime(startUtc: String, offsetS: Int?): String {
        val zone = offsetS?.let { ZoneOffset.ofTotalSeconds(it) } ?: ZoneId.systemDefault()
        return Instant.parse(startUtc).atZone(zone).format(DateTimeFormatter.ofPattern("EEE d MMM · HH:mm"))
    }

    fun ago(instant: Instant?, now: Instant = Instant.now()): String {
        if (instant == null) return "never"
        val d = Duration.between(instant, now)
        return when {
            d.toMinutes() < 1 -> "just now"
            d.toMinutes() < 60 -> "${d.toMinutes()} min ago"
            d.toHours() < 24 -> "${d.toHours()} h ago"
            else -> "${d.toDays()} d ago"
        }
    }

    fun dateTime(i: Instant): String = i.atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM))

    /** The first day of the week from the backend's setting ("monday" … "sunday"). */
    fun firstDay(name: String?): java.time.DayOfWeek =
        runCatching { java.time.DayOfWeek.valueOf((name ?: "monday").uppercase()) }.getOrDefault(java.time.DayOfWeek.MONDAY)

    fun weekStart(d: java.time.LocalDate, first: java.time.DayOfWeek): java.time.LocalDate =
        d.with(java.time.temporal.TemporalAdjusters.previousOrSame(first))
}

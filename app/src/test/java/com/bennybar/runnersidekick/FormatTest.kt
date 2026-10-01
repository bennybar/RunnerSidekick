package com.bennybar.runnersidekick

import com.bennybar.runnersidekick.data.local.Units
import com.bennybar.runnersidekick.data.remote.MorningReport
import com.bennybar.runnersidekick.ui.Format
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.util.Locale

class FormatTest {
    init { Locale.setDefault(Locale.US) }

    @Test fun paceMetricAndImperial() {
        assertEquals("5:00 /km", Format.pace(300.0, Units.METRIC))
        assertEquals("8:03 /mi", Format.pace(300.0, Units.IMPERIAL)) // 300 s/km * 1.609344 = 482.8 s
        assertEquals("5:00 /km", Format.paceFromSpeed(1000.0 / 300.0, Units.METRIC))
    }

    @Test fun paceRoundingNeverShows60Seconds() {
        assertEquals("5:00 /km", Format.pace(299.6, Units.METRIC))
    }

    @Test fun missingValuesAreDashesNotZero() {
        assertEquals("—", Format.pace(null, Units.METRIC))
        assertEquals("—", Format.paceFromSpeed(0.0, Units.METRIC)) // stopped: no pace, not 0:00
        assertEquals("—", Format.distance(null, Units.METRIC))
        assertEquals("—", Format.metricValue("resting_hr", null))
    }

    @Test fun distanceAndDuration() {
        assertEquals("10.00 km", Format.distance(10000.0, Units.METRIC))
        assertEquals("6.21 mi", Format.distance(10000.0, Units.IMPERIAL))
        assertEquals("1:15:00", Format.duration(4500.0))
        assertEquals("49:05", Format.duration(2945.0))
        assertEquals("7 h 02 min", Format.hoursMinutes(25320.0))
    }

    @Test fun activityTimeUsesActivityOffsetNotPhoneZone() {
        // 03:30Z run recorded at UTC+3 shows 06:30 regardless of the device zone
        assertTrue(Format.activityTime("2026-09-30T03:30:00Z", 10800).endsWith("06:30"))
    }

    @Test fun agoIsHonest() {
        val now = Instant.parse("2026-10-01T08:00:00Z")
        assertEquals("never", Format.ago(null, now))
        assertEquals("2 h ago", Format.ago(Instant.parse("2026-10-01T06:00:00Z"), now))
    }

    @Test fun decodesBackendMorningReportContract() {
        val body = """{"id":5,"type":"morning","local_date":"2026-10-01","revision":2,"generated_at":"2026-10-01T05:00:00Z",
            "synthetic":true,"provisional":false,"headline":"h","top_finding_ids":[],"findings":[],
            "recommendation":{"state":"usual_plan","rule_id":"R5","reason":"r","suggestion":"s","evidence_ids":[],
              "suppress_intensity":false,"rules_version":"rules-1.1","planned_run_day":true},
            "checkin":{"id":"a","local_date":"2026-10-01","energy":3,"pain":false,"illness":false,"tags":[],
              "client_updated_at":"x","deleted":false,"received_at":"y"},"unknown_future_field":1}"""
        val r = Json { ignoreUnknownKeys = true }.decodeFromString<MorningReport>(body)
        assertEquals(2, r.revision)
        assertEquals(3, r.checkin?.energy)
    }
}

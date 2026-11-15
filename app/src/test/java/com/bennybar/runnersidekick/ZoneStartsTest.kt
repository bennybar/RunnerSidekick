package com.bennybar.runnersidekick

import com.bennybar.runnersidekick.ui.settings.zoneStartsError
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ZoneStartsTest {
    @Test fun fiveRisingStartsInRangeAreFine() {
        assertNull(zoneStartsError(listOf("94", "112", "131", "150", "168")))
        assertNull(zoneStartsError(listOf("60", "61", "62", "63", "230")))
    }

    @Test fun missingOrNotANumber() {
        assertEquals("Enter all five zone starts", zoneStartsError(listOf("94", "112", "", "150", "168")))
        assertEquals("Enter all five zone starts", zoneStartsError(listOf("94", "112", "131", "150")))
    }

    @Test fun outOfRange() {
        assertEquals("Each zone start has to be between 60 and 230 bpm", zoneStartsError(listOf("59", "112", "131", "150", "168")))
        assertEquals("Each zone start has to be between 60 and 230 bpm", zoneStartsError(listOf("94", "112", "131", "150", "231")))
    }

    @Test fun mustRiseStrictly() {
        assertEquals("Each zone has to start higher than the one before", zoneStartsError(listOf("94", "112", "112", "150", "168")))
        assertEquals("Each zone has to start higher than the one before", zoneStartsError(listOf("94", "131", "112", "150", "168")))
    }
}

package com.bennybar.runnersidekick

import com.bennybar.runnersidekick.ui.settings.normalizedServer
import com.bennybar.runnersidekick.ui.settings.serverAddressProblem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class ServerAddressTest {
    @Test fun trimsSpacesAndTrailingSlashes() {
        assertEquals("https://rs.example.org", normalizedServer("  https://rs.example.org//  "))
    }

    @Test fun httpsOnlyInRelease() {
        assertNull(serverAddressProblem("https://rs.example.org", allowHttp = false))
        assertNotNull(serverAddressProblem("http://rs.example.org", allowHttp = false))
        assertNotNull(serverAddressProblem("rs.example.org", allowHttp = false))
        assertNotNull(serverAddressProblem("", allowHttp = false))
    }

    @Test fun httpAllowedInDebug() {
        assertNull(serverAddressProblem("http://10.0.2.2:8765", allowHttp = true))
        assertNotNull(serverAddressProblem("ftp://rs.example.org", allowHttp = true))
    }

    @Test fun rejectsAddressWithoutHost() {
        assertNotNull(serverAddressProblem("https://", allowHttp = false))
    }
}

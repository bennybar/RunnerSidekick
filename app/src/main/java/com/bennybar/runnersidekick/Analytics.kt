package com.bennybar.runnersidekick

import android.content.Context
import com.aptabase.Aptabase

/**
 * Anonymous usage (Aptabase): which screens and features are used, nothing else. Event properties are names only
 * (a screen's route pattern, a setting's key); never health values, runs, the server address, emails or tokens.
 * Off in Settings ("Share anonymous usage"): nothing is sent.
 */
object Analytics {
    private const val APP_KEY = "A-US-6676968280"

    /** Follows the "Share anonymous usage" setting; false until it has been read, so nothing is sent before then. */
    @Volatile var enabled = false

    fun init(context: Context) = Aptabase.instance.initialize(context.applicationContext, APP_KEY)

    fun track(event: String, props: Map<String, Any> = emptyMap()) {
        if (enabled) Aptabase.instance.trackEvent(event, props)
    }
}

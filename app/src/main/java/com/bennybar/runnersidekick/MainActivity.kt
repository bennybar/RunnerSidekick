package com.bennybar.runnersidekick

import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.unit.dp
import android.os.Bundle
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import androidx.compose.foundation.background
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onPlaced
import androidx.compose.ui.layout.positionInParent
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.DirectionsRun
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.bennybar.runnersidekick.ui.activities.ActivitiesScreen
import com.bennybar.runnersidekick.ui.activities.ActivityDetailScreen
import com.bennybar.runnersidekick.ui.insights.InsightsScreen
import com.bennybar.runnersidekick.ui.journal.DayScreen
import com.bennybar.runnersidekick.ui.journal.JournalScreen
import com.bennybar.runnersidekick.ui.journal.ReportScreen
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bennybar.runnersidekick.ui.settings.SettingsScreen
import com.bennybar.runnersidekick.ui.settings.SignInScreen
import com.bennybar.runnersidekick.ui.settings.GarminConnectScreen
import com.bennybar.runnersidekick.ui.theme.RunnerTheme
import com.bennybar.runnersidekick.ui.today.TodayScreen

class MainActivity : ComponentActivity() {
    /** A run or report to open, from a notification ("activity/<id>" or "report/<id>"). */
    private val openRun = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (savedInstanceState == null) { openRun.value = route(intent); finishGarmin(intent); finishWatchletic(intent) }
        val repo = (application as RunnerApp).repository
        val progress = repo.progress
        setContent {
            val local by repo.settings.settings.collectAsStateWithLifecycle(initialValue = null)
            val appearance = com.bennybar.runnersidekick.ui.theme.Appearance.of(local?.appearance)
            val dark = when (appearance) {
                com.bennybar.runnersidekick.ui.theme.Appearance.SYSTEM -> androidx.compose.foundation.isSystemInDarkTheme()
                com.bennybar.runnersidekick.ui.theme.Appearance.LIGHT -> false
                com.bennybar.runnersidekick.ui.theme.Appearance.DARK -> true
            }
            // Status and navigation bar icons follow the app's light/dark choice, not only the phone's
            androidx.compose.runtime.LaunchedEffect(dark) {
                val style = if (dark) androidx.activity.SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)
                    else androidx.activity.SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT)
                enableEdgeToEdge(statusBarStyle = style, navigationBarStyle = style)
            }
            RunnerTheme(appearance) {
                androidx.compose.runtime.CompositionLocalProvider(com.bennybar.runnersidekick.ui.components.LocalProgress provides progress) { App(openRun) }
            }
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        route(intent)?.let { openRun.value = it }
        finishGarmin(intent)
        finishWatchletic(intent)
    }

    /** Garmin's answer, handed over by the server's callback page: finish linking, signed in as this app's user. */
    private fun finishGarmin(i: android.content.Intent?) {
        val data = i?.data?.takeIf { it.scheme == "runnersidekick" && it.host == "garmin-callback" } ?: return
        val state = data.getQueryParameter("state") ?: return
        val code = data.getQueryParameter("code") ?: return
        val repo = (application as RunnerApp).repository
        lifecycleScope.launch {
            val msg = runCatching { repo.completeGarmin(state, code); "Garmin connected" }
                .getOrElse { e -> (e as? com.bennybar.runnersidekick.data.remote.ApiException)?.message ?: "Garmin couldn't be connected. Please try again." }
            android.widget.Toast.makeText(this@MainActivity, msg, android.widget.Toast.LENGTH_LONG).show()
        }
    }

    /** Watchletic's answer, handed over by the server's callback page: finish linking, signed in as this app's user. */
    private fun finishWatchletic(i: android.content.Intent?) {
        val data = i?.data?.takeIf { it.scheme == "runnersidekick" && it.host == "watchletic-callback" } ?: return
        val state = data.getQueryParameter("state") ?: return
        val code = data.getQueryParameter("code") ?: return
        val repo = (application as RunnerApp).repository
        lifecycleScope.launch {
            val msg = runCatching { repo.completeWatchletic(state, code); "Watchletic connected" }
                .getOrElse { e -> (e as? com.bennybar.runnersidekick.data.remote.ApiException)?.message ?: "Watchletic couldn't be connected. Please try again." }
            android.widget.Toast.makeText(this@MainActivity, msg, android.widget.Toast.LENGTH_LONG).show()
        }
    }

    private fun route(i: android.content.Intent?): String? = i?.getStringExtra(EXTRA_OPEN_RUN)?.let { "activity/$it" }
        ?: i?.getLongExtra(EXTRA_OPEN_REPORT, -1L)?.takeIf { it >= 0 }?.let { "report/$it" }

    companion object {
        const val EXTRA_OPEN_RUN = "open_run"
        const val EXTRA_OPEN_REPORT = "open_report"
    }
}

// As in kitzi: every screen change (tabs, details, back button or back swipe) is one quick crossfade.
private val quickIn = androidx.compose.animation.fadeIn(androidx.compose.animation.core.tween(120))
private val quickOut = androidx.compose.animation.fadeOut(androidx.compose.animation.core.tween(120))

/** A page that can be left with back: opaque, so the page below only shows where this one has slid away. */
@Composable
private fun Page(content: @Composable () -> Unit) {
    androidx.compose.foundation.layout.Box(Modifier.background(androidx.compose.material3.MaterialTheme.colorScheme.surface)) { content() }
}

private data class Tab(val route: String, val label: String, val selected: ImageVector, val unselected: ImageVector)

// Four tabs: Today; Runs (the activities); Trends (insights, comparisons, charts); Me (settings, with the reports
// that were the Journal tab)
private val TABS = listOf(
    Tab("today", "Today", Icons.Filled.Home, Icons.Outlined.Home),
    Tab("activities", "Runs", Icons.AutoMirrored.Filled.DirectionsRun, Icons.AutoMirrored.Outlined.DirectionsRun),
    Tab("insights", "Trends", Icons.Filled.Insights, Icons.Outlined.Insights),
    Tab("settings", "Me", Icons.Filled.Person, Icons.Outlined.Person),
)

/** The tab bar: a centred pill of tabs; the current one fills in with its label (with a little bounce). Outlined and
 *  lifted so it reads apart from the tiles behind it. Sliding a finger along it moves from tab to tab. */
@Composable
private fun FloatingNav(selected: Int, onSelected: (Int) -> Unit) {
    val cs = androidx.compose.material3.MaterialTheme.colorScheme
    val dark = com.bennybar.runnersidekick.ui.theme.LocalDark.current
    val shape = androidx.compose.foundation.shape.RoundedCornerShape(32.dp)
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    // Each tab's horizontal span in the row, for drag hit-testing
    val spans = androidx.compose.runtime.remember { arrayOfNulls<ClosedFloatingPointRange<Float>>(TABS.size) }
    val current by androidx.compose.runtime.rememberUpdatedState(selected)
    val select by androidx.compose.runtime.rememberUpdatedState(onSelected)
    androidx.compose.foundation.layout.Box(Modifier.navigationBarsPadding().padding(top = 28.dp, bottom = 16.dp)) {
        androidx.compose.material3.Surface(
            Modifier.height(64.dp).shadow(14.dp, shape, ambientColor = androidx.compose.ui.graphics.Color.Black.copy(alpha = 0.25f),
                spotColor = androidx.compose.ui.graphics.Color.Black.copy(alpha = 0.25f)),
            shape = shape, color = if (dark) cs.surfaceContainerHigh else cs.surfaceContainer,
            border = androidx.compose.foundation.BorderStroke(1.dp, cs.outlineVariant),
        ) {
            androidx.compose.foundation.layout.Row(
                Modifier.pointerInput(Unit) {
                    // Only switch once the finger is inside another tab, so a tab growing under it can't bounce back
                    fun pick(x: Float) {
                        val i = spans.indexOfFirst { it != null && x in it }
                        if (i >= 0 && i != current) {
                            haptic.performHapticFeedback(androidx.compose.ui.hapticfeedback.HapticFeedbackType.SegmentTick)
                            select(i)
                        }
                    }
                    detectHorizontalDragGestures(onDragStart = { pick(it.x) },
                        onHorizontalDrag = { change, _ -> pick(change.position.x) })
                }.padding(horizontal = 8.dp),
                horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(6.dp),
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
            ) {
                TABS.forEachIndexed { i, tab ->
                    NavButton(tab, selected == i, onClick = { onSelected(i) }, modifier = Modifier.onPlaced { c ->
                        val x = c.positionInParent().x
                        spans[i] = x..(x + c.size.width)
                    })
                }
            }
        }
    }
}

@Composable
private fun NavButton(tab: Tab, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val cs = androidx.compose.material3.MaterialTheme.colorScheme
    val fg by androidx.compose.animation.animateColorAsState(if (selected) cs.onPrimary else cs.onSurfaceVariant,
        androidx.compose.animation.core.tween(250), label = "navFg")
    val bg by androidx.compose.animation.animateColorAsState(if (selected) cs.primary else cs.primary.copy(alpha = 0f),
        androidx.compose.animation.core.tween(250), label = "navBg")
    androidx.compose.foundation.layout.Row(
        modifier.height(48.dp).clip(androidx.compose.foundation.shape.CircleShape).background(bg)
            .clickable(onClickLabel = tab.label, role = androidx.compose.ui.semantics.Role.Tab, onClick = onClick)
            .semantics { this.selected = selected }
            // The selected pill grows to fit its label with a little bounce
            .animateContentSize(androidx.compose.animation.core.spring(dampingRatio = androidx.compose.animation.core.Spring.DampingRatioLowBouncy,
                stiffness = androidx.compose.animation.core.Spring.StiffnessMediumLow))
            .padding(horizontal = if (selected) 18.dp else 12.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
    ) {
        Icon(if (selected) tab.selected else tab.unselected, tab.label, Modifier.size(24.dp), tint = fg)
        if (selected) {
            androidx.compose.foundation.layout.Spacer(Modifier.width(8.dp))
            Text(tab.label, style = androidx.compose.material3.MaterialTheme.typography.labelLarge, color = fg, maxLines = 1)
        }
    }
}

@Composable
private fun App(openRun: kotlinx.coroutines.flow.MutableStateFlow<String?>) {
    val repo = (LocalContext.current.applicationContext as RunnerApp).repository
    val local by repo.settings.settings.collectAsStateWithLifecycle(initialValue = null)
    when (local?.hasToken) {
        null -> Unit                  // settings still loading: draw nothing for a frame rather than flash sign-in
        false -> SignInScreen()
        true -> MainNav(openRun)
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun MainNav(openRun: kotlinx.coroutines.flow.MutableStateFlow<String?>) {
    val nav = rememberNavController()
    val pendingRun by openRun.collectAsStateWithLifecycle()
    androidx.compose.runtime.LaunchedEffect(pendingRun) {
        pendingRun?.let { nav.navigate(it); openRun.value = null }
    }
    // Signed in without Garmin connected: Connect Garmin opens by itself, once, until it's connected or skipped
    val repo = (LocalContext.current.applicationContext as RunnerApp).repository
    val status by repo.status.collectAsStateWithLifecycle(initialValue = null)
    val local by repo.settings.settings.collectAsStateWithLifecycle(initialValue = null)
    var prompted by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf(false) }
    androidx.compose.runtime.LaunchedEffect(status?.value?.garminLinked, local?.garminPromptSkipped) {
        val s = status?.value ?: return@LaunchedEffect
        if (!prompted && !s.garminLinked && !s.synthetic && local?.garminPromptSkipped == false) {
            prompted = true
            nav.navigate("garmin")
        }
    }
    val entry by nav.currentBackStackEntryAsState()
    val dest = entry?.destination
    val onTab = TABS.any { t -> dest?.hierarchy?.any { it.route == t.route } == true }
    fun go(route: String) = nav.navigate(route) {
        popUpTo(nav.graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
    // The outer Scaffold only owns the navigation bar. It must not consume the status-bar inset, or each screen's
    // top app bar draws underneath the status bar.
    Scaffold(
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            // A floating pill (as in Ilay for Reddit); the page scrolls underneath it
            if (onTab) androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth(), contentAlignment = androidx.compose.ui.Alignment.BottomCenter) {
                FloatingNav(selected = TABS.indexOfFirst { t -> dest?.hierarchy?.any { it.route == t.route } == true }, onSelected = { go(TABS[it].route) })
            }
        },
    ) { padding ->
        val aiOn by repo.aiEnabled.collectAsStateWithLifecycle(initialValue = false)
        androidx.compose.runtime.CompositionLocalProvider(com.bennybar.runnersidekick.ui.components.LocalNavBarPadding provides padding.calculateBottomPadding(),
            com.bennybar.runnersidekick.ui.components.LocalAiEnabled provides aiOn) {
        NavHost(nav, startDestination = "today",
            enterTransition = { quickIn },
            exitTransition = { quickOut },
            popEnterTransition = { quickIn },
            popExitTransition = { quickOut },
            predictivePopEnterTransition = { _ -> quickIn },
            predictivePopExitTransition = { _ -> quickOut },
            modifier = Modifier.consumeWindowInsets(PaddingValues(bottom = padding.calculateBottomPadding()))) {
            composable("today") {
                TodayScreen(onOpenRun = { nav.navigate("activity/$it") }, onOpenSettings = { go("settings") }, onOpenInsights = { go("insights") })
            }
            composable("insights") {
                Page { InsightsScreen(onOpenDay = { nav.navigate("day/$it") }, onOpenRun = { nav.navigate("activity/$it") },
                    onOpenReport = { nav.navigate("report/$it") }, onOpenSettings = { go("settings") }) }
            }
            composable("day/{date}") { Page { DayScreen(it.arguments!!.getString("date")!!, onBack = { nav.popBackStack() }) } }
            composable("activities") { Page { ActivitiesScreen(onOpen = { nav.navigate("activity/$it") }, onTrophies = { nav.navigate("trophies") }) } }
            composable("trophies") { Page { com.bennybar.runnersidekick.ui.activities.TrophiesScreen(onBack = { nav.popBackStack() },
                onOpenRun = { nav.navigate("activity/$it") }) } }
            composable("journal") { Page { JournalScreen(onOpenReport = { nav.navigate("report/$it") }, onBack = { nav.popBackStack() }) } }
            composable("settings") { Page { SettingsScreen(onConnectGarmin = { nav.navigate("garmin") },
                onSamsungCheck = { nav.navigate("samsung-check") }, onOpenReports = { nav.navigate("journal") }) } }
            composable("samsung-check") { Page { com.bennybar.runnersidekick.ui.settings.SamsungCheckScreen(onBack = { nav.popBackStack() }) } }
            composable("garmin") {
                Page {
                    val scope = androidx.compose.runtime.rememberCoroutineScope()
                    GarminConnectScreen(
                        onDone = { nav.popBackStack(); go("today") },
                        onSkip = if (status?.value?.garminLinked == false) ({
                            scope.launch { repo.settings.setGarminPromptSkipped(true) }; nav.popBackStack() }) else null,
                        onClose = { nav.popBackStack() })
                }
            }
            composable("activity/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) {
                Page { ActivityDetailScreen(it.arguments!!.getString("id")!!, onBack = { nav.popBackStack() },
                    onOpenRun = { rid -> nav.navigate("activity/$rid") }) }
            }
            composable("report/{id}", arguments = listOf(navArgument("id") { type = NavType.LongType })) {
                Page {
                    ReportScreen(it.arguments!!.getLong("id"), onBack = { nav.popBackStack() }, onOpenRun = { id -> nav.navigate("activity/$id") },
                        onOpenReport = { id -> nav.navigate("report/$id") })
                }
            }
        }
        }
    }
}

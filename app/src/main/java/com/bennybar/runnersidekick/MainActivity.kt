package com.bennybar.runnersidekick

import androidx.compose.runtime.getValue
import androidx.compose.ui.unit.dp
import android.os.Bundle
import androidx.compose.foundation.background
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.DirectionsRun
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material.icons.outlined.MenuBook
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.Icon
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.ShortNavigationBar
import androidx.compose.material3.ShortNavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
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
import com.bennybar.runnersidekick.ui.theme.RunnerTheme
import com.bennybar.runnersidekick.ui.today.TodayScreen

class MainActivity : ComponentActivity() {
    /** A run or report to open, from a notification ("activity/<id>" or "report/<id>"). */
    private val openRun = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (savedInstanceState == null) openRun.value = route(intent)
        val progress = (application as RunnerApp).repository.progress
        setContent {
            RunnerTheme {
                androidx.compose.runtime.CompositionLocalProvider(com.bennybar.runnersidekick.ui.components.LocalProgress provides progress) { App(openRun) }
            }
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        route(intent)?.let { openRun.value = it }
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

private val TABS = listOf(
    Tab("today", "Today", Icons.Filled.WbSunny, Icons.Outlined.WbSunny),
    Tab("insights", "Insights", Icons.Filled.Insights, Icons.Outlined.Insights),
    Tab("activities", "Activities", Icons.AutoMirrored.Filled.DirectionsRun, Icons.AutoMirrored.Outlined.DirectionsRun),
    Tab("journal", "Journal", Icons.Filled.MenuBook, Icons.Outlined.MenuBook),
    Tab("settings", "Settings", Icons.Filled.Settings, Icons.Outlined.Settings),
)

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
            if (onTab) ShortNavigationBar {
                TABS.forEach { t ->
                    val sel = dest?.hierarchy?.any { it.route == t.route } == true
                    ShortNavigationBarItem(
                        selected = sel, onClick = { go(t.route) },
                        icon = { Icon(if (sel) t.selected else t.unselected, null) }, label = { Text(t.label, maxLines = 1, softWrap = false, overflow = TextOverflow.Ellipsis) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(nav, startDestination = "today",
            enterTransition = { quickIn },
            exitTransition = { quickOut },
            popEnterTransition = { quickIn },
            popExitTransition = { quickOut },
            predictivePopEnterTransition = { _ -> quickIn },
            predictivePopExitTransition = { _ -> quickOut },
            modifier = Modifier.padding(bottom = padding.calculateBottomPadding()).consumeWindowInsets(PaddingValues(bottom = padding.calculateBottomPadding()))) {
            composable("today") {
                TodayScreen(onOpenRun = { nav.navigate("activity/$it") }, onOpenSettings = { go("settings") }, onOpenInsights = { go("insights") })
            }
            composable("insights") {
                Page { InsightsScreen(onOpenDay = { nav.navigate("day/$it") }, onOpenRun = { nav.navigate("activity/$it") },
                    onOpenReport = { nav.navigate("report/$it") }, onOpenSettings = { go("settings") }) }
            }
            composable("day/{date}") { Page { DayScreen(it.arguments!!.getString("date")!!, onBack = { nav.popBackStack() }) } }
            composable("activities") { Page { ActivitiesScreen(onOpen = { nav.navigate("activity/$it") }) } }
            composable("journal") { Page { JournalScreen(onOpenReport = { nav.navigate("report/$it") }) } }
            composable("settings") { Page { SettingsScreen() } }
            composable("activity/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) {
                Page { ActivityDetailScreen(it.arguments!!.getString("id")!!, onBack = { nav.popBackStack() }) }
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

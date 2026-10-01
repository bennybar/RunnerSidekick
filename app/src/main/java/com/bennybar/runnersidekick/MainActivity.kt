package com.bennybar.runnersidekick

import android.os.Bundle
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.background
import androidx.compose.ui.draw.clip
import androidx.compose.animation.core.animateDp
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
import androidx.compose.runtime.getValue
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
    /** A run to open, from a run-report notification. */
    private val openRun = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (savedInstanceState == null) openRun.value = intent?.getStringExtra(EXTRA_OPEN_RUN)
        setContent { RunnerTheme { App(openRun) } }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra(EXTRA_OPEN_RUN)?.let { openRun.value = it }
    }

    companion object { const val EXTRA_OPEN_RUN = "open_run" }
}

// Material 3 motion: emphasized easing; fade-through between tabs, a horizontal shared axis into and out of details.
// Navigation drives the pop transitions with the predictive back gesture, so the screen follows the finger.
private val Emphasized = androidx.compose.animation.core.CubicBezierEasing(0.2f, 0f, 0f, 1f)
private val EmphasizedDecelerate = androidx.compose.animation.core.CubicBezierEasing(0.05f, 0.7f, 0.1f, 1f)
private val EmphasizedAccelerate = androidx.compose.animation.core.CubicBezierEasing(0.3f, 0f, 0.8f, 0.15f)
private val TAB_ROUTES = setOf("today", "insights", "activities", "journal", "settings")

private fun isTab(route: String?) = route in TAB_ROUTES

private fun <T> spec(ms: Int, easing: androidx.compose.animation.core.Easing = Emphasized, delay: Int = 0) =
    androidx.compose.animation.core.tween<T>(ms, delay, easing)

private val fadeThroughIn = androidx.compose.animation.fadeIn(spec(210, EmphasizedDecelerate, 90)) +
    androidx.compose.animation.scaleIn(spec(210, EmphasizedDecelerate, 90), initialScale = 0.96f)
private val fadeThroughOut = androidx.compose.animation.fadeOut(spec(90, EmphasizedAccelerate))

private val pushIn = androidx.compose.animation.slideInHorizontally(spec(400)) { it / 4 } + androidx.compose.animation.fadeIn(spec(300))
private val pushOut = androidx.compose.animation.slideOutHorizontally(spec(400)) { -it / 10 } + androidx.compose.animation.fadeOut(spec(250))
// Back (gesture or button): the detail shrinks and slides toward the edge while the screen behind settles into place
private val popIn = androidx.compose.animation.slideInHorizontally(spec(400)) { -it / 10 } +
    androidx.compose.animation.fadeIn(spec(300)) + androidx.compose.animation.scaleIn(spec(400), initialScale = 0.97f)
private val popOut = androidx.compose.animation.scaleOut(spec(400), targetScale = 0.9f) +
    androidx.compose.animation.slideOutHorizontally(spec(400)) { it / 4 } + androidx.compose.animation.fadeOut(spec(350))

/** A detail destination: while it enters or leaves (including mid back gesture) its corners round like a card. */
@Composable
private fun androidx.compose.animation.AnimatedContentScope.Detail(content: @Composable () -> Unit) {
    val corner by transition.animateDp(label = "corner") { if (it == androidx.compose.animation.EnterExitState.Visible) 0.dp else 32.dp }
    androidx.compose.foundation.layout.Box(Modifier.clip(androidx.compose.foundation.shape.RoundedCornerShape(corner))
        .background(androidx.compose.material3.MaterialTheme.colorScheme.surface)) { content() }
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
        pendingRun?.let { nav.navigate("activity/$it"); openRun.value = null }
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
            enterTransition = { if (isTab(initialState.destination.route) && isTab(targetState.destination.route)) fadeThroughIn else pushIn },
            exitTransition = { if (isTab(initialState.destination.route) && isTab(targetState.destination.route)) fadeThroughOut else pushOut },
            popEnterTransition = { if (isTab(initialState.destination.route) && isTab(targetState.destination.route)) fadeThroughIn else popIn },
            popExitTransition = { if (isTab(initialState.destination.route) && isTab(targetState.destination.route)) fadeThroughOut else popOut },
            modifier = Modifier.padding(bottom = padding.calculateBottomPadding()).consumeWindowInsets(PaddingValues(bottom = padding.calculateBottomPadding()))) {
            composable("today") {
                TodayScreen(onOpenRun = { nav.navigate("activity/$it") }, onOpenSettings = { go("settings") }, onOpenInsights = { go("insights") })
            }
            composable("insights") {
                InsightsScreen(onOpenDay = { nav.navigate("day/$it") }, onOpenRun = { nav.navigate("activity/$it") },
                    onOpenReport = { nav.navigate("report/$it") }, onOpenSettings = { go("settings") })
            }
            composable("day/{date}") { Detail { DayScreen(it.arguments!!.getString("date")!!, onBack = { nav.popBackStack() }) } }
            composable("activities") { ActivitiesScreen(onOpen = { nav.navigate("activity/$it") }) }
            composable("journal") { JournalScreen(onOpenReport = { nav.navigate("report/$it") }) }
            composable("settings") { SettingsScreen() }
            composable("activity/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) {
                Detail { ActivityDetailScreen(it.arguments!!.getString("id")!!, onBack = { nav.popBackStack() }) }
            }
            composable("report/{id}", arguments = listOf(navArgument("id") { type = NavType.LongType })) {
                Detail {
                    ReportScreen(it.arguments!!.getLong("id"), onBack = { nav.popBackStack() }, onOpenRun = { id -> nav.navigate("activity/$id") },
                        onOpenReport = { id -> nav.navigate("report/$id") })
                }
            }
        }
    }
}

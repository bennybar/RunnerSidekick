package com.bennybar.runnersidekick

import android.os.Bundle
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
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { RunnerTheme { App() } }
    }
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
private fun App() {
    val repo = (LocalContext.current.applicationContext as RunnerApp).repository
    val local by repo.settings.settings.collectAsStateWithLifecycle(initialValue = null)
    when (local?.hasToken) {
        null -> Unit                  // settings still loading: draw nothing for a frame rather than flash sign-in
        false -> SignInScreen()
        true -> MainNav()
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun MainNav() {
    val nav = rememberNavController()
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
        NavHost(nav, startDestination = "today", modifier = Modifier.padding(bottom = padding.calculateBottomPadding()).consumeWindowInsets(PaddingValues(bottom = padding.calculateBottomPadding()))) {
            composable("today") {
                TodayScreen(onOpenRun = { nav.navigate("activity/$it") }, onOpenSettings = { go("settings") }, onOpenInsights = { go("insights") })
            }
            composable("insights") {
                InsightsScreen(onOpenDay = { nav.navigate("day/$it") }, onOpenRun = { nav.navigate("activity/$it") },
                    onOpenReport = { nav.navigate("report/$it") })
            }
            composable("day/{date}") { DayScreen(it.arguments!!.getString("date")!!, onBack = { nav.popBackStack() }) }
            composable("activities") { ActivitiesScreen(onOpen = { nav.navigate("activity/$it") }) }
            composable("journal") { JournalScreen(onOpenReport = { nav.navigate("report/$it") }) }
            composable("settings") { SettingsScreen() }
            composable("activity/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) {
                ActivityDetailScreen(it.arguments!!.getString("id")!!, onBack = { nav.popBackStack() })
            }
            composable("report/{id}", arguments = listOf(navArgument("id") { type = NavType.LongType })) {
                ReportScreen(it.arguments!!.getLong("id"), onBack = { nav.popBackStack() }, onOpenRun = { id -> nav.navigate("activity/$id") },
                    onOpenReport = { id -> nav.navigate("report/$id") })
            }
        }
    }
}

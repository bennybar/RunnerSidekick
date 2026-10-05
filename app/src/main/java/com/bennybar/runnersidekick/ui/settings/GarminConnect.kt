package com.bennybar.runnersidekick.ui.settings

import android.annotation.SuppressLint
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.bennybar.runnersidekick.RunnerApp
import com.bennybar.runnersidekick.data.remote.ApiException
import kotlinx.coroutines.launch

/** Garmin's own sign-in page, asked for a ticket for this service (as Garmin's sign-in widget does). */
private const val SSO_EMBED = "https://sso.garmin.com/sso/embed"
private val SIGN_IN_URL = android.net.Uri.parse("https://sso.garmin.com/sso/signin").buildUpon()
    .appendQueryParameter("id", "gauth-widget").appendQueryParameter("embedWidget", "true")
    .appendQueryParameter("gauthHost", SSO_EMBED).appendQueryParameter("service", SSO_EMBED)
    .appendQueryParameter("source", SSO_EMBED).appendQueryParameter("redirectAfterAccountLoginUrl", SSO_EMBED)
    .appendQueryParameter("redirectAfterAccountCreationUrl", SSO_EMBED).build().toString()
private val TICKET = Regex("""ticket=(ST-[A-Za-z0-9._\-]{8,300})""")

/**
 * Connects Garmin: you sign in on Garmin's own page, here on the phone (your password and any two-factor code go only
 * to Garmin). Garmin answers with a one-time ticket, which is all the app sends to the server; the server turns it
 * into a lasting connection and starts downloading your history. [onSkip] is null when there's nothing to skip to.
 */
@OptIn(ExperimentalMaterial3Api::class)
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun GarminConnectScreen(onDone: () -> Unit, onSkip: (() -> Unit)?, onClose: () -> Unit) {
    val repo = (LocalContext.current.applicationContext as RunnerApp).repository
    val scope = rememberCoroutineScope()
    var linking by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var attempt by remember { mutableIntStateOf(0) }  // a new attempt loads a fresh sign-in page
    var sent by remember { mutableStateOf(false) }

    fun submit(ticket: String) {
        if (sent) return
        sent = true; linking = true; error = null
        scope.launch {
            try {
                repo.linkGarmin(ticket)
                CookieManager.getInstance().removeAllCookies(null)  // nothing of the Garmin web session stays on the phone
                onDone()
            } catch (e: ApiException.Http) {
                error = e.detail ?: "Couldn't connect Garmin (${e.code}). Please try again."
            } catch (e: ApiException) {
                error = e.message
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                android.util.Log.e("RunnerSidekick", "Garmin connect failed", e)
                error = "Couldn't connect Garmin. Please try again."
            } finally {
                linking = false
            }
        }
    }

    Scaffold(topBar = {
        TopAppBar(title = { Text("Connect Garmin") },
            navigationIcon = { IconButton(onClick = onClose) { Icon(Icons.Outlined.Close, "Close") } },
            actions = { onSkip?.let { TextButton(onClick = it) { Text("Skip for now") } } })
    }) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            Text("Sign in on Garmin's page below. Your password goes only to Garmin; Runner Sidekick gets read access to your " +
                "Garmin data and downloads your history.", style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
            when {
                linking -> Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp),
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                    Text("Connecting to Garmin…", style = MaterialTheme.typography.titleMedium)
                }
                error != null -> Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text(error!!, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.error)
                    Button(onClick = { error = null; sent = false; attempt++ }) { Text("Try again") }
                }
                else -> Box(Modifier.fillMaxSize()) {
                    androidx.compose.runtime.key(attempt) {
                        AndroidView(modifier = Modifier.fillMaxSize(), factory = { ctx ->
                            CookieManager.getInstance().removeAllCookies(null)  // a fresh sign-in, never someone's old session
                            WebView(ctx).apply {
                                settings.javaScriptEnabled = true  // Garmin's page needs it
                                settings.domStorageEnabled = true
                                webViewClient = object : WebViewClient() {
                                    fun caught(url: String?): Boolean =
                                        url?.let { TICKET.find(it) }?.groupValues?.get(1)?.let { submit(it); true } ?: false

                                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                                        val url = request.url
                                        if (caught(url.toString())) return true
                                        // Only Garmin's own pages load here
                                        return url.host?.let { it == "garmin.com" || it.endsWith(".garmin.com") } != true
                                    }

                                    override fun onPageStarted(view: WebView, url: String?, favicon: android.graphics.Bitmap?) {
                                        if (caught(url)) view.stopLoading()
                                    }

                                    override fun onPageFinished(view: WebView, url: String?) {
                                        // The sign-in widget's success page carries the ticket in its own script
                                        view.evaluateJavascript("document.documentElement.outerHTML") { html -> caught(html) }
                                    }
                                }
                                loadUrl(SIGN_IN_URL)
                            }
                        })
                    }
                }
            }
        }
    }
}

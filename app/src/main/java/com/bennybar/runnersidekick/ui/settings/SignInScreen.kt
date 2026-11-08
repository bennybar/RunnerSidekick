package com.bennybar.runnersidekick.ui.settings

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.DirectionsRun
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.LoadingIndicator
import androidx.compose.material3.MaterialShapes
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.OutlinedButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import com.bennybar.runnersidekick.Analytics
import com.bennybar.runnersidekick.BuildConfig
import com.bennybar.runnersidekick.RunnerApp
import com.bennybar.runnersidekick.data.remote.ApiException
import com.bennybar.runnersidekick.ui.components.ShapeBadge
import com.bennybar.runnersidekick.ui.components.Tile
import com.bennybar.runnersidekick.ui.theme.LocalDark
import com.bennybar.runnersidekick.ui.theme.Tint
import com.bennybar.runnersidekick.ui.theme.ink
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/** Gets a Google ID token for our backend's Web client ID via Credential Manager. Null if the user cancelled. */
suspend fun googleIdToken(context: Context): String? {
    val option = GetSignInWithGoogleOption.Builder(BuildConfig.GOOGLE_WEB_CLIENT_ID).build()
    val request = GetCredentialRequest.Builder().addCredentialOption(option).build()
    return try {
        val cred = CredentialManager.create(context).getCredential(context, request).credential
        if (cred is CustomCredential && cred.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
            GoogleIdTokenCredential.createFrom(cred.data).idToken
        } else null
    } catch (_: GetCredentialCancellationException) {
        null
    }
}

/** The server address as typed, trimmed and without a trailing slash. */
fun normalizedServer(raw: String): String = raw.trim().trimEnd('/')

/** Why [url] (normalized) can't be used as the server address, or null when it can. Plain http only when [allowHttp]. */
fun serverAddressProblem(url: String, allowHttp: Boolean): String? = when {
    url.isEmpty() -> "Enter your server's address."
    !url.startsWith("https://") && !(allowHttp && url.startsWith("http://")) ->
        if (allowHttp) "The address must start with https:// or http://." else "The address must start with https://."
    url.toHttpUrlOrNull()?.host.isNullOrBlank() -> "That isn't a valid web address."
    else -> null
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun SignInScreen() {
    val ctx = LocalContext.current
    val repo = (ctx.applicationContext as RunnerApp).repository
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf(repo.signInNote.value.also { repo.signInNote.value = null }) }
    // The last server signed in to (kept across sign-out), else this build's default (empty in release)
    var server by remember { mutableStateOf("") }
    LaunchedEffect(Unit) {
        server = repo.settings.settings.first().backendUrl.ifBlank { BuildConfig.DEFAULT_BACKEND_URL }
    }
    var token by remember { mutableStateOf("") }
    val googleReady = BuildConfig.GOOGLE_WEB_CLIENT_ID.isNotBlank()

    /** Checks the address, then runs [signIn] against it; any failure becomes a message on this screen. */
    fun connect(signIn: suspend (url: String) -> Unit) {
        val url = normalizedServer(server)
        serverAddressProblem(url, BuildConfig.ALLOW_HTTP)?.let { error = it; return }
        server = url
        scope.launch {
            busy = true; error = null
            try {
                signIn(url)
            } catch (e: GetCredentialException) {
                error = "Google sign-in didn't complete (${e.type.substringAfterLast('.')})."
            } catch (_: ApiException.Network) {
                error = "Couldn't reach $url. Check the address, your connection, and that the server is running."
            } catch (e: ApiException) {
                error = e.message
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {  // anything else: a message, never a crash
                android.util.Log.e("RunnerSidekick", "Sign-in failed", e)
                error = "Couldn't connect. Check the address and try again."
            } finally {
                busy = false
            }
        }
    }

    Column(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).systemBarsPadding().verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Spacer(Modifier.height(72.dp))
        ShapeBadge(Icons.AutoMirrored.Outlined.DirectionsRun, MaterialShapes.Cookie9Sided, Modifier.size(96.dp),
            container = Tint.ORANGE.hue.copy(alpha = if (LocalDark.current) 0.26f else 0.20f), content = ink(Tint.ORANGE), iconSize = 48.dp)
        Text("Runner Sidekick", style = MaterialTheme.typography.headlineLarge, textAlign = TextAlign.Center)
        Text("Your Garmin's data, turned into a daily briefing, run analysis and insights you can check.",
            style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center,
            modifier = Modifier.padding(horizontal = 12.dp))
        Spacer(Modifier.height(16.dp))
        Tile(contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp)) {
            Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
                if (busy) LoadingIndicator(Modifier.size(56.dp))
                OutlinedTextField(server, { server = it }, label = { Text("Server address") }, placeholder = { Text("https://…") },
                    supportingText = { Text("Your Runner Sidekick server") }, singleLine = true, enabled = !busy, modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, autoCorrectEnabled = false))
                // Token keyboard: no autocorrect (it mangles tokens)
                OutlinedTextField(token, { token = it.trim() }, label = { Text("Device token (rsk_…)") }, singleLine = true, enabled = !busy,
                    visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false))
                Button(enabled = !busy && token.startsWith("rsk_"), modifier = Modifier.fillMaxWidth().height(56.dp), onClick = {
                    connect { url ->
                        // Checked before it's saved: a token the server rejects is never stored
                        error = repo.checkToken(url, token)
                        // Saving the token opens the app; Today loads everything itself (a refresh started here would be
                        // cancelled as this screen closes, and Today's own would wait on it)
                        if (error == null) {
                            Analytics.track("signed_in", mapOf("method" to "token"))
                            repo.settings.setBackend(url, token)
                        }
                    }
                }) { Text("Connect") }
                Text("or", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                OutlinedButton(
                    enabled = googleReady && !busy, modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        connect { url ->
                            val id = googleIdToken(ctx)
                            if (id != null) error = repo.signInWithGoogle(id, url)
                        }
                    },
                ) { Text("Sign in with Google") }
                Text(if (googleReady) "Google sign-in works on servers that have invited your Google email."
                    else "Google sign-in isn't set up in this build. Use a device token.",
                    style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
                error?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center) }
            }
        }
        Spacer(Modifier.height(32.dp))
    }
}

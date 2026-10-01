package com.bennybar.runnersidekick.ui.settings

import android.content.Context
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
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import com.bennybar.runnersidekick.BuildConfig
import com.bennybar.runnersidekick.RunnerApp
import com.bennybar.runnersidekick.data.remote.ApiException
import com.bennybar.runnersidekick.ui.components.ShapeBadge
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import kotlinx.coroutines.launch

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

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun SignInScreen() {
    val ctx = LocalContext.current
    val repo = (ctx.applicationContext as RunnerApp).repository
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var manual by remember { mutableStateOf(false) }
    var url by remember { mutableStateOf(BuildConfig.DEFAULT_BACKEND_URL) }
    var token by remember { mutableStateOf("") }
    val googleReady = BuildConfig.GOOGLE_WEB_CLIENT_ID.isNotBlank()

    Column(
        Modifier.fillMaxSize().systemBarsPadding().verticalScroll(rememberScrollState()).padding(horizontal = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Spacer(Modifier.height(72.dp))
        ShapeBadge(Icons.AutoMirrored.Outlined.DirectionsRun, MaterialShapes.Cookie9Sided, Modifier.size(96.dp),
            container = MaterialTheme.colorScheme.primaryContainer, content = MaterialTheme.colorScheme.onPrimaryContainer, iconSize = 48.dp)
        Text("Runner Sidekick", style = MaterialTheme.typography.displaySmall, textAlign = TextAlign.Center)
        Text("Your Garmin data, turned into a daily briefing, run analysis and insights you can check.",
            style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
        Spacer(Modifier.height(24.dp))
        if (busy) LoadingIndicator(Modifier.size(56.dp))
        Button(
            enabled = googleReady && !busy, modifier = Modifier.fillMaxWidth().height(56.dp),
            onClick = {
                scope.launch {
                    busy = true; error = null
                    try {
                        val id = googleIdToken(ctx)
                        if (id != null) error = repo.signInWithGoogle(id, BuildConfig.DEFAULT_BACKEND_URL)
                    } catch (e: GetCredentialException) {
                        error = "Google sign-in didn't complete (${e.type.substringAfterLast('.')})."
                    } catch (e: ApiException) {
                        error = e.message
                    } finally {
                        busy = false
                    }
                }
            },
        ) { Text("Sign in with Google") }
        if (!googleReady) Text("Google sign-in isn't set up in this build yet. Use a device token below.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
        Text("Invite-only for now. Ask the owner to add your Google email.", style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
        error?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center) }
        TextButton(onClick = { manual = !manual }) { Text(if (manual) "Hide device token" else "Use a device token instead") }
        if (manual) {
            // URL and token keyboards: no autocorrect (it turns "http" into "https" and mangles tokens)
            OutlinedTextField(url, { url = it.trim() }, label = { Text("Backend URL") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Uri,
                    autoCorrectEnabled = false))
            OutlinedTextField(token, { token = it.trim() }, label = { Text("Device token (rsk_…)") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth(),
                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Password,
                    autoCorrectEnabled = false))
            Button(enabled = !busy && url.isNotBlank() && token.startsWith("rsk_"), modifier = Modifier.fillMaxWidth(), onClick = {
                scope.launch {
                    busy = true; error = null
                    try {
                        repo.settings.setBackend(url, token)
                        repo.refreshAll()
                    } catch (e: ApiException) {
                        repo.settings.clearToken()
                        error = e.message
                    } finally {
                        busy = false
                    }
                }
            }) { Text("Connect") }
        }
        Spacer(Modifier.height(32.dp))
    }
}

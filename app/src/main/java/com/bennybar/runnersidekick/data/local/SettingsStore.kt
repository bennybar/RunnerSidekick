package com.bennybar.runnersidekick.data.local

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.bennybar.runnersidekick.BuildConfig
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

private val Context.dataStore by preferencesDataStore("settings")

enum class Units { METRIC, IMPERIAL }

data class LocalSettings(
    val backendUrl: String,
    val hasToken: Boolean,
    val units: Units,
    val currentMode: String?,
    val notificationsEnabled: Boolean,
    /** "<backend url>#<user id>" of the signed-in account, once known. Scopes local check-ins. */
    val account: String?,
    val hasOwnAiKey: Boolean = false,
    /** Keep the phone's copy fresh in the background even with notifications off (every few hours). */
    val backgroundRefresh: Boolean = false,
    /** Colour theme and light/dark: names of ui.theme.ThemeChoice and Appearance. */
    val theme: String? = null,
    val appearance: String? = null,
)

/** Notification de-duplication state, kept on the phone. */
data class NotifyState(val morningDate: String?, val morningState: String?, val runsSeen: Set<String>, val runsSeeded: Boolean,
                       val weeklyWeek: String? = null)

/** Local preferences. The device token is encrypted with an AES-GCM key held in Android Keystore. */
class SettingsStore(private val context: Context) {
    private val kUrl = stringPreferencesKey("backend_url")
    private val kToken = stringPreferencesKey("device_token_enc")
    private val kImperial = booleanPreferencesKey("imperial")
    private val kMode = stringPreferencesKey("current_mode")
    private val kNotify = booleanPreferencesKey("notifications_enabled")
    private val kBackground = booleanPreferencesKey("background_refresh")
    private val kAccount = stringPreferencesKey("current_account")
    private val kAiKey = stringPreferencesKey("own_openai_key_enc")
    private val kMorningDate = stringPreferencesKey("notified_morning_date")
    private val kMorningState = stringPreferencesKey("notified_morning_state")
    private val kRunsSeen = stringSetPreferencesKey("notified_runs")
    private val kRunsSeeded = booleanPreferencesKey("notified_runs_seeded")
    private val kWeekly = stringPreferencesKey("notified_weekly_week")
    private val kTheme = stringPreferencesKey("theme")
    private val kAppearance = stringPreferencesKey("appearance")

    val settings: Flow<LocalSettings> = context.dataStore.data.map { p ->
        LocalSettings(
            backendUrl = p[kUrl] ?: BuildConfig.DEFAULT_BACKEND_URL,
            hasToken = p[kToken] != null,
            units = if (p[kImperial] == true) Units.IMPERIAL else Units.METRIC,
            currentMode = p[kMode],
            notificationsEnabled = p[kNotify] ?: false,
            account = p[kAccount],
            hasOwnAiKey = p[kAiKey] != null,
            backgroundRefresh = p[kBackground] ?: false,
            theme = p[kTheme],
            appearance = p[kAppearance],
        )
    }

    val notifyState: Flow<NotifyState> = context.dataStore.data.map { p ->
        NotifyState(p[kMorningDate], p[kMorningState], p[kRunsSeen] ?: emptySet(), p[kRunsSeeded] ?: false, p[kWeekly])
    }

    suspend fun setNotificationsEnabled(on: Boolean) = context.dataStore.edit { it[kNotify] = on }
    suspend fun setBackgroundRefresh(on: Boolean) = context.dataStore.edit { it[kBackground] = on }

    suspend fun markWeeklyNotified(weekStart: String) = context.dataStore.edit { it[kWeekly] = weekStart }

    suspend fun markMorningNotified(date: String, state: String) = context.dataStore.edit { it[kMorningDate] = date; it[kMorningState] = state }

    /** Keeps the most recent IDs only, so the set can't grow without bound. */
    suspend fun markRunsSeen(ids: Collection<String>) = context.dataStore.edit {
        it[kRunsSeen] = ((it[kRunsSeen] ?: emptySet()) + ids).toList().takeLast(200).toSet()
        it[kRunsSeeded] = true
    }

    suspend fun credentials(): Pair<String, String>? {
        val p = context.dataStore.data.first()
        val url = p[kUrl] ?: BuildConfig.DEFAULT_BACKEND_URL
        val token = p[kToken]?.let { decrypt(it) } ?: return null
        return if (url.isBlank()) null else url to token
    }

    suspend fun setBackend(url: String, token: String?) {
        context.dataStore.edit { p ->
            p[kUrl] = url.trim()
            if (!token.isNullOrBlank()) p[kToken] = encrypt(token.trim())
        }
    }

    suspend fun setTheme(theme: String) = context.dataStore.edit { it[kTheme] = theme }
    suspend fun setAppearance(appearance: String) = context.dataStore.edit { it[kAppearance] = appearance }

    suspend fun setUnits(units: Units) = context.dataStore.edit { it[kImperial] = units == Units.IMPERIAL }

    suspend fun setMode(mode: String) = context.dataStore.edit { it[kMode] = mode }

    /** Signing out also forgets the runner's own OpenAI key, so a later account never inherits it. */
    suspend fun clearToken() = context.dataStore.edit { it.remove(kToken); it.remove(kAccount); it.remove(kAiKey) }

    suspend fun setAccount(account: String) = context.dataStore.edit { it[kAccount] = account }

    /** The user's own OpenAI key, Keystore-encrypted like the device token. */
    suspend fun setOwnAiKey(key: String?) = context.dataStore.edit { if (key.isNullOrBlank()) it.remove(kAiKey) else it[kAiKey] = encrypt(key.trim()) }

    suspend fun ownAiKey(): String? = context.dataStore.data.first()[kAiKey]?.let { decrypt(it) }

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return gen.generateKey()
    }

    private fun encrypt(plain: String): String {
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val out = c.iv + c.doFinal(plain.toByteArray())
        return Base64.encodeToString(out, Base64.NO_WRAP)
    }

    private fun decrypt(enc: String): String? = runCatching {
        val bytes = Base64.decode(enc, Base64.NO_WRAP)
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes, 0, 12))
        String(c.doFinal(bytes, 12, bytes.size - 12))
    }.getOrNull()

    private companion object {
        const val ALIAS = "rsk_device_token"
    }
}

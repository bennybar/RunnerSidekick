package com.bennybar.runnersidekick.data

import com.google.mlkit.genai.common.DownloadStatus
import com.google.mlkit.genai.common.FeatureStatus
import com.google.mlkit.genai.prompt.Generation
import com.google.mlkit.genai.prompt.GenerativeModel
import com.google.mlkit.genai.prompt.SystemInstruction
import com.google.mlkit.genai.prompt.TextPart
import com.google.mlkit.genai.prompt.generateContentRequest
import kotlinx.coroutines.flow.Flow

/**
 * Gemini Nano, Android's built-in model, through ML Kit's GenAI Prompt API (AICore). Only on phones that have it; the
 * model is downloaded by the system, once. Used for AI input on a run when the runner chooses "on this phone": the
 * prompt comes from the server, the answer goes back to be checked like the server's own.
 */
object LocalAi {
    private val model: GenerativeModel by lazy { Generation.getClient() }

    /** UNAVAILABLE (this phone can't), DOWNLOADABLE, DOWNLOADING or AVAILABLE (FeatureStatus). */
    suspend fun status(): Int = check().first

    /** The status and, when the check itself failed, why (shown in Settings, so "not available" can be told apart from
     *  "couldn't ask"). */
    suspend fun check(): Pair<Int, String?> = try {
        model.checkStatus() to null
    } catch (e: kotlinx.coroutines.CancellationException) {
        throw e
    } catch (e: Exception) {
        android.util.Log.w("RunnerSidekick", "Gemini Nano status check failed", e)
        FeatureStatus.UNAVAILABLE to ((e as? com.google.mlkit.genai.common.GenAiException)?.let { "error ${it.errorCode}: ${it.message}" }
            ?: "${e.javaClass.simpleName}: ${e.message}")
    }

    fun describe(status: Int): String = when (status) {
        FeatureStatus.AVAILABLE -> "ready"
        FeatureStatus.DOWNLOADABLE -> "can be downloaded"
        FeatureStatus.DOWNLOADING -> "downloading"
        else -> "not available on this phone"
    }

    fun download(): Flow<DownloadStatus> = model.download()

    suspend fun generate(system: String, input: String): String {
        val withSystem = runCatching { model.isSystemPromptAvailable() }.getOrDefault(false)
        val request = if (withSystem) generateContentRequest(SystemInstruction(system), TextPart(input)) {
            temperature = 0.2f
            maxOutputTokens = 900
        } else generateContentRequest(TextPart("$system\n\nThe evidence bundle:\n$input")) {
            temperature = 0.2f
            maxOutputTokens = 900
        }
        return model.generateContent(request).candidates.firstOrNull()?.text.orEmpty()
    }
}

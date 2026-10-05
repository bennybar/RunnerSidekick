package com.bennybar.runnersidekick.data.remote

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

sealed class ApiException(message: String) : Exception(message) {
    class NotConfigured : ApiException("Backend URL or device token not set")
    class Unauthorized : ApiException("Device token rejected by the backend")
    class Http(val code: Int) : ApiException("Backend returned HTTP $code")
    class Network(cause: IOException) : ApiException("Backend unreachable: ${cause.message}")
    /** The backend answered, but the Garmin sync itself didn't finish well (or is still running). */
    class Sync(val detail: String) : ApiException(detail)
}

class ApiClient(private val credentials: suspend () -> Pair<String, String>?) {

    val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .callTimeout(45, TimeUnit.SECONDS)  // the whole request, so a slow backend can't hold the radio open
        .build()

    // Last body and ETag per GET URL: an unchanged answer comes back as an empty 304 instead of the full JSON
    private val etags = java.util.concurrent.ConcurrentHashMap<String, Pair<String, String>>()

    /** Returns the raw JSON body so callers can cache exactly what the backend said. */
    suspend fun getRaw(path: String, query: Map<String, String> = emptyMap(), headers: Map<String, String> = emptyMap()): String =
        call("GET", path, query, null, headers)

    suspend fun putRaw(path: String, body: String): String = call("PUT", path, emptyMap(), body)

    suspend fun post(path: String): String = call("POST", path, emptyMap(), "")

    suspend fun postRaw(path: String, headers: Map<String, String> = emptyMap()): String = call("POST", path, emptyMap(), "", headers)

    suspend fun postJson(path: String, body: String): String = call("POST", path, emptyMap(), body)

    suspend fun delete(path: String, query: Map<String, String>): String = call("DELETE", path, query, null)

    /** Unauthenticated POST (sign-in), against an explicit base URL. Returns the HTTP code and body. */
    suspend fun postPublic(base: String, path: String, body: String): Pair<Int, String> = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(base.trimEnd('/') + path).post(body.toRequestBody("application/json".toMediaType())).build()
        try {
            http.newCall(req).await().use { it.code to it.body.string() }
        } catch (e: IOException) {
            throw ApiException.Network(e)
        }
    }

    /** A GET with an explicit token, before it's saved (e.g. to check a device token). (HTTP code, body). */
    suspend fun getWithToken(base: String, path: String, token: String): Pair<Int, String> = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(base.trimEnd('/') + path).header("Authorization", "Bearer $token").get().build()
        try {
            http.newCall(req).await().use { it.code to it.body.string() }
        } catch (e: IOException) {
            throw ApiException.Network(e)
        }
    }

    /** Runs the call asynchronously; cancelling the coroutine cancels the HTTP request itself. */
    private suspend fun okhttp3.Call.await(): okhttp3.Response = kotlinx.coroutines.suspendCancellableCoroutine { cont ->
        cont.invokeOnCancellation { cancel() }
        enqueue(object : okhttp3.Callback {
            override fun onFailure(call: okhttp3.Call, e: IOException) { if (!cont.isCancelled) cont.resumeWith(Result.failure(e)) }
            override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                if (cont.isActive) cont.resumeWith(Result.success(response)) else response.close()
            }
        })
    }

    private suspend fun call(method: String, path: String, query: Map<String, String>, body: String?,
                             headers: Map<String, String> = emptyMap()): String =
        withContext(Dispatchers.IO) {
            val (base, token) = credentials() ?: throw ApiException.NotConfigured()
            val url = (base.trimEnd('/') + path).toHttpUrl().newBuilder().apply {
                query.forEach { (k, v) -> addQueryParameter(k, v) }
            }.build()
            val key = "$token|$url"
            val known = if (method == "GET") etags[key] else null
            val req = Request.Builder().url(url)
                .apply { headers.forEach { (k, v) -> header(k, v) } }
                .header("Authorization", "Bearer $token")
                .apply { known?.let { header("If-None-Match", it.first) } }
                .method(method, body?.toRequestBody("application/json".toMediaType()))
                .build()
            try {
                http.newCall(req).await().use { resp ->
                    when {
                        resp.code == 304 && known != null -> known.second
                        resp.code == 401 -> throw ApiException.Unauthorized()
                        !resp.isSuccessful -> throw ApiException.Http(resp.code)
                        else -> resp.body.string().also { text ->
                            if (method == "GET") resp.header("ETag")?.let { etags[key] = it to text } ?: etags.remove(key)
                        }
                    }
                }
            } catch (e: IOException) {
                throw ApiException.Network(e)
            }
        }
}

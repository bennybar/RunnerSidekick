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
}

class ApiClient(private val credentials: suspend () -> Pair<String, String>?) {

    val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    /** Returns the raw JSON body so callers can cache exactly what the backend said. */
    suspend fun getRaw(path: String, query: Map<String, String> = emptyMap()): String = call("GET", path, query, null)

    suspend fun putRaw(path: String, body: String): String = call("PUT", path, emptyMap(), body)

    suspend fun post(path: String): String = call("POST", path, emptyMap(), "")

    suspend fun delete(path: String, query: Map<String, String>): String = call("DELETE", path, query, null)

    /** Unauthenticated POST (sign-in), against an explicit base URL. Returns the HTTP code and body. */
    suspend fun postPublic(base: String, path: String, body: String): Pair<Int, String> = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(base.trimEnd('/') + path).post(body.toRequestBody("application/json".toMediaType())).build()
        try {
            http.newCall(req).execute().use { it.code to it.body.string() }
        } catch (e: IOException) {
            throw ApiException.Network(e)
        }
    }

    private suspend fun call(method: String, path: String, query: Map<String, String>, body: String?): String =
        withContext(Dispatchers.IO) {
            val (base, token) = credentials() ?: throw ApiException.NotConfigured()
            val url = (base.trimEnd('/') + path).toHttpUrl().newBuilder().apply {
                query.forEach { (k, v) -> addQueryParameter(k, v) }
            }.build()
            val req = Request.Builder().url(url)
                .header("Authorization", "Bearer $token")
                .method(method, body?.toRequestBody("application/json".toMediaType()))
                .build()
            try {
                http.newCall(req).execute().use { resp ->
                    when {
                        resp.code == 401 -> throw ApiException.Unauthorized()
                        !resp.isSuccessful -> throw ApiException.Http(resp.code)
                        else -> resp.body.string()
                    }
                }
            } catch (e: IOException) {
                throw ApiException.Network(e)
            }
        }
}

package com.yjkim9670.codexworkbench

import android.os.SystemClock
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

enum class QuickTunnelDiscoveryKind {
    ONLINE,
    UNAVAILABLE,
    AUTH_REQUIRED,
    CONFIGURATION_ERROR,
    SERVICE_ERROR,
    NETWORK_ERROR,
    INVALID_RESPONSE,
}

data class QuickTunnelDiscoveryResult(
    val kind: QuickTunnelDiscoveryKind,
    val rootUrl: String? = null,
    val message: String,
)

object QuickTunnelDiscoveryClient {
    private const val CACHE_TTL_MS = 45_000L
    private const val CONNECT_TIMEOUT_MS = 7_000
    private const val READ_TIMEOUT_MS = 7_000
    private val USER_AGENT = "CodexWorkbenchAndroid/${BuildConfig.VERSION_NAME}"

    private data class CachedRoot(val url: String, val expiresAtMs: Long)

    @Volatile
    private var cachedRoot: CachedRoot? = null

    @Synchronized
    fun invalidate() {
        cachedRoot = null
    }

    fun resolve(forceRefresh: Boolean = false): QuickTunnelDiscoveryResult {
        if (!forceRefresh) {
            val cached = cachedRoot
            if (cached != null && SystemClock.elapsedRealtime() < cached.expiresAtMs) {
                return QuickTunnelDiscoveryResult(
                    QuickTunnelDiscoveryKind.ONLINE,
                    cached.url,
                    "Quick Tunnel 주소를 확인했습니다.",
                )
            }
        } else {
            invalidate()
        }

        val baseEndpoint = WorkbenchCatalog.QUICK_TUNNEL_DISCOVERY_BFF_URL
        val endpoint = if (forceRefresh) "$baseEndpoint?refresh=1" else baseEndpoint
        var connection: HttpURLConnection? = null
        return try {
            connection = (URL(endpoint).openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = CONNECT_TIMEOUT_MS
                readTimeout = READ_TIMEOUT_MS
                instanceFollowRedirects = false
                setRequestProperty("Accept", "application/json")
                setRequestProperty("User-Agent", USER_AGENT)
            }
            val code = connection.responseCode
            val body = runCatching {
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                stream?.bufferedReader()?.use { it.readText().take(128 * 1024) }.orEmpty()
            }.getOrDefault("")
            parseResponse(code, body)
        } catch (_: Exception) {
            invalidate()
            QuickTunnelDiscoveryResult(
                QuickTunnelDiscoveryKind.NETWORK_ERROR,
                message = "Quick Tunnel discovery 서버에 연결할 수 없습니다.",
            )
        } finally {
            connection?.disconnect()
        }
    }

    private fun parseResponse(code: Int, body: String): QuickTunnelDiscoveryResult {
        val payload = runCatching { JSONObject(body) }.getOrNull()
        if (code == 200 && payload != null) {
            if (!payload.optBoolean("available", false) || payload.optString("status") != "online") {
                invalidate()
                return QuickTunnelDiscoveryResult(
                    QuickTunnelDiscoveryKind.UNAVAILABLE,
                    message = "Quick Tunnel이 현재 준비되지 않았습니다",
                )
            }
            val root = WorkbenchCatalog.normalizeQuickTunnelRoot(payload.optString("url"))
            if (root == null) {
                invalidate()
                return QuickTunnelDiscoveryResult(
                    QuickTunnelDiscoveryKind.INVALID_RESPONSE,
                    message = "Quick Tunnel discovery 응답 URL이 올바르지 않습니다.",
                )
            }
            synchronized(this) {
                cachedRoot = CachedRoot(root, SystemClock.elapsedRealtime() + CACHE_TTL_MS)
            }
            return QuickTunnelDiscoveryResult(
                QuickTunnelDiscoveryKind.ONLINE,
                root,
                "Quick Tunnel 주소를 확인했습니다.",
            )
        }

        invalidate()
        val errorCode = payload?.optString("error_code").orEmpty()
        val serverMessage = payload?.optString("message").orEmpty()
        if (errorCode == "quick_tunnel_secret_misconfigured") {
            return QuickTunnelDiscoveryResult(
                QuickTunnelDiscoveryKind.CONFIGURATION_ERROR,
                message = serverMessage.ifBlank { "Quick Tunnel discovery 서버 설정을 확인해야 합니다." },
            )
        }
        if (code == 401 || code == 403 || code in 300..399) {
            return QuickTunnelDiscoveryResult(
                QuickTunnelDiscoveryKind.AUTH_REQUIRED,
                message = "Quick Tunnel discovery 접근 인증이 필요합니다.",
            )
        }
        return QuickTunnelDiscoveryResult(
            QuickTunnelDiscoveryKind.SERVICE_ERROR,
            message = serverMessage.ifBlank { "Quick Tunnel discovery 요청이 실패했습니다. (HTTP $code)" },
        )
    }
}

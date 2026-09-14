package com.yjkim9670.codexworkbench

import java.net.URI

enum class ConnectionMode {
    FUNNEL,
    TAILSCALE,
    QUICK_TUNNEL,
    ;

    companion object {
        fun fromPreference(value: String?): ConnectionMode? =
            entries.firstOrNull { it.name == value }
    }
}

data class WorkbenchTarget(
    val id: String,
    val name: String,
    val funnelUrl: String,
    val tailscaleUrl: String,
    val quickTunnelPath: String,
    val isCodexWorkbench: Boolean = true,
) {
    fun urlFor(mode: ConnectionMode): String = when (mode) {
        ConnectionMode.FUNNEL -> funnelUrl
        ConnectionMode.TAILSCALE -> tailscaleUrl
        ConnectionMode.QUICK_TUNNEL -> error("Quick Tunnel URL must be discovered before use")
    }

    fun quickTunnelUrl(rootUrl: String): String? =
        WorkbenchCatalog.combineQuickTunnelUrl(rootUrl, quickTunnelPath)
}

object WorkbenchCatalog {
    const val DEFAULT_ID = "common_tg"
    const val FUNNEL_ROOT = "https://dinya.wind-mintaka.ts.net"
    const val TAILSCALE_HOST = "dinya.wind-mintaka.ts.net"
    const val QUICK_TUNNEL_DISCOVERY_BFF_URL = "$FUNNEL_ROOT/tg/api/android/quick-tunnel"

    private val allowedQuickTunnelPaths = setOf(
        "/",
        "/tg/",
        "/finance-codex/",
        "/local/",
        "/constraint/",
        "/dev/",
    )

    val targets = listOf(
        WorkbenchTarget(
            id = "common_tg",
            name = "Common TG Codex Workbench",
            funnelUrl = "$FUNNEL_ROOT/tg/",
            tailscaleUrl = "http://$TAILSCALE_HOST:3000/",
            quickTunnelPath = "/tg/",
        ),
        WorkbenchTarget(
            id = "finance",
            name = "Finance Codex Workbench",
            funnelUrl = "$FUNNEL_ROOT/finance-codex/",
            tailscaleUrl = "http://$TAILSCALE_HOST:3001/",
            quickTunnelPath = "/finance-codex/",
        ),
        WorkbenchTarget(
            id = "local",
            name = "Local Codex Workbench",
            funnelUrl = "$FUNNEL_ROOT/local/",
            tailscaleUrl = "http://$TAILSCALE_HOST:3002/",
            quickTunnelPath = "/local/",
        ),
        WorkbenchTarget(
            id = "constraint",
            name = "Constraint Codex Workbench",
            funnelUrl = "$FUNNEL_ROOT/constraint/",
            tailscaleUrl = "http://$TAILSCALE_HOST:3003/",
            quickTunnelPath = "/constraint/",
        ),
        WorkbenchTarget(
            id = "dev",
            name = "Dev Codex Workbench",
            funnelUrl = "$FUNNEL_ROOT/dev/",
            tailscaleUrl = "http://$TAILSCALE_HOST:3004/",
            quickTunnelPath = "/dev/",
        ),
        WorkbenchTarget(
            id = "process_dashboard",
            name = "Mac Process Dashboard",
            funnelUrl = "$FUNNEL_ROOT/",
            tailscaleUrl = "http://$TAILSCALE_HOST:18000/",
            quickTunnelPath = "/",
            isCodexWorkbench = false,
        ),
    )

    fun byId(id: String?): WorkbenchTarget =
        targets.firstOrNull { it.id == id } ?: targets.first()

    fun byUrl(url: String?): WorkbenchTarget? {
        val normalized = normalizeUrl(url)
        if (normalized.isBlank()) return null
        targets.firstOrNull { target ->
            normalizeUrl(target.funnelUrl) == normalized ||
                normalizeUrl(target.tailscaleUrl) == normalized
        }?.let { return it }
        return quickTunnelTargetForUrl(normalized)
    }

    fun modeForUrl(url: String?): ConnectionMode? {
        val normalized = normalizeUrl(url)
        if (normalized.isBlank()) return null
        return when {
            targets.any { normalizeUrl(it.tailscaleUrl) == normalized } -> ConnectionMode.TAILSCALE
            targets.any { normalizeUrl(it.funnelUrl) == normalized } -> ConnectionMode.FUNNEL
            quickTunnelTargetForUrl(normalized) != null -> ConnectionMode.QUICK_TUNNEL
            else -> null
        }
    }

    fun normalizeQuickTunnelRoot(url: String?): String? {
        val value = url.orEmpty().trim()
        if (value.isBlank()) return null
        val parsed = runCatching { URI(value) }.getOrNull() ?: return null
        if (!parsed.scheme.equals("https", ignoreCase = true)) return null
        if (parsed.userInfo != null || parsed.port != -1 || parsed.query != null || parsed.fragment != null) return null
        if (parsed.path !in listOf("", "/")) return null
        val host = parsed.host?.lowercase().orEmpty()
        if (!isValidQuickTunnelHost(host)) return null
        return "https://$host"
    }

    fun combineQuickTunnelUrl(rootUrl: String?, appPath: String?): String? {
        val root = normalizeQuickTunnelRoot(rootUrl) ?: return null
        val path = appPath.orEmpty().trim()
        if (path !in allowedQuickTunnelPaths) return null
        if (!path.startsWith('/') || path.contains("..") || path.contains('\\') ||
            path.contains('?') || path.contains('#') || path.contains("//")
        ) {
            return null
        }
        return root.trimEnd('/') + path
    }

    private fun quickTunnelTargetForUrl(url: String): WorkbenchTarget? {
        val parsed = runCatching { URI(url) }.getOrNull() ?: return null
        if (!parsed.scheme.equals("https", ignoreCase = true)) return null
        if (parsed.userInfo != null || parsed.port != -1 || parsed.query != null || parsed.fragment != null) return null
        val host = parsed.host?.lowercase().orEmpty()
        if (!isValidQuickTunnelHost(host)) return null
        val path = normalizePath(parsed.path)
        return targets.firstOrNull { normalizePath(it.quickTunnelPath) == path }
    }

    private fun isValidQuickTunnelHost(host: String): Boolean {
        if (!host.endsWith(".trycloudflare.com")) return false
        val prefix = host.removeSuffix(".trycloudflare.com")
        if (prefix.isBlank()) return false
        return prefix.split('.').all { label ->
            label.length in 1..63 &&
                label.first().isLetterOrDigit() &&
                label.last().isLetterOrDigit() &&
                label.all { it.isLowerCase() || it.isDigit() || it == '-' }
        }
    }

    private fun normalizePath(path: String?): String {
        val value = path.orEmpty().ifBlank { "/" }
        return if (value == "/") value else value.trimEnd('/')
    }

    private fun normalizeUrl(url: String?): String =
        url.orEmpty().trim().trimEnd('/')
}

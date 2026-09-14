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
        ConnectionMode.QUICK_TUNNEL -> quickTunnelUrl(WorkbenchCatalog.QUICK_TUNNEL_ROOT)
    }

    fun quickTunnelUrl(rootUrl: String = WorkbenchCatalog.QUICK_TUNNEL_ROOT): String {
        val normalizedRoot = WorkbenchCatalog.normalizeQuickTunnelRoot(rootUrl)
            ?: throw IllegalArgumentException("Invalid Quick Tunnel root URL")
        return normalizedRoot + quickTunnelPath
    }
}

object WorkbenchCatalog {
    const val DEFAULT_ID = "common_tg"
    const val FUNNEL_ROOT = "https://dinya.wind-mintaka.ts.net"
    const val TAILSCALE_HOST = "dinya.wind-mintaka.ts.net"
    const val QUICK_TUNNEL_ROOT = "https://painted-slideshow-hampshire-main.trycloudflare.com"

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

    fun normalizeQuickTunnelRoot(rawUrl: String?): String? {
        val value = rawUrl.orEmpty().trim()
        if (value.isBlank()) return null
        val uri = runCatching { URI(value) }.getOrNull() ?: return null
        if (!uri.scheme.equals("https", ignoreCase = true)) return null
        if (uri.rawUserInfo != null || uri.port != -1 || uri.rawQuery != null || uri.rawFragment != null) return null
        if (!uri.rawPath.isNullOrEmpty() && uri.rawPath != "/") return null
        val host = uri.host?.lowercase()?.trimEnd('.') ?: return null
        if (host == "trycloudflare.com" || !host.endsWith(".trycloudflare.com")) return null
        val prefix = host.removeSuffix(".trycloudflare.com")
        if (prefix.isBlank() || prefix.split('.').any { label ->
                label.isBlank() ||
                    label.length > 63 ||
                    label.first() == '-' ||
                    label.last() == '-' ||
                    label.any { ch -> !(ch.isLetterOrDigit() || ch == '-') }
            }
        ) {
            return null
        }
        return "https://$host"
    }

    fun byId(id: String?): WorkbenchTarget =
        targets.firstOrNull { it.id == id } ?: targets.first()

    fun byUrl(url: String?): WorkbenchTarget? {
        val normalized = normalizeUrl(url)
        if (normalized.isBlank()) return null
        val staticTarget = targets.firstOrNull { target ->
            normalizeUrl(target.funnelUrl) == normalized ||
                normalizeUrl(target.tailscaleUrl) == normalized ||
                normalizeUrl(target.urlFor(ConnectionMode.QUICK_TUNNEL)) == normalized
        }
        return staticTarget ?: dynamicQuickTunnelTarget(url)
    }

    fun modeForUrl(url: String?): ConnectionMode? {
        val normalized = normalizeUrl(url)
        if (normalized.isBlank()) return null
        return when {
            targets.any { normalizeUrl(it.tailscaleUrl) == normalized } -> ConnectionMode.TAILSCALE
            targets.any { normalizeUrl(it.funnelUrl) == normalized } -> ConnectionMode.FUNNEL
            targets.any { normalizeUrl(it.urlFor(ConnectionMode.QUICK_TUNNEL)) == normalized } ->
                ConnectionMode.QUICK_TUNNEL
            dynamicQuickTunnelTarget(url) != null -> ConnectionMode.QUICK_TUNNEL
            else -> null
        }
    }

    private fun dynamicQuickTunnelTarget(url: String?): WorkbenchTarget? {
        val uri = runCatching { URI(url.orEmpty().trim()) }.getOrNull() ?: return null
        if (!uri.scheme.equals("https", ignoreCase = true)) return null
        if (uri.rawUserInfo != null || uri.port != -1 || uri.rawQuery != null || uri.rawFragment != null) return null
        val host = uri.host ?: return null
        if (normalizeQuickTunnelRoot("https://$host") == null) return null
        val normalizedPath = normalizePath(uri.rawPath)
        return targets.firstOrNull { target -> normalizePath(target.quickTunnelPath) == normalizedPath }
    }

    private fun normalizePath(path: String?): String =
        if (path.isNullOrBlank() || path == "/") "/" else "/${path.trim('/')}/"

    private fun normalizeUrl(url: String?): String =
        url.orEmpty().trim().trimEnd('/')
}

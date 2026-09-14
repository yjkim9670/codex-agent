package com.yjkim9670.codexworkbench

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

    fun quickTunnelUrl(rootUrl: String = WorkbenchCatalog.QUICK_TUNNEL_ROOT): String =
        rootUrl.trimEnd('/') + quickTunnelPath
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

    fun byId(id: String?): WorkbenchTarget =
        targets.firstOrNull { it.id == id } ?: targets.first()

    fun byUrl(url: String?): WorkbenchTarget? {
        val normalized = normalizeUrl(url)
        if (normalized.isBlank()) return null
        return targets.firstOrNull { target ->
            ConnectionMode.entries.any { mode -> normalizeUrl(target.urlFor(mode)) == normalized }
        }
    }

    fun modeForUrl(url: String?): ConnectionMode? {
        val normalized = normalizeUrl(url)
        if (normalized.isBlank()) return null
        return ConnectionMode.entries.firstOrNull { mode ->
            targets.any { target -> normalizeUrl(target.urlFor(mode)) == normalized }
        }
    }

    private fun normalizeUrl(url: String?): String =
        url.orEmpty().trim().trimEnd('/')
}

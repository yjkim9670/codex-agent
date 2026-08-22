package com.yjkim9670.codexworkbench

enum class ConnectionMode {
    FUNNEL,
    TAILSCALE,
}

data class WorkbenchTarget(
    val id: String,
    val name: String,
    val funnelUrl: String,
    val tailscaleUrl: String,
    val isCodexWorkbench: Boolean = true,
) {
    fun urlFor(mode: ConnectionMode): String =
        if (mode == ConnectionMode.TAILSCALE) tailscaleUrl else funnelUrl
}

object WorkbenchCatalog {
    const val DEFAULT_ID = "common_tg"
    const val FUNNEL_ROOT = "https://dinya.wind-mintaka.ts.net"
    const val TAILSCALE_HOST = "dinya.wind-mintaka.ts.net"

    val targets = listOf(
        WorkbenchTarget(
            id = "common_tg",
            name = "Common TG Codex Workbench",
            funnelUrl = "$FUNNEL_ROOT/tg/",
            tailscaleUrl = "http://$TAILSCALE_HOST:3000/",
        ),
        WorkbenchTarget(
            id = "finance",
            name = "Finance Codex Workbench",
            funnelUrl = "$FUNNEL_ROOT/finance-codex/",
            tailscaleUrl = "http://$TAILSCALE_HOST:3001/",
        ),
        WorkbenchTarget(
            id = "local",
            name = "Local Codex Workbench",
            funnelUrl = "$FUNNEL_ROOT/local/",
            tailscaleUrl = "http://$TAILSCALE_HOST:3002/",
        ),
        WorkbenchTarget(
            id = "constraint",
            name = "Constraint Codex Workbench",
            funnelUrl = "$FUNNEL_ROOT/constraint/",
            tailscaleUrl = "http://$TAILSCALE_HOST:3003/",
        ),
        WorkbenchTarget(
            id = "dev",
            name = "Dev Codex Workbench",
            funnelUrl = "$FUNNEL_ROOT/dev/",
            tailscaleUrl = "http://$TAILSCALE_HOST:3004/",
        ),
        WorkbenchTarget(
            id = "process_dashboard",
            name = "Mac Process Dashboard",
            funnelUrl = "$FUNNEL_ROOT/",
            tailscaleUrl = "http://$TAILSCALE_HOST:18000/",
            isCodexWorkbench = false,
        ),
    )

    // Stored preferences from an older app version must never make startup fail.
    fun byId(id: String?): WorkbenchTarget =
        targets.firstOrNull { it.id == id } ?: targets.first()

    fun byUrl(url: String?): WorkbenchTarget? {
        val normalized = normalizeUrl(url)
        if (normalized.isBlank()) return null
        return targets.firstOrNull { target ->
            normalizeUrl(target.funnelUrl) == normalized ||
                normalizeUrl(target.tailscaleUrl) == normalized
        }
    }

    fun modeForUrl(url: String?): ConnectionMode? {
        val normalized = normalizeUrl(url)
        if (normalized.isBlank()) return null
        return when {
            targets.any { normalizeUrl(it.tailscaleUrl) == normalized } -> ConnectionMode.TAILSCALE
            targets.any { normalizeUrl(it.funnelUrl) == normalized } -> ConnectionMode.FUNNEL
            else -> null
        }
    }

    private fun normalizeUrl(url: String?): String =
        url.orEmpty().trim().trimEnd('/')
}

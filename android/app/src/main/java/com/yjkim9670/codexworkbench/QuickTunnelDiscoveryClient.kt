package com.yjkim9670.codexworkbench

enum class QuickTunnelDiscoveryKind {
    ONLINE,
}

data class QuickTunnelDiscoveryResult(
    val kind: QuickTunnelDiscoveryKind,
    val rootUrl: String? = null,
    val message: String,
)

/**
 * Compatibility wrapper for the existing MainActivity/notification flow.
 *
 * Quick Tunnel now uses a fixed app-side root. No discovery request, bearer
 * token, server-side BFF, cache, or secret is involved.
 */
object QuickTunnelDiscoveryClient {
    fun invalidate() = Unit

    fun resolve(forceRefresh: Boolean = false): QuickTunnelDiscoveryResult {
        @Suppress("UNUSED_VARIABLE")
        val ignored = forceRefresh
        return QuickTunnelDiscoveryResult(
            kind = QuickTunnelDiscoveryKind.ONLINE,
            rootUrl = WorkbenchCatalog.QUICK_TUNNEL_ROOT,
            message = "고정 Quick Tunnel 주소를 사용합니다.",
        )
    }
}

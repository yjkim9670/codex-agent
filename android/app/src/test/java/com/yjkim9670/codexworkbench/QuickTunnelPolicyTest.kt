package com.yjkim9670.codexworkbench

import org.junit.Assert.assertEquals
import org.junit.Test

class QuickTunnelPolicyTest {
    @Test
    fun usesFixedQuickTunnelRoot() {
        assertEquals(
            "https://painted-slideshow-hampshire-main.trycloudflare.com",
            WorkbenchCatalog.QUICK_TUNNEL_ROOT,
        )
    }

    @Test
    fun buildsExpectedQuickTunnelWorkbenchUrls() {
        assertEquals(
            "https://painted-slideshow-hampshire-main.trycloudflare.com/tg/",
            WorkbenchCatalog.byId("common_tg").urlFor(ConnectionMode.QUICK_TUNNEL),
        )
        assertEquals(
            "https://painted-slideshow-hampshire-main.trycloudflare.com/finance-codex/",
            WorkbenchCatalog.byId("finance").urlFor(ConnectionMode.QUICK_TUNNEL),
        )
        assertEquals(
            "https://painted-slideshow-hampshire-main.trycloudflare.com/local/",
            WorkbenchCatalog.byId("local").urlFor(ConnectionMode.QUICK_TUNNEL),
        )
        assertEquals(
            "https://painted-slideshow-hampshire-main.trycloudflare.com/constraint/",
            WorkbenchCatalog.byId("constraint").urlFor(ConnectionMode.QUICK_TUNNEL),
        )
        assertEquals(
            "https://painted-slideshow-hampshire-main.trycloudflare.com/dev/",
            WorkbenchCatalog.byId("dev").urlFor(ConnectionMode.QUICK_TUNNEL),
        )
        assertEquals(
            "https://painted-slideshow-hampshire-main.trycloudflare.com/",
            WorkbenchCatalog.byId("process_dashboard").urlFor(ConnectionMode.QUICK_TUNNEL),
        )
    }

    @Test
    fun recognizesFixedQuickTunnelUrls() {
        val url = "https://painted-slideshow-hampshire-main.trycloudflare.com/finance-codex/"
        assertEquals(ConnectionMode.QUICK_TUNNEL, WorkbenchCatalog.modeForUrl(url))
        assertEquals("finance", WorkbenchCatalog.byUrl(url)?.id)
    }
}

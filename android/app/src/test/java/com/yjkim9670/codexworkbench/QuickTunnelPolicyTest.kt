package com.yjkim9670.codexworkbench

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class QuickTunnelPolicyTest {
    @Test
    fun keepsCurrentQuickTunnelRootAsDefault() {
        assertEquals(
            "https://painted-slideshow-hampshire-main.trycloudflare.com",
            WorkbenchCatalog.QUICK_TUNNEL_ROOT,
        )
    }

    @Test
    fun buildsExpectedDefaultQuickTunnelWorkbenchUrls() {
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
    fun normalizesAndBuildsCustomQuickTunnelRoot() {
        val customRoot = "https://new-random-name.trycloudflare.com/"
        assertEquals(
            "https://new-random-name.trycloudflare.com",
            WorkbenchCatalog.normalizeQuickTunnelRoot(customRoot),
        )
        assertEquals(
            "https://new-random-name.trycloudflare.com/dev/",
            WorkbenchCatalog.byId("dev").quickTunnelUrl(customRoot),
        )
    }

    @Test
    fun rejectsUnsafeQuickTunnelRoots() {
        assertNull(WorkbenchCatalog.normalizeQuickTunnelRoot("http://name.trycloudflare.com"))
        assertNull(WorkbenchCatalog.normalizeQuickTunnelRoot("https://trycloudflare.com"))
        assertNull(WorkbenchCatalog.normalizeQuickTunnelRoot("https://name.trycloudflare.com/dev/"))
        assertNull(WorkbenchCatalog.normalizeQuickTunnelRoot("https://name.trycloudflare.com:8443"))
        assertNull(WorkbenchCatalog.normalizeQuickTunnelRoot("https://name.trycloudflare.com?x=1"))
        assertNull(WorkbenchCatalog.normalizeQuickTunnelRoot("https://user@name.trycloudflare.com"))
        assertNull(WorkbenchCatalog.normalizeQuickTunnelRoot("https://example.com"))
    }

    @Test
    fun recognizesCustomQuickTunnelWorkbenchUrls() {
        val url = "https://new-random-name.trycloudflare.com/finance-codex/"
        assertEquals(ConnectionMode.QUICK_TUNNEL, WorkbenchCatalog.modeForUrl(url))
        assertEquals("finance", WorkbenchCatalog.byUrl(url)?.id)
    }
}

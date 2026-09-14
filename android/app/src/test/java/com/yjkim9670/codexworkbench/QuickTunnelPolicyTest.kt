package com.yjkim9670.codexworkbench

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class QuickTunnelPolicyTest {
    @Test
    fun combinesValidatedRootWithKnownWorkbenchPath() {
        val target = WorkbenchCatalog.byId("common_tg")
        assertEquals(
            "https://painted-slideshow-hampshire-main.trycloudflare.com/tg/",
            target.quickTunnelUrl("https://painted-slideshow-hampshire-main.trycloudflare.com/"),
        )
    }

    @Test
    fun rejectsUnsafeRootAndPath() {
        assertNull(WorkbenchCatalog.normalizeQuickTunnelRoot("http://bad.trycloudflare.com"))
        assertNull(WorkbenchCatalog.normalizeQuickTunnelRoot("https://good.trycloudflare.com/path"))
        assertNull(
            WorkbenchCatalog.combineQuickTunnelUrl(
                "https://good.trycloudflare.com",
                "/../admin/",
            ),
        )
    }

    @Test
    fun recognizesDynamicQuickTunnelWorkbenchUrl() {
        val url = "https://painted-slideshow-hampshire-main.trycloudflare.com/finance-codex/"
        assertEquals(ConnectionMode.QUICK_TUNNEL, WorkbenchCatalog.modeForUrl(url))
        assertEquals("finance", WorkbenchCatalog.byUrl(url)?.id)
    }

    @Test
    fun retryPolicyMatchesRequiredFailuresOnly() {
        assertTrue(QuickTunnelRetryPolicy.shouldRediscoverForHttpStatus(502))
        assertTrue(QuickTunnelRetryPolicy.shouldRediscoverForHttpStatus(503))
        assertTrue(QuickTunnelRetryPolicy.shouldRediscoverForHttpStatus(504))
        assertFalse(QuickTunnelRetryPolicy.shouldRediscoverForHttpStatus(500))
        assertTrue(QuickTunnelRetryPolicy.shouldRediscoverForWebViewError(-2))
        assertTrue(QuickTunnelRetryPolicy.shouldRediscoverForWebViewError(-6))
        assertTrue(QuickTunnelRetryPolicy.shouldRediscoverForWebViewError(-7))
        assertTrue(QuickTunnelRetryPolicy.shouldRediscoverForWebViewError(-8))
        assertFalse(QuickTunnelRetryPolicy.shouldRediscoverForWebViewError(-11))
    }
}

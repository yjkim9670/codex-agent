package com.yjkim9670.codexworkbench

import org.junit.Assert.*
import org.junit.Test

class ConnectionAndCompletionTest {
    @Test fun migratesFunnelAndRejectsOtherOrigins() {
        assertEquals(ConnectionMode.QUICK_TUNNEL, ConnectionMode.fromPreference("FUNNEL"))
        assertEquals(2, ConnectionMode.entries.size)
        assertTrue(WorkbenchCatalog.isAllowedPage("https://${WorkbenchCatalog.TAILSCALE_HOST}:3102/"))
        assertTrue(WorkbenchCatalog.isAllowedPage(WorkbenchCatalog.QUICK_TUNNEL_ROOT + "/__funnel_auth/login"))
        for (url in listOf("https://${WorkbenchCatalog.TAILSCALE_HOST}/tg/", "http://127.0.0.1:3000/",
            "https://evil.trycloudflare.com/", "https://user@${WorkbenchCatalog.TAILSCALE_HOST}:3102/",
            "https://strategy-lawrence-runs-places.trycloudflare.com.evil.test/")) {
            assertFalse(url, WorkbenchCatalog.isAllowedPage(url))
        }
        val custom="https://new-name.trycloudflare.com"
        assertTrue(WorkbenchCatalog.isAllowedPage(custom+"/dev/", custom))
        assertFalse(WorkbenchCatalog.isAllowedPage(WorkbenchCatalog.QUICK_TUNNEL_ROOT, custom))
    }
    @Test fun providesEncryptedChatInBothNetworks() {
        val chat = WorkbenchCatalog.byId("conversation")
        assertTrue(chat.isConversation)
        assertFalse(chat.isCodexWorkbench)
        assertEquals("https://${WorkbenchCatalog.TAILSCALE_HOST}:3102/", chat.urlFor(ConnectionMode.TAILSCALE))
        assertEquals(chat, WorkbenchCatalog.byUrl(chat.quickTunnelUrl()))
    }
    @Test fun ignoresHistoryAndFindsFastCompletedTaskOnce() {
        val tracker=CompletionTracker()
        val old=CompletionTracker.Stream("old-session", true)
        assertTrue(tracker.observe(mapOf("old" to old), 0).isEmpty())
        val done=CompletionTracker.Stream("new-session", true)
        assertEquals(setOf("new-session"), tracker.observe(mapOf("old" to old,"fast" to done),0))
        assertTrue(tracker.observe(mapOf("old" to old,"fast" to done),0).isEmpty())
    }
    @Test fun waitsForExplicitCompletionAndQueueDrain() {
        val tracker=CompletionTracker()
        val running=CompletionTracker.Stream("session", false)
        assertTrue(tracker.observe(mapOf("a" to running),0).isEmpty())
        assertTrue(tracker.observe(emptyMap(),0).isEmpty()) // Missing data is not completion.
        assertTrue(tracker.observe(mapOf("a" to running.copy(done=true)),1).isEmpty())
        assertEquals(setOf("session"), tracker.observe(mapOf("a" to running.copy(done=true)),0))
    }
    @Test fun cancellationDoesNotAnnounceSuccess() {
        val tracker=CompletionTracker()
        tracker.observe(mapOf("a" to CompletionTracker.Stream("session",false)),0)
        assertTrue(tracker.observe(mapOf("a" to CompletionTracker.Stream("session",true,true)),0).isEmpty())
    }
}

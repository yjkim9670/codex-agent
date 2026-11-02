package com.yjkim9670.codexworkbench

import android.content.Context
import android.content.Intent

/** Compatibility intent factory; all browser and download logic lives in V2. */
object DashboardBrowserActivity {
    const val EXTRA_URL = "dashboard_browser_url"
    fun createIntent(context: Context, url: String): Intent =
        Intent(context, DashboardBrowserActivityV2::class.java).putExtra(EXTRA_URL, url)
}

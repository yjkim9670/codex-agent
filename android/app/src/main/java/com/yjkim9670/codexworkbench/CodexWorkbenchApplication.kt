package com.yjkim9670.codexworkbench

import android.app.Activity
import android.app.Application
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsetsController
import android.webkit.WebView
import java.lang.ref.WeakReference
import java.util.WeakHashMap

class CodexWorkbenchApplication : Application(), Application.ActivityLifecycleCallbacks {
    companion object {
        private const val WEBVIEW_PATCH_INTERVAL_MS = 1_500L

        private val WEBVIEW_MOBILE_LAYOUT_FIX = """
            (() => {
                const root = document.documentElement;
                const head = document.head;
                if (!root || !head) return;
                root.classList.add('codex-android-webview');
                if (document.getElementById('codex-android-webview-layout-fix')) return;
                const style = document.createElement('style');
                style.id = 'codex-android-webview-layout-fix';
                style.textContent = `
                    @media (max-width: 840px) {
                        html.codex-android-webview .chat-input {
                            padding-bottom: 0 !important;
                        }
                    }
                `;
                head.appendChild(style);
            })();
        """.trimIndent()
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    private val webViewPatchPollers = WeakHashMap<Activity, Runnable>()
    private val patchedUrls = WeakHashMap<WebView, String>()

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(this)
    }

    override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {
        applyStableSystemBars(activity)
        installSystemUiGuard(activity)
    }

    override fun onActivityResumed(activity: Activity) {
        applyStableSystemBars(activity)
        startWebViewPatchPolling(activity)
    }

    override fun onActivityPaused(activity: Activity) {
        stopWebViewPatchPolling(activity)
    }

    private fun installSystemUiGuard(activity: Activity) {
        activity.window.decorView.setOnSystemUiVisibilityChangeListener {
            runCatching { applyStableSystemBars(activity) }
        }
    }

    private fun startWebViewPatchPolling(activity: Activity) {
        stopWebViewPatchPolling(activity)
        val activityRef = WeakReference(activity)
        lateinit var poller: Runnable
        poller = Runnable {
            val target = activityRef.get()
            if (target == null || target.isFinishing || target.isDestroyed) {
                return@Runnable
            }

            runCatching {
                patchWebViews(target.window.decorView)
            }
            mainHandler.postDelayed(poller, WEBVIEW_PATCH_INTERVAL_MS)
        }
        webViewPatchPollers[activity] = poller
        mainHandler.post(poller)
    }

    private fun stopWebViewPatchPolling(activity: Activity) {
        webViewPatchPollers.remove(activity)?.let(mainHandler::removeCallbacks)
    }

    private fun patchWebViews(view: View) {
        if (view is WebView) {
            patchWebView(view)
            return
        }
        if (view is ViewGroup) {
            for (index in 0 until view.childCount) {
                patchWebViews(view.getChildAt(index))
            }
        }
    }

    private fun patchWebView(webView: WebView) {
        val url = webView.url.orEmpty()
        if (!url.startsWith("http://") && !url.startsWith("https://")) return
        if (patchedUrls[webView] == url) return

        runCatching {
            webView.evaluateJavascript(WEBVIEW_MOBILE_LAYOUT_FIX) {
                patchedUrls[webView] = url
            }
        }
    }

    private fun applyStableSystemBars(activity: Activity) {
        val window = activity.window
        val background = activity.getColor(R.color.system_bar_background_light)

        @Suppress("DEPRECATION")
        run {
            window.statusBarColor = background
            window.navigationBarColor = background
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            window.isStatusBarContrastEnforced = true
            window.isNavigationBarContrastEnforced = true
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val appearance =
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                    WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
            window.insetsController?.setSystemBarsAppearance(appearance, appearance)
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility =
                window.decorView.systemUiVisibility or
                    View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or
                    View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        }
    }

    override fun onActivityStarted(activity: Activity) = Unit
    override fun onActivityStopped(activity: Activity) = Unit
    override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit

    override fun onActivityDestroyed(activity: Activity) {
        stopWebViewPatchPolling(activity)
    }
}

package com.yjkim9670.codexworkbench

import android.app.Activity
import android.app.Application
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.ViewTreeObserver
import android.view.WindowInsetsController
import android.webkit.WebView
import java.util.WeakHashMap

class CodexWorkbenchApplication : Application(), Application.ActivityLifecycleCallbacks {
    companion object {
        private const val WEBVIEW_PATCH_INTERVAL_MS = 1_200L

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

    private val layoutListeners = WeakHashMap<Activity, ViewTreeObserver.OnGlobalLayoutListener>()
    private val lastWebViewPatchAttempt = WeakHashMap<WebView, Long>()

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(this)
    }

    override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {
        applyStableSystemBars(activity)
        installSystemUiGuard(activity)
        installWebViewLayoutGuard(activity)
    }

    override fun onActivityResumed(activity: Activity) {
        applyStableSystemBars(activity)
        activity.window.decorView.post {
            patchWebViews(activity.window.decorView)
        }
    }

    private fun installSystemUiGuard(activity: Activity) {
        activity.window.decorView.setOnSystemUiVisibilityChangeListener {
            applyStableSystemBars(activity)
        }
    }

    private fun installWebViewLayoutGuard(activity: Activity) {
        val decor = activity.window.decorView
        val listener = ViewTreeObserver.OnGlobalLayoutListener {
            patchWebViews(decor)
        }
        layoutListeners[activity] = listener
        decor.viewTreeObserver.addOnGlobalLayoutListener(listener)
        decor.post { patchWebViews(decor) }
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

        val now = SystemClock.elapsedRealtime()
        val previous = lastWebViewPatchAttempt[webView] ?: 0L
        if (now - previous < WEBVIEW_PATCH_INTERVAL_MS) return
        lastWebViewPatchAttempt[webView] = now

        webView.post {
            runCatching {
                webView.evaluateJavascript(WEBVIEW_MOBILE_LAYOUT_FIX, null)
            }
        }
    }

    private fun applyStableSystemBars(activity: Activity) {
        val window = activity.window
        val background = activity.getColor(R.color.system_bar_background_light)

        // On Android 15+ the platform may make system bars transparent for edge-to-edge.
        // The app content already respects WindowInsets, so a light inset background plus
        // dark system icons remains readable whether the bar color is honored or transparent.
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
    override fun onActivityPaused(activity: Activity) = Unit
    override fun onActivityStopped(activity: Activity) = Unit
    override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit

    override fun onActivityDestroyed(activity: Activity) {
        val listener = layoutListeners.remove(activity) ?: return
        val observer = activity.window.decorView.viewTreeObserver
        if (observer.isAlive) {
            observer.removeOnGlobalLayoutListener(listener)
        }
    }
}

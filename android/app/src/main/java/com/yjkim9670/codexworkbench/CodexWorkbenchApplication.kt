package com.yjkim9670.codexworkbench

import android.app.Activity
import android.app.Application
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.Window
import android.view.WindowInsetsController

class CodexWorkbenchApplication : Application(), Application.ActivityLifecycleCallbacks {
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
    }

    private fun installSystemUiGuard(activity: Activity) {
        activity.window.decorView.setOnSystemUiVisibilityChangeListener {
            applyStableSystemBars(activity)
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
    override fun onActivityDestroyed(activity: Activity) = Unit
}

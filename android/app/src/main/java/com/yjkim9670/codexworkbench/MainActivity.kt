package com.yjkim9670.codexworkbench

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Message
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.webkit.CookieManager
import android.webkit.HttpAuthHandler
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {
    companion object {
        const val EXTRA_OPEN_BASE = "open_base"
        const val EXTRA_OPEN_SESSION = "open_session"
        @Volatile var isVisible = false
        const val EXTRA_SHOW_SERVER_SELECTION = "show_server_selection"
        private const val PREFS_NAME = "codex_workbench"
        private const val PREF_SERVER_URL = "server_url"
        private const val PREF_WORKBENCH_ID = "workbench_id"
        private const val PREF_USE_TAILSCALE = "use_tailscale"
        private const val PREF_CONNECTION_MODE = "connection_mode"
        private const val PREF_QUICK_TUNNEL_ROOT = "quick_tunnel_root"
        private const val PREF_WEB_TEXT_ZOOM = "web_text_zoom"
        private const val PREF_NOTIFICATIONS_ENABLED = "notifications_enabled"
        private const val PREF_LAST_CRASH = "last_crash"
        private const val FILE_CHOOSER_REQUEST_CODE = 7001
        private const val NOTIFICATION_PERMISSION_REQUEST_CODE = 7002
        private const val AUDIO_PERMISSION_REQUEST_CODE = 7003
        private const val SPLASH_DURATION_MS = 900L
        private const val DEFAULT_WEB_TEXT_ZOOM_PERCENT = 100
        private const val MIN_WEB_TEXT_ZOOM_PERCENT = 60
        private const val MAX_WEB_TEXT_ZOOM_PERCENT = 125
        private const val WEB_TEXT_ZOOM_STEP_PERCENT = 5
        private val USER_AGENT_SUFFIX = "CodexWorkbenchAndroid/${BuildConfig.VERSION_NAME}"

        private val COLOR_CANVAS = Color.rgb(247, 249, 252)
        private val COLOR_SURFACE = Color.WHITE
        private val COLOR_INK = Color.rgb(20, 34, 54)
        private val COLOR_MUTED = Color.rgb(91, 106, 128)
        private val COLOR_BORDER = Color.rgb(221, 227, 236)
        private val COLOR_PRIMARY = Color.rgb(35, 104, 196)
        private val COLOR_PRIMARY_SOFT = Color.rgb(237, 245, 255)
    }

    private lateinit var root: FrameLayout
    private var webView: WebView? = null
    private var connectionStatus: TextView? = null
    private var connectionFailed = false
    private val networkCallback = object : android.net.ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: android.net.Network) {
            runOnUiThread {
                if (connectionFailed && isVisible) webView?.reload()
            }
        }
    }
    private var pendingSession: String? = null
    private var pendingAudioRequest: PermissionRequest? = null
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var currentTarget: WorkbenchTarget? = null
    private var currentConnectionMode = ConnectionMode.QUICK_TUNNEL
    private var serverBaseUrl = ""
    private var splashTransition: Runnable? = null
    private var settingsOverlay: View? = null
    private var suppressNextPauseMonitor = false
    private var previousUncaughtHandler: Thread.UncaughtExceptionHandler? = null
    private var downloadController: WebViewDownloadController? = null

    private val prefs by lazy { getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33) {
            onBackInvokedDispatcher.registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT
            ) { navigateBack() }
        }

        root = FrameLayout(this).apply { setBackgroundColor(COLOR_CANVAS) }
        setContentView(root)
        installCrashRecorder()

        try {
            (getSystemService(Context.CONNECTIVITY_SERVICE) as android.net.ConnectivityManager)
                .registerDefaultNetworkCallback(networkCallback)
            configureSystemBars()
            applySystemBarInsets()

            val priorCrash = prefs.getString(PREF_LAST_CRASH, null)
            if (!priorCrash.isNullOrBlank()) {
                prefs.edit().remove(PREF_LAST_CRASH).apply()
                showRecoveryScreen(
                    title = "이전 실행에서 오류가 감지되었습니다",
                    detail = priorCrash,
                )
                return
            }

            if (prefs.getString(PREF_QUICK_TUNNEL_ROOT, "")?.contains("painted-slideshow-hampshire-main.trycloudflare.com") == true) {
                prefs.edit().remove(PREF_QUICK_TUNNEL_ROOT).apply()
            }
            val legacyUrl = prefs.getString(PREF_SERVER_URL, null)
            if (!prefs.contains(PREF_CONNECTION_MODE)) {
                val migratedMode = WorkbenchCatalog.modeForUrl(legacyUrl)
                    ?: if (prefs.getBoolean(PREF_USE_TAILSCALE, false)) {
                        ConnectionMode.TAILSCALE
                    } else {
                        ConnectionMode.QUICK_TUNNEL
                    }
                prefs.edit()
                    .putString(PREF_CONNECTION_MODE, migratedMode.name)
                    .putBoolean(PREF_USE_TAILSCALE, migratedMode == ConnectionMode.TAILSCALE)
                    .apply()
            }
            val savedId = prefs.getString(PREF_WORKBENCH_ID, null)
                ?: WorkbenchCatalog.byUrl(legacyUrl)?.id
                ?: WorkbenchCatalog.DEFAULT_ID
            if (openNotification(intent)) return
            val restoreId = savedInstanceState?.getString("connected_target")
            if (restoreId != null) {
                val target = WorkbenchCatalog.byId(restoreId)
                val mode = storedConnectionMode()
                showWorkbench(target, mode, resolvedTargetUrl(target, mode))
            } else showConnectionScreen(savedId)
        } catch (error: Throwable) {
            recordCrash(error)
            showRecoveryScreen("앱 초기화 오류", formatError(error))
        }
    }

    private fun openNotification(source: Intent?): Boolean {
        val base = source?.getStringExtra(EXTRA_OPEN_BASE) ?: return false
        val target = WorkbenchCatalog.byUrl(base) ?: return false
        if (!target.isCodexWorkbench || !WorkbenchCatalog.isAllowedPage(base, quickTunnelRoot())) return false
        pendingSession = source.getStringExtra(EXTRA_OPEN_SESSION)
        source.removeExtra(EXTRA_OPEN_BASE)
        source.removeExtra(EXTRA_OPEN_SESSION)
        showWorkbench(target, WorkbenchCatalog.modeForUrl(base) ?: storedConnectionMode(), base)
        return true
    }

    override fun onSaveInstanceState(outState: Bundle) {
        currentTarget?.let { outState.putString("connected_target", it.id) }
        super.onSaveInstanceState(outState)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (openNotification(intent)) return
        if (intent?.getBooleanExtra(EXTRA_SHOW_SERVER_SELECTION, false) != true) return
        intent.removeExtra(EXTRA_SHOW_SERVER_SELECTION)
        val savedId = prefs.getString(PREF_WORKBENCH_ID, null) ?: WorkbenchCatalog.DEFAULT_ID
        runCatching { showConnectionScreen(savedId) }
            .onFailure {
                recordCrash(it)
                showRecoveryScreen("연결 화면 오류", formatError(it))
            }
    }

    override fun onResume() {
        super.onResume()
        isVisible = true
        suppressNextPauseMonitor = false
        webView?.onResume()
        webView?.evaluateJavascript("document.dispatchEvent(new Event('visibilitychange'));", null)
    }

    override fun onPause() {
        isVisible = false
        if (!suppressNextPauseMonitor) {
            runCatching { startBackgroundCompletionMonitorIfNeeded() }
                .onFailure { recordCrash(it) }
        }
        suppressNextPauseMonitor = false
        super.onPause()
    }

    override fun onDestroy() {
        splashTransition?.let { runnable ->
            if (::root.isInitialized) root.removeCallbacks(runnable)
        }
        splashTransition = null
        settingsOverlay = null
        runCatching { fileChooserCallback?.onReceiveValue(null) }
        fileChooserCallback = null
        runCatching { destroyWebView() }
        if (Thread.getDefaultUncaughtExceptionHandler() === crashHandler) {
            Thread.setDefaultUncaughtExceptionHandler(previousUncaughtHandler)
        }
        runCatching {
            (getSystemService(Context.CONNECTIVITY_SERVICE) as android.net.ConnectivityManager)
                .unregisterNetworkCallback(networkCallback)
        }
        super.onDestroy()
    }

    private val crashHandler = Thread.UncaughtExceptionHandler { thread, throwable ->
        recordCrash(throwable)
        previousUncaughtHandler?.uncaughtException(thread, throwable)
    }

    private fun installCrashRecorder() {
        previousUncaughtHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler(crashHandler)
    }

    private fun recordCrash(error: Throwable) {
        runCatching {
            prefs.edit().putString(PREF_LAST_CRASH, formatError(error)).commit()
        }
    }

    private fun formatError(error: Throwable): String {
        val className = error.javaClass.simpleName.ifBlank { error.javaClass.name }
        val message = error.message?.take(500).orEmpty()
        val firstAppFrame = error.stackTrace.firstOrNull {
            it.className.startsWith("com.yjkim9670.codexworkbench")
        }
        return buildString {
            append(className)
            if (message.isNotBlank()) append(": ").append(message)
            if (firstAppFrame != null) {
                append("\n")
                append(firstAppFrame.className.substringAfterLast('.'))
                append(".").append(firstAppFrame.methodName)
                append(":").append(firstAppFrame.lineNumber)
            }
        }
    }

    private fun showRecoveryScreen(title: String, detail: String) {
        if (!::root.isInitialized) return
        runCatching {
            root.removeAllViews()
            root.setBackgroundColor(COLOR_CANVAS)

            val scroll = ScrollView(this).apply { isFillViewport = true }
            val panel = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER_HORIZONTAL
                setPadding(dp(24), dp(40), dp(24), dp(40))
            }

            val mark = TextView(this).apply {
                text = "CW"
                textSize = 24f
                setTextColor(Color.WHITE)
                gravity = Gravity.CENTER
                typeface = Typeface.DEFAULT_BOLD
                background = roundedDrawable(COLOR_PRIMARY, dp(24).toFloat())
            }
            panel.addView(mark, LinearLayout.LayoutParams(dp(72), dp(72)).apply {
                bottomMargin = dp(22)
            })

            panel.addView(simpleText(title, 21f, COLOR_INK, true, Gravity.CENTER), matchWrap().apply {
                bottomMargin = dp(10)
            })
            panel.addView(
                simpleText(
                    "앱이 종료되지 않도록 복구 모드로 전환했습니다.\n아래 오류 정보만 확인하면 ADB 없이도 원인을 좁힐 수 있습니다.",
                    13.5f,
                    COLOR_MUTED,
                    false,
                    Gravity.CENTER,
                ),
                matchWrap().apply { bottomMargin = dp(20) },
            )

            val errorBox = simpleText(detail.ifBlank { "원인 정보 없음" }, 12.5f, COLOR_INK, false).apply {
                setPadding(dp(14), dp(14), dp(14), dp(14))
                setTextIsSelectable(true)
                background = roundedDrawable(Color.WHITE, dp(14).toFloat(), COLOR_BORDER, 1)
            }
            panel.addView(errorBox, matchWrap().apply { bottomMargin = dp(16) })

            val retry = simpleButton("기본 설정으로 다시 시작", true)
            val reset = simpleButton("저장된 앱 설정 초기화", false)
            panel.addView(retry, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)).apply {
                bottomMargin = dp(10)
            })
            panel.addView(reset, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50)))

            retry.setOnClickListener {
                prefs.edit().remove(PREF_LAST_CRASH).apply()
                runCatching { showConnectionScreen(WorkbenchCatalog.DEFAULT_ID) }
                    .onFailure { showRecoveryScreen("연결 화면 오류", formatError(it)) }
            }
            reset.setOnClickListener {
                prefs.edit().clear().apply()
                runCatching { recreate() }
                    .onFailure { showRecoveryScreen("재시작 오류", formatError(it)) }
            }

            scroll.addView(panel, FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ))
            root.addView(scroll, fillFrame())
        }.onFailure {
            root.removeAllViews()
            root.addView(TextView(this).apply {
                text = "코덱스 워크벤치 복구 모드\n\n${formatError(it)}"
                textSize = 16f
                setTextColor(Color.BLACK)
                setBackgroundColor(Color.WHITE)
                setPadding(32, 64, 32, 32)
            }, fillFrame())
        }
    }

    private fun configureSystemBars() {
        val background = COLOR_CANVAS
        @Suppress("DEPRECATION")
        run {
            window.statusBarColor = background
            window.navigationBarColor = background
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
            window.insetsController?.setSystemBarsAppearance(mask, mask)
        } else {
            @Suppress("DEPRECATION")
            run {
                window.decorView.systemUiVisibility =
                    View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
            }
        }
    }

    private fun applySystemBarInsets() {
        root.setOnApplyWindowInsetsListener { _, windowInsets ->
            val left: Int
            val top: Int
            val right: Int
            val bottom: Int
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val insets = windowInsets.getInsets(
                    WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout() or WindowInsets.Type.ime(),
                )
                left = insets.left
                top = insets.top
                right = insets.right
                bottom = insets.bottom
            } else {
                @Suppress("DEPRECATION")
                run {
                    left = windowInsets.systemWindowInsetLeft
                    top = windowInsets.systemWindowInsetTop
                    right = windowInsets.systemWindowInsetRight
                    bottom = windowInsets.systemWindowInsetBottom
                }
            }
            root.setPadding(left, top, right, bottom)
            windowInsets
        }
        root.requestApplyInsets()
    }

    private fun showOpeningScreen(nextWorkbenchId: String) {
        destroyWebView()
        root.removeAllViews()
        root.setBackgroundColor(Color.rgb(7, 26, 53))
        currentTarget = null
        currentConnectionMode = ConnectionMode.QUICK_TUNNEL
        serverBaseUrl = ""

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(28), dp(28), dp(28), dp(28))
        }

        val icon = ImageView(this).apply {
            adjustViewBounds = true
            scaleType = ImageView.ScaleType.FIT_CENTER
            contentDescription = "코덱스 워크벤치 아이콘"
        }
        runCatching { icon.setImageResource(R.drawable.ic_workbench_foreground) }
        content.addView(icon, LinearLayout.LayoutParams(dp(196), dp(196)).apply {
            bottomMargin = dp(14)
        })
        content.addView(simpleText("코덱스 워크벤치", 28f, Color.WHITE, true, Gravity.CENTER), matchWrap())
        content.addView(
            simpleText("Workspace · Git · Terminal", 13f, Color.rgb(184, 226, 237), false, Gravity.CENTER),
            matchWrap().apply { topMargin = dp(8) },
        )
        root.addView(content, fillFrame())

        splashTransition?.let(root::removeCallbacks)
        splashTransition = Runnable {
            if (isFinishing || isDestroyed) return@Runnable
            runCatching { showConnectionScreen(nextWorkbenchId) }
                .onFailure {
                    recordCrash(it)
                    showRecoveryScreen("연결 화면 초기화 오류", formatError(it))
                }
        }.also { root.postDelayed(it, SPLASH_DURATION_MS) }
    }

    private fun storedConnectionMode(): ConnectionMode =
        ConnectionMode.fromPreference(prefs.getString(PREF_CONNECTION_MODE, null))
            ?: if (prefs.getBoolean(PREF_USE_TAILSCALE, false)) {
                ConnectionMode.TAILSCALE
            } else {
                ConnectionMode.QUICK_TUNNEL
            }

    private fun persistConnectionMode(mode: ConnectionMode) {
        prefs.edit()
            .putString(PREF_CONNECTION_MODE, mode.name)
            .putBoolean(PREF_USE_TAILSCALE, mode == ConnectionMode.TAILSCALE)
            .apply()
    }

    private fun quickTunnelRoot(): String =
        WorkbenchCatalog.normalizeQuickTunnelRoot(prefs.getString(PREF_QUICK_TUNNEL_ROOT, null))
            ?: WorkbenchCatalog.QUICK_TUNNEL_ROOT

    private fun resolvedTargetUrl(target: WorkbenchTarget, mode: ConnectionMode): String =
        if (mode == ConnectionMode.QUICK_TUNNEL) {
            target.quickTunnelUrl(quickTunnelRoot())
        } else {
            target.urlFor(mode)
        }

    private fun persistQuickTunnelRoot(normalizedRoot: String?): String {
        val effectiveRoot = normalizedRoot ?: WorkbenchCatalog.QUICK_TUNNEL_ROOT
        val editor = prefs.edit()
        if (normalizedRoot == null) {
            editor.remove(PREF_QUICK_TUNNEL_ROOT)
        } else {
            editor.putString(PREF_QUICK_TUNNEL_ROOT, effectiveRoot)
        }
        if (storedConnectionMode() == ConnectionMode.QUICK_TUNNEL) {
            val savedTarget = WorkbenchCatalog.byId(
                prefs.getString(PREF_WORKBENCH_ID, null) ?: WorkbenchCatalog.DEFAULT_ID,
            )
            editor.putString(PREF_SERVER_URL, savedTarget.quickTunnelUrl(effectiveRoot))
        }
        editor.apply()
        return effectiveRoot
    }

    private fun showConnectionScreen(initialWorkbenchId: String) {
        splashTransition?.let(root::removeCallbacks)
        splashTransition = null
        closeSettingsOverlay()
        destroyWebView()
        root.removeAllViews()
        root.setBackgroundColor(COLOR_CANVAS)
        currentTarget = null
        connectionStatus = null
        TaskNotificationService.stop(this)
        serverBaseUrl = ""

        val scroll = ScrollView(this).apply {
            isFillViewport = true
            setBackgroundColor(COLOR_CANVAS)
        }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val side = if (resources.configuration.screenWidthDp >= 840) 80 else 16
            setPadding(dp(side), dp(20), dp(side), dp(24))
        }

        panel.addView(simpleText("코덱스 워크벤치", 26f, COLOR_INK, true, Gravity.CENTER), matchWrap())
        panel.addView(
            simpleText("접속할 서비스와 네트워크 방식을 선택하세요.", 13.5f, COLOR_MUTED, false, Gravity.CENTER),
            matchWrap().apply { topMargin = dp(6); bottomMargin = dp(16) },
        )

        val chatMode = prefs.getBoolean("chat_mode", false)
        val applicationModes = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        listOf(false to "작업", true to "채팅").forEach { (chat, label) ->
            val button = simpleButton(label, chat == chatMode)
            applicationModes.addView(button, LinearLayout.LayoutParams(0, dp(48), 1f))
            button.setOnClickListener {
                prefs.edit().putBoolean("chat_mode", chat).apply()
                showConnectionScreen(if (chat) "conversation" else WorkbenchCatalog.DEFAULT_ID)
            }
        }
        panel.addView(applicationModes, matchWrap().apply { bottomMargin = dp(14) })
        var selectedId = if (chatMode) "conversation" else WorkbenchCatalog.byId(initialWorkbenchId).let {
            if (it.isCodexWorkbench) it.id else WorkbenchCatalog.DEFAULT_ID
        }
        var selectedConnectionMode = storedConnectionMode()
        val cards = linkedMapOf<String, TextView>()
        val modeButtons = linkedMapOf<ConnectionMode, TextView>()

        fun connectionSummary(): String = when (selectedConnectionMode) {
            ConnectionMode.TAILSCALE ->
                "내부 Tailscale · ${WorkbenchCatalog.TAILSCALE_HOST}:3000~3004 · Dashboard :18000"
            ConnectionMode.QUICK_TUNNEL ->
                "Cloudflare Quick Tunnel · ${quickTunnelRoot()}"
        }

        fun cardLabel(target: WorkbenchTarget): String = buildString {
            append(target.name.removeSuffix(" Codex Workbench"))
            append("\n")
            when (selectedConnectionMode) {
                ConnectionMode.TAILSCALE -> append("Tailscale · ${target.tailscaleUrl}")
                ConnectionMode.QUICK_TUNNEL ->
                    append("Quick Tunnel · ${target.quickTunnelUrl(quickTunnelRoot())}")
            }
        }

        val modeRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(5), dp(5), dp(5), dp(5))
            background = roundedDrawable(Color.WHITE, dp(15).toFloat(), COLOR_BORDER, 1)
        }
        listOf(
            ConnectionMode.TAILSCALE to "Tailscale",
            ConnectionMode.QUICK_TUNNEL to "Cloudflare",
        ).forEach { (mode, label) ->
            val button = simpleText(label, 12.5f, COLOR_INK, true, Gravity.CENTER).apply {
                isClickable = true
                isFocusable = true
                setPadding(dp(6), dp(10), dp(6), dp(10))
            }
            modeButtons[mode] = button
            modeRow.addView(button, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                if (mode != ConnectionMode.TAILSCALE) leftMargin = dp(4)
            })
        }
        panel.addView(modeRow, matchWrap().apply { bottomMargin = dp(6) })

        val modeSummary = simpleText(connectionSummary(), 12f, COLOR_MUTED, false).apply {
            setPadding(dp(4), 0, dp(4), 0)
        }
        panel.addView(modeSummary, matchWrap().apply { bottomMargin = dp(14) })

        fun refreshModeButtons() {
            modeButtons.forEach { (mode, view) ->
                val selected = mode == selectedConnectionMode
                view.background = roundedDrawable(
                    if (selected) COLOR_PRIMARY_SOFT else Color.WHITE,
                    dp(11).toFloat(),
                    if (selected) COLOR_PRIMARY else COLOR_BORDER,
                    if (selected) 2 else 1,
                )
                view.setTextColor(if (selected) COLOR_PRIMARY else COLOR_INK)
            }
        }

        fun refreshCards() {
            modeSummary.text = connectionSummary()
            cards.forEach { (id, view) ->
                val selected = id == selectedId
                view.text = cardLabel(WorkbenchCatalog.byId(id))
                view.background = roundedDrawable(
                    if (selected) COLOR_PRIMARY_SOFT else COLOR_SURFACE,
                    dp(15).toFloat(),
                    if (selected) COLOR_PRIMARY else COLOR_BORDER,
                    if (selected) 2 else 1,
                )
                view.setTextColor(if (selected) COLOR_PRIMARY else COLOR_INK)
            }
        }

        modeButtons.forEach { (mode, view) ->
            view.setOnClickListener {
                selectedConnectionMode = mode
                persistConnectionMode(mode)
                refreshModeButtons()
                refreshCards()
            }
        }

        fun connectToTarget(target: WorkbenchTarget) {
            val mode = selectedConnectionMode
            val resolvedUrl = resolvedTargetUrl(target, mode)
            prefs.edit()
                .putString(PREF_WORKBENCH_ID, target.id)
                .putString(PREF_CONNECTION_MODE, mode.name)
                .putBoolean(PREF_USE_TAILSCALE, mode == ConnectionMode.TAILSCALE)
                .putString(PREF_SERVER_URL, resolvedUrl)
                .apply()

            suppressNextPauseMonitor = true
            if (target.isCodexWorkbench) {
                runCatching { requestNotificationPermissionIfNeeded() }
            }
            runCatching { showWorkbench(target, mode, resolvedUrl) }
                .onFailure {
                    recordCrash(it)
                    showRecoveryScreen("WebView 시작 오류", formatError(it))
                }
        }

        fun addTargetCard(target: WorkbenchTarget) {
            val card = simpleText(cardLabel(target), 14f, COLOR_INK, true).apply {
                setPadding(dp(16), dp(13), dp(16), dp(13))
                isClickable = true
                isFocusable = true
                setLineSpacing(dp(3).toFloat(), 1f)
                setOnClickListener {
                    if (target.isCodexWorkbench || target.isConversation) {
                        selectedId = target.id
                        refreshCards()
                    } else {
                        connectToTarget(target)
                    }
                }
            }
            cards[target.id] = card
            panel.addView(card, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(9) })
        }

        panel.addView(
            simpleText("시스템 대시보드", 12.5f, COLOR_MUTED, true),
            matchWrap().apply { bottomMargin = dp(7) },
        )
        WorkbenchCatalog.targets
            .filter { !it.isCodexWorkbench && !it.isConversation }
            .forEach { addTargetCard(it) }

        panel.addView(
            simpleText(if (chatMode) "Workbench Chat" else "Codex Workbench", 12.5f, COLOR_MUTED, true),
            matchWrap().apply { topMargin = dp(8); bottomMargin = dp(7) },
        )
        WorkbenchCatalog.targets
            .filter { if (chatMode) it.isConversation else it.isCodexWorkbench }
            .forEach { addTargetCard(it) }
        refreshModeButtons()
        refreshCards()

        val connect = simpleButton("선택한 서비스 접속", true)
        val settings = simpleButton("앱 설정", false)
        panel.addView(connect, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(54)).apply {
            topMargin = dp(10)
            bottomMargin = dp(10)
        })
        panel.addView(settings, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50)))

        connect.setOnClickListener {
            connectToTarget(WorkbenchCatalog.byId(selectedId))
        }
        settings.setOnClickListener {
            runCatching { showSettingsOverlay() }
                .onFailure { showRecoveryScreen("설정 화면 오류", formatError(it)) }
        }

        scroll.addView(panel, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        ))
        root.addView(scroll, fillFrame())
        prefs.edit().remove(PREF_LAST_CRASH).apply()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun showWorkbench(target: WorkbenchTarget, mode: ConnectionMode, resolvedUrl: String) {
        closeSettingsOverlay()
        TaskNotificationService.stop(this)
        destroyWebView()
        root.removeAllViews()
        root.setBackgroundColor(Color.WHITE)
        currentTarget = target
        currentConnectionMode = mode
        serverBaseUrl = resolvedUrl

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.WHITE)
        }
        val toolbar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(5), dp(8), dp(5))
            setBackgroundColor(COLOR_CANVAS)
        }
        val title = simpleText(
            buildString {
                append(target.name.removeSuffix(" Codex Workbench"))
                append(
                    when (mode) {
                        ConnectionMode.TAILSCALE -> " · Tailscale"
                        ConnectionMode.QUICK_TUNNEL -> " · Quick Tunnel"
                    },
                )
            },
            13f,
            COLOR_INK,
            true,
        ).apply {
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
        }
        toolbar.addView(title, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))

        val reload = toolbarButton("↻")
        val server = toolbarButton("서버")
        val settings = toolbarButton("설정")
        toolbar.addView(reload, LinearLayout.LayoutParams(dp(42), dp(38)).apply { leftMargin = dp(4) })
        toolbar.addView(server, LinearLayout.LayoutParams(dp(54), dp(38)).apply { leftMargin = dp(4) })
        toolbar.addView(settings, LinearLayout.LayoutParams(dp(54), dp(38)).apply { leftMargin = dp(4) })
        container.addView(toolbar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50)))
        val status = simpleText("연결 중…", 12f, COLOR_MUTED, false).apply {
            setPadding(dp(12), dp(8), dp(12), dp(8))
            minHeight = dp(44)
            setOnClickListener { webView?.reload() }
        }
        connectionStatus = status
        connectionFailed = false
        container.addView(status, matchWrap())

        runCatching { WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG) }

        val browser = WebView(this)
        webView = browser
        browser.setBackgroundColor(Color.WHITE)
        browser.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = true
            javaScriptCanOpenWindowsAutomatically = !target.isCodexWorkbench
            setSupportMultipleWindows(!target.isCodexWorkbench)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            mediaPlaybackRequiresUserGesture = true
            builtInZoomControls = false
            displayZoomControls = false
            loadWithOverviewMode = false
            useWideViewPort = true
            cacheMode = WebSettings.LOAD_DEFAULT
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) safeBrowsingEnabled = true
            textZoom = webTextZoomPercent()
            userAgentString = "${userAgentString} $USER_AGENT_SUFFIX"
        }

        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(browser, false)
        }

        browser.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val uri = request?.url ?: return false
                val scheme = uri.scheme?.lowercase().orEmpty()
                if (scheme == "blob" || scheme == "data" || scheme == WebViewDownloadController.BRIDGE_SCHEME) {
                    if (!request.isForMainFrame) return true
                    return downloadController?.handleNavigation(uri) ?: true
                }
                if (scheme == "http" || scheme == "https") {
                    if (isSameServerOrigin(uri)) return false
                    return openExternal(uri)
                }
                if (scheme == "mailto" || scheme == "tel") return openExternal(uri)
                return true
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                super.onPageStarted(view, url, favicon)
                pendingAudioRequest?.deny()
                pendingAudioRequest = null
                connectionFailed = false
                connectionStatus?.text = "연결 중…"
                connectionStatus?.visibility = View.VISIBLE
            }

            override fun onReceivedHttpError(view: WebView?, request: WebResourceRequest?, response: android.webkit.WebResourceResponse?) {
                if (request?.isForMainFrame != true) return
                connectionFailed = true
                connectionStatus?.visibility = View.VISIBLE
                connectionStatus?.text = when (response?.statusCode) {
                    401, 403 -> "인증이 필요하거나 만료되었습니다. 로그인 후 다시 시도하세요. · 탭하여 재시도"
                    502, 503, 504 -> "서버가 응답하지 않습니다. 터널 주소와 서버 상태를 확인하세요. · 탭하여 재시도"
                    else -> "서버 오류 ${response?.statusCode} · 탭하여 재시도"
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                if (!WorkbenchCatalog.isAllowedPage(url, quickTunnelRoot())) return
                if (!connectionFailed) connectionStatus?.visibility = View.GONE
                startBackgroundCompletionMonitorIfNeeded()
                runCatching { downloadController?.installInterceptor() }
                if (target.isCodexWorkbench) {
                    runCatching { removeDuplicatedPromptSafeArea(view) }
                    runCatching { enableWorkModeByDefault(view) }
                }
                if (target.isCodexWorkbench || target.isConversation) {
                    applyReadingPreferences(view)
                }
            }

            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame != true) return
                val message = when (currentConnectionMode) {
                    ConnectionMode.TAILSCALE ->
                        "Tailscale 연결 오류: ${error?.description ?: "unknown error"}\nTailscale 앱의 연결 상태를 확인하거나 Cloudflare 모드로 전환하세요."
                    ConnectionMode.QUICK_TUNNEL ->
                        "Quick Tunnel 연결 오류: ${error?.description ?: "unknown error"}"
                }
                connectionFailed = true
                connectionStatus?.visibility = View.VISIBLE
                connectionStatus?.text = "$message · 탭하여 재시도"
            }

            override fun onRenderProcessGone(view: WebView?, detail: android.webkit.RenderProcessGoneDetail?): Boolean {
                downloadController?.close()
                downloadController = null
                (view?.parent as? ViewGroup)?.removeView(view)
                if (webView === view) webView = null
                view?.destroy()
                showRecoveryScreen("웹 화면이 종료되었습니다", "다시 연결하면 저장된 대화와 초안을 복원합니다.")
                return true
            }

            override fun onReceivedHttpAuthRequest(
                view: WebView?,
                handler: HttpAuthHandler?,
                host: String?,
                realm: String?,
            ) {
                handler?.cancel()
            }
        }

        browser.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                runOnUiThread {
                    val origin = request.origin
                    val safe = origin.scheme.equals("https", true) && isSameServerOrigin(origin) &&
                        request.resources.contentEquals(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) &&
                        webView?.url?.let { isSameServerOrigin(Uri.parse(it)) } == true
                    if (!safe || pendingAudioRequest != null) {
                        request.deny()
                    } else if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                    } else {
                        pendingAudioRequest = request
                        requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), AUDIO_PERMISSION_REQUEST_CODE)
                    }
                }
            }

            override fun onPermissionRequestCanceled(request: PermissionRequest) {
                if (pendingAudioRequest === request) pendingAudioRequest = null
            }

            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: Message?,
            ): Boolean {
                if (target.isCodexWorkbench) return false
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false
                var handled = false
                val popup = WebView(this@MainActivity)
                popup.settings.apply {
                    javaScriptEnabled = true
                    domStorageEnabled = true
                    allowFileAccess = false
                    allowContentAccess = true
                }

                fun openCapturedUrl(uri: Uri): Boolean {
                    if (handled) return true
                    val scheme = uri.scheme?.lowercase().orEmpty()
                    handled = true
                    when (scheme) {
                        "http", "https" -> {
                            if (!WorkbenchCatalog.isAllowedPage(uri.toString(), quickTunnelRoot())) {
                                openExternal(uri)
                                popup.post { popup.destroy() }
                                return true
                            }
                            suppressNextPauseMonitor = true
                            runCatching {
                                startActivity(
                                    DashboardBrowserActivity.createIntent(
                                        this@MainActivity,
                                        uri.toString(),
                                    ),
                                )
                            }.onFailure {
                                Toast.makeText(
                                    this@MainActivity,
                                    "앱 내부 새 창을 열 수 없습니다.",
                                    Toast.LENGTH_LONG,
                                ).show()
                            }
                        }
                        "mailto", "tel" -> openExternal(uri)
                    }
                    popup.post { runCatching { popup.destroy() } }
                    return true
                }

                popup.webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(
                        view: WebView?,
                        request: WebResourceRequest?,
                    ): Boolean {
                        val uri = request?.url ?: return true
                        return openCapturedUrl(uri)
                    }

                    override fun onPageFinished(view: WebView?, url: String?) {
                        super.onPageFinished(view, url)
                        if (handled || url.isNullOrBlank() || url == "about:blank") return
                        runCatching { Uri.parse(url) }
                            .getOrNull()
                            ?.let { openCapturedUrl(it) }
                    }
                }
                transport.webView = popup
                resultMsg.sendToTarget()
                return true
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?,
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback
                val intent = runCatching { fileChooserParams?.createIntent() }.getOrNull()
                    ?: Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "*/*"
                    }
                return try {
                    suppressNextPauseMonitor = true
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST_CODE)
                    true
                } catch (_: Exception) {
                    suppressNextPauseMonitor = false
                    fileChooserCallback?.onReceiveValue(null)
                    fileChooserCallback = null
                    Toast.makeText(this@MainActivity, "파일 선택기를 열 수 없습니다.", Toast.LENGTH_LONG).show()
                    false
                }
            }
        }

        val downloads = WebViewDownloadController(this, browser, serverBaseUrl)
        downloadController = downloads
        runCatching { downloads.install() }
            .onFailure {
                Toast.makeText(
                    this,
                    "다운로드 기능 초기화 실패: ${it.message ?: it.javaClass.simpleName}",
                    Toast.LENGTH_LONG,
                ).show()
            }

        container.addView(browser, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        reload.setOnClickListener { runCatching { browser.reload() } }
        server.setOnClickListener { runCatching { showConnectionScreen(target.id) } }
        settings.setOnClickListener { runCatching { showSettingsOverlay() } }
        root.addView(container, fillFrame())
        val session = pendingSession
        pendingSession = null
        browser.loadUrl(if (session.isNullOrBlank()) serverBaseUrl else Uri.parse(serverBaseUrl).buildUpon()
            .appendQueryParameter("session", session).build().toString())
    }

    private fun removeDuplicatedPromptSafeArea(browser: WebView?) {
        val script = """
            (() => {
                const styleId = 'codex-android-prompt-safe-area-fix';
                let style = document.getElementById(styleId);
                if (!style) {
                    style = document.createElement('style');
                    style.id = styleId;
                    (document.head || document.documentElement).appendChild(style);
                }
                style.textContent = `
                    @media (max-width: 840px) {
                        .chat-input {
                            padding-bottom: 0 !important;
                        }
                    }
                `;
            })();
        """.trimIndent()
        browser?.evaluateJavascript(script, null)
    }

    private fun applyReadingPreferences(browser: WebView?) {
        if (browser == null || !WorkbenchCatalog.isAllowedPage(browser.url, quickTunnelRoot())) return
        val lineHeight = prefs.getInt("reading_line_height", 180).coerceIn(150, 220) / 100.0
        val font = prefs.getString("reading_font", "page").orEmpty()
        browser.evaluateJavascript("""
            (() => {
              let style = document.getElementById('android-reading-preferences');
              if (!style) { style = document.createElement('style'); style.id = 'android-reading-preferences'; document.head.append(style); }
              style.textContent = '.answer-body,.message-bubble,.message-content,.markdown-body {line-height:$lineHeight!important; overflow-wrap:anywhere} pre {max-width:100%;overflow-x:auto} textarea {max-width:100%}';
              const font = ${org.json.JSONObject.quote(font)};
              if (font !== 'page') document.documentElement.dataset.uiFont = font;
              if (font === 'system') style.textContent += 'body,textarea,button,input,select {font-family:system-ui,sans-serif!important}';
            })();
        """.trimIndent(), null)
    }

    private fun enableWorkModeByDefault(browser: WebView?) {
        val script = """
            (() => {
                let attempts = 0;
                const openWorkMode = () => {
                    const button = document.getElementById('codex-work-mode-toggle');
                    if (button) {
                        if (button.getAttribute('aria-pressed') !== 'true') button.click();
                        return;
                    }
                    attempts += 1;
                    if (attempts < 24) window.setTimeout(openWorkMode, 250);
                };
                openWorkMode();
            })();
        """.trimIndent()
        browser?.evaluateJavascript(script, null)
    }

    private fun showSettingsOverlay() {
        if (settingsOverlay != null) return

        val overlay = FrameLayout(this).apply {
            setBackgroundColor(COLOR_CANVAS)
            elevation = dp(10).toFloat()
        }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val side = if (resources.configuration.screenWidthDp >= 840) 80 else 16
            setPadding(dp(side), dp(20), dp(side), dp(24))
        }
        panel.addView(simpleText("설정", 25f, COLOR_INK, true), matchWrap().apply { bottomMargin = dp(16) })

        val displayCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(15), dp(16), dp(15))
            background = roundedDrawable(Color.WHITE, dp(15).toFloat(), COLOR_BORDER, 1)
        }
        displayCard.addView(simpleText("화면", 14f, COLOR_INK, true), matchWrap().apply {
            bottomMargin = dp(5)
        })
        val scaleValue = simpleText(
            "Workbench 본문 글자 크기 ${webTextZoomPercent()}%",
            13.5f,
            COLOR_INK,
            true,
        )
        displayCard.addView(scaleValue, matchWrap().apply { bottomMargin = dp(2) })
        displayCard.addView(
            simpleText(
                "60~125% · 5% 단위 · 접속 시 작업모드 기본 활성화",
                12f,
                COLOR_MUTED,
                false,
            ),
            matchWrap().apply { bottomMargin = dp(6) },
        )

        val scaleSeek = SeekBar(this).apply {
            max = (MAX_WEB_TEXT_ZOOM_PERCENT - MIN_WEB_TEXT_ZOOM_PERCENT) / WEB_TEXT_ZOOM_STEP_PERCENT
            progress = (webTextZoomPercent() - MIN_WEB_TEXT_ZOOM_PERCENT) / WEB_TEXT_ZOOM_STEP_PERCENT
        }
        displayCard.addView(scaleSeek, matchWrap().apply { bottomMargin = dp(6) })

        val resetScale = simpleButton("100%로 초기화", false)
        displayCard.addView(resetScale, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(44)))
        val readingFont = simpleButton("글꼴: " + prefs.getString("reading_font", "page"), false)
        displayCard.addView(readingFont, matchWrap().apply { topMargin = dp(10) })
        readingFont.setOnClickListener {
            val names = arrayOf("페이지 설정 사용", "IBM Plex Sans KR", "SUIT", "시스템 글꼴")
            val values = arrayOf("page", "ibm-plex", "suit", "system")
            android.app.AlertDialog.Builder(this).setTitle("본문 글꼴")
                .setItems(names) { _, index ->
                    prefs.edit().putString("reading_font", values[index]).apply()
                    readingFont.text = "글꼴: ${names[index]}"
                    if (values[index] == "page") webView?.reload() else applyReadingPreferences(webView)
                }.show()
        }
        val spacing = simpleText("줄간격 ${prefs.getInt("reading_line_height", 180)}%", 13f, COLOR_INK, false)
        displayCard.addView(spacing, matchWrap().apply { topMargin = dp(12) })
        displayCard.addView(SeekBar(this).apply {
            max = 7
            progress = (prefs.getInt("reading_line_height", 180) - 150) / 10
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(bar: SeekBar?, value: Int, fromUser: Boolean) {
                    val height = 150 + value * 10
                    prefs.edit().putInt("reading_line_height", height).apply()
                    spacing.text = "줄간격 $height%"
                    applyReadingPreferences(webView)
                }
                override fun onStartTrackingTouch(bar: SeekBar?) = Unit
                override fun onStopTrackingTouch(bar: SeekBar?) = Unit
            })
        }, matchWrap())
        panel.addView(displayCard, matchWrap().apply { bottomMargin = dp(12) })

        val quickTunnelCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(15), dp(16), dp(15))
            background = roundedDrawable(Color.WHITE, dp(15).toFloat(), COLOR_BORDER, 1)
        }
        quickTunnelCard.addView(simpleText("Quick Tunnel", 14f, COLOR_INK, true), matchWrap().apply {
            bottomMargin = dp(5)
        })
        val quickTunnelValue = simpleText(quickTunnelRoot(), 12.5f, COLOR_INK, false).apply {
            setTextIsSelectable(true)
        }
        quickTunnelCard.addView(quickTunnelValue, matchWrap().apply { bottomMargin = dp(5) })
        quickTunnelCard.addView(
            simpleText(
                "Quick Tunnel 주소가 바뀌면 Root 주소만 변경하세요. /tg/, /dev/ 등의 경로는 자동으로 붙습니다.",
                12f,
                COLOR_MUTED,
                false,
            ),
            matchWrap().apply { bottomMargin = dp(9) },
        )
        val changeQuickTunnel = simpleButton("Quick Tunnel 주소 변경", false)
        quickTunnelCard.addView(
            changeQuickTunnel,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(44)),
        )
        panel.addView(quickTunnelCard, matchWrap().apply { bottomMargin = dp(12) })

        val notificationRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(16), dp(13), dp(16), dp(13))
            background = roundedDrawable(Color.WHITE, dp(15).toFloat(), COLOR_BORDER, 1)
        }
        notificationRow.addView(simpleText("작업 완료 알림", 14f, COLOR_INK, true), LinearLayout.LayoutParams(
            0,
            ViewGroup.LayoutParams.WRAP_CONTENT,
            1f,
        ))
        val notificationToggle = Switch(this).apply {
            isChecked = prefs.getBoolean(PREF_NOTIFICATIONS_ENABLED, true)
            showText = false
        }
        notificationRow.addView(notificationToggle)
        panel.addView(notificationRow, matchWrap().apply { bottomMargin = dp(12) })

        val close = simpleButton("닫기", true)
        panel.addView(close, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50)))

        scaleSeek.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val value = MIN_WEB_TEXT_ZOOM_PERCENT + progress * WEB_TEXT_ZOOM_STEP_PERCENT
                scaleValue.text = "Workbench 본문 글자 크기 ${value}%"
                prefs.edit().putInt(PREF_WEB_TEXT_ZOOM, value).apply()
                runCatching { webView?.settings?.textZoom = value }
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) = Unit
            override fun onStopTrackingTouch(seekBar: SeekBar?) = Unit
        })
        resetScale.setOnClickListener {
            scaleSeek.progress =
                (DEFAULT_WEB_TEXT_ZOOM_PERCENT - MIN_WEB_TEXT_ZOOM_PERCENT) / WEB_TEXT_ZOOM_STEP_PERCENT
        }

        changeQuickTunnel.setOnClickListener {
            showQuickTunnelRootDialog { updatedRoot ->
                quickTunnelValue.text = updatedRoot
            }
        }

        notificationToggle.setOnCheckedChangeListener { _, checked ->
            prefs.edit().putBoolean(PREF_NOTIFICATIONS_ENABLED, checked).apply()
            if (checked) {
                suppressNextPauseMonitor = true
                runCatching { requestNotificationPermissionIfNeeded() }
            } else {
                runCatching { TaskNotificationService.stop(this) }
            }
        }
        close.setOnClickListener { closeSettingsOverlay() }

        val scroll = ScrollView(this).apply { isFillViewport = true }
        scroll.addView(panel, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        ))
        overlay.addView(scroll, fillFrame())
        settingsOverlay = overlay
        root.addView(overlay, fillFrame())
    }

    private fun showQuickTunnelRootDialog(onSaved: ((String) -> Unit)? = null) {
        val input = android.widget.EditText(this).apply {
            setSingleLine(true)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
            setText(quickTunnelRoot())
            selectAll()
        }
        val inputFrame = FrameLayout(this).apply {
            setPadding(dp(20), 0, dp(20), 0)
            addView(
                input,
                FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ),
            )
        }
        val dialog = android.app.AlertDialog.Builder(this)
            .setTitle("Quick Tunnel Root")
            .setMessage("https://xxxxx.trycloudflare.com 형식의 Root 주소만 입력하세요.")
            .setView(inputFrame)
            .setNegativeButton("취소", null)
            .setNeutralButton("기본값", null)
            .setPositiveButton("저장", null)
            .create()

        fun finishUpdate(updatedRoot: String, message: String) {
            onSaved?.invoke(updatedRoot)
            Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
            dialog.dismiss()
            if (currentTarget == null && webView == null) {
                val savedId = prefs.getString(PREF_WORKBENCH_ID, null) ?: WorkbenchCatalog.DEFAULT_ID
                runCatching { showConnectionScreen(savedId) }
                    .onFailure { showRecoveryScreen("연결 화면 오류", formatError(it)) }
            }
        }

        dialog.setOnShowListener {
            dialog.getButton(android.content.DialogInterface.BUTTON_POSITIVE).setOnClickListener {
                val normalized = WorkbenchCatalog.normalizeQuickTunnelRoot(input.text?.toString())
                if (normalized == null) {
                    input.error = "https://xxxxx.trycloudflare.com 형식의 Root 주소를 입력하세요."
                    return@setOnClickListener
                }
                val updatedRoot = persistQuickTunnelRoot(normalized)
                finishUpdate(updatedRoot, "Quick Tunnel 주소를 저장했습니다.")
            }
            dialog.getButton(android.content.DialogInterface.BUTTON_NEUTRAL).setOnClickListener {
                val updatedRoot = persistQuickTunnelRoot(null)
                finishUpdate(updatedRoot, "Quick Tunnel 주소를 기본값으로 복원했습니다.")
            }
        }
        dialog.show()
    }

    private fun webTextZoomPercent(): Int {
        val stored = prefs.getInt(PREF_WEB_TEXT_ZOOM, DEFAULT_WEB_TEXT_ZOOM_PERCENT)
        val clamped = stored.coerceIn(MIN_WEB_TEXT_ZOOM_PERCENT, MAX_WEB_TEXT_ZOOM_PERCENT)
        val stepIndex = ((clamped - MIN_WEB_TEXT_ZOOM_PERCENT) + WEB_TEXT_ZOOM_STEP_PERCENT / 2) /
            WEB_TEXT_ZOOM_STEP_PERCENT
        return (MIN_WEB_TEXT_ZOOM_PERCENT + stepIndex * WEB_TEXT_ZOOM_STEP_PERCENT)
            .coerceIn(MIN_WEB_TEXT_ZOOM_PERCENT, MAX_WEB_TEXT_ZOOM_PERCENT)
    }

    private fun closeSettingsOverlay() {
        settingsOverlay?.let { runCatching { root.removeView(it) } }
        settingsOverlay = null
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (!prefs.getBoolean(PREF_NOTIFICATIONS_ENABLED, true)) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), NOTIFICATION_PERMISSION_REQUEST_CODE)
        }
    }

    private fun notificationsAllowed(): Boolean {
        if (!prefs.getBoolean(PREF_NOTIFICATIONS_ENABLED, true)) return false
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    }

    private fun startBackgroundCompletionMonitorIfNeeded() {
        val target = currentTarget ?: return
        if (!target.isCodexWorkbench) return
        if (webView == null || serverBaseUrl.isBlank() || !notificationsAllowed() || isFinishing) return
        val cookie = runCatching { CookieManager.getInstance().getCookie(serverBaseUrl) }.getOrNull()
        TaskNotificationService.start(this, serverBaseUrl, target.name, cookie)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == AUDIO_PERMISSION_REQUEST_CODE) {
            val request = pendingAudioRequest
            pendingAudioRequest = null
            if (request != null) {
                if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED &&
                    request.origin.scheme.equals("https", true) && isSameServerOrigin(request.origin) &&
                    webView?.url?.let { isSameServerOrigin(Uri.parse(it)) } == true) {
                    request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                } else request.deny()
            }
            return
        }
        if (requestCode != NOTIFICATION_PERMISSION_REQUEST_CODE) return
        if (grantResults.firstOrNull() != PackageManager.PERMISSION_GRANTED) {
            prefs.edit().putBoolean(PREF_NOTIFICATIONS_ENABLED, false).apply()
            Toast.makeText(this, "알림 권한이 없어 작업 완료 알림을 껐습니다.", Toast.LENGTH_LONG).show()
        }
    }

    private fun isSameServerOrigin(uri: Uri): Boolean {
        if (serverBaseUrl.isBlank()) return false
        val base = Uri.parse(serverBaseUrl)
        return base.scheme.equals(uri.scheme, ignoreCase = true) &&
            base.host.equals(uri.host, ignoreCase = true) &&
            effectivePort(base) == effectivePort(uri)
    }

    private fun effectivePort(uri: Uri): Int {
        if (uri.port != -1) return uri.port
        return when (uri.scheme?.lowercase()) {
            "https" -> 443
            "http" -> 80
            else -> -1
        }
    }

    private fun openExternal(uri: Uri): Boolean = try {
        suppressNextPauseMonitor = true
        startActivity(Intent(Intent.ACTION_VIEW, uri))
        true
    } catch (_: Exception) {
        suppressNextPauseMonitor = false
        Toast.makeText(this, "외부 링크를 열 수 없습니다.", Toast.LENGTH_SHORT).show()
        true
    }

    @Deprecated("WebView file chooser compatibility")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == FILE_CHOOSER_REQUEST_CODE) {
            val callback = fileChooserCallback
            fileChooserCallback = null
            val result = WebChromeClient.FileChooserParams.parseResult(resultCode, data)
            callback?.onReceiveValue(result)
            return
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    @Deprecated("Server selection is the navigation root")
    @SuppressLint("GestureBackNavigation")
    override fun onBackPressed() = navigateBack()

    private fun navigateBack() {
        if (settingsOverlay != null) {
            closeSettingsOverlay()
            return
        }
        if (webView != null || currentTarget != null) {
            val selectedId = currentTarget?.id
                ?: prefs.getString(PREF_WORKBENCH_ID, null)
                ?: WorkbenchCatalog.DEFAULT_ID
            showConnectionScreen(selectedId)
            return
        }
        finish()
    }

    private fun destroyWebView() {
        pendingAudioRequest?.deny()
        pendingAudioRequest = null
        downloadController?.close()
        downloadController = null
        val browser = webView ?: return
        webView = null
        runCatching { browser.stopLoading() }
        runCatching { browser.loadUrl("about:blank") }
        runCatching { browser.clearHistory() }
        runCatching { browser.removeAllViews() }
        runCatching { browser.destroy() }
    }

    private fun simpleText(
        value: String,
        sizeSp: Float,
        color: Int,
        bold: Boolean = false,
        gravity: Int = Gravity.START,
    ): TextView = TextView(this).apply {
        text = value
        textSize = sizeSp
        setTextColor(color)
        this.gravity = gravity
        includeFontPadding = false
        typeface = Typeface.create("sans-serif", if (bold) Typeface.BOLD else Typeface.NORMAL)
        setLineSpacing(0f, 1.06f)
    }

    private fun simpleButton(label: String, filled: Boolean): TextView =
        simpleText(
            label,
            14.5f,
            if (filled) Color.WHITE else COLOR_PRIMARY,
            true,
            Gravity.CENTER,
        ).apply {
            isClickable = true
            isFocusable = true
            background = roundedDrawable(
                if (filled) COLOR_PRIMARY else Color.WHITE,
                dp(15).toFloat(),
                if (filled) COLOR_PRIMARY else COLOR_BORDER,
                1,
            )
        }

    private fun toolbarButton(label: String): TextView =
        simpleText(label, 12f, COLOR_INK, true, Gravity.CENTER).apply {
            isClickable = true
            isFocusable = true
            background = roundedDrawable(Color.WHITE, dp(11).toFloat(), COLOR_BORDER, 1)
        }

    private fun roundedDrawable(
        fillColor: Int,
        radius: Float,
        strokeColor: Int? = null,
        strokeWidthDp: Int = 0,
    ): GradientDrawable = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        setColor(fillColor)
        cornerRadius = radius
        if (strokeColor != null && strokeWidthDp > 0) setStroke(dp(strokeWidthDp), strokeColor)
    }

    private fun matchWrap(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)

    private fun fillFrame(): FrameLayout.LayoutParams =
        FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}

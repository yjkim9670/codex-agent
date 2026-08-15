package com.yjkim9670.codexworkbench

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.webkit.CookieManager
import android.webkit.DownloadListener
import android.webkit.HttpAuthHandler
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {
    companion object {
        private const val PREFS_NAME = "codex_workbench"
        private const val PREF_SERVER_URL = "server_url"
        private const val PREF_WORKBENCH_ID = "workbench_id"
        private const val PREF_NOTIFICATIONS_ENABLED = "notifications_enabled"
        private const val FILE_CHOOSER_REQUEST_CODE = 7001
        private const val NOTIFICATION_PERMISSION_REQUEST_CODE = 7002
        private const val USER_AGENT_SUFFIX = "CodexWorkbenchAndroid/1.1"
        private const val SPLASH_DURATION_MS = 1100L
        private const val WEB_TEXT_ZOOM_PERCENT = 90
    }

    private lateinit var root: FrameLayout
    private var webView: WebView? = null
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var serverBaseUrl: String = ""
    private var currentTarget: WorkbenchTarget? = null
    private var splashTransition: Runnable? = null
    private var settingsOverlay: View? = null

    private val prefs by lazy {
        getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        configureSystemBars()
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)

        root = FrameLayout(this).apply {
            setBackgroundColor(Color.WHITE)
        }
        setContentView(root)
        applySystemBarInsets()

        val legacyUrl = prefs.getString(PREF_SERVER_URL, null)
        val savedId = prefs.getString(PREF_WORKBENCH_ID, null)
            ?: WorkbenchCatalog.byUrl(legacyUrl)?.id
            ?: WorkbenchCatalog.DEFAULT_ID
        showOpeningScreen(savedId)
    }

    override fun onResume() {
        super.onResume()
        TaskNotificationService.stop(this)
    }

    override fun onPause() {
        startBackgroundCompletionMonitorIfNeeded()
        super.onPause()
    }

    private fun configureSystemBars() {
        val navy = Color.rgb(7, 26, 53)
        window.statusBarColor = navy
        window.navigationBarColor = navy

        val decor = window.decorView
        decor.systemUiVisibility = decor.systemUiVisibility and
            View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR.inv() and
            View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR.inv()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            window.navigationBarDividerColor = navy
        }
    }

    private fun applySystemBarInsets() {
        root.setOnApplyWindowInsetsListener { _, windowInsets ->
            val left: Int
            val top: Int
            val right: Int
            val bottom: Int

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val safeInsets = windowInsets.getInsets(
                    WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout(),
                )
                left = safeInsets.left
                top = safeInsets.top
                right = safeInsets.right
                bottom = safeInsets.bottom
            } else {
                @Suppress("DEPRECATION")
                left = windowInsets.systemWindowInsetLeft
                @Suppress("DEPRECATION")
                top = windowInsets.systemWindowInsetTop
                @Suppress("DEPRECATION")
                right = windowInsets.systemWindowInsetRight
                @Suppress("DEPRECATION")
                bottom = windowInsets.systemWindowInsetBottom
            }

            root.setPadding(left, top, right, bottom)
            windowInsets
        }
        root.requestApplyInsets()
    }

    private fun showOpeningScreen(nextWorkbenchId: String) {
        destroyWebView()
        root.removeAllViews()
        serverBaseUrl = ""
        currentTarget = null

        val splash = FrameLayout(this).apply {
            setBackgroundResource(R.drawable.splash_background)
        }

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(28), dp(32), dp(28), dp(32))
        }

        val artwork = ImageView(this).apply {
            setImageResource(R.drawable.ic_workbench_foreground)
            adjustViewBounds = true
            scaleType = ImageView.ScaleType.FIT_CENTER
            contentDescription = "코덱스 워크벤치 아이콘"
        }
        content.addView(
            artwork,
            LinearLayout.LayoutParams(dp(236), dp(236)).apply {
                bottomMargin = dp(18)
                gravity = Gravity.CENTER_HORIZONTAL
            },
        )

        content.addView(
            TextView(this).apply {
                text = "코덱스 워크벤치"
                textSize = 30f
                setTextColor(Color.WHITE)
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                letterSpacing = 0.02f
            },
            matchWrap().apply { bottomMargin = dp(8) },
        )
        content.addView(
            TextView(this).apply {
                text = "Workspace · Git · Terminal"
                textSize = 14f
                setTextColor(Color.rgb(184, 226, 237))
                gravity = Gravity.CENTER
            },
            matchWrap(),
        )

        splash.addView(content, fillFrame())
        root.addView(splash, fillFrame())

        splashTransition?.let { root.removeCallbacks(it) }
        splashTransition = Runnable {
            if (!isFinishing && !isDestroyed) {
                showConnectionScreen(nextWorkbenchId)
            }
        }.also { root.postDelayed(it, SPLASH_DURATION_MS) }
    }

    private fun showConnectionScreen(initialWorkbenchId: String) {
        splashTransition?.let { root.removeCallbacks(it) }
        splashTransition = null
        closeSettingsOverlay()
        destroyWebView()
        root.removeAllViews()
        root.setBackgroundColor(Color.WHITE)
        serverBaseUrl = ""
        currentTarget = null

        val scroll = ScrollView(this).apply {
            isFillViewport = true
        }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(22), dp(26), dp(22), dp(28))
        }
        scroll.addView(
            panel,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ),
        )

        panel.addView(
            TextView(this).apply {
                text = "코덱스 워크벤치"
                textSize = 25f
                setTextColor(Color.rgb(15, 27, 45))
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
            },
            matchWrap().apply { bottomMargin = dp(7) },
        )
        panel.addView(
            TextView(this).apply {
                text = "접속할 Workbench를 선택하세요.\nGateway: dinya.wind-mintaka.ts.net"
                textSize = 13.5f
                setTextColor(Color.rgb(76, 91, 113))
                gravity = Gravity.CENTER
            },
            matchWrap().apply { bottomMargin = dp(20) },
        )

        val selected = WorkbenchCatalog.byId(initialWorkbenchId)
        val radioGroup = RadioGroup(this).apply {
            orientation = RadioGroup.VERTICAL
        }
        WorkbenchCatalog.targets.forEachIndexed { index, target ->
            val radio = RadioButton(this).apply {
                id = View.generateViewId()
                tag = target.id
                text = "${target.name}\n${target.url.removePrefix(WorkbenchCatalog.GATEWAY_ROOT)}"
                textSize = 14.5f
                setTextColor(Color.rgb(31, 48, 72))
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(6), dp(6), dp(6), dp(6))
                isChecked = target.id == selected.id
            }
            radioGroup.addView(
                radio,
                RadioGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ).apply {
                    if (index < WorkbenchCatalog.targets.lastIndex) bottomMargin = dp(3)
                },
            )
        }
        panel.addView(
            radioGroup,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(18) },
        )

        val connectButton = Button(this).apply {
            text = "선택한 Workbench 접속"
            isAllCaps = false
            textSize = 15f
        }
        panel.addView(
            connectButton,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(50),
            ).apply { bottomMargin = dp(9) },
        )

        val settingsButton = Button(this).apply {
            text = "설정"
            isAllCaps = false
            textSize = 14f
        }
        panel.addView(
            settingsButton,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(46),
            ),
        )

        connectButton.setOnClickListener {
            val checked = radioGroup.findViewById<RadioButton>(radioGroup.checkedRadioButtonId)
            val target = WorkbenchCatalog.byId(checked?.tag?.toString())
            prefs.edit()
                .putString(PREF_WORKBENCH_ID, target.id)
                .putString(PREF_SERVER_URL, target.url)
                .apply()
            requestNotificationPermissionIfNeeded()
            showWorkbench(target)
        }
        settingsButton.setOnClickListener { showSettingsOverlay() }

        root.addView(scroll, fillFrame())
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun showWorkbench(target: WorkbenchTarget) {
        closeSettingsOverlay()
        root.removeAllViews()
        root.setBackgroundColor(Color.WHITE)
        currentTarget = target
        serverBaseUrl = target.url

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.WHITE)
        }
        val toolbar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(10), 0, dp(5), 0)
            setBackgroundColor(Color.rgb(244, 247, 251))
        }
        val toolbarTitle = TextView(this).apply {
            text = target.name
            textSize = 13.5f
            setTextColor(Color.rgb(15, 27, 45))
            maxLines = 1
        }
        toolbar.addView(
            toolbarTitle,
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f),
        )

        val reloadButton = compactToolbarButton("↻", "새로고침")
        val serverButton = compactToolbarButton("서버", "Workbench 선택")
        val settingsButton = compactToolbarButton("설정", "앱 설정")
        toolbar.addView(reloadButton, LinearLayout.LayoutParams(dp(44), dp(38)))
        toolbar.addView(serverButton, LinearLayout.LayoutParams(dp(54), dp(38)))
        toolbar.addView(settingsButton, LinearLayout.LayoutParams(dp(54), dp(38)))
        container.addView(
            toolbar,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46)),
        )

        val browser = WebView(this)
        webView = browser
        browser.setBackgroundColor(Color.WHITE)
        browser.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = false
            allowContentAccess = true
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            mediaPlaybackRequiresUserGesture = true
            builtInZoomControls = false
            displayZoomControls = false
            loadWithOverviewMode = false
            useWideViewPort = true
            cacheMode = WebSettings.LOAD_DEFAULT
            safeBrowsingEnabled = true
            textZoom = WEB_TEXT_ZOOM_PERCENT
            userAgentString = "${userAgentString} $USER_AGENT_SUFFIX"
        }

        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(browser, false)
        }

        browser.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView?,
                request: WebResourceRequest?,
            ): Boolean {
                val uri = request?.url ?: return false
                val scheme = uri.scheme?.lowercase().orEmpty()
                if (scheme == "http" || scheme == "https") {
                    if (isSameServerOrigin(uri)) return false
                    return openExternal(uri)
                }
                if (scheme == "mailto" || scheme == "tel") return openExternal(uri)
                return true
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                toolbarTitle.text = target.name
                enableWorkModeByDefault(view)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?,
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    Toast.makeText(
                        this@MainActivity,
                        "Workbench 연결 오류: ${error?.description ?: "unknown error"}",
                        Toast.LENGTH_LONG,
                    ).show()
                }
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
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?,
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback
                val intent = try {
                    fileChooserParams?.createIntent() ?: Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "*/*"
                    }
                } catch (_: Exception) {
                    Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "*/*"
                    }
                }
                return try {
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST_CODE)
                    true
                } catch (_: Exception) {
                    fileChooserCallback?.onReceiveValue(null)
                    fileChooserCallback = null
                    Toast.makeText(
                        this@MainActivity,
                        "파일 선택기를 열 수 없습니다.",
                        Toast.LENGTH_LONG,
                    ).show()
                    false
                }
            }
        }

        browser.setDownloadListener(
            DownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
                enqueueDownload(url, userAgent, contentDisposition, mimeType)
            },
        )

        container.addView(
            browser,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f),
        )
        reloadButton.setOnClickListener { browser.reload() }
        serverButton.setOnClickListener { showConnectionScreen(target.id) }
        settingsButton.setOnClickListener { showSettingsOverlay() }
        root.addView(container, fillFrame())
        browser.loadUrl(target.url)
    }

    private fun compactToolbarButton(label: String, description: String): Button =
        Button(this).apply {
            text = label
            textSize = if (label == "↻") 18f else 12f
            isAllCaps = false
            minWidth = 0
            minimumWidth = 0
            minHeight = 0
            minimumHeight = 0
            setPadding(dp(3), 0, dp(3), 0)
            contentDescription = description
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
            setBackgroundColor(Color.WHITE)
            elevation = dp(8).toFloat()
        }
        val scroll = ScrollView(this).apply { isFillViewport = true }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(22), dp(20), dp(22), dp(28))
        }

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        header.addView(
            TextView(this).apply {
                text = "설정"
                textSize = 24f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(Color.rgb(15, 27, 45))
            },
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f),
        )
        val close = Button(this).apply {
            text = "닫기"
            textSize = 13f
            isAllCaps = false
        }
        header.addView(close, LinearLayout.LayoutParams(dp(66), dp(42)))
        panel.addView(header, matchWrap().apply { bottomMargin = dp(22) })

        panel.addView(
            TextView(this).apply {
                text = "화면"
                textSize = 17f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(Color.rgb(31, 48, 72))
            },
            matchWrap().apply { bottomMargin = dp(6) },
        )
        panel.addView(
            TextView(this).apply {
                text = "Workbench 본문 글자 크기: 90%\n접속 직후 작업모드를 기본으로 엽니다."
                textSize = 14f
                setTextColor(Color.rgb(76, 91, 113))
            },
            matchWrap().apply { bottomMargin = dp(24) },
        )

        panel.addView(
            TextView(this).apply {
                text = "알림"
                textSize = 17f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(Color.rgb(31, 48, 72))
            },
            matchWrap().apply { bottomMargin = dp(5) },
        )

        val notificationSwitch = Switch(this).apply {
            text = "작업 완료 푸시 알림"
            textSize = 15.5f
            isChecked = prefs.getBoolean(PREF_NOTIFICATIONS_ENABLED, true)
            setPadding(0, dp(6), 0, dp(6))
        }
        panel.addView(notificationSwitch, matchWrap().apply { bottomMargin = dp(6) })
        panel.addView(
            TextView(this).apply {
                text = "앱을 백그라운드로 전환하면 실행 중인 Workbench 작업만 짧게 모니터링합니다. 작업이 끝나면 Android 알림을 보내고 모니터를 자동 종료합니다. 인증 쿠키는 저장하지 않습니다."
                textSize = 13.5f
                setTextColor(Color.rgb(76, 91, 113))
            },
            matchWrap().apply { bottomMargin = dp(22) },
        )

        val selectedTarget = currentTarget ?: WorkbenchCatalog.byId(
            prefs.getString(PREF_WORKBENCH_ID, WorkbenchCatalog.DEFAULT_ID),
        )
        panel.addView(
            TextView(this).apply {
                text = "현재 Workbench\n${selectedTarget.name}\n${selectedTarget.url}"
                textSize = 13.5f
                setTextColor(Color.rgb(76, 91, 113))
            },
            matchWrap(),
        )

        notificationSwitch.setOnCheckedChangeListener { _, checked ->
            prefs.edit().putBoolean(PREF_NOTIFICATIONS_ENABLED, checked).apply()
            if (checked) {
                requestNotificationPermissionIfNeeded()
            } else {
                TaskNotificationService.stop(this)
            }
        }
        close.setOnClickListener { closeSettingsOverlay() }

        scroll.addView(panel)
        overlay.addView(scroll, fillFrame())
        settingsOverlay = overlay
        root.addView(overlay, fillFrame())
    }

    private fun closeSettingsOverlay() {
        settingsOverlay?.let { root.removeView(it) }
        settingsOverlay = null
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (!prefs.getBoolean(PREF_NOTIFICATIONS_ENABLED, true)) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                NOTIFICATION_PERMISSION_REQUEST_CODE,
            )
        }
    }

    private fun notificationsAllowed(): Boolean {
        if (!prefs.getBoolean(PREF_NOTIFICATIONS_ENABLED, true)) return false
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    }

    private fun startBackgroundCompletionMonitorIfNeeded() {
        val target = currentTarget ?: return
        if (webView == null || serverBaseUrl.isBlank() || !notificationsAllowed() || isFinishing) return
        val cookie = CookieManager.getInstance().getCookie(serverBaseUrl)
        TaskNotificationService.start(this, serverBaseUrl, target.name, cookie)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != NOTIFICATION_PERMISSION_REQUEST_CODE) return
        val granted = grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
        if (!granted) {
            prefs.edit().putBoolean(PREF_NOTIFICATIONS_ENABLED, false).apply()
            Toast.makeText(
                this,
                "알림 권한이 없어 작업 완료 알림을 껐습니다. 설정에서 다시 켤 수 있습니다.",
                Toast.LENGTH_LONG,
            ).show()
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

    private fun openExternal(uri: Uri): Boolean {
        return try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
            true
        } catch (_: Exception) {
            Toast.makeText(this, "외부 링크를 열 수 없습니다.", Toast.LENGTH_SHORT).show()
            true
        }
    }

    private fun enqueueDownload(
        url: String?,
        userAgent: String?,
        contentDisposition: String?,
        mimeType: String?,
    ) {
        if (url.isNullOrBlank()) return
        val uri = runCatching { Uri.parse(url) }.getOrNull() ?: return
        if (uri.scheme != "http" && uri.scheme != "https") {
            Toast.makeText(this, "지원하지 않는 다운로드 URL입니다.", Toast.LENGTH_SHORT).show()
            return
        }

        val guessedName = android.webkit.URLUtil.guessFileName(url, contentDisposition, mimeType)
        val fileName = guessedName
            .replace('/', '_')
            .replace('\\', '_')
            .ifBlank { "download.bin" }
        try {
            val request = DownloadManager.Request(uri).apply {
                setTitle(fileName)
                setDescription("코덱스 워크벤치 다운로드")
                setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                setAllowedOverMetered(true)
                setAllowedOverRoaming(false)
                if (!mimeType.isNullOrBlank()) setMimeType(mimeType)
                val cookie = CookieManager.getInstance().getCookie(url)
                if (!cookie.isNullOrBlank()) addRequestHeader("Cookie", cookie)
                if (!userAgent.isNullOrBlank()) addRequestHeader("User-Agent", userAgent)
                setDestinationInExternalFilesDir(
                    this@MainActivity,
                    Environment.DIRECTORY_DOWNLOADS,
                    fileName,
                )
            }
            val manager = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
            manager.enqueue(request)
            Toast.makeText(this, "다운로드 시작: $fileName", Toast.LENGTH_LONG).show()
        } catch (error: Exception) {
            Toast.makeText(
                this,
                "다운로드 실패: ${error.message ?: error.javaClass.simpleName}",
                Toast.LENGTH_LONG,
            ).show()
        }
    }

    @Deprecated("Deprecated in Android; retained for WebView file chooser compatibility.")
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

    @Deprecated("Deprecated in Android; WebView history behavior is intentional here.")
    override fun onBackPressed() {
        if (settingsOverlay != null) {
            closeSettingsOverlay()
            return
        }
        val browser = webView
        if (browser != null && browser.canGoBack()) {
            browser.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        splashTransition?.let { root.removeCallbacks(it) }
        splashTransition = null
        settingsOverlay = null
        fileChooserCallback?.onReceiveValue(null)
        fileChooserCallback = null
        destroyWebView()
        super.onDestroy()
    }

    private fun destroyWebView() {
        webView?.apply {
            stopLoading()
            loadUrl("about:blank")
            clearHistory()
            removeAllViews()
            destroy()
        }
        webView = null
    }

    private fun matchWrap(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        )

    private fun fillFrame(): FrameLayout.LayoutParams =
        FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT,
        )

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()
}

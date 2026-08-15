package com.yjkim9670.codexworkbench

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.text.TextUtils
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
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
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
        private const val USER_AGENT_SUFFIX = "CodexWorkbenchAndroid/1.1.1"
        private const val SPLASH_DURATION_MS = 1100L
        private const val WEB_TEXT_ZOOM_PERCENT = 85

        private val COLOR_NAVY = Color.rgb(7, 26, 53)
        private val COLOR_INK = Color.rgb(20, 34, 54)
        private val COLOR_MUTED = Color.rgb(91, 106, 128)
        private val COLOR_MUTED_LIGHT = Color.rgb(123, 138, 158)
        private val COLOR_CANVAS = Color.rgb(247, 249, 252)
        private val COLOR_SURFACE = Color.WHITE
        private val COLOR_BORDER = Color.rgb(221, 227, 236)
        private val COLOR_PRIMARY = Color.rgb(35, 104, 196)
        private val COLOR_PRIMARY_DARK = Color.rgb(25, 78, 151)
        private val COLOR_PRIMARY_SOFT = Color.rgb(237, 245, 255)
        private val COLOR_PRIMARY_BORDER = Color.rgb(116, 163, 222)
    }

    private lateinit var root: FrameLayout
    private var webView: WebView? = null
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var serverBaseUrl: String = ""
    private var currentTarget: WorkbenchTarget? = null
    private var splashTransition: Runnable? = null
    private var settingsOverlay: View? = null
    private var suppressNextPauseMonitor = false

    private val prefs by lazy {
        getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    private val plexRegular: Typeface by lazy {
        Typeface.create("sans-serif", Typeface.NORMAL)
    }
    private val plexMedium: Typeface by lazy {
        Typeface.create("sans-serif-medium", Typeface.NORMAL)
    }
    private val plexSemibold: Typeface by lazy {
        Typeface.create("sans-serif", Typeface.BOLD)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        configureSystemBars()
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)

        root = FrameLayout(this).apply {
            setBackgroundColor(COLOR_CANVAS)
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
        suppressNextPauseMonitor = false
        TaskNotificationService.stop(this)
    }

    override fun onPause() {
        if (!suppressNextPauseMonitor) {
            startBackgroundCompletionMonitorIfNeeded()
        }
        suppressNextPauseMonitor = false
        super.onPause()
    }

    private fun configureSystemBars() {
        window.statusBarColor = COLOR_NAVY
        window.navigationBarColor = COLOR_NAVY

        val decor = window.decorView
        decor.systemUiVisibility = decor.systemUiVisibility and
            View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR.inv() and
            View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR.inv()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            window.navigationBarDividerColor = COLOR_NAVY
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

        content.addView(
            ImageView(this).apply {
                setImageResource(R.drawable.ic_workbench_foreground)
                adjustViewBounds = true
                scaleType = ImageView.ScaleType.FIT_CENTER
                contentDescription = "코덱스 워크벤치 아이콘"
            },
            LinearLayout.LayoutParams(dp(226), dp(226)).apply {
                bottomMargin = dp(16)
                gravity = Gravity.CENTER_HORIZONTAL
            },
        )
        content.addView(
            nativeText(
                value = "코덱스 워크벤치",
                sizeSp = 29f,
                color = Color.WHITE,
                weight = NativeWeight.SEMIBOLD,
                gravity = Gravity.CENTER,
            ).apply { letterSpacing = -0.005f },
            matchWrap().apply { bottomMargin = dp(8) },
        )
        content.addView(
            nativeText(
                value = "Workspace · Git · Terminal",
                sizeSp = 13.5f,
                color = Color.rgb(184, 226, 237),
                weight = NativeWeight.MEDIUM,
                gravity = Gravity.CENTER,
            ).apply { letterSpacing = 0.035f },
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
        root.setBackgroundColor(COLOR_CANVAS)
        serverBaseUrl = ""
        currentTarget = null

        val scroll = ScrollView(this).apply {
            isFillViewport = true
            setBackgroundColor(COLOR_CANVAS)
            clipToPadding = false
        }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(20), dp(22), dp(20), dp(30))
        }
        scroll.addView(panel, matchWrap())

        val eyebrow = nativeText(
            value = "CODEX WORKBENCH",
            sizeSp = 11.5f,
            color = COLOR_PRIMARY,
            weight = NativeWeight.SEMIBOLD,
            gravity = Gravity.CENTER,
        ).apply { letterSpacing = 0.12f }
        panel.addView(eyebrow, matchWrap().apply { bottomMargin = dp(7) })

        panel.addView(
            nativeText(
                value = "코덱스 워크벤치",
                sizeSp = 27f,
                color = COLOR_INK,
                weight = NativeWeight.SEMIBOLD,
                gravity = Gravity.CENTER,
            ),
            matchWrap().apply { bottomMargin = dp(8) },
        )
        panel.addView(
            nativeText(
                value = "사용할 Workbench를 선택하세요.\n인증은 선택한 Funnel Gateway에서 그대로 진행됩니다.",
                sizeSp = 13.5f,
                color = COLOR_MUTED,
                weight = NativeWeight.REGULAR,
                gravity = Gravity.CENTER,
            ).apply { setLineSpacing(dp(2).toFloat(), 1f) },
            matchWrap().apply { bottomMargin = dp(20) },
        )

        val gatewayPill = nativeText(
            value = "dinya.wind-mintaka.ts.net",
            sizeSp = 11.5f,
            color = COLOR_MUTED,
            weight = NativeWeight.MEDIUM,
            gravity = Gravity.CENTER,
        ).apply {
            setPadding(dp(14), dp(7), dp(14), dp(7))
            background = roundedDrawable(Color.WHITE, dp(99).toFloat(), COLOR_BORDER, 1)
        }
        panel.addView(
            gatewayPill,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(18) },
        )

        var selectedId = WorkbenchCatalog.byId(initialWorkbenchId).id
        val cardViews = linkedMapOf<String, Pair<LinearLayout, TextView>>()
        val listContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        fun refreshCards() {
            cardViews.forEach { (id, pair) ->
                applyWorkbenchCardState(pair.first, pair.second, id == selectedId)
            }
        }

        WorkbenchCatalog.targets.forEachIndexed { index, target ->
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                isClickable = true
                isFocusable = true
                elevation = dp(1).toFloat()
                setPadding(dp(14), dp(13), dp(12), dp(13))
            }

            val badge = nativeText(
                value = targetBadge(target),
                sizeSp = 11.5f,
                color = COLOR_PRIMARY,
                weight = NativeWeight.SEMIBOLD,
                gravity = Gravity.CENTER,
            ).apply {
                background = roundedDrawable(COLOR_PRIMARY_SOFT, dp(13).toFloat())
            }
            card.addView(badge, LinearLayout.LayoutParams(dp(42), dp(42)).apply { rightMargin = dp(12) })

            val copy = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            copy.addView(
                nativeText(
                    value = target.name.removeSuffix(" Codex Workbench"),
                    sizeSp = 15f,
                    color = COLOR_INK,
                    weight = NativeWeight.MEDIUM,
                ).apply {
                    maxLines = 1
                    ellipsize = TextUtils.TruncateAt.END
                },
                matchWrap().apply { bottomMargin = dp(3) },
            )
            copy.addView(
                nativeText(
                    value = target.url.removePrefix(WorkbenchCatalog.GATEWAY_ROOT),
                    sizeSp = 12.5f,
                    color = COLOR_MUTED_LIGHT,
                    weight = NativeWeight.REGULAR,
                ),
                matchWrap(),
            )
            card.addView(copy, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))

            val indicator = nativeText(
                value = "",
                sizeSp = 14f,
                color = Color.WHITE,
                weight = NativeWeight.SEMIBOLD,
                gravity = Gravity.CENTER,
            )
            card.addView(indicator, LinearLayout.LayoutParams(dp(28), dp(28)).apply { leftMargin = dp(10) })

            cardViews[target.id] = Pair(card, indicator)
            applyWorkbenchCardState(card, indicator, target.id == selectedId)
            card.setOnClickListener {
                selectedId = target.id
                refreshCards()
            }

            listContainer.addView(
                card,
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ).apply {
                    if (index < WorkbenchCatalog.targets.lastIndex) bottomMargin = dp(9)
                },
            )
        }
        panel.addView(listContainer, matchWrap().apply { bottomMargin = dp(18) })

        val connectButton = modernButton(
            label = "선택한 Workbench 접속",
            filled = true,
        )
        panel.addView(
            connectButton,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(54)).apply {
                bottomMargin = dp(10)
            },
        )

        val settingsButton = modernButton(
            label = "앱 설정",
            filled = false,
        )
        panel.addView(
            settingsButton,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50)),
        )

        connectButton.setOnClickListener {
            val target = WorkbenchCatalog.byId(selectedId)
            prefs.edit()
                .putString(PREF_WORKBENCH_ID, target.id)
                .putString(PREF_SERVER_URL, target.url)
                .apply()
            suppressNextPauseMonitor = true
            requestNotificationPermissionIfNeeded()
            showWorkbench(target)
        }
        settingsButton.setOnClickListener { showSettingsOverlay() }

        root.addView(scroll, fillFrame())
    }

    private fun applyWorkbenchCardState(
        card: LinearLayout,
        indicator: TextView,
        selected: Boolean,
    ) {
        card.background = roundedDrawable(
            fillColor = if (selected) COLOR_PRIMARY_SOFT else COLOR_SURFACE,
            radius = dp(17).toFloat(),
            strokeColor = if (selected) COLOR_PRIMARY_BORDER else COLOR_BORDER,
            strokeWidthDp = if (selected) 2 else 1,
        )
        card.elevation = if (selected) dp(2).toFloat() else dp(1).toFloat()
        indicator.text = if (selected) "✓" else ""
        indicator.background = roundedDrawable(
            fillColor = if (selected) COLOR_PRIMARY else COLOR_SURFACE,
            radius = dp(14).toFloat(),
            strokeColor = if (selected) COLOR_PRIMARY else COLOR_BORDER,
            strokeWidthDp = 1,
        )
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
            setPadding(dp(12), dp(5), dp(8), dp(5))
            setBackgroundColor(Color.rgb(249, 250, 252))
            elevation = dp(1).toFloat()
        }
        val titleBlock = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        titleBlock.addView(
            nativeText(
                value = target.name.removeSuffix(" Codex Workbench"),
                sizeSp = 13f,
                color = COLOR_INK,
                weight = NativeWeight.MEDIUM,
            ).apply {
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
            },
            matchWrap(),
        )
        titleBlock.addView(
            nativeText(
                value = target.url.removePrefix(WorkbenchCatalog.GATEWAY_ROOT),
                sizeSp = 10.5f,
                color = COLOR_MUTED_LIGHT,
                weight = NativeWeight.REGULAR,
            ).apply {
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
            },
            matchWrap(),
        )
        toolbar.addView(
            titleBlock,
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                rightMargin = dp(6)
            },
        )

        val reloadButton = compactToolbarButton("↻", "새로고침", wide = false)
        val serverButton = compactToolbarButton("서버", "Workbench 선택", wide = true)
        val settingsButton = compactToolbarButton("설정", "앱 설정", wide = true)
        toolbar.addView(reloadButton, LinearLayout.LayoutParams(dp(38), dp(36)).apply { rightMargin = dp(5) })
        toolbar.addView(serverButton, LinearLayout.LayoutParams(dp(48), dp(36)).apply { rightMargin = dp(5) })
        toolbar.addView(settingsButton, LinearLayout.LayoutParams(dp(48), dp(36)))
        container.addView(
            toolbar,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50)),
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
                    suppressNextPauseMonitor = true
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST_CODE)
                    true
                } catch (_: Exception) {
                    suppressNextPauseMonitor = false
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

    private fun compactToolbarButton(
        label: String,
        description: String,
        wide: Boolean,
    ): TextView = nativeText(
        value = label,
        sizeSp = if (wide) 10.5f else 17f,
        color = COLOR_INK,
        weight = if (wide) NativeWeight.MEDIUM else NativeWeight.REGULAR,
        gravity = Gravity.CENTER,
    ).apply {
        contentDescription = description
        isClickable = true
        isFocusable = true
        background = rippleBackground(
            fillColor = Color.rgb(241, 244, 248),
            radiusDp = 11,
            rippleColor = Color.rgb(216, 225, 236),
        )
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
        val scroll = ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
        }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(18), dp(20), dp(30))
        }

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val headingBlock = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        headingBlock.addView(
            nativeText(
                value = "설정",
                sizeSp = 25f,
                color = COLOR_INK,
                weight = NativeWeight.SEMIBOLD,
            ),
            matchWrap(),
        )
        headingBlock.addView(
            nativeText(
                value = "코덱스 워크벤치 Android",
                sizeSp = 12f,
                color = COLOR_MUTED,
                weight = NativeWeight.REGULAR,
            ),
            matchWrap(),
        )
        header.addView(
            headingBlock,
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f),
        )
        val close = modernMiniButton("닫기")
        header.addView(close, LinearLayout.LayoutParams(dp(62), dp(40)))
        panel.addView(header, matchWrap().apply { bottomMargin = dp(20) })

        val displayCard = settingsCard("화면", "DISPLAY")
        displayCard.addView(
            nativeText(
                value = "Workbench 본문 글자 크기 85%",
                sizeSp = 14.5f,
                color = COLOR_INK,
                weight = NativeWeight.MEDIUM,
            ),
            matchWrap().apply { bottomMargin = dp(5) },
        )
        displayCard.addView(
            nativeText(
                value = "모바일에서 더 많은 정보를 한 화면에 표시하고, 접속 직후 작업모드를 기본으로 엽니다.",
                sizeSp = 13f,
                color = COLOR_MUTED,
                weight = NativeWeight.REGULAR,
            ).apply { setLineSpacing(dp(2).toFloat(), 1f) },
            matchWrap(),
        )
        panel.addView(displayCard, matchWrap().apply { bottomMargin = dp(12) })

        val notificationCard = settingsCard("알림", "NOTIFICATION")
        val notificationRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        notificationRow.addView(
            nativeText(
                value = "작업 완료 알림",
                sizeSp = 14.5f,
                color = COLOR_INK,
                weight = NativeWeight.MEDIUM,
            ),
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f),
        )
        val notificationSwitch = Switch(this).apply {
            isChecked = prefs.getBoolean(PREF_NOTIFICATIONS_ENABLED, true)
            showText = false
            thumbTintList = ColorStateList(
                arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
                intArrayOf(COLOR_PRIMARY, Color.rgb(190, 199, 211)),
            )
            trackTintList = ColorStateList(
                arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
                intArrayOf(Color.rgb(181, 208, 242), Color.rgb(226, 231, 238)),
            )
        }
        notificationRow.addView(notificationSwitch)
        notificationCard.addView(notificationRow, matchWrap().apply { bottomMargin = dp(7) })
        notificationCard.addView(
            nativeText(
                value = "앱이 백그라운드일 때 실행 중인 작업만 확인합니다. 완료되면 Android 알림을 보내고 모니터를 자동 종료하며, 인증 쿠키는 별도로 저장하지 않습니다.",
                sizeSp = 13f,
                color = COLOR_MUTED,
                weight = NativeWeight.REGULAR,
            ).apply { setLineSpacing(dp(2).toFloat(), 1f) },
            matchWrap(),
        )
        panel.addView(notificationCard, matchWrap().apply { bottomMargin = dp(12) })

        val selectedTarget = currentTarget ?: WorkbenchCatalog.byId(
            prefs.getString(PREF_WORKBENCH_ID, WorkbenchCatalog.DEFAULT_ID),
        )
        val workbenchCard = settingsCard("현재 Workbench", "CONNECTION")
        workbenchCard.addView(
            nativeText(
                value = selectedTarget.name,
                sizeSp = 14.5f,
                color = COLOR_INK,
                weight = NativeWeight.MEDIUM,
            ),
            matchWrap().apply { bottomMargin = dp(4) },
        )
        workbenchCard.addView(
            nativeText(
                value = selectedTarget.url,
                sizeSp = 12.5f,
                color = COLOR_MUTED,
                weight = NativeWeight.REGULAR,
            ),
            matchWrap(),
        )
        panel.addView(workbenchCard, matchWrap())

        notificationSwitch.setOnCheckedChangeListener { _, checked ->
            prefs.edit().putBoolean(PREF_NOTIFICATIONS_ENABLED, checked).apply()
            if (checked) {
                suppressNextPauseMonitor = true
                requestNotificationPermissionIfNeeded()
            } else {
                TaskNotificationService.stop(this)
            }
        }
        close.setOnClickListener { closeSettingsOverlay() }

        scroll.addView(panel, matchWrap())
        overlay.addView(scroll, fillFrame())
        settingsOverlay = overlay
        root.addView(overlay, fillFrame())
    }

    private fun settingsCard(title: String, eyebrow: String): LinearLayout =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(17), dp(15), dp(17), dp(16))
            elevation = dp(1).toFloat()
            background = roundedDrawable(COLOR_SURFACE, dp(18).toFloat(), COLOR_BORDER, 1)
            addView(
                nativeText(
                    value = eyebrow,
                    sizeSp = 10f,
                    color = COLOR_PRIMARY,
                    weight = NativeWeight.SEMIBOLD,
                ).apply { letterSpacing = 0.1f },
                matchWrap().apply { bottomMargin = dp(5) },
            )
            addView(
                nativeText(
                    value = title,
                    sizeSp = 18f,
                    color = COLOR_INK,
                    weight = NativeWeight.SEMIBOLD,
                ),
                matchWrap().apply { bottomMargin = dp(11) },
            )
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
            suppressNextPauseMonitor = true
            startActivity(Intent(Intent.ACTION_VIEW, uri))
            true
        } catch (_: Exception) {
            suppressNextPauseMonitor = false
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

    private enum class NativeWeight {
        REGULAR,
        MEDIUM,
        SEMIBOLD,
    }

    private fun nativeText(
        value: String,
        sizeSp: Float,
        color: Int,
        weight: NativeWeight = NativeWeight.REGULAR,
        gravity: Int = Gravity.START,
    ): TextView = TextView(this).apply {
        text = value
        textSize = sizeSp
        setTextColor(color)
        this.gravity = gravity
        includeFontPadding = false
        typeface = when (weight) {
            NativeWeight.REGULAR -> plexRegular
            NativeWeight.MEDIUM -> plexMedium
            NativeWeight.SEMIBOLD -> plexSemibold
        }
        letterSpacing = -0.008f
        setLineSpacing(0f, 1.04f)
    }

    private fun modernButton(label: String, filled: Boolean): TextView =
        nativeText(
            value = label,
            sizeSp = 14.5f,
            color = if (filled) Color.WHITE else COLOR_PRIMARY_DARK,
            weight = NativeWeight.MEDIUM,
            gravity = Gravity.CENTER,
        ).apply {
            isClickable = true
            isFocusable = true
            background = rippleBackground(
                fillColor = if (filled) COLOR_PRIMARY else Color.WHITE,
                radiusDp = 16,
                rippleColor = if (filled) Color.rgb(72, 132, 211) else Color.rgb(231, 238, 248),
                strokeColor = if (filled) null else COLOR_PRIMARY_BORDER,
            )
        }

    private fun modernMiniButton(label: String): TextView =
        nativeText(
            value = label,
            sizeSp = 12.5f,
            color = COLOR_INK,
            weight = NativeWeight.MEDIUM,
            gravity = Gravity.CENTER,
        ).apply {
            isClickable = true
            isFocusable = true
            background = rippleBackground(
                fillColor = Color.WHITE,
                radiusDp = 12,
                rippleColor = Color.rgb(230, 236, 244),
                strokeColor = COLOR_BORDER,
            )
        }

    private fun targetBadge(target: WorkbenchTarget): String = when (target.id) {
        "common_tg" -> "TG"
        "finance" -> "FN"
        "local" -> "LC"
        "constraint" -> "CT"
        "dev" -> "DV"
        else -> "WB"
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
        if (strokeColor != null && strokeWidthDp > 0) {
            setStroke(dp(strokeWidthDp), strokeColor)
        }
    }

    private fun rippleBackground(
        fillColor: Int,
        radiusDp: Int,
        rippleColor: Int,
        strokeColor: Int? = null,
    ): RippleDrawable {
        val content = roundedDrawable(
            fillColor = fillColor,
            radius = dp(radiusDp).toFloat(),
            strokeColor = strokeColor,
            strokeWidthDp = if (strokeColor == null) 0 else 1,
        )
        return RippleDrawable(ColorStateList.valueOf(rippleColor), content, null)
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

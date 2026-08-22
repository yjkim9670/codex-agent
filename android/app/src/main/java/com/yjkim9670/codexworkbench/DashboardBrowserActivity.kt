package com.yjkim9670.codexworkbench

import android.annotation.SuppressLint
import android.app.Activity
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Message
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.webkit.CookieManager
import android.webkit.DownloadListener
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

class DashboardBrowserActivity : Activity() {
    companion object {
        const val EXTRA_URL = "dashboard_browser_url"
        private const val FILE_CHOOSER_REQUEST_CODE = 7101
        private const val PREFS_NAME = "codex_workbench"
        private const val PREF_WEB_TEXT_ZOOM = "web_text_zoom"
        private const val DEFAULT_WEB_TEXT_ZOOM_PERCENT = 85
        private const val USER_AGENT_SUFFIX = "CodexWorkbenchAndroid/1.1.10"

        fun createIntent(context: Context, url: String): Intent =
            Intent(context, DashboardBrowserActivity::class.java).apply {
                putExtra(EXTRA_URL, url)
            }
    }

    private val colorCanvas = Color.rgb(247, 249, 252)
    private val colorInk = Color.rgb(20, 34, 54)
    private val colorMuted = Color.rgb(91, 106, 128)
    private val colorBorder = Color.rgb(221, 227, 236)

    private lateinit var root: FrameLayout
    private var browser: WebView? = null
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Establish a minimal view hierarchy first. If anything after this point fails,
        // keep the Activity alive and surface the real cause instead of letting Android
        // wrap it as "Unable to start activity" and terminate the app process.
        root = FrameLayout(this).apply { setBackgroundColor(Color.WHITE) }
        setContentView(root)

        runCatching { configureSystemBars() }
        runCatching { applySystemBarInsets() }

        val initialUrl = intent.getStringExtra(EXTRA_URL).orEmpty().trim()
        val initialUri = runCatching { Uri.parse(initialUrl) }.getOrNull()
        if (initialUri == null || initialUri.scheme?.lowercase() !in setOf("http", "https")) {
            showStartupError(IllegalArgumentException("Invalid dashboard URL: $initialUrl"))
            return
        }

        runCatching { buildBrowser(initialUri) }
            .onFailure { error ->
                destroyBrowser()
                showStartupError(error)
            }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun buildBrowser(initialUri: Uri) {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.WHITE)
        }
        val toolbar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(10), dp(5), dp(8), dp(5))
            setBackgroundColor(colorCanvas)
        }
        val title = textView("프로세스 앱", 13f, true).apply {
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
        }
        toolbar.addView(title, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))

        val back = toolbarButton("‹")
        val reload = toolbarButton("↻")
        val close = toolbarButton("닫기")
        toolbar.addView(back, LinearLayout.LayoutParams(dp(42), dp(38)).apply { leftMargin = dp(4) })
        toolbar.addView(reload, LinearLayout.LayoutParams(dp(42), dp(38)).apply { leftMargin = dp(4) })
        toolbar.addView(close, LinearLayout.LayoutParams(dp(54), dp(38)).apply { leftMargin = dp(4) })
        container.addView(toolbar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50)))

        val webView = WebView(this)
        browser = webView

        // Keep the startup settings deliberately small. Optional settings are guarded so
        // device/WebView-provider differences cannot abort Activity creation.
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = false
        webView.settings.allowContentAccess = true
        webView.settings.javaScriptCanOpenWindowsAutomatically = true
        webView.settings.setSupportMultipleWindows(true)
        runCatching { webView.settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW }
        runCatching { webView.settings.mediaPlaybackRequiresUserGesture = true }
        runCatching { webView.settings.builtInZoomControls = false }
        runCatching { webView.settings.displayZoomControls = false }
        runCatching { webView.settings.useWideViewPort = true }
        runCatching { webView.settings.cacheMode = WebSettings.LOAD_DEFAULT }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            runCatching { webView.settings.safeBrowsingEnabled = true }
        }
        runCatching {
            webView.settings.textZoom = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .getInt(PREF_WEB_TEXT_ZOOM, DEFAULT_WEB_TEXT_ZOOM_PERCENT)
                .coerceIn(60, 125)
        }
        runCatching {
            webView.settings.userAgentString =
                "${webView.settings.userAgentString} $USER_AGENT_SUFFIX"
        }

        runCatching {
            CookieManager.getInstance().apply {
                setAcceptCookie(true)
                setAcceptThirdPartyCookies(webView, false)
            }
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val uri = request?.url ?: return false
                return when (uri.scheme?.lowercase()) {
                    "http", "https" -> false
                    "mailto", "tel" -> openExternal(uri)
                    else -> true
                }
            }
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onReceivedTitle(view: WebView?, pageTitle: String?) {
                super.onReceivedTitle(view, pageTitle)
                title.text = pageTitle?.takeIf { it.isNotBlank() } ?: "프로세스 앱"
            }

            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: Message?,
            ): Boolean {
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false
                return runCatching {
                    val capture = createPopupCaptureWebView()
                    transport.webView = capture
                    resultMsg.sendToTarget()
                    true
                }.getOrElse {
                    Toast.makeText(
                        this@DashboardBrowserActivity,
                        "앱 내부 새 창을 만들 수 없습니다: ${shortError(it)}",
                        Toast.LENGTH_LONG,
                    ).show()
                    false
                }
            }

            override fun onCloseWindow(window: WebView?) {
                if (window === webView) finish()
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?,
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback
                val picker = runCatching { fileChooserParams?.createIntent() }.getOrNull()
                    ?: Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "*/*"
                    }
                return try {
                    startActivityForResult(picker, FILE_CHOOSER_REQUEST_CODE)
                    true
                } catch (_: Exception) {
                    fileChooserCallback?.onReceiveValue(null)
                    fileChooserCallback = null
                    Toast.makeText(this@DashboardBrowserActivity, "파일 선택기를 열 수 없습니다.", Toast.LENGTH_LONG).show()
                    false
                }
            }
        }
        webView.setDownloadListener(
            DownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
                enqueueDownload(url, userAgent, contentDisposition, mimeType)
            },
        )

        container.addView(webView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        root.removeAllViews()
        root.addView(
            container,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )

        back.setOnClickListener {
            if (webView.canGoBack()) webView.goBack() else finish()
        }
        reload.setOnClickListener { runCatching { webView.reload() } }
        close.setOnClickListener { finish() }
        webView.loadUrl(initialUri.toString())
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun createPopupCaptureWebView(): WebView {
        var handled = false
        val capture = WebView(this)
        capture.settings.javaScriptEnabled = true
        capture.settings.domStorageEnabled = true
        capture.settings.allowFileAccess = false
        capture.settings.allowContentAccess = true

        fun handle(uri: Uri): Boolean {
            if (handled) return true
            handled = true
            when (uri.scheme?.lowercase()) {
                "http", "https" -> runCatching {
                    startActivity(createIntent(this, uri.toString()))
                }.onFailure {
                    Toast.makeText(
                        this,
                        "앱 내부 새 창을 열 수 없습니다: ${shortError(it)}",
                        Toast.LENGTH_LONG,
                    ).show()
                }
                "mailto", "tel" -> openExternal(uri)
            }
            capture.post { runCatching { capture.destroy() } }
            return true
        }

        capture.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val uri = request?.url ?: return true
                return handle(uri)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                if (handled || url.isNullOrBlank() || url == "about:blank") return
                runCatching { Uri.parse(url) }.getOrNull()?.let { handle(it) }
            }
        }
        return capture
    }

    private fun showStartupError(error: Throwable) {
        runCatching {
            root.removeAllViews()
            val panel = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                setPadding(dp(24), dp(32), dp(24), dp(32))
                setBackgroundColor(Color.WHITE)
            }
            panel.addView(
                textView("프로세스 앱 창을 열지 못했습니다", 18f, true).apply {
                    gravity = Gravity.CENTER
                },
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ),
            )
            panel.addView(
                textView(shortError(error), 13f, false).apply {
                    gravity = Gravity.CENTER
                    setTextColor(colorMuted)
                    setPadding(0, dp(12), 0, dp(20))
                },
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ),
            )
            val close = toolbarButton("닫기").apply { gravity = Gravity.CENTER }
            close.setOnClickListener { finish() }
            panel.addView(
                close,
                LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)),
            )
            root.addView(
                panel,
                FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT,
                ),
            )
        }.onFailure {
            Toast.makeText(this, "프로세스 앱 창 초기화 실패: ${shortError(error)}", Toast.LENGTH_LONG).show()
        }
    }

    private fun shortError(error: Throwable): String {
        val cause = generateSequence(error) { it.cause }.lastOrNull() ?: error
        val name = cause.javaClass.simpleName.ifBlank { cause.javaClass.name }
        val message = cause.message?.takeIf { it.isNotBlank() }
        return if (message == null) name else "$name: $message"
    }

    private fun openExternal(uri: Uri): Boolean = try {
        startActivity(Intent(Intent.ACTION_VIEW, uri))
        true
    } catch (_: Exception) {
        Toast.makeText(this, "링크를 열 수 없습니다.", Toast.LENGTH_SHORT).show()
        true
    }

    private fun enqueueDownload(
        url: String?,
        userAgent: String?,
        contentDisposition: String?,
        mimeType: String?,
    ) {
        if (url.isNullOrBlank()) return
        val uri = runCatching { Uri.parse(url) }.getOrNull() ?: return
        if (uri.scheme !in setOf("http", "https")) return
        val fileName = android.webkit.URLUtil.guessFileName(url, contentDisposition, mimeType)
            .replace('/', '_')
            .replace('\\', '_')
            .ifBlank { "download.bin" }
        runCatching {
            val request = DownloadManager.Request(uri).apply {
                setTitle(fileName)
                setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                if (!mimeType.isNullOrBlank()) setMimeType(mimeType)
                CookieManager.getInstance().getCookie(url)?.takeIf { it.isNotBlank() }?.let {
                    addRequestHeader("Cookie", it)
                }
                if (!userAgent.isNullOrBlank()) addRequestHeader("User-Agent", userAgent)
                setDestinationInExternalFilesDir(
                    this@DashboardBrowserActivity,
                    Environment.DIRECTORY_DOWNLOADS,
                    fileName,
                )
            }
            (getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager).enqueue(request)
            Toast.makeText(this, "다운로드 시작: $fileName", Toast.LENGTH_LONG).show()
        }.onFailure {
            Toast.makeText(this, "다운로드 실패: ${shortError(it)}", Toast.LENGTH_LONG).show()
        }
    }

    @Deprecated("WebView file chooser compatibility")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == FILE_CHOOSER_REQUEST_CODE) {
            val callback = fileChooserCallback
            fileChooserCallback = null
            callback?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data))
            return
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    @Deprecated("WebView history behavior")
    override fun onBackPressed() {
        val current = browser
        if (current != null && current.canGoBack()) current.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        fileChooserCallback?.onReceiveValue(null)
        fileChooserCallback = null
        destroyBrowser()
        super.onDestroy()
    }

    private fun destroyBrowser() {
        browser?.let { webView ->
            browser = null
            runCatching { webView.stopLoading() }
            runCatching { webView.loadUrl("about:blank") }
            runCatching { webView.clearHistory() }
            runCatching { webView.removeAllViews() }
            runCatching { webView.destroy() }
        }
    }

    private fun configureSystemBars() {
        @Suppress("DEPRECATION")
        run {
            window.statusBarColor = colorCanvas
            window.navigationBarColor = colorCanvas
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
            window.insetsController?.setSystemBarsAppearance(mask, mask)
        }
    }

    private fun applySystemBarInsets() {
        root.setOnApplyWindowInsetsListener { _, windowInsets ->
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val insets = windowInsets.getInsets(
                    WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout(),
                )
                root.setPadding(insets.left, insets.top, insets.right, insets.bottom)
            } else {
                @Suppress("DEPRECATION")
                root.setPadding(
                    windowInsets.systemWindowInsetLeft,
                    windowInsets.systemWindowInsetTop,
                    windowInsets.systemWindowInsetRight,
                    windowInsets.systemWindowInsetBottom,
                )
            }
            windowInsets
        }
        root.requestApplyInsets()
    }

    private fun textView(value: String, sizeSp: Float, bold: Boolean): TextView =
        TextView(this).apply {
            text = value
            textSize = sizeSp
            setTextColor(colorInk)
            includeFontPadding = false
            gravity = Gravity.CENTER_VERTICAL
            typeface = Typeface.create("sans-serif", if (bold) Typeface.BOLD else Typeface.NORMAL)
        }

    private fun toolbarButton(label: String): TextView =
        textView(label, 12f, true).apply {
            gravity = Gravity.CENTER
            isClickable = true
            isFocusable = true
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                setColor(Color.WHITE)
                cornerRadius = dp(11).toFloat()
                setStroke(dp(1), colorBorder)
            }
        }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}

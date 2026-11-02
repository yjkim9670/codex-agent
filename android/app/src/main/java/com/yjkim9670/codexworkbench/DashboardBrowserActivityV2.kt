package com.yjkim9670.codexworkbench

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Message
import android.text.TextUtils
import android.view.Gravity
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
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
import java.io.File
import java.net.URL

class DashboardBrowserActivityV2 : Activity() {
    companion object {
        private const val EXTRA_URL = "dashboard_browser_url"
        private const val FILE_CHOOSER_REQUEST_CODE = 7201
        private const val PREFS_NAME = "codex_workbench"
        private const val PREF_WEB_TEXT_ZOOM = "web_text_zoom"
        private const val DEFAULT_WEB_TEXT_ZOOM_PERCENT = 100
        private val USER_AGENT_SUFFIX = "CodexWorkbenchAndroid/${BuildConfig.VERSION_NAME}"
        private const val DOWNLOAD_BRIDGE_SCHEME = "codex-download"
        private const val BLOB_CHUNK_BYTES = 48 * 1024
    }

    private val colorCanvas = Color.rgb(247, 249, 252)
    private val colorInk = Color.rgb(20, 34, 54)
    private val colorMuted = Color.rgb(91, 106, 128)
    private val colorBorder = Color.rgb(221, 227, 236)

    private lateinit var root: FrameLayout
    private var browser: WebView? = null
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var downloads: WebViewDownloadController? = null
    private fun quickRoot(): String = WorkbenchCatalog.normalizeQuickTunnelRoot(
        getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).getString("quick_tunnel_root", null)
    ) ?: WorkbenchCatalog.QUICK_TUNNEL_ROOT

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33) {
            onBackInvokedDispatcher.registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT
            ) { navigateBack() }
        }

        root = FrameLayout(this).apply { setBackgroundColor(Color.WHITE) }
        setContentView(root)
        runCatching { configureSystemBars() }
        runCatching { applySystemBarInsets() }

        val initialUrl = intent.getStringExtra(EXTRA_URL).orEmpty().trim()
        val initialUri = runCatching { Uri.parse(initialUrl) }.getOrNull()
        if (initialUri == null || !WorkbenchCatalog.isAllowedPage(initialUrl, quickRoot())) {
            showStartupError(IllegalArgumentException("Invalid dashboard URL: $initialUrl"))
            return
        }

        runCatching { buildBrowser(initialUri) }
            .onFailure { error ->
                destroyBrowser()
                showStartupError(error)
            }
    }

    @SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
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

        downloads = WebViewDownloadController(this, webView, initialUri.toString()).also { it.install() }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val uri = request?.url ?: return false
                if (!request.isForMainFrame && uri.scheme?.lowercase() in setOf("blob", "data", DOWNLOAD_BRIDGE_SCHEME)) return true
                val active = view ?: webView
                return when (uri.scheme?.lowercase()) {
                    "http", "https" -> if (WorkbenchCatalog.isAllowedPage(uri.toString(), quickRoot())) false else openExternal(uri)
                    "blob", "data" -> {
                        downloads?.handleNavigation(uri)
                        true
                    }
                    DOWNLOAD_BRIDGE_SCHEME -> downloads?.handleNavigation(uri) ?: true
                    "mailto", "tel" -> openExternal(uri)
                    else -> true
                }
            }

            override fun onRenderProcessGone(view: WebView?, detail: android.webkit.RenderProcessGoneDetail?): Boolean {
                downloads?.close()
                downloads = null
                (view?.parent as? ViewGroup)?.removeView(view)
                if (browser === view) browser = null
                view?.destroy()
                showStartupError(IllegalStateException("웹 화면이 종료되었습니다. 다시 접속하세요."))
                return true
            }

            override fun onPageCommitVisible(view: WebView?, url: String?) {
                super.onPageCommitVisible(view, url)
                downloads?.installInterceptor()
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                downloads?.installInterceptor()
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
                    val capture = createPopupCaptureWebView(view ?: webView)
                    transport.webView = capture
                    resultMsg.sendToTarget()
                    true
                }.getOrElse {
                    Toast.makeText(
                        this@DashboardBrowserActivityV2,
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
                    Toast.makeText(this@DashboardBrowserActivityV2, "파일 선택기를 열 수 없습니다.", Toast.LENGTH_LONG).show()
                    false
                }
            }
        }

        container.addView(webView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        root.removeAllViews()
        root.addView(
            container,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )

        back.setOnClickListener { returnToServerSelection() }
        reload.setOnClickListener { runCatching { webView.reload() } }
        close.setOnClickListener { finish() }
        webView.loadUrl(initialUri.toString())
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun createPopupCaptureWebView(sourceWebView: WebView): WebView {
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
                "http", "https" -> if (!WorkbenchCatalog.isAllowedPage(uri.toString(), quickRoot())) {
                    openExternal(uri)
                } else runCatching {
                    startActivity(DashboardBrowserActivity.createIntent(this, uri.toString()))
                }.onFailure {
                    Toast.makeText(
                        this,
                        "앱 내부 새 창을 열 수 없습니다: ${shortError(it)}",
                        Toast.LENGTH_LONG,
                    ).show()
                }
                "blob", "data" -> downloads?.handleNavigation(uri)
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
        root.removeAllViews()
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(24), dp(32), dp(24), dp(32))
            setBackgroundColor(Color.WHITE)
        }
        panel.addView(
            textView("프로세스 앱 창을 열지 못했습니다", 18f, true).apply { gravity = Gravity.CENTER },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT),
        )
        panel.addView(
            textView(shortError(error), 13f, false).apply {
                gravity = Gravity.CENTER
                setTextColor(colorMuted)
                setPadding(0, dp(12), 0, dp(20))
            },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT),
        )
        val close = toolbarButton("닫기").apply { gravity = Gravity.CENTER }
        close.setOnClickListener { finish() }
        panel.addView(close, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)))
        root.addView(
            panel,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT),
        )
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

    private fun returnToServerSelection() {
        startActivity(Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(MainActivity.EXTRA_SHOW_SERVER_SELECTION, true)
        })
        finish()
    }

    @Deprecated("Server selection is the navigation root")
    @SuppressLint("GestureBackNavigation")
    override fun onBackPressed() = navigateBack()

    private fun navigateBack() {
        returnToServerSelection()
    }

    override fun onDestroy() {
        fileChooserCallback?.onReceiveValue(null)
        fileChooserCallback = null
        destroyBrowser()
        super.onDestroy()
    }

    private fun destroyBrowser() {
        downloads?.close()
        downloads = null
        browser?.let { webView ->
            browser = null
            runCatching { webView.removeJavascriptInterface(DownloadClickInterceptor.BRIDGE_NAME) }
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

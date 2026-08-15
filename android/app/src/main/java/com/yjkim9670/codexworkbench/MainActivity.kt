package com.yjkim9670.codexworkbench

import android.annotation.SuppressLint
import android.app.Activity
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
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
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : Activity() {
    companion object {
        private const val PREFS_NAME = "codex_workbench"
        private const val PREF_SERVER_URL = "server_url"
        private const val FILE_CHOOSER_REQUEST_CODE = 7001
        private const val HEALTH_TIMEOUT_MS = 6000
        private const val USER_AGENT_SUFFIX = "CodexWorkbenchAndroid/1.0"
        private const val SPLASH_DURATION_MS = 1100L
    }

    private lateinit var root: FrameLayout
    private var webView: WebView? = null
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var serverBaseUrl: String = ""
    private var splashTransition: Runnable? = null

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

        val savedServer = prefs.getString(PREF_SERVER_URL, "").orEmpty()
        showOpeningScreen(savedServer)
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

    private fun showOpeningScreen(nextServer: String) {
        destroyWebView()
        root.removeAllViews()
        serverBaseUrl = ""

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

        val title = TextView(this).apply {
            text = "코덱스 워크벤치"
            textSize = 30f
            setTextColor(Color.WHITE)
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            letterSpacing = 0.02f
        }
        content.addView(
            title,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(8) },
        )

        val subtitle = TextView(this).apply {
            text = "Workspace · Git · Terminal"
            textSize = 14f
            setTextColor(Color.rgb(184, 226, 237))
            gravity = Gravity.CENTER
        }
        content.addView(
            subtitle,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ),
        )

        splash.addView(
            content,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )
        root.addView(
            splash,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )

        splashTransition?.let { root.removeCallbacks(it) }
        splashTransition = Runnable {
            if (!isFinishing && !isDestroyed) {
                showConnectionScreen(nextServer)
            }
        }.also { root.postDelayed(it, SPLASH_DURATION_MS) }
    }

    private fun showConnectionScreen(initialUrl: String) {
        splashTransition?.let { root.removeCallbacks(it) }
        splashTransition = null
        destroyWebView()
        root.removeAllViews()
        root.setBackgroundColor(Color.WHITE)
        serverBaseUrl = ""

        val scroll = ScrollView(this).apply {
            isFillViewport = true
        }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(24), dp(36), dp(24), dp(36))
        }
        scroll.addView(
            panel,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ),
        )

        val title = TextView(this).apply {
            text = "코덱스 워크벤치"
            textSize = 26f
            setTextColor(Color.rgb(15, 27, 45))
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
        }
        panel.addView(title, matchWrap().apply { bottomMargin = dp(10) })

        val description = TextView(this).apply {
            text = "PC/Mac/Linux에서 실행 중인 Workbench 서버 주소를 입력하세요.\nTailscale HTTPS 주소 사용을 권장합니다."
            textSize = 15f
            setTextColor(Color.rgb(60, 75, 99))
            gravity = Gravity.CENTER
        }
        panel.addView(description, matchWrap().apply { bottomMargin = dp(28) })

        val urlInput = EditText(this).apply {
            hint = "https://workbench.example.ts.net"
            setSingleLine(true)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_VARIATION_URI
            setText(initialUrl)
            textSize = 16f
        }
        panel.addView(
            urlInput,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(12) },
        )

        val connectButton = Button(this).apply {
            text = "연결"
            isAllCaps = false
        }
        panel.addView(
            connectButton,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(52),
            ).apply { bottomMargin = dp(14) },
        )

        val progress = ProgressBar(this).apply {
            visibility = View.GONE
        }
        panel.addView(progress, wrapWrap().apply { bottomMargin = dp(10) })

        val status = TextView(this).apply {
            textSize = 14f
            setTextColor(Color.rgb(107, 122, 144))
            gravity = Gravity.CENTER
        }
        panel.addView(status, matchWrap())

        connectButton.setOnClickListener {
            val normalized = normalizeServerUrl(urlInput.text?.toString().orEmpty())
            if (normalized == null) {
                status.setTextColor(Color.rgb(190, 40, 55))
                status.text = "올바른 http:// 또는 https:// 서버 주소를 입력하세요."
                return@setOnClickListener
            }

            urlInput.setText(normalized)
            connectButton.isEnabled = false
            progress.visibility = View.VISIBLE
            status.setTextColor(
                if (normalized.startsWith("http://", ignoreCase = true)) {
                    Color.rgb(180, 95, 20)
                } else {
                    Color.rgb(60, 75, 99)
                },
            )
            status.text = if (normalized.startsWith("http://", ignoreCase = true)) {
                "HTTP는 로컬 테스트용으로만 권장합니다. /health 연결 확인 중..."
            } else {
                "/health 연결 확인 중..."
            }

            checkWorkbenchHealth(normalized) { ok, message ->
                runOnUiThread {
                    if (isFinishing || isDestroyed) return@runOnUiThread
                    connectButton.isEnabled = true
                    progress.visibility = View.GONE
                    if (ok) {
                        prefs.edit().putString(PREF_SERVER_URL, normalized).apply()
                        showWorkbench(normalized)
                    } else {
                        status.setTextColor(Color.rgb(190, 40, 55))
                        status.text = message
                    }
                }
            }
        }

        root.addView(
            scroll,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )
    }

    private fun normalizeServerUrl(raw: String): String? {
        var value = raw.trim().trimEnd('/')
        if (value.isBlank()) return null
        if (!value.contains("://")) value = "https://$value"

        val uri = runCatching { Uri.parse(value) }.getOrNull() ?: return null
        val scheme = uri.scheme?.lowercase()
        if (scheme != "http" && scheme != "https") return null
        if (uri.host.isNullOrBlank()) return null
        return value
    }

    private fun checkWorkbenchHealth(
        baseUrl: String,
        callback: (Boolean, String) -> Unit,
    ) {
        Thread {
            var connection: HttpURLConnection? = null
            try {
                connection = URL("$baseUrl/health").openConnection() as HttpURLConnection
                connection.requestMethod = "GET"
                connection.connectTimeout = HEALTH_TIMEOUT_MS
                connection.readTimeout = HEALTH_TIMEOUT_MS
                connection.instanceFollowRedirects = false
                connection.setRequestProperty("Accept", "application/json")
                connection.setRequestProperty("User-Agent", USER_AGENT_SUFFIX)

                val code = connection.responseCode
                val body = if (code in 200..299) {
                    connection.inputStream.bufferedReader().use { it.readText() }
                } else {
                    connection.errorStream?.bufferedReader()?.use { it.readText() }.orEmpty()
                }

                if (code in 200..299 && body.contains("codex-workbench", ignoreCase = true)) {
                    callback(true, "연결됨")
                } else {
                    callback(false, "Workbench /health 확인 실패 (HTTP $code). 서버 주소와 접근 권한을 확인하세요.")
                }
            } catch (error: Exception) {
                callback(false, "서버 연결 실패: ${error.message ?: error.javaClass.simpleName}")
            } finally {
                connection?.disconnect()
            }
        }.start()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun showWorkbench(baseUrl: String) {
        root.removeAllViews()
        root.setBackgroundColor(Color.WHITE)
        serverBaseUrl = baseUrl

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.WHITE)
        }

        val toolbar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), 0, dp(8), 0)
            setBackgroundColor(Color.rgb(244, 247, 251))
        }
        val toolbarTitle = TextView(this).apply {
            text = "코덱스 워크벤치"
            textSize = 16f
            setTextColor(Color.rgb(15, 27, 45))
            maxLines = 1
        }
        toolbar.addView(
            toolbarTitle,
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f),
        )

        val reloadButton = Button(this).apply {
            text = "↻"
            textSize = 20f
            minWidth = 0
            minimumWidth = 0
            minHeight = 0
            minimumHeight = 0
            setPadding(dp(12), 0, dp(12), 0)
            contentDescription = "새로고침"
        }
        toolbar.addView(reloadButton, LinearLayout.LayoutParams(dp(52), dp(40)))

        val serverButton = Button(this).apply {
            text = "서버"
            textSize = 13f
            isAllCaps = false
            minWidth = 0
            minimumWidth = 0
            minHeight = 0
            minimumHeight = 0
        }
        toolbar.addView(serverButton, LinearLayout.LayoutParams(dp(64), dp(40)))

        container.addView(
            toolbar,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(48),
            ),
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
                if (scheme == "mailto" || scheme == "tel") {
                    return openExternal(uri)
                }
                return true
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                toolbarTitle.text = view?.title?.takeIf { it.isNotBlank() } ?: "코덱스 워크벤치"
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
                // Never auto-submit credentials from the APK.
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
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f,
            ),
        )

        reloadButton.setOnClickListener { browser.reload() }
        serverButton.setOnClickListener { showConnectionScreen(baseUrl) }

        root.addView(
            container,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )

        browser.loadUrl(baseUrl)
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
            Toast.makeText(
                this,
                "다운로드 시작: $fileName",
                Toast.LENGTH_LONG,
            ).show()
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

    private fun wrapWrap(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        )

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()
}

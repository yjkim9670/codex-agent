from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


main_path = "android/app/src/main/java/com/yjkim9670/codexworkbench/MainActivity.kt"
main = Path(main_path).read_text(encoding="utf-8")
main = main.replace(
    'private const val USER_AGENT_SUFFIX = "CodexWorkbenchAndroid/1.1.9"',
    'private const val USER_AGENT_SUFFIX = "CodexWorkbenchAndroid/1.1.10"',
    1,
)

old_cards = '''        WorkbenchCatalog.targets.forEach { target ->
            val card = simpleText(cardLabel(target), 14f, COLOR_INK, true).apply {
                setPadding(dp(16), dp(13), dp(16), dp(13))
                isClickable = true
                isFocusable = true
                setLineSpacing(dp(3).toFloat(), 1f)
                setOnClickListener {
                    selectedId = target.id
                    refreshCards()
                }
            }
            cards[target.id] = card
            panel.addView(card, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(9) })
        }
        refreshCards()
'''
new_cards = '''        fun addTargetCard(target: WorkbenchTarget) {
            val card = simpleText(cardLabel(target), 14f, COLOR_INK, true).apply {
                setPadding(dp(16), dp(13), dp(16), dp(13))
                isClickable = true
                isFocusable = true
                setLineSpacing(dp(3).toFloat(), 1f)
                setOnClickListener {
                    selectedId = target.id
                    refreshCards()
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
            .filter { !it.isCodexWorkbench }
            .forEach { addTargetCard(it) }

        panel.addView(
            simpleText("Codex Workbench", 12.5f, COLOR_MUTED, true),
            matchWrap().apply { topMargin = dp(8); bottomMargin = dp(7) },
        )
        WorkbenchCatalog.targets
            .filter { it.isCodexWorkbench }
            .forEach { addTargetCard(it) }
        refreshCards()
'''
if old_cards not in main:
    raise RuntimeError("MainActivity target-card block was not found")
main = main.replace(old_cards, new_cards, 1)

pattern = re.compile(
    r'''            override fun onCreateWindow\(\n.*?\n            override fun onShowFileChooser\(''',
    re.S,
)
match = pattern.search(main)
if not match:
    raise RuntimeError("MainActivity onCreateWindow block was not found")
new_popup = '''            override fun onCreateWindow(
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

            override fun onShowFileChooser('''
main = main[:match.start()] + new_popup + main[match.end():]
Path(main_path).write_text(main, encoding="utf-8")

replace_once(
    "android/app/build.gradle.kts",
    'versionCode = ciVersionCode ?: 11\n        versionName = "1.1.9"',
    'versionCode = ciVersionCode ?: 12\n        versionName = "1.1.10"',
)
replace_once(
    "android/app/src/main/java/com/yjkim9670/codexworkbench/TaskNotificationService.kt",
    'private const val USER_AGENT = "CodexWorkbenchAndroid/1.1.9"',
    'private const val USER_AGENT = "CodexWorkbenchAndroid/1.1.10"',
)

manifest_path = Path("android/app/src/main/AndroidManifest.xml")
manifest = manifest_path.read_text(encoding="utf-8")
activity_marker = '''        <activity
            android:name=".MainActivity"'''
activity_block = '''        <activity
            android:name=".DashboardBrowserActivity"
            android:configChanges="keyboardHidden|orientation|screenSize"
            android:exported="false"
            android:windowSoftInputMode="adjustResize" />

        <activity
            android:name=".MainActivity"'''
if activity_marker not in manifest:
    raise RuntimeError("MainActivity manifest marker was not found")
manifest_path.write_text(manifest.replace(activity_marker, activity_block, 1), encoding="utf-8")

activity_source = r'''package com.yjkim9670.codexworkbench

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

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        configureSystemBars()

        val initialUrl = intent.getStringExtra(EXTRA_URL).orEmpty().trim()
        val initialUri = runCatching { Uri.parse(initialUrl) }.getOrNull()
        if (initialUri == null || initialUri.scheme?.lowercase() !in setOf("http", "https")) {
            finish()
            return
        }

        root = FrameLayout(this).apply { setBackgroundColor(Color.WHITE) }
        setContentView(root)
        applySystemBarInsets()

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
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = false
            allowContentAccess = true
            javaScriptCanOpenWindowsAutomatically = true
            setSupportMultipleWindows(true)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            mediaPlaybackRequiresUserGesture = true
            builtInZoomControls = false
            displayZoomControls = false
            useWideViewPort = true
            cacheMode = WebSettings.LOAD_DEFAULT
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) safeBrowsingEnabled = true
            textZoom = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .getInt(PREF_WEB_TEXT_ZOOM, DEFAULT_WEB_TEXT_ZOOM_PERCENT)
                .coerceIn(60, 125)
            userAgentString = "${userAgentString} $USER_AGENT_SUFFIX"
        }
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, false)
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
                val capture = createPopupCaptureWebView()
                transport.webView = capture
                resultMsg.sendToTarget()
                return true
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
        root.addView(container, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT,
        ))

        back.setOnClickListener {
            if (webView.canGoBack()) webView.goBack() else finish()
        }
        reload.setOnClickListener { webView.reload() }
        close.setOnClickListener { finish() }
        webView.loadUrl(initialUri.toString())
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun createPopupCaptureWebView(): WebView {
        var handled = false
        val capture = WebView(this)
        capture.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = true
        }

        fun handle(uri: Uri): Boolean {
            if (handled) return true
            handled = true
            when (uri.scheme?.lowercase()) {
                "http", "https" -> runCatching {
                    startActivity(createIntent(this, uri.toString()))
                }.onFailure {
                    Toast.makeText(this, "앱 내부 새 창을 열 수 없습니다.", Toast.LENGTH_LONG).show()
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
            Toast.makeText(this, "다운로드 실패", Toast.LENGTH_LONG).show()
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
        browser?.let { webView ->
            browser = null
            runCatching { webView.stopLoading() }
            runCatching { webView.loadUrl("about:blank") }
            runCatching { webView.clearHistory() }
            runCatching { webView.removeAllViews() }
            runCatching { webView.destroy() }
        }
        super.onDestroy()
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
'''
activity_path = Path("android/app/src/main/java/com/yjkim9670/codexworkbench/DashboardBrowserActivity.kt")
if activity_path.exists():
    raise RuntimeError("DashboardBrowserActivity.kt already exists")
activity_path.write_text(activity_source, encoding="utf-8")

# Documentation updates.
docs_path = Path("docs/android.md")
docs = docs_path.read_text(encoding="utf-8")
docs = docs.replace(
    '- Mac Process Dashboard의 `target="_blank"` / `window.open()` 요청은 dashboard WebView에서 multi-window 요청으로 받아 Android 외부 브라우저에서 엽니다. Codex Workbench WebView의 기존 popup 정책은 변경하지 않습니다.',
    '- 서버 선택 화면에서 `Mac Process Dashboard`는 최상단 `시스템 대시보드` 그룹에 별도로 표시하고, 5개 Codex Workbench는 그 아래 `Codex Workbench` 그룹에 표시합니다.\n- Mac Process Dashboard의 `target="_blank"` / `window.open()` 요청은 외부 브라우저로 보내지 않고 앱 내부 `DashboardBrowserActivity`의 독립 WebView 인스턴스로 엽니다. 각 인스턴스는 자체 뒤로가기/새로고침/닫기와 추가 popup 생성을 지원합니다. Codex Workbench WebView의 기존 popup 정책은 변경하지 않습니다.',
    1,
)
docs = docs.replace(
    '현재 Android client source fallback 버전은 `1.1.9` (`versionCode 11`)입니다.',
    '현재 Android client source fallback 버전은 `1.1.10` (`versionCode 12`)입니다.',
    1,
)
docs_path.write_text(docs, encoding="utf-8")

# Restore the normal workflow in the resulting source commit and remove this helper.
workflow_path = Path(".github/workflows/android-apk.yml")
workflow = workflow_path.read_text(encoding="utf-8")
workflow = workflow.replace("permissions:\n  contents: write", "permissions:\n  contents: read", 1)
workflow = re.sub(
    r'''\n      - name: Apply dashboard in-app window patch\n        if: github\.ref == 'refs/heads/agent/android-dashboard-inapp-windows'\n        run: python3 \.github/scripts/apply_dashboard_inapp_windows\.py\n''',
    "\n",
    workflow,
    count=1,
)
workflow = re.sub(
    r'''\n      - name: Commit validated dashboard changes\n        if: github\.ref == 'refs/heads/agent/android-dashboard-inapp-windows'\n        shell: bash\n        run: \|\n(?:          .*\n)+?(?=\n      - name: Upload debug APK)''',
    "\n",
    workflow,
    count=1,
)
workflow_path.write_text(workflow, encoding="utf-8")
Path(__file__).unlink()

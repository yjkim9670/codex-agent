package com.yjkim9670.codexworkbench

import android.app.Activity
import android.content.ContentValues
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Base64
import android.webkit.CookieManager
import android.webkit.DownloadListener
import android.webkit.JavascriptInterface
import android.webkit.URLUtil
import android.webkit.WebView
import android.widget.Toast
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

internal class WebViewDownloadController(
    private val activity: Activity,
    private val webView: WebView,
) {
    companion object {
        const val BRIDGE_SCHEME = "codex-download"
        private const val BLOB_CHUNK_BYTES = 48 * 1024
    }

    private data class PendingBlobDownload(
        val fileName: String,
        val mimeType: String?,
        val tempFile: File,
    )

    private val pendingBlobDownloads = mutableMapOf<String, PendingBlobDownload>()
    @Volatile
    private var closed = false

    fun install() {
        if (closed) return
        webView.addJavascriptInterface(DownloadBridge(), DownloadClickInterceptor.BRIDGE_NAME)
        webView.setDownloadListener(
            DownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
                handleDownload(url, userAgent, contentDisposition, mimeType)
            },
        )
        installInterceptor()
    }

    fun installInterceptor() {
        if (closed) return
        DownloadClickInterceptor.install(webView, BRIDGE_SCHEME)
    }

    fun handleNavigation(uri: Uri): Boolean {
        if (closed) return true
        return when (uri.scheme?.lowercase()) {
            "blob", "data" -> {
                handleDownload(
                    uri.toString(),
                    webView.settings.userAgentString,
                    null,
                    null,
                )
                true
            }
            BRIDGE_SCHEME -> handleBridgeRequest(uri)
            else -> false
        }
    }

    fun close() {
        if (closed) return
        closed = true
        runCatching { webView.removeJavascriptInterface(DownloadClickInterceptor.BRIDGE_NAME) }
        runCatching { webView.setDownloadListener(null) }
        val pending = synchronized(pendingBlobDownloads) {
            val values = pendingBlobDownloads.values.toList()
            pendingBlobDownloads.clear()
            values
        }
        pending.forEach { runCatching { it.tempFile.delete() } }
    }

    private inner class DownloadBridge {
        @JavascriptInterface
        fun request(url: String?, fileName: String?, mimeType: String?) {
            val value = url.orEmpty().trim()
            if (value.isBlank() || closed) return
            activity.runOnUiThread {
                if (closed || activity.isFinishing || activity.isDestroyed) return@runOnUiThread
                val safeName = fileName.orEmpty().trim().takeIf { it.isNotBlank() }?.let(::safeFileName)
                val disposition = safeName?.let { "attachment; filename=\"$it\"" }
                handleDownload(
                    value,
                    webView.settings.userAgentString,
                    disposition,
                    mimeType?.takeIf { it.isNotBlank() },
                )
            }
        }

        @JavascriptInterface
        fun blobChunk(token: String?, encoded: String?) {
            if (closed) return
            val id = token.orEmpty()
            val payload = encoded.orEmpty()
            if (id.isBlank() || payload.isBlank()) return
            val pending = synchronized(pendingBlobDownloads) { pendingBlobDownloads[id] } ?: return
            runCatching {
                val bytes = Base64.decode(payload, Base64.DEFAULT)
                synchronized(pending) {
                    FileOutputStream(pending.tempFile, true).use { it.write(bytes) }
                }
            }.onFailure {
                synchronized(pendingBlobDownloads) { pendingBlobDownloads.remove(id) }
                    ?.tempFile
                    ?.delete()
                showDownloadFailed(it)
            }
        }

        @JavascriptInterface
        fun blobFinish(token: String?, resolvedMimeType: String?) {
            if (closed) return
            val id = token.orEmpty()
            val pending = synchronized(pendingBlobDownloads) { pendingBlobDownloads.remove(id) } ?: return
            Thread {
                try {
                    val mime = resolvedMimeType?.takeIf { it.isNotBlank() } ?: pending.mimeType
                    publishTempFile(pending.tempFile, pending.fileName, mime)
                    pending.tempFile.delete()
                    showDownloadCompleted(pending.fileName)
                } catch (error: Throwable) {
                    pending.tempFile.delete()
                    showDownloadFailed(error)
                }
            }.start()
        }

        @JavascriptInterface
        fun blobError(token: String?, message: String?) {
            val id = token.orEmpty()
            synchronized(pendingBlobDownloads) { pendingBlobDownloads.remove(id) }
                ?.tempFile
                ?.delete()
            showDownloadFailed(IOException(message.orEmpty().ifBlank { "blob download failed" }))
        }
    }

    private fun handleBridgeRequest(uri: Uri): Boolean {
        if (!uri.host.equals("request", ignoreCase = true)) return true
        val url = uri.getQueryParameter("url").orEmpty()
        if (url.isBlank()) return true
        val safeName = uri.getQueryParameter("name")
            ?.takeIf { it.isNotBlank() }
            ?.let(::safeFileName)
        val disposition = safeName?.let { "attachment; filename=\"$it\"" }
        handleDownload(
            url,
            webView.settings.userAgentString,
            disposition,
            uri.getQueryParameter("mime")?.takeIf { it.isNotBlank() },
        )
        return true
    }

    private fun handleDownload(
        url: String?,
        userAgent: String?,
        contentDisposition: String?,
        mimeType: String?,
    ) {
        if (url.isNullOrBlank() || closed) return
        val uri = runCatching { Uri.parse(url) }.getOrNull()
        when (uri?.scheme?.lowercase().orEmpty()) {
            "http", "https" -> downloadHttp(url, userAgent, contentDisposition, mimeType)
            "blob" -> downloadBlob(url, contentDisposition, mimeType)
            "data" -> downloadDataUrl(url, contentDisposition, mimeType)
            else -> showDownloadFailed(IOException("Unsupported download URL"))
        }
    }

    private fun downloadHttp(
        url: String,
        userAgent: String?,
        contentDisposition: String?,
        mimeType: String?,
    ) {
        val initialName = safeFileName(URLUtil.guessFileName(url, contentDisposition, mimeType))
        val cookie = runCatching { CookieManager.getInstance().getCookie(url) }.getOrNull()
        val referer = webView.url?.takeIf { it.startsWith("http://") || it.startsWith("https://") }
        val resolvedUserAgent = userAgent?.takeIf { it.isNotBlank() }
            ?: webView.settings.userAgentString

        showDownloadStarted(initialName)
        Thread {
            var connection: HttpURLConnection? = null
            var tempFile: File? = null
            try {
                connection = (URL(url).openConnection() as HttpURLConnection).apply {
                    instanceFollowRedirects = true
                    connectTimeout = 15_000
                    readTimeout = 120_000
                    requestMethod = "GET"
                    doInput = true
                    setRequestProperty("Accept", "*/*")
                    setRequestProperty("Accept-Encoding", "identity")
                    if (!cookie.isNullOrBlank()) setRequestProperty("Cookie", cookie)
                    if (!resolvedUserAgent.isNullOrBlank()) setRequestProperty("User-Agent", resolvedUserAgent)
                    if (!referer.isNullOrBlank()) setRequestProperty("Referer", referer)
                }
                connection.connect()
                val responseCode = connection.responseCode
                if (responseCode !in 200..299) {
                    throw IOException("HTTP $responseCode ${connection.responseMessage.orEmpty()}".trim())
                }

                val responseMime = connection.contentType
                    ?.substringBefore(';')
                    ?.trim()
                    ?.takeIf { it.isNotBlank() }
                    ?: mimeType
                val responseDisposition = connection.getHeaderField("Content-Disposition")
                    ?.takeIf { it.isNotBlank() }
                    ?: contentDisposition
                val finalName = safeFileName(
                    URLUtil.guessFileName(connection.url.toString(), responseDisposition, responseMime),
                )
                tempFile = File.createTempFile("workbench-download-", ".part", activity.cacheDir)
                connection.inputStream.use { input ->
                    FileOutputStream(tempFile).use { output ->
                        input.copyTo(output, 64 * 1024)
                    }
                }
                publishTempFile(tempFile, finalName, responseMime)
                tempFile.delete()
                tempFile = null
                showDownloadCompleted(finalName)
            } catch (error: Throwable) {
                tempFile?.delete()
                showDownloadFailed(error)
            } finally {
                connection?.disconnect()
            }
        }.start()
    }

    private fun downloadDataUrl(
        url: String,
        contentDisposition: String?,
        mimeType: String?,
    ) {
        val initialName = safeFileName(URLUtil.guessFileName("download", contentDisposition, mimeType))
        showDownloadStarted(initialName)
        Thread {
            var tempFile: File? = null
            try {
                val comma = url.indexOf(',')
                if (comma <= 5) throw IOException("Invalid data URL")
                val metadata = url.substring(5, comma)
                val payload = url.substring(comma + 1)
                val resolvedMime = metadata.substringBefore(';')
                    .takeIf { it.isNotBlank() }
                    ?: mimeType
                val bytes = if (metadata.split(';').any { it.equals("base64", ignoreCase = true) }) {
                    Base64.decode(payload, Base64.DEFAULT)
                } else {
                    Uri.decode(payload).toByteArray(Charsets.UTF_8)
                }
                val finalName = safeFileName(
                    URLUtil.guessFileName("download", contentDisposition, resolvedMime),
                )
                tempFile = File.createTempFile("workbench-download-", ".part", activity.cacheDir)
                tempFile.writeBytes(bytes)
                publishTempFile(tempFile, finalName, resolvedMime)
                tempFile.delete()
                tempFile = null
                showDownloadCompleted(finalName)
            } catch (error: Throwable) {
                tempFile?.delete()
                showDownloadFailed(error)
            }
        }.start()
    }

    private fun downloadBlob(
        blobUrl: String,
        contentDisposition: String?,
        mimeType: String?,
    ) {
        val token = UUID.randomUUID().toString()
        val fileName = safeFileName(URLUtil.guessFileName("download", contentDisposition, mimeType))
        val tempFile = runCatching {
            File.createTempFile("workbench-blob-", ".part", activity.cacheDir)
        }.getOrElse {
            showDownloadFailed(it)
            return
        }
        synchronized(pendingBlobDownloads) {
            pendingBlobDownloads[token] = PendingBlobDownload(fileName, mimeType, tempFile)
        }

        val script = """
            (async function() {
              const bridge = window[${JSONObject.quote(DownloadClickInterceptor.BRIDGE_NAME)}];
              if (!bridge) throw new Error('Android download bridge unavailable');
              try {
                const response = await fetch(${JSONObject.quote(blobUrl)});
                const blob = await response.blob();
                const chunkSize = $BLOB_CHUNK_BYTES;
                for (let offset = 0; offset < blob.size; offset += chunkSize) {
                  const slice = blob.slice(offset, Math.min(offset + chunkSize, blob.size));
                  const bytes = new Uint8Array(await slice.arrayBuffer());
                  let binary = '';
                  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
                  bridge.blobChunk(${JSONObject.quote(token)}, btoa(binary));
                }
                bridge.blobFinish(${JSONObject.quote(token)}, blob.type || '');
              } catch (error) {
                bridge.blobError(${JSONObject.quote(token)}, String(error));
              }
            })();
            null;
        """.trimIndent()

        showDownloadStarted(fileName)
        runCatching { webView.evaluateJavascript(script, null) }
            .onFailure {
                synchronized(pendingBlobDownloads) { pendingBlobDownloads.remove(token) }
                    ?.tempFile
                    ?.delete()
                showDownloadFailed(it)
            }
    }

    private fun publishTempFile(tempFile: File, fileName: String, mimeType: String?) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                put(MediaStore.MediaColumns.MIME_TYPE, mimeType ?: "application/octet-stream")
                put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val destination = activity.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: throw IOException("Cannot create a Downloads destination")
            try {
                activity.contentResolver.openOutputStream(destination, "w")?.use { output ->
                    tempFile.inputStream().use { input -> input.copyTo(output, 64 * 1024) }
                } ?: throw IOException("Cannot open the Downloads destination")
                activity.contentResolver.update(
                    destination,
                    ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) },
                    null,
                    null,
                )
            } catch (error: Throwable) {
                runCatching { activity.contentResolver.delete(destination, null, null) }
                throw error
            }
            return
        }

        val directory = activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            ?: throw IOException("Downloads directory is unavailable")
        if (!directory.exists() && !directory.mkdirs()) {
            throw IOException("Cannot create the Downloads directory")
        }
        var destination = File(directory, fileName)
        var suffix = 1
        val dot = fileName.lastIndexOf('.')
        val stem = if (dot > 0) fileName.substring(0, dot) else fileName
        val extension = if (dot > 0) fileName.substring(dot) else ""
        while (destination.exists()) {
            destination = File(directory, "$stem ($suffix)$extension")
            suffix += 1
        }
        tempFile.inputStream().use { input ->
            FileOutputStream(destination).use { output -> input.copyTo(output, 64 * 1024) }
        }
    }

    private fun safeFileName(value: String?): String =
        value.orEmpty()
            .replace('/', '_')
            .replace('\\', '_')
            .replace(':', '_')
            .replace('"', '_')
            .trim()
            .ifBlank { "download.bin" }

    private fun showDownloadStarted(fileName: String) {
        activity.runOnUiThread {
            if (!activity.isFinishing && !activity.isDestroyed) {
                Toast.makeText(activity, "다운로드 시작: $fileName", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun showDownloadCompleted(fileName: String) {
        activity.runOnUiThread {
            if (!activity.isFinishing && !activity.isDestroyed) {
                Toast.makeText(activity, "다운로드 완료: $fileName · Downloads", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun showDownloadFailed(error: Throwable) {
        activity.runOnUiThread {
            if (!activity.isFinishing && !activity.isDestroyed) {
                Toast.makeText(activity, "다운로드 실패: ${shortError(error)}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun shortError(error: Throwable): String {
        val cause = generateSequence(error) { it.cause }.lastOrNull() ?: error
        val name = cause.javaClass.simpleName.ifBlank { cause.javaClass.name }
        val message = cause.message?.takeIf { it.isNotBlank() }
        return if (message == null) name else "$name: $message"
    }
}

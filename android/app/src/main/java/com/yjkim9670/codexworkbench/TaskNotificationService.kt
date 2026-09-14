package com.yjkim9670.codexworkbench

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicBoolean

class TaskNotificationService : Service() {
    companion object {
        private const val ACTION_START = "com.yjkim9670.codexworkbench.action.START_TASK_MONITOR"
        private const val EXTRA_BASE_URL = "base_url"
        private const val EXTRA_LABEL = "workbench_label"
        private const val EXTRA_COOKIE = "cookie"
        private const val PREFS_NAME = "codex_workbench"
        private const val PREF_NOTIFICATIONS_ENABLED = "notifications_enabled"
        private const val MONITOR_CHANNEL_ID = "workbench_task_monitor_silent_v2"
        private const val COMPLETE_CHANNEL_ID = "workbench_task_complete"
        private const val MONITOR_NOTIFICATION_ID = 3101
        private const val COMPLETE_NOTIFICATION_ID = 3102
        private const val POLL_INTERVAL_MS = 5_000L
        private const val IDLE_GRACE_POLLS = 2
        private const val MAX_MONITOR_MS = 4 * 60 * 60 * 1000L
        private val USER_AGENT = "CodexWorkbenchAndroid/${BuildConfig.VERSION_NAME}"

        fun start(context: Context, baseUrl: String, label: String, cookie: String?) {
            if (baseUrl.isBlank()) return
            val intent = Intent(context, TaskNotificationService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_BASE_URL, baseUrl)
                putExtra(EXTRA_LABEL, label)
                putExtra(EXTRA_COOKIE, cookie.orEmpty())
            }
            runCatching {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            }
        }

        fun stop(context: Context) {
            runCatching {
                context.stopService(Intent(context, TaskNotificationService::class.java))
            }
        }
    }

    private val stopRequested = AtomicBoolean(false)
    private var monitorThread: Thread? = null
    private var baseUrl: String = ""
    private var workbenchLabel: String = "코덱스 워크벤치"
    private var cookie: String = ""

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val enabled = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(PREF_NOTIFICATIONS_ENABLED, true)
        if (!enabled) {
            stopSelf()
            return START_NOT_STICKY
        }

        baseUrl = intent?.getStringExtra(EXTRA_BASE_URL).orEmpty().trim()
        workbenchLabel = intent?.getStringExtra(EXTRA_LABEL).orEmpty().ifBlank { "코덱스 워크벤치" }
        cookie = intent?.getStringExtra(EXTRA_COOKIE).orEmpty()
        if (baseUrl.isBlank()) {
            stopSelf()
            return START_NOT_STICKY
        }

        stopRequested.set(false)
        startForeground(MONITOR_NOTIFICATION_ID, buildMonitorNotification())

        if (monitorThread?.isAlive != true) {
            monitorThread = Thread({ monitorLoop() }, "codex-workbench-task-monitor").apply {
                isDaemon = true
                start()
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        stopRequested.set(true)
        monitorThread?.interrupt()
        monitorThread = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun monitorLoop() {
        val startedAt = System.currentTimeMillis()
        var idlePolls = 0
        var seenActiveTask = false
        val observedSessionIds = linkedSetOf<String>()

        while (!stopRequested.get() && System.currentTimeMillis() - startedAt < MAX_MONITOR_MS) {
            val snapshot = fetchStreamSnapshot()
            if (snapshot == null) {
                idlePolls += 1
                if (!seenActiveTask && idlePolls >= IDLE_GRACE_POLLS) break
                sleepPollInterval()
                continue
            }

            if (snapshot.activeStreams.isNotEmpty()) {
                seenActiveTask = true
                idlePolls = 0
                snapshot.activeStreams.values
                    .filter { it.isNotBlank() }
                    .forEach { observedSessionIds.add(it) }
            } else if (!seenActiveTask) {
                idlePolls += 1
                if (idlePolls >= IDLE_GRACE_POLLS) break
            }

            if (seenActiveTask && snapshot.activeStreams.isEmpty() && snapshot.pendingQueueCount <= 0) {
                val sessionLabel = resolveCompletedSessionLabel(observedSessionIds)
                postCompletionNotification(sessionLabel)
                break
            }

            sleepPollInterval()
        }

        stopRequested.set(true)
        stopForegroundCompat()
        stopSelf()
    }

    private data class StreamSnapshot(
        val activeStreams: Map<String, String>,
        val pendingQueueCount: Int,
    )

    private fun fetchStreamSnapshot(): StreamSnapshot? {
        var connection: HttpURLConnection? = null
        return try {
            val endpoint = baseUrl.trimEnd('/') + "/api/codex/streams?include_done=1"
            connection = openJsonConnection(endpoint)

            val code = connection.responseCode
            if (code !in 200..299) return null
            val body = connection.inputStream.bufferedReader().use { it.readText() }
            if (!looksLikeJson(connection.contentType, body)) return null

            val root = JSONObject(body)
            val streams = root.optJSONArray("streams") ?: return StreamSnapshot(emptyMap(), 0)
            val active = linkedMapOf<String, String>()
            var pending = 0
            for (index in 0 until streams.length()) {
                val stream = streams.optJSONObject(index) ?: continue
                val id = stream.optString("id").trim()
                val sessionId = stream.optString("session_id").trim()
                val done = stream.optBoolean("done", false)
                val cancelled = stream.optBoolean("cancelled", false)
                pending = maxOf(pending, stream.optInt("pending_queue_count", 0))
                if (id.isNotBlank() && !done && !cancelled) {
                    active[id] = sessionId
                }
            }
            StreamSnapshot(active, pending)
        } catch (_: Exception) {
            null
        } finally {
            connection?.disconnect()
        }
    }

    private fun resolveCompletedSessionLabel(sessionIds: Set<String>): String? {
        if (sessionIds.isEmpty()) return null
        val titles = fetchSessionTitles(sessionIds)
        val resolved = sessionIds.mapNotNull { sessionId ->
            titles[sessionId]?.trim()?.takeIf { it.isNotBlank() }
        }.distinct()

        if (resolved.isNotEmpty()) {
            return if (resolved.size == 1) {
                resolved.first()
            } else {
                "${resolved.first()} 외 ${resolved.size - 1}개 채팅"
            }
        }

        return if (sessionIds.size == 1) {
            "세션 ${sessionIds.first().take(8)}"
        } else {
            "${sessionIds.size}개 채팅 세션"
        }
    }

    private fun fetchSessionTitles(sessionIds: Set<String>): Map<String, String> {
        var connection: HttpURLConnection? = null
        return try {
            val endpoint = baseUrl.trimEnd('/') + "/api/codex/sessions"
            connection = openJsonConnection(endpoint)

            val code = connection.responseCode
            if (code !in 200..299) return emptyMap()
            val body = connection.inputStream.bufferedReader().use { it.readText() }
            if (!looksLikeJson(connection.contentType, body)) return emptyMap()

            val root = JSONObject(body)
            val sessions = root.optJSONArray("sessions") ?: return emptyMap()
            val result = linkedMapOf<String, String>()
            for (index in 0 until sessions.length()) {
                val session = sessions.optJSONObject(index) ?: continue
                val id = session.optString("id").trim()
                if (id !in sessionIds) continue
                val title = session.optString("title").trim()
                if (title.isNotBlank()) result[id] = title
            }
            result
        } catch (_: Exception) {
            emptyMap()
        } finally {
            connection?.disconnect()
        }
    }

    private fun openJsonConnection(endpoint: String): HttpURLConnection =
        (URL(endpoint).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 7_000
            readTimeout = 7_000
            instanceFollowRedirects = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", USER_AGENT)
            if (cookie.isNotBlank()) setRequestProperty("Cookie", cookie)
        }

    private fun looksLikeJson(contentType: String?, body: String): Boolean =
        contentType.orEmpty().lowercase().contains("json") || body.trimStart().startsWith("{")

    private fun sleepPollInterval() {
        try {
            Thread.sleep(POLL_INTERVAL_MS)
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
            stopRequested.set(true)
        }
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)

        manager.createNotificationChannel(
            NotificationChannel(
                MONITOR_CHANNEL_ID,
                "백그라운드 작업 감시",
                NotificationManager.IMPORTANCE_MIN,
            ).apply {
                description = "실행 중인 Workbench 작업을 백그라운드에서 조용히 확인합니다."
                setShowBadge(false)
                enableLights(false)
                enableVibration(false)
                setSound(null, null)
                lockscreenVisibility = Notification.VISIBILITY_SECRET
            },
        )
        manager.createNotificationChannel(
            NotificationChannel(
                COMPLETE_CHANNEL_ID,
                "작업 완료 알림",
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "코덱스 워크벤치 작업이 완료되면 알려줍니다."
            },
        )
    }

    private fun buildMonitorNotification(): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, MONITOR_CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setSmallIcon(R.drawable.ic_notification_monitor)
            .setContentTitle("코덱스 워크벤치")
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setCategory(Notification.CATEGORY_SERVICE)
            .setVisibility(Notification.VISIBILITY_SECRET)
            .build()
    }

    private fun postCompletionNotification(sessionLabel: String?) {
        val openIntent = PendingIntent.getActivity(
            this,
            1,
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, COMPLETE_CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }

        val content = sessionLabel
            ?.takeIf { it.isNotBlank() }
            ?.let { "채팅: $it" }
            ?: "$workbenchLabel 작업이 완료되었습니다."

        val notification = builder
            .setSmallIcon(R.drawable.ic_notification_task_complete)
            .setContentTitle("작업 완료")
            .setContentText(content)
            .setSubText(shortWorkbenchLabel())
            .setStyle(Notification.BigTextStyle().bigText(content))
            .setContentIntent(openIntent)
            .setAutoCancel(true)
            .setCategory(Notification.CATEGORY_STATUS)
            .build()
        getSystemService(NotificationManager::class.java)
            .notify(COMPLETE_NOTIFICATION_ID, notification)
    }

    private fun shortWorkbenchLabel(): String =
        workbenchLabel
            .removeSuffix(" Codex Workbench")
            .removeSuffix(" Workbench")
            .ifBlank { "코덱스 워크벤치" }

    private fun stopForegroundCompat() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
    }
}

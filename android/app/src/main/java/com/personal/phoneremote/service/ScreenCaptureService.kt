package com.personal.phoneremote.service

import android.app.Activity
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import com.personal.phoneremote.AppState
import com.personal.phoneremote.Hub
import com.personal.phoneremote.Notifications
import com.personal.phoneremote.capture.ScreenCapturer

/**
 * MediaProjection must run in a foreground service of type mediaProjection.
 * The user grants that capture with the system dialog. The token cannot be reused,
 * so each Start screen sharing tap asks again. That is an Android rule.
 */
class ScreenCaptureService : Service() {
    private var capturer: ScreenCapturer? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = Notifications.build(
            this,
            "Screen sharing",
            "Phone Remote is capturing your screen",
            stopSharing = true,
        )
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
        when (intent?.action) {
            ACTION_STOP -> {
                stopCapture()
                return START_NOT_STICKY
            }
            ACTION_START -> startCapture(intent)
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        Hub.onCaptureStopped = null
        capturer?.stop()
        if (Hub.capturer === capturer) Hub.capturer = null
        capturer = null
        super.onDestroy()
    }

    private fun startCapture(intent: Intent) {
        val code = intent.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED)
        val data = if (Build.VERSION.SDK_INT >= 33) {
            intent.getParcelableExtra(EXTRA_DATA, Intent::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableExtra(EXTRA_DATA)
        }
        if (code != Activity.RESULT_OK || data == null) {
            AppState.log("Screen capture permission was not granted")
            stopCapture()
            return
        }
        capturer?.stop()
        val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val projection = try {
            manager.getMediaProjection(code, data)
        } catch (error: Exception) {
            AppState.log("Android did not start screen capture. ${error.message}")
            null
        }
        if (projection == null) {
            AppState.log("Android did not provide a screen capture token. Try Start screen sharing again.")
            stopCapture()
            return
        }
        Hub.onCaptureStopped = { stopCapture() }
        val created = ScreenCapturer(this) { frame -> Hub.server?.sendBinary(frame) }
        capturer = created
        Hub.capturer = created
        created.start(projection)
    }

    private fun stopCapture() {
        Hub.onCaptureStopped = null
        capturer?.stop()
        if (Hub.capturer === capturer) Hub.capturer = null
        capturer = null
        AppState.update { it.copy(sharing = false, statusLine = if (Hub.isAuthed()) "Connected" else it.statusLine) }
        if (Build.VERSION.SDK_INT >= 24) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        stopSelf()
    }

    companion object {
        const val ACTION_START = "com.personal.phoneremote.START_CAPTURE"
        const val ACTION_STOP = "com.personal.phoneremote.STOP_CAPTURE"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_DATA = "result_data"
        private const val NOTIFICATION_ID = 12
    }
}

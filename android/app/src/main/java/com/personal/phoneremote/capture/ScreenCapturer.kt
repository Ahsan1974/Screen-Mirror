package com.personal.phoneremote.capture

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.Point
import android.graphics.Rect
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.view.Display
import android.view.WindowManager
import com.personal.phoneremote.AppState
import com.personal.phoneremote.Hub
import com.personal.phoneremote.net.Protocol
import java.io.ByteArrayOutputStream

/**
 * Captures the phone screen with MediaProjection and sends JPEG frames.
 *
 * Android only allows this after the user accepts the system screen-share dialog.
 * The capture runs in a foreground service of type mediaProjection. There is no
 * way for a normal app to record the screen without that consent, and this class
 * does not try to.
 */
class ScreenCapturer(
    private val context: Context,
    private val sendFrame: (ByteArray) -> Unit,
) {
    private var projection: MediaProjection? = null
    private var reader: ImageReader? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    private var srcBitmap: Bitmap? = null
    private var dstBitmap: Bitmap? = null
    private val jpegBuffer = ByteArrayOutputStream(256 * 1024)
    private val swapPaint = Paint().apply {
        colorFilter = ColorMatrixColorFilter(
            ColorMatrix(
                floatArrayOf(
                    0f, 0f, 1f, 0f, 0f,
                    0f, 1f, 0f, 0f, 0f,
                    1f, 0f, 0f, 0f, 0f,
                    0f, 0f, 0f, 1f, 0f,
                ),
            ),
        )
    }
    private var lastFrameMs = 0L
    private var running = false
    private var stopping = false
    private var listening = false
    private var restartScheduled = false

    val isRunning: Boolean
        get() = running

    private val displayListener = object : DisplayManager.DisplayListener {
        override fun onDisplayChanged(displayId: Int) {
            if (displayId != Display.DEFAULT_DISPLAY || restartScheduled || !running) return
            restartScheduled = true
            handler?.postDelayed({
                restartScheduled = false
                if (running) openDisplay()
            }, 300)
        }

        override fun onDisplayAdded(displayId: Int) = Unit
        override fun onDisplayRemoved(displayId: Int) = Unit
    }

    fun start(mediaProjection: MediaProjection) {
        stop()
        stopping = false
        projection = mediaProjection
        // Android 14 throws if this callback is missing before the virtual display is created.
        mediaProjection.registerCallback(
            object : MediaProjection.Callback() {
                override fun onStop() {
                    // The system cast chip calls this. projection.stop() also calls it,
                    // so local stop() clears `projection` first and this becomes a no-op.
                    releaseAfterSystemStop()
                }
            },
            Handler(Looper.getMainLooper()),
        )
        thread = HandlerThread("screen-capture").also { it.start() }
        handler = Handler(thread!!.looper)
        running = true
        val displays = context.getSystemService(DisplayManager::class.java)
        displays.registerDisplayListener(displayListener, handler)
        listening = true
        openDisplay()
        AppState.update { it.copy(sharing = true, statusLine = "Sharing your screen") }
        Hub.server?.sendStreamState(true)
        AppState.log("Screen capture started")
    }

    fun applyConfig() {
        handler?.post {
            if (running) openDisplay()
        }
    }

    fun stop() {
        if (stopping) return
        stopping = true
        running = false
        unregisterDisplayListener()
        releaseDisplay()
        val current = projection
        projection = null
        try {
            current?.stop()
        } catch (_: Exception) {
        }
        quitThread()
        stopping = false
    }

    private fun releaseAfterSystemStop() {
        if (stopping || projection == null) return
        stopping = true
        running = false
        unregisterDisplayListener()
        releaseDisplay()
        projection = null
        quitThread()
        stopping = false
        AppState.update { it.copy(sharing = false, statusLine = "Screen sharing stopped") }
        Hub.server?.sendStreamState(false)
        AppState.log("Screen sharing was stopped")
        Hub.onCaptureStopped?.invoke()
    }

    private fun unregisterDisplayListener() {
        if (!listening) return
        try {
            context.getSystemService(DisplayManager::class.java).unregisterDisplayListener(displayListener)
        } catch (_: Exception) {
        }
        listening = false
    }

    private fun quitThread() {
        thread?.quitSafely()
        thread = null
        handler = null
        srcBitmap?.recycle()
        dstBitmap?.recycle()
        srcBitmap = null
        dstBitmap = null
    }

    private fun releaseDisplay() {
        virtualDisplay?.release()
        virtualDisplay = null
        reader?.setOnImageAvailableListener(null, null)
        reader?.close()
        reader = null
    }

    private fun openDisplay() {
        val current = projection ?: return
        if (!running) return
        releaseDisplay()
        val (screenW, screenH) = screenSize(context)
        val config = Hub.stream
        val (captureW, captureH) = fit(screenW, screenH, config.maxWidth, config.maxHeight)
        val imageReader = ImageReader.newInstance(captureW, captureH, PixelFormat.RGBA_8888, 2)
        imageReader.setOnImageAvailableListener(
            { source -> onImage(source, captureW, captureH, screenW, screenH) },
            handler,
        )
        reader = imageReader
        virtualDisplay = current.createVirtualDisplay(
            "phone-remote",
            captureW,
            captureH,
            context.resources.displayMetrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader.surface,
            null,
            handler,
        )
        if (virtualDisplay == null) {
            Log.e(TAG, "Virtual display was not created")
        }
    }

    private fun onImage(source: ImageReader, captureW: Int, captureH: Int, screenW: Int, screenH: Int) {
        val image = try {
            source.acquireLatestImage()
        } catch (_: Exception) {
            null
        } ?: return
        try {
            if (!running || !Hub.isAuthed() || Hub.transfersBusy) return
            val interval = 1000L / Hub.stream.fps.coerceAtLeast(1)
            val now = SystemClock.elapsedRealtime()
            if (now - lastFrameMs < interval) return
            val jpeg = encode(image, captureW, captureH) ?: return
            lastFrameMs = now
            Hub.frameCount.incrementAndGet()
            sendFrame(Protocol.packFrame(captureW, captureH, screenW, screenH, System.currentTimeMillis(), jpeg))
        } finally {
            image.close()
        }
    }

    /**
     * ImageReader gives RGBA with row padding. Bitmap.copyPixelsFromBuffer matches that
     * layout on current Android versions. The red/blue swap is a manual escape hatch
     * for the rare device where the bytes come out reversed.
     */
    private fun encode(image: Image, width: Int, height: Int): ByteArray? {
        val planes = image.planes
        if (planes.isEmpty()) return null
        val plane = planes[0]
        val buffer = plane.buffer
        val pixelStride = plane.pixelStride
        val rowStride = plane.rowStride
        if (pixelStride != 4 || rowStride < width * pixelStride) return null
        val padded = rowStride / pixelStride
        if (buffer.remaining() < rowStride * height) return null
        return try {
            val source = bitmap(padded, height, source = true)
            buffer.rewind()
            source.copyPixelsFromBuffer(buffer)
            val quality = Hub.stream.quality.coerceIn(30, 90)
            val output = if (padded == width && !Hub.swapRedBlue) {
                source
            } else {
                val destination = bitmap(width, height, source = false)
                Canvas(destination).drawBitmap(
                    source,
                    Rect(0, 0, width, height),
                    Rect(0, 0, width, height),
                    if (Hub.swapRedBlue) swapPaint else null,
                )
                destination
            }
            jpegBuffer.reset()
            if (!output.compress(Bitmap.CompressFormat.JPEG, quality, jpegBuffer)) return null
            jpegBuffer.toByteArray()
        } catch (error: Exception) {
            Log.w(TAG, "Could not encode a frame", error)
            null
        }
    }

    private fun bitmap(width: Int, height: Int, source: Boolean): Bitmap {
        val current = if (source) srcBitmap else dstBitmap
        if (current != null && !current.isRecycled && current.width == width && current.height == height) {
            return current
        }
        current?.recycle()
        val created = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        if (source) srcBitmap = created else dstBitmap = created
        return created
    }

    companion object {
        private const val TAG = "PhoneRemote"

        fun screenSize(context: Context): Pair<Int, Int> {
            val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
            return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val bounds = windowManager.currentWindowMetrics.bounds
                bounds.width() to bounds.height()
            } else {
                val point = Point()
                @Suppress("DEPRECATION")
                windowManager.defaultDisplay.getRealSize(point)
                point.x to point.y
            }
        }
    }
}

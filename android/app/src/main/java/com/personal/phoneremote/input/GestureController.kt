package com.personal.phoneremote.input

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.Handler
import android.os.Looper
import com.personal.phoneremote.capture.ScreenCapturer
import kotlin.math.hypot

/**
 * Turns laptop pointer events into AccessibilityService gestures.
 *
 * dispatchGesture is the supported API for an app the user enabled in
 * Accessibility settings. It is not available to a normal foreground app,
 * and this code does not use hidden input-injection APIs.
 *
 * A right-click with no drag becomes a long press. A drag continues one stroke
 * so the finger stays down until the laptop releases the button.
 */
class GestureController(private val service: AccessibilityService) {
    private val handler = Handler(Looper.getMainLooper())
    private val queue = ArrayDeque<Op>()
    private var stroke: GestureDescription.StrokeDescription? = null
    private var busy = false
    private var dragging = false
    private var button = "left"
    private var downX = 0f
    private var downY = 0f
    private var lastX = 0f
    private var lastY = 0f

    fun onMouse(action: String, x: Float, y: Float, button: String) {
        val (screenW, screenH) = ScreenCapturer.screenSize(service)
        val clampedX = x.coerceIn(0f, (screenW - 1).coerceAtLeast(0).toFloat())
        val clampedY = y.coerceIn(0f, (screenH - 1).coerceAtLeast(0).toFloat())
        when (action) {
            "down" -> {
                queue.clear()
                stroke = null
                dragging = false
                this.button = button
                downX = clampedX
                downY = clampedY
                lastX = clampedX
                lastY = clampedY
            }
            "move" -> {
                if (button == "right") return
                if (!dragging && hypot(clampedX - downX, clampedY - downY) < SLOP) {
                    lastX = clampedX
                    lastY = clampedY
                    return
                }
                queue.removeAll { it is Op.Move }
                queue.add(Op.Move(clampedX, clampedY))
                drain()
            }
            "up" -> {
                queue.removeAll { it is Op.Move }
                queue.add(Op.Up(clampedX, clampedY))
                drain()
            }
        }
    }

    private fun drain() {
        if (busy) return
        val op = queue.removeFirstOrNull() ?: return
        val gesture = when (op) {
            is Op.Move -> buildMove(op.x, op.y)
            is Op.Up -> buildUp(op.x, op.y)
        }
        if (gesture == null) {
            drain()
            return
        }
        busy = true
        val accepted = service.dispatchGesture(
            gesture,
            object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) {
                    busy = false
                    handler.post { drain() }
                }

                override fun onCancelled(gestureDescription: GestureDescription?) {
                    stroke = null
                    dragging = false
                    busy = false
                    queue.clear()
                }
            },
            handler,
        )
        if (!accepted) {
            busy = false
            stroke = null
            dragging = false
            InputErrors.report(
                "accessibility_disabled",
                service.getString(com.personal.phoneremote.R.string.accessibility_required),
            )
        }
    }

    private fun buildMove(x: Float, y: Float): GestureDescription? {
        val path = Path()
        val next = if (!dragging) {
            path.moveTo(downX, downY)
            path.lineTo(x, y)
            GestureDescription.StrokeDescription(path, 0, SEGMENT_MS, true)
        } else {
            val current = stroke ?: return null
            path.moveTo(lastX, lastY)
            path.lineTo(x, y)
            current.continueStroke(path, 0, SEGMENT_MS, true)
        }
        stroke = next
        dragging = true
        lastX = x
        lastY = y
        return GestureDescription.Builder().addStroke(next).build()
    }

    private fun buildUp(x: Float, y: Float): GestureDescription? {
        if (!dragging) {
            val path = Path().apply {
                moveTo(x, y)
                lineTo(x + 1f, y + 1f)
            }
            val duration = if (button == "right") LONG_PRESS_MS else TAP_MS
            val tap = GestureDescription.StrokeDescription(path, 0, duration, false)
            stroke = null
            return GestureDescription.Builder().addStroke(tap).build()
        }
        val current = stroke ?: return null
        val path = Path().apply {
            moveTo(lastX, lastY)
            if (lastX == x && lastY == y) lineTo(x + 1f, y) else lineTo(x, y)
        }
        val end = current.continueStroke(path, 0, SEGMENT_MS, false)
        stroke = null
        dragging = false
        lastX = x
        lastY = y
        return GestureDescription.Builder().addStroke(end).build()
    }

    private sealed class Op {
        data class Move(val x: Float, val y: Float) : Op()
        data class Up(val x: Float, val y: Float) : Op()
    }

    companion object {
        private const val SLOP = 10f
        private const val SEGMENT_MS = 30L
        private const val TAP_MS = 50L
        private const val LONG_PRESS_MS = 600L
    }
}

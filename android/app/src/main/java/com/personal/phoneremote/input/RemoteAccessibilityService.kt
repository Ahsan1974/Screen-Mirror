package com.personal.phoneremote.input

import android.accessibilityservice.AccessibilityService
import android.content.ComponentName
import android.content.Context
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.personal.phoneremote.AppState
import com.personal.phoneremote.Hub
import com.personal.phoneremote.R
import com.personal.phoneremote.clipboard.ClipboardSync
import org.json.JSONObject

/**
 * The only supported way for this app to tap, type, and press Back/Home/Recents.
 * The user turns it on in system settings. The service does not turn itself on.
 */
class RemoteAccessibilityService : AccessibilityService() {
    private val main = Handler(Looper.getMainLooper())
    private lateinit var gestures: GestureController
    private lateinit var text: TextController

    override fun onServiceConnected() {
        super.onServiceConnected()
        gestures = GestureController(this)
        text = TextController(this)
        instance = this
        AppState.update { it.copy(accessibilityEnabled = true) }
        AppState.log("Accessibility service connected")
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        AppState.update { it.copy(accessibilityEnabled = false) }
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit

    override fun onInterrupt() = Unit

    fun handleMouse(action: String, x: Float, y: Float, button: String) {
        main.post { gestures.onMouse(action, x, y, button) }
    }

    fun handleKey(key: String) {
        main.post { text.handle(key) }
    }

    fun insertText(text: String) {
        main.post {
            val clean = text.take(20_000)
            if (clean.isEmpty()) return@post
            if (RemoteInputMethod.instance?.commit(clean) == true) {
                reportInserted(clean.length)
                return@post
            }
            if (pasteWithAccessibility(clean)) {
                reportInserted(clean.length)
                return@post
            }
            ClipboardSync.write(this, clean)
            InputErrors.report("input_failed", getString(R.string.keyboard_required))
        }
    }

    fun sendScreenText() {
        main.post {
            val root = rootInActiveWindow
            if (root == null) {
                InputErrors.report("screen_text", getString(R.string.screen_text_empty))
                return@post
            }
            val selected = StringBuilder()
            val lines = ArrayList<String>()
            collectText(root, lines, selected, 0)
            root.recycle()
            val text = (if (selected.isNotEmpty()) selected.toString() else lines.joinToString("\n"))
                .take(20_000)
            if (text.isBlank()) {
                InputErrors.report("screen_text", getString(R.string.screen_text_empty))
                return@post
            }
            Hub.server?.sendClipboardText(text)
            AppState.log("Sent on-screen text to the laptop (${text.length} characters)")
        }
    }

    private fun reportInserted(length: Int) {
        AppState.log("Sent text into the focused field ($length characters)")
        Hub.server?.sendText(
            JSONObject().put("type", "status").put("message", "Sent into the phone"),
        )
    }

    private fun pasteWithAccessibility(text: String): Boolean {
        val root = rootInActiveWindow ?: return false
        try {
            val node = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: return false
            try {
                if (!node.isEditable) return false
                val original = node.text?.toString() ?: ""
                var start = node.textSelectionStart
                var end = node.textSelectionEnd
                if (start < 0 || end < 0) {
                    start = original.length
                    end = original.length
                }
                if (start > end) {
                    val swap = start
                    start = end
                    end = swap
                }
                start = start.coerceIn(0, original.length)
                end = end.coerceIn(0, original.length)
                val updated = original.substring(0, start) + text + original.substring(end)
                val args = Bundle()
                args.putCharSequence(
                    AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                    updated,
                )
                if (node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) return true
                ClipboardSync.write(this, text)
                return node.performAction(AccessibilityNodeInfo.ACTION_PASTE)
            } finally {
                node.recycle()
            }
        } finally {
            root.recycle()
        }
    }

    private fun collectText(
        node: AccessibilityNodeInfo,
        lines: MutableList<String>,
        selected: StringBuilder,
        depth: Int,
    ) {
        if (depth > 40 || lines.size > 400) return
        val raw = node.text?.toString().orEmpty()
        val value = raw.trim()
        val start = node.textSelectionStart
        val end = node.textSelectionEnd
        if (selected.isEmpty() && start >= 0 && end > start && end <= raw.length) {
            selected.append(raw.substring(start, end))
        }
        if (value.length > 1 && lines.lastOrNull() != value) lines.add(value)
        for (index in 0 until node.childCount) {
            val child = node.getChild(index) ?: continue
            collectText(child, lines, selected, depth + 1)
            child.recycle()
        }
    }

    fun handleNav(action: String) {
        main.post {
            val global = when (action) {
                "BACK" -> GLOBAL_ACTION_BACK
                "HOME" -> GLOBAL_ACTION_HOME
                "RECENTS" -> GLOBAL_ACTION_RECENTS
                else -> return@post
            }
            performGlobalAction(global)
        }
    }

    companion object {
        @Volatile
        var instance: RemoteAccessibilityService? = null

        fun isEnabled(context: Context): Boolean {
            val expected = ComponentName(context, RemoteAccessibilityService::class.java).flattenToString()
            val enabled = Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            ) ?: return false
            return enabled.split(':').any { it.equals(expected, ignoreCase = true) }
        }
    }
}

package com.personal.phoneremote.input

import android.accessibilityservice.AccessibilityService
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.accessibility.AccessibilityNodeInfo
import com.personal.phoneremote.R

/**
 * Types into the focused field with ACTION_SET_TEXT.
 *
 * Android does not let a normal app inject key events. Games, browsers, and
 * custom views that hide their text from accessibility will not receive keys.
 * Escape is performed as the Back global action because KEYCODE_ESCAPE cannot
 * be injected. That behavior is intentional and documented for the user.
 */
class TextController(private val service: AccessibilityService) {
    fun handle(key: String) {
        when (key) {
            "ESCAPE" -> service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
            "LEFT" -> move(forward = false, line = false)
            "RIGHT" -> move(forward = true, line = false)
            "UP" -> move(forward = false, line = true)
            "DOWN" -> move(forward = true, line = true)
            else -> type(key)
        }
    }

    private fun type(key: String) {
        val node = focused() ?: run {
            InputErrors.report("accessibility_disabled", service.getString(R.string.accessibility_required))
            return
        }
        if (key == "ENTER" && tryImeEnter(node)) return
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
        val updated: String
        val cursor: Int
        when (key) {
            "BACKSPACE" -> {
                if (start != end) {
                    updated = original.removeRange(start, end)
                    cursor = start
                } else if (start > 0) {
                    updated = original.removeRange(start - 1, start)
                    cursor = start - 1
                } else {
                    updated = original
                    cursor = start
                }
            }
            "DELETE" -> {
                if (start != end) {
                    updated = original.removeRange(start, end)
                    cursor = start
                } else if (end < original.length) {
                    updated = original.removeRange(end, end + 1)
                    cursor = start
                } else {
                    updated = original
                    cursor = start
                }
            }
            "SPACE" -> {
                val inserted = insert(original, start, end, " ")
                updated = inserted.first
                cursor = inserted.second
            }
            "ENTER" -> {
                val inserted = insert(original, start, end, "\n")
                updated = inserted.first
                cursor = inserted.second
            }
            else -> {
                if (key.length != 1) {
                    InputErrors.report("key_unsupported", "The key $key is not supported.")
                    return
                }
                val inserted = insert(original, start, end, key)
                updated = inserted.first
                cursor = inserted.second
            }
        }
        val args = Bundle()
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, updated)
        val wrote = node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
        if (!wrote) {
            InputErrors.report(
                "input_failed",
                "This field does not accept typing from Phone Remote. Tap a normal text field on the phone.",
            )
            return
        }
        val selection = Bundle()
        selection.putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, cursor)
        selection.putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, cursor)
        node.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, selection)
    }

    private fun tryImeEnter(node: AccessibilityNodeInfo): Boolean {
        val multiline = (node.inputType and InputType.TYPE_TEXT_FLAG_MULTI_LINE) != 0
        if (multiline || Build.VERSION.SDK_INT < 30) return false
        return node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id)
    }

    private fun move(forward: Boolean, line: Boolean) {
        val node = focused() ?: run {
            InputErrors.report("accessibility_disabled", service.getString(R.string.accessibility_required))
            return
        }
        val granularity = if (line) {
            AccessibilityNodeInfo.MOVEMENT_GRANULARITY_LINE
        } else {
            AccessibilityNodeInfo.MOVEMENT_GRANULARITY_CHARACTER
        }
        val action = if (forward) {
            AccessibilityNodeInfo.ACTION_NEXT_AT_MOVEMENT_GRANULARITY
        } else {
            AccessibilityNodeInfo.ACTION_PREVIOUS_AT_MOVEMENT_GRANULARITY
        }
        val args = Bundle()
        args.putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_MOVEMENT_GRANULARITY_INT, granularity)
        args.putBoolean(AccessibilityNodeInfo.ACTION_ARGUMENT_EXTEND_SELECTION_BOOLEAN, false)
        if (node.performAction(action, args)) return
        val text = node.text?.toString() ?: return
        var cursor = node.textSelectionStart
        if (cursor < 0) cursor = text.length
        cursor = if (forward) (cursor + 1).coerceAtMost(text.length) else (cursor - 1).coerceAtLeast(0)
        val selection = Bundle()
        selection.putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, cursor)
        selection.putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, cursor)
        node.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, selection)
    }

    private fun focused(): AccessibilityNodeInfo? {
        val root = service.rootInActiveWindow ?: return null
        val focus = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        return if (focus != null && focus.isEditable) focus else null
    }

    private fun insert(original: String, start: Int, end: Int, text: String): Pair<String, Int> {
        return original.substring(0, start) + text + original.substring(end) to (start + text.length)
    }
}

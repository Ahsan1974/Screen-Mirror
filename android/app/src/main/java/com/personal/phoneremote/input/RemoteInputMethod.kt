package com.personal.phoneremote.input

import android.inputmethodservice.InputMethodService
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.InputConnection
import android.widget.TextView
import com.personal.phoneremote.R

/**
 * Keyboard the user selects so laptop text can enter any focused field,
 * including ChatGPT's reply box, which refuses accessibility typing.
 */
class RemoteInputMethod : InputMethodService() {
    override fun onCreate() {
        super.onCreate()
        instance = this
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onEvaluateFullscreenMode(): Boolean = false

    override fun onCreateInputView(): View {
        return TextView(this).apply {
            text = getString(R.string.keyboard_strip)
            setPadding(28, 18, 28, 18)
            setTextColor(0xFFFFFFFF.toInt())
            setBackgroundColor(0xFF0C6B66.toInt())
        }
    }

    fun apply(key: String): Boolean {
        val input = currentInputConnection ?: return false
        when (key) {
            "BACKSPACE" -> input.deleteSurroundingText(1, 0)
            "DELETE" -> input.deleteSurroundingText(0, 1)
            "ENTER" -> keyEvent(input, KeyEvent.KEYCODE_ENTER)
            "NEWLINE" -> input.commitText("\n", 1)
            "SPACE" -> input.commitText(" ", 1)
            "LEFT" -> keyEvent(input, KeyEvent.KEYCODE_DPAD_LEFT)
            "RIGHT" -> keyEvent(input, KeyEvent.KEYCODE_DPAD_RIGHT)
            "UP" -> keyEvent(input, KeyEvent.KEYCODE_DPAD_UP)
            "DOWN" -> keyEvent(input, KeyEvent.KEYCODE_DPAD_DOWN)
            else -> {
                if (key.length != 1) return false
                input.commitText(key, 1)
            }
        }
        return true
    }

    fun commit(text: String): Boolean {
        val input = currentInputConnection ?: return false
        if (text.isEmpty()) return false
        return input.commitText(text, 1)
    }

    private fun keyEvent(input: InputConnection, code: Int) {
        val now = android.os.SystemClock.uptimeMillis()
        input.sendKeyEvent(KeyEvent(now, now, KeyEvent.ACTION_DOWN, code, 0))
        input.sendKeyEvent(KeyEvent(now, now, KeyEvent.ACTION_UP, code, 0))
    }

    companion object {
        @Volatile
        var instance: RemoteInputMethod? = null
    }
}

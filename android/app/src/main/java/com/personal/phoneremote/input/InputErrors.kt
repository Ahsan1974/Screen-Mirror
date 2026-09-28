package com.personal.phoneremote.input

import android.os.SystemClock
import com.personal.phoneremote.Hub
import org.json.JSONObject

/** Avoid flooding the laptop when the user moves the mouse and accessibility is off. */
object InputErrors {
    private var lastMs = 0L

    fun report(code: String, message: String) {
        val now = SystemClock.elapsedRealtime()
        if (now - lastMs < 3000) return
        lastMs = now
        Hub.server?.sendText(
            JSONObject()
                .put("type", "error")
                .put("code", code)
                .put("message", message),
        )
    }
}

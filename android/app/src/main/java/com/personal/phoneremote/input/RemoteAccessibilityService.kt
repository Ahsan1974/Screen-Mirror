package com.personal.phoneremote.input

import android.accessibilityservice.AccessibilityService
import android.content.ComponentName
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import com.personal.phoneremote.AppState

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

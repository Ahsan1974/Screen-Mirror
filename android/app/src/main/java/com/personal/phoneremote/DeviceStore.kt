package com.personal.phoneremote

import android.content.Context
import java.util.UUID

/** Local name, port, and the one pairing token. Nothing here is an account. */
class DeviceStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("phone_remote", Context.MODE_PRIVATE)

    val phoneId: String = prefs.getString(KEY_ID, null) ?: UUID.randomUUID().toString().also { created ->
        prefs.edit().putString(KEY_ID, created).apply()
    }

    var phoneName: String
        get() = prefs.getString(KEY_NAME, "My Phone")?.ifBlank { "My Phone" } ?: "My Phone"
        set(value) {
            prefs.edit().putString(KEY_NAME, value.trim().ifBlank { "My Phone" }.take(40)).apply()
        }

    var port: Int
        get() = prefs.getInt(KEY_PORT, DEFAULT_PORT)
        set(value) {
            prefs.edit().putInt(KEY_PORT, value).apply()
        }

    var token: String
        get() = prefs.getString(KEY_TOKEN, "") ?: ""
        set(value) {
            prefs.edit().putString(KEY_TOKEN, value).apply()
        }

    var laptopId: String
        get() = prefs.getString(KEY_LAPTOP_ID, "") ?: ""
        private set(value) {
            prefs.edit().putString(KEY_LAPTOP_ID, value).apply()
        }

    var laptopName: String
        get() = prefs.getString(KEY_LAPTOP_NAME, "") ?: ""
        private set(value) {
            prefs.edit().putString(KEY_LAPTOP_NAME, value).apply()
        }

    var swapRedBlue: Boolean
        get() = prefs.getBoolean(KEY_SWAP, false)
        set(value) {
            prefs.edit().putBoolean(KEY_SWAP, value).apply()
        }

    val isPaired: Boolean
        get() = token.isNotEmpty()

    fun savePairing(id: String, name: String, newToken: String) {
        prefs.edit()
            .putString(KEY_LAPTOP_ID, id)
            .putString(KEY_LAPTOP_NAME, name)
            .putString(KEY_TOKEN, newToken)
            .apply()
    }

    fun clearPairing() {
        prefs.edit()
            .remove(KEY_LAPTOP_ID)
            .remove(KEY_LAPTOP_NAME)
            .remove(KEY_TOKEN)
            .apply()
    }

    companion object {
        const val DEFAULT_PORT = 8765
        private const val KEY_ID = "phone_id"
        private const val KEY_NAME = "phone_name"
        private const val KEY_PORT = "port"
        private const val KEY_TOKEN = "token"
        private const val KEY_LAPTOP_ID = "laptop_id"
        private const val KEY_LAPTOP_NAME = "laptop_name"
        private const val KEY_SWAP = "swap_red_blue"
    }
}

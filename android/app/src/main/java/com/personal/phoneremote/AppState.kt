package com.personal.phoneremote

import android.os.Handler
import android.os.Looper
import android.util.Log
import java.text.SimpleDateFormat
import java.util.ArrayDeque
import java.util.Date
import java.util.Locale
import java.util.concurrent.CopyOnWriteArrayList

data class Snapshot(
    val serverRunning: Boolean = false,
    val clientConnected: Boolean = false,
    val clientName: String = "",
    val sharing: Boolean = false,
    val accessibilityEnabled: Boolean = false,
    val localIp: String = "",
    val port: Int = DeviceStore.DEFAULT_PORT,
    val clientSocketOpen: Boolean = false,
    val pairingWaiting: Boolean = false,
    val statusLine: String = "Starting…",
    val transferLine: String = "",
    val logText: String = "",
)

/** Small in-memory state shared by the services and the activity. */
object AppState {
    private val listeners = CopyOnWriteArrayList<(Snapshot) -> Unit>()
    private val handler = Handler(Looper.getMainLooper())
    private val lines = ArrayDeque<String>()

    @Volatile
    var snapshot: Snapshot = Snapshot()
        private set

    fun listen(listener: (Snapshot) -> Unit) {
        listeners.add(listener)
        listener(snapshot)
    }

    fun unlisten(listener: (Snapshot) -> Unit) {
        listeners.remove(listener)
    }

    fun update(block: (Snapshot) -> Snapshot) {
        val next = synchronized(this) {
            snapshot = block(snapshot)
            snapshot
        }
        handler.post {
            listeners.forEach { listener -> listener(next) }
        }
    }

    fun log(line: String) {
        Log.i(TAG, line)
        val stamped = SimpleDateFormat("HH:mm:ss", Locale.US).format(Date()) + " " + line
        synchronized(lines) {
            lines.addLast(stamped)
            while (lines.size > 40) {
                lines.removeFirst()
            }
            val text = lines.joinToString("\n")
            update { it.copy(logText = text) }
        }
    }

    private const val TAG = "PhoneRemote"
}

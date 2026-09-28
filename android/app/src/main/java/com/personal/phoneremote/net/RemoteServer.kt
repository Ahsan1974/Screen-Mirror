package com.personal.phoneremote.net

import android.content.Context
import android.util.Log
import com.personal.phoneremote.AppState
import com.personal.phoneremote.DeviceStore
import com.personal.phoneremote.Hub
import com.personal.phoneremote.NetUtils
import com.personal.phoneremote.R
import com.personal.phoneremote.capture.ScreenCapturer
import com.personal.phoneremote.capture.StreamConfig
import com.personal.phoneremote.clipboard.ClipboardSync
import com.personal.phoneremote.input.InputErrors
import com.personal.phoneremote.input.RemoteAccessibilityService
import com.personal.phoneremote.transfer.FileTransferManager
import com.personal.phoneremote.transfer.Wire
import org.java_websocket.WebSocket
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.server.WebSocketServer
import org.json.JSONObject
import java.net.InetSocketAddress
import java.nio.ByteBuffer
import java.security.MessageDigest

/**
 * One laptop at a time, on a private address, after pairing.
 *
 * The laptop connects to this server. The first visit shows a code on the laptop
 * and the phone sends back the code the user typed. Later visits send the saved token.
 */
class RemoteServer(
    private val appContext: Context,
    private val store: DeviceStore,
    private val listenPort: Int,
) : WebSocketServer(InetSocketAddress(listenPort)), Wire {
    var files: FileTransferManager? = null

    @Volatile
    var isAuthed: Boolean = false
        private set

    private val lock = Any()
    private var client: WebSocket? = null
    private var laptopName = ""
    private var laptopId = ""

    init {
        setReuseAddr(true)
        setConnectionLostTimeout(60)
    }

    override fun onStart() {
        Log.i(TAG, "Listening on port $listenPort")
    }

    override fun onOpen(conn: WebSocket, handshake: ClientHandshake) {
        val address = conn.remoteSocketAddress?.address
        if (address == null || !NetUtils.isPrivate(address)) {
            AppState.log("Rejected a connection that was not from the local network")
            conn.close(4003, "local network only")
            return
        }
        val replaced = synchronized(lock) {
            val current = client
            if (current != null && current != conn && current.isOpen) {
                conn.close(4001, "busy")
                return
            }
            client = conn
            true
        }
        if (replaced) {
            isAuthed = false
            AppState.log("Laptop socket opened")
        }
    }

    override fun onClose(conn: WebSocket, code: Int, reason: String, remote: Boolean) {
        val wasActive = synchronized(lock) {
            if (client == conn) {
                client = null
                isAuthed = false
                true
            } else {
                false
            }
        }
        if (wasActive) {
            AppState.update {
                it.copy(
                    clientConnected = false,
                    clientName = "",
                    pairingWaiting = false,
                    statusLine = "Waiting for your laptop",
                )
            }
            AppState.log("Laptop disconnected")
        }
    }

    override fun onMessage(conn: WebSocket, message: String) {
        if (!isActive(conn)) return
        try {
            handle(JSONObject(message))
        } catch (error: Exception) {
            Log.w(TAG, "Ignored a control message", error)
        }
    }

    override fun onMessage(conn: WebSocket, message: ByteBuffer) {
        if (!isActive(conn) || !isAuthed) return
        val bytes = ByteArray(message.remaining())
        message.get(bytes)
        val chunk = Protocol.parseChunk(bytes) ?: return
        files?.onChunk(chunk)
    }

    override fun onError(conn: WebSocket?, ex: Exception) {
        Log.w(TAG, "WebSocket error", ex)
        AppState.log("Network error: ${ex.message ?: "unknown"}")
    }

    fun submitPairCode(code: String) {
        val current = synchronized(lock) { client }
        if (current == null || !current.isOpen) {
            AppState.log("Open the laptop app and tap Connect first")
            return
        }
        sendText(
            JSONObject()
                .put("type", "pair_submit")
                .put("code", code.trim())
                .put("phone_id", store.phoneId)
                .put("phone_name", store.phoneName),
        )
    }

    fun sendClipboardText(text: String) {
        if (!isAuthed) {
            AppState.log("Connect the laptop before sending the clipboard")
            return
        }
        val clipped = text.take(ClipboardSync.MAX_CHARS)
        sendText(JSONObject().put("type", "clipboard_data").put("text", clipped).put("source", "phone"))
        AppState.log("Clipboard sent to the laptop (${clipped.length} characters)")
    }

    fun sendStatus() {
        if (!isAuthed) return
        val (width, height) = ScreenCapturer.screenSize(appContext)
        sendText(
            JSONObject()
                .put("type", "status")
                .put("sharing", Hub.capturer?.isRunning == true)
                .put("accessibility", RemoteAccessibilityService.instance != null)
                .put("fps", Hub.frameCount.getAndSet(0))
                .put("screen_width", width)
                .put("screen_height", height),
        )
    }

    fun sendStreamState(on: Boolean) {
        val (width, height) = ScreenCapturer.screenSize(appContext)
        sendText(
            JSONObject()
                .put("type", "stream_state")
                .put("on", on)
                .put("screen_width", width)
                .put("screen_height", height),
        )
    }

    fun closeClient() {
        synchronized(lock) {
            client?.close(1000, "closed")
            client = null
            isAuthed = false
        }
        AppState.update {
            it.copy(clientConnected = false, clientName = "", pairingWaiting = false, statusLine = "Waiting for your laptop")
        }
    }

    override fun sendText(json: JSONObject) {
        val current = synchronized(lock) { client } ?: return
        if (current.isOpen) current.send(json.toString())
    }

    override fun sendBinary(data: ByteArray) {
        if (!isAuthed) return
        val current = synchronized(lock) { client } ?: return
        if (current.isOpen) current.send(data)
    }

    private fun handle(json: JSONObject) {
        when (json.optString("type")) {
            "hello" -> onHello(json)
            "pair_begin" -> {
                laptopName = json.optString("laptop_name", laptopName)
                AppState.update {
                    it.copy(
                        pairingWaiting = true,
                        statusLine = "Enter the code shown on ${laptopName.ifBlank { "the laptop" }}",
                    )
                }
            }
            "pair_ok" -> onPairOk(json)
            "pair_fail" -> {
                AppState.update { it.copy(statusLine = "Pairing failed. Please try again.") }
                AppState.log("Pairing failed. Please try again.")
            }
            "ping" -> {
                if (!isAuthed) return
                sendText(JSONObject().put("type", "pong").put("t", json.optLong("t")))
            }
            "stream_start" -> onStreamStart(json)
            "mouse" -> onMouse(json)
            "key" -> onKey(json)
            "text_insert" -> onTextInsert(json)
            "screen_text" -> onScreenText()
            "navigation" -> onNavigation(json)
            "file_start" -> {
                if (isAuthed) files?.onFileStart(json)
            }
            "file_accept" -> files?.onAccept(json.optString("id"))
            "file_reject" -> files?.onReject(json.optString("id"))
            "file_done" -> files?.onDone(json.optString("id"))
            "file_error" -> files?.onError(json.optString("id"), json.optString("message", "transfer failed"))
            "clipboard_push" -> {
                if (!isAuthed) return
                val text = json.optString("text", "").take(ClipboardSync.MAX_CHARS)
                ClipboardSync.write(appContext, text)
                AppState.log("Clipboard updated from the laptop (${text.length} characters)")
            }
            "clipboard_pull" -> onClipboardPull()
            else -> Log.d(TAG, "Ignored message ${json.optString("type")}")
        }
    }

    private fun onHello(json: JSONObject) {
        if (json.optInt("protocol", 0) != Protocol.VERSION) {
            sendText(
                JSONObject()
                    .put("type", "error")
                    .put("code", "protocol")
                    .put("message", "Protocol mismatch. Update both the phone and laptop apps."),
            )
            closeClient()
            return
        }
        laptopName = json.optString("laptop_name", "Laptop")
        laptopId = json.optString("laptop_id", "")
        val given = json.optString("token", "")
        if (tokensMatch(store.token, given)) {
            markAuthed(announce = true)
        } else {
            isAuthed = false
            AppState.update {
                it.copy(
                    pairingWaiting = true,
                    clientConnected = false,
                    statusLine = "Enter the code shown on $laptopName",
                )
            }
            sendText(
                JSONObject()
                    .put("type", "auth_required")
                    .put("phone_id", store.phoneId)
                    .put("phone_name", store.phoneName),
            )
        }
    }

    private fun onPairOk(json: JSONObject) {
        val newToken = json.optString("token", "")
        if (newToken.isEmpty()) return
        val name = json.optString("laptop_name", laptopName)
        laptopName = name
        laptopId = json.optString("laptop_id", laptopId)
        store.savePairing(laptopId, name, newToken)
        markAuthed(announce = false)
        AppState.log("Paired with ${name.ifBlank { "laptop" }}")
    }

    private fun markAuthed(announce: Boolean) {
        isAuthed = true
        val (width, height) = ScreenCapturer.screenSize(appContext)
        val name = laptopName.ifBlank { "Laptop" }
        AppState.update {
            it.copy(
                clientConnected = true,
                clientName = name,
                pairingWaiting = false,
                statusLine = "Connected to $name",
            )
        }
        AppState.log("Laptop connected: $name")
        if (announce) {
            sendText(
                JSONObject()
                    .put("type", "auth_ok")
                    .put("phone_id", store.phoneId)
                    .put("phone_name", store.phoneName)
                    .put("screen_width", width)
                    .put("screen_height", height),
            )
        }
        sendStatus()
    }

    private fun onStreamStart(json: JSONObject) {
        if (!isAuthed) return
        Hub.stream = StreamConfig(
            maxWidth = json.optInt("max_width", 1280).coerceIn(240, 1920),
            maxHeight = json.optInt("max_height", 1280).coerceIn(240, 1920),
            fps = json.optInt("fps", 15).coerceIn(5, 30),
            quality = json.optInt("quality", 60).coerceIn(30, 90),
        )
        val capturer = Hub.capturer
        if (capturer == null || !capturer.isRunning) {
            sendText(
                JSONObject()
                    .put("type", "error")
                    .put("code", "projection_required")
                    .put("message", appContext.getString(R.string.projection_required)),
            )
            sendStreamState(false)
        } else {
            capturer.applyConfig()
            sendStreamState(true)
        }
    }

    private fun onMouse(json: JSONObject) {
        if (!isAuthed) return
        val service = RemoteAccessibilityService.instance
        if (service == null) {
            InputErrors.report("accessibility_disabled", appContext.getString(R.string.accessibility_required))
            return
        }
        service.handleMouse(
            json.optString("action", ""),
            json.optDouble("x").toFloat(),
            json.optDouble("y").toFloat(),
            json.optString("button", "left"),
        )
    }

    private fun onKey(json: JSONObject) {
        if (!isAuthed) return
        val service = RemoteAccessibilityService.instance
        if (service == null) {
            InputErrors.report("accessibility_disabled", appContext.getString(R.string.accessibility_required))
            return
        }
        service.handleKey(json.optString("key", ""))
    }

    private fun onTextInsert(json: JSONObject) {
        if (!isAuthed) return
        val service = RemoteAccessibilityService.instance
        if (service == null) {
            InputErrors.report("accessibility_disabled", appContext.getString(R.string.accessibility_required))
            return
        }
        service.insertText(json.optString("text", ""))
    }

    private fun onScreenText() {
        if (!isAuthed) return
        val service = RemoteAccessibilityService.instance
        if (service == null) {
            InputErrors.report("accessibility_disabled", appContext.getString(R.string.accessibility_required))
            return
        }
        service.sendScreenText()
    }

    private fun onNavigation(json: JSONObject) {
        if (!isAuthed) return
        val service = RemoteAccessibilityService.instance
        if (service == null) {
            InputErrors.report("accessibility_disabled", appContext.getString(R.string.accessibility_required))
            return
        }
        service.handleNav(json.optString("action", ""))
    }

    private fun onClipboardPull() {
        if (!isAuthed) return
        val text = ClipboardSync.read(appContext)
        if (text == null) {
            sendText(
                JSONObject()
                    .put("type", "error")
                    .put("code", "clipboard_unavailable")
                    .put("message", appContext.getString(R.string.clipboard_blocked)),
            )
            return
        }
        sendText(JSONObject().put("type", "clipboard_data").put("text", text).put("source", "phone"))
        AppState.log("Clipboard sent to the laptop (${text.length} characters)")
    }

    private fun isActive(conn: WebSocket): Boolean = synchronized(lock) { client == conn }

    private fun tokensMatch(saved: String, given: String): Boolean {
        if (saved.isEmpty() || given.isEmpty()) return false
        return MessageDigest.isEqual(saved.toByteArray(Charsets.UTF_8), given.toByteArray(Charsets.UTF_8))
    }

    companion object {
        private const val TAG = "PhoneRemote"
    }
}

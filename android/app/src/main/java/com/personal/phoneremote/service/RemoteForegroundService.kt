package com.personal.phoneremote.service

import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import com.personal.phoneremote.AppState
import com.personal.phoneremote.DeviceStore
import com.personal.phoneremote.Hub
import com.personal.phoneremote.NetUtils
import com.personal.phoneremote.Notifications
import com.personal.phoneremote.Snapshot
import com.personal.phoneremote.net.NsdAdvertiser
import com.personal.phoneremote.net.RemoteServer
import com.personal.phoneremote.net.WebHost
import com.personal.phoneremote.transfer.FileTransferManager
import com.personal.phoneremote.transfer.PreparedFile
import java.io.File

/**
 * Foreground service that owns the WebSocket server and the mDNS advertisement.
 *
 * Android will not keep a plain background process alive, so the socket lives here
 * and a notification stays visible. Screen capture is a second service because
 * Android 14 requires the mediaProjection foreground type for that work.
 */
class RemoteForegroundService : Service() {
    private lateinit var store: DeviceStore
    private lateinit var server: RemoteServer
    private lateinit var files: FileTransferManager
    private lateinit var nsd: NsdAdvertiser
    private var webHost: WebHost? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var multicast: WifiManager.MulticastLock? = null
    private val handler = Handler(Looper.getMainLooper())
    private var lastNotificationKey = ""

    private val tick = object : Runnable {
        override fun run() {
            Hub.server?.sendStatus()
            val ip = NetUtils.wifiIpv4()
            if (ip != "unknown" && ip != AppState.snapshot.localIp) {
                AppState.update { it.copy(localIp = ip) }
            }
            handler.postDelayed(this, 1000)
        }
    }

    private val listener: (Snapshot) -> Unit = { snap ->
        val key = "${snap.clientConnected}|${snap.clientName}|${snap.sharing}|${snap.localIp}|${snap.port}"
        if (key != lastNotificationKey) {
            lastNotificationKey = key
            val text = when {
                snap.sharing && snap.clientConnected -> "Your screen is being viewed by ${snap.clientName}"
                snap.clientConnected -> "Connected to ${snap.clientName}"
                else -> "Open http://${snap.localIp}:${WebHost.PORT}"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.notify(NOTIFICATION_ID, Notifications.build(this, "Phone Remote", text, stopSharing = false))
        }
        if (snap.clientConnected) acquireWake() else releaseWake()
    }

    override fun onCreate() {
        super.onCreate()
        store = DeviceStore(this)
        Hub.swapRedBlue = store.swapRedBlue
        Notifications.ensure(this)
        val initial = Notifications.build(this, "Phone Remote", "Starting on your Wi-Fi", stopSharing = false)
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, initial, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        } else {
            startForeground(NOTIFICATION_ID, initial)
        }
        acquireMulticast()
        wakeLock = (getSystemService(POWER_SERVICE) as PowerManager).newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "PhoneRemote::session",
        ).apply { setReferenceCounted(false) }
        server = RemoteServer(applicationContext, store, store.port)
        files = FileTransferManager(applicationContext, server)
        server.files = files
        Hub.server = server
        try {
            server.start()
            val ip = NetUtils.wifiIpv4()
            AppState.update { current ->
                val base = current.copy(serverRunning = true, localIp = ip, port = store.port)
                if (server.hasClient()) {
                    base
                } else {
                    base.copy(
                        clientSocketOpen = false,
                        clientConnected = false,
                        pairingWaiting = false,
                        statusLine = "Waiting for your laptop",
                    )
                }
            }
            AppState.log("Listening on $ip:${store.port}")
        } catch (error: Exception) {
            AppState.log("Could not listen on port ${store.port}. ${error.message}")
        }
        webHost = WebHost(assets, store.port).also { it.start() }
        nsd = NsdAdvertiser(this)
        nsd.register(store.phoneName, store.port, store.phoneId)
        handler.postDelayed(tick, 1000)
        AppState.listen(listener)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_READVERTISE -> {
                if (::nsd.isInitialized) nsd.register(store.phoneName, store.port, store.phoneId)
            }
            ACTION_REBIND -> rebind(intent.getIntExtra(EXTRA_PORT, store.port))
            ACTION_SEND_FILE -> sendFile(intent)
            ACTION_FORGET -> {
                store.clearPairing()
                if (::server.isInitialized) server.closeClient()
                AppState.log("Forgot the paired laptop")
            }
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        handler.removeCallbacks(tick)
        AppState.unlisten(listener)
        webHost?.stop()
        if (::nsd.isInitialized) nsd.unregister()
        if (Hub.server === server) Hub.server = null
        try {
            if (::server.isInitialized) server.stop(500)
        } catch (_: Exception) {
        }
        releaseWake()
        try {
            multicast?.release()
        } catch (_: Exception) {
        }
        AppState.update { it.copy(serverRunning = false, clientConnected = false, statusLine = "Stopped") }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun sendFile(intent: Intent) {
        val path = intent.getStringExtra(EXTRA_PATH) ?: return
        val file = File(path)
        val prepared = PreparedFile(
            file = file,
            name = intent.getStringExtra(EXTRA_NAME) ?: file.name,
            size = intent.getLongExtra(EXTRA_SIZE, file.length()),
            sha256 = intent.getStringExtra(EXTRA_SHA) ?: "",
        )
        if (::files.isInitialized) files.sendPrepared(prepared) else file.delete()
    }

    private fun rebind(port: Int) {
        if (port !in 1024..65535 || port == store.port) return
        store.port = port
        Thread {
            try {
                server.closeClient()
                server.stop(1000)
            } catch (_: Exception) {
            }
            val fresh = RemoteServer(applicationContext, store, port)
            fresh.files = files
            files.wire = fresh
            try {
                fresh.start()
                handler.post {
                    server = fresh
                    Hub.server = fresh
                    webHost?.socketPort = port
                    nsd.register(store.phoneName, port, store.phoneId)
                    val ip = NetUtils.wifiIpv4()
                    AppState.update { current ->
                        if (current.clientSocketOpen) current.copy(localIp = ip, port = port)
                        else current.copy(
                            localIp = ip,
                            port = port,
                            clientSocketOpen = false,
                            pairingWaiting = false,
                            statusLine = "Waiting for your laptop",
                        )
                    }
                    AppState.log("Listening on $ip:$port")
                }
            } catch (error: Exception) {
                AppState.log("Could not listen on port $port. ${error.message}")
            }
        }.start()
    }

    @Suppress("DEPRECATION")
    private fun acquireMulticast() {
        val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        multicast = wifi.createMulticastLock("phoneremote-mdns").apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    private fun acquireWake() {
        val lock = wakeLock ?: return
        if (!lock.isHeld) lock.acquire()
    }

    private fun releaseWake() {
        val lock = wakeLock ?: return
        if (lock.isHeld) lock.release()
    }

    companion object {
        const val ACTION_READVERTISE = "com.personal.phoneremote.READVERTISE"
        const val ACTION_REBIND = "com.personal.phoneremote.REBIND"
        const val ACTION_SEND_FILE = "com.personal.phoneremote.SEND_FILE"
        const val ACTION_FORGET = "com.personal.phoneremote.FORGET"
        const val ACTION_STOP = "com.personal.phoneremote.STOP_SERVICE"
        const val EXTRA_PORT = "port"
        const val EXTRA_PATH = "path"
        const val EXTRA_NAME = "name"
        const val EXTRA_SIZE = "size"
        const val EXTRA_SHA = "sha"
        private const val NOTIFICATION_ID = 11
    }
}

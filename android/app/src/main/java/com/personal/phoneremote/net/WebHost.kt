package com.personal.phoneremote.net

import com.personal.phoneremote.AppState
import com.personal.phoneremote.NetUtils
import java.io.BufferedOutputStream
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import android.content.res.AssetManager
import kotlin.concurrent.thread

/**
 * Serves the browser viewer to other devices on this Wi-Fi.
 * The page and the screen stay on the local network.
 */
class WebHost(private val assets: AssetManager, @Volatile var socketPort: Int) {
    private var socket: ServerSocket? = null
    private var worker: Thread? = null

    fun start() {
        if (worker?.isAlive == true) return
        worker = thread(name = "web-host", isDaemon = true) {
            try {
                val server = ServerSocket()
                server.reuseAddress = true
                server.bind(InetSocketAddress(PORT))
                socket = server
                val ip = NetUtils.wifiIpv4()
                AppState.log("Laptop browser: http://$ip:$PORT")
                while (!server.isClosed) {
                    val client = server.accept()
                    thread(name = "web-client", isDaemon = true) {
                        try {
                            serve(client)
                        } catch (_: Exception) {
                            try {
                                client.close()
                            } catch (_: Exception) {
                            }
                        }
                    }
                }
            } catch (error: Exception) {
                AppState.log("Laptop page did not start. ${error.message ?: "port in use"}")
            }
        }
    }

    fun stop() {
        try {
            socket?.close()
        } catch (_: Exception) {
        }
    }

    private fun serve(client: Socket) {
        client.use { socket ->
            socket.soTimeout = 8000
            val reader = socket.getInputStream().bufferedReader()
            val request = reader.readLine() ?: return
            val path = request.split(" ").getOrNull(1)?.substringBefore("?") ?: "/"
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isEmpty()) break
            }
            val out = BufferedOutputStream(socket.getOutputStream())
            if (path == "/config.json") {
                val body = """{"port":$socketPort}""".toByteArray()
                out.write(header(200, "application/json; charset=utf-8", body.size))
                out.write(body)
                out.flush()
                return
            }
            val name = when (path) {
                "/", "/index.html" -> "index.html"
                "/styles.css" -> "styles.css"
                "/app.js" -> "app.js"
                else -> null
            }
            if (name == null) {
                val body = "Not found".toByteArray()
                out.write(header(404, "text/plain; charset=utf-8", body.size))
                out.write(body)
                out.flush()
                return
            }
            val bytes = assets.open("web/$name").use { it.readBytes() }
            val type = when (name) {
                "index.html" -> "text/html; charset=utf-8"
                "styles.css" -> "text/css; charset=utf-8"
                else -> "text/javascript; charset=utf-8"
            }
            out.write(header(200, type, bytes.size))
            out.write(bytes)
            out.flush()
        }
    }

    private fun header(code: Int, type: String, length: Int): ByteArray {
        val status = if (code == 200) "OK" else "Not Found"
        return (
            "HTTP/1.1 $code $status\r\n" +
                "Content-Type: $type\r\n" +
                "Content-Length: $length\r\n" +
                "Connection: close\r\n" +
                "Cache-Control: no-store\r\n\r\n"
            ).toByteArray()
    }

    companion object {
        const val PORT = 8080
    }
}

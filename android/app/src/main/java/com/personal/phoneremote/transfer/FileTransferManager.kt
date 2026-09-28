package com.personal.phoneremote.transfer

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.provider.OpenableColumns
import com.personal.phoneremote.AppState
import com.personal.phoneremote.Hub
import com.personal.phoneremote.net.FileChunk
import com.personal.phoneremote.net.Protocol
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

interface Wire {
    fun sendText(json: JSONObject)
    fun sendBinary(data: ByteArray)
}

data class PreparedFile(val file: File, val name: String, val size: Long, val sha256: String)

fun prepareOutgoing(context: Context, uri: Uri): PreparedFile {
    val name = displayName(context, uri)
    val temp = File(context.cacheDir, "out-${UUID.randomUUID()}")
    val digest = MessageDigest.getInstance("SHA-256")
    context.contentResolver.openInputStream(uri)?.use { input ->
        FileOutputStream(temp).use { output ->
            val buffer = ByteArray(48 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                output.write(buffer, 0, count)
                digest.update(buffer, 0, count)
            }
        }
    } ?: error("Could not read that file")
    return PreparedFile(temp, name, temp.length(), digest.hex())
}

/** One file at a time, in either direction, over the same WebSocket as the screen. */
class FileTransferManager(
    private val context: Context,
    var wire: Wire,
) {
    private val busy = AtomicBoolean(false)
    private val chunks = LinkedBlockingQueue<FileChunk>()
    private val accepted = AtomicBoolean(false)
    private val pendingId = AtomicReference("")
    private val failMessage = AtomicReference<String?>(null)
    private var acceptLatch = CountDownLatch(1)
    private var doneLatch = CountDownLatch(1)

    fun onFileStart(json: JSONObject) {
        if (!busy.compareAndSet(false, true)) {
            wire.sendText(JSONObject().put("type", "file_reject").put("id", json.optString("id")).put("reason", "busy"))
            return
        }
        Thread {
            Hub.transfersBusy = true
            try {
                receive(json)
            } catch (error: Exception) {
                val id = json.optString("id")
                AppState.log("File receive failed")
                wire.sendText(
                    JSONObject().put("type", "file_error").put("id", id).put("message", error.message ?: "transfer failed"),
                )
                AppState.update { it.copy(transferLine = error.message ?: "Transfer failed") }
            } finally {
                Hub.transfersBusy = false
                busy.set(false)
            }
        }.start()
    }

    fun onChunk(chunk: FileChunk) {
        chunks.offer(chunk)
    }

    fun onAccept(id: String) {
        if (id == pendingId.get()) {
            accepted.set(true)
            acceptLatch.countDown()
        }
    }

    fun onReject(id: String) {
        if (id == pendingId.get()) {
            accepted.set(false)
            acceptLatch.countDown()
        }
    }

    fun onDone(id: String) {
        if (id == pendingId.get()) doneLatch.countDown()
    }

    fun onError(id: String, message: String) {
        if (id != pendingId.get()) return
        failMessage.set(message)
        accepted.set(false)
        acceptLatch.countDown()
        doneLatch.countDown()
    }

    fun sendPrepared(prepared: PreparedFile) {
        if (!Hub.isAuthed()) {
            prepared.file.delete()
            AppState.log("Connect the laptop before sending a file")
            return
        }
        if (!busy.compareAndSet(false, true)) {
            prepared.file.delete()
            AppState.log("A transfer is already running")
            return
        }
        Thread {
            Hub.transfersBusy = true
            try {
                sendFile(prepared)
            } catch (error: Exception) {
                AppState.log("File send failed")
                AppState.update { it.copy(transferLine = error.message ?: "Transfer failed") }
            } finally {
                prepared.file.delete()
                Hub.transfersBusy = false
                busy.set(false)
            }
        }.start()
    }

    private fun receive(json: JSONObject) {
        val id = json.optString("id")
        val name = safeName(json.optString("name", "file"))
        val size = json.optLong("size", -1)
        val sha = json.optString("sha256", "").lowercase()
        if (id.length != 36 || size < 0 || size > MAX_BYTES) error("Invalid file offer")
        chunks.clear()
        wire.sendText(JSONObject().put("type", "file_accept").put("id", id))
        AppState.log("File transfer started: $name")
        val temp = File(context.cacheDir, "$id.partial")
        val digest = MessageDigest.getInstance("SHA-256")
        var next = 0
        var received = 0L
        try {
            FileOutputStream(temp).use { output ->
                while (true) {
                    val chunk = chunks.poll(60, TimeUnit.SECONDS) ?: error("Timed out waiting for the file")
                    if (chunk.id != id) continue
                    if (chunk.sequence != next) error("File chunk arrived out of order")
                    output.write(chunk.payload)
                    digest.update(chunk.payload)
                    received += chunk.payload.size
                    next += 1
                    val percent = if (size == 0L) 100 else received * 100 / size
                    AppState.update { it.copy(transferLine = "Receiving $name  $percent%") }
                    if (chunk.last) break
                }
            }
            if (received != size) error("File size did not match")
            val actual = digest.hex()
            if (sha.isNotEmpty() && actual != sha) error("File checksum did not match")
            val saved = publish(name, temp)
            AppState.log("Saved $name")
            AppState.update { it.copy(transferLine = "Saved $saved") }
            wire.sendText(JSONObject().put("type", "file_done").put("id", id).put("name", name).put("size", size))
        } finally {
            temp.delete()
        }
    }

    private fun sendFile(prepared: PreparedFile) {
        val id = UUID.randomUUID().toString()
        pendingId.set(id)
        accepted.set(false)
        failMessage.set(null)
        acceptLatch = CountDownLatch(1)
        doneLatch = CountDownLatch(1)
        AppState.log("File transfer started: ${prepared.name}")
        wire.sendText(
            JSONObject()
                .put("type", "file_start")
                .put("id", id)
                .put("name", prepared.name)
                .put("size", prepared.size)
                .put("sha256", prepared.sha256),
        )
        if (!acceptLatch.await(120, TimeUnit.SECONDS) || !accepted.get()) {
            val reason = failMessage.get() ?: "The laptop did not accept the file"
            AppState.update { it.copy(transferLine = reason) }
            return
        }
        prepared.file.inputStream().use { input ->
            var sequence = 0
            var sent = 0L
            while (true) {
                val buffer = ByteArray(CHUNK)
                val count = input.read(buffer)
                if (count < 0 && sent > 0) break
                val piece = if (count <= 0) ByteArray(0) else buffer.copyOf(count)
                if (piece.isEmpty() && sent > 0) break
                val last = sent + piece.size >= prepared.size
                wire.sendBinary(Protocol.packChunk(id, sequence, last, piece))
                sent += piece.size
                sequence += 1
                val percent = if (prepared.size == 0L) 100 else sent * 100 / prepared.size
                AppState.update { it.copy(transferLine = "Sending ${prepared.name}  $percent%") }
                if (last) break
                Thread.sleep(15)
            }
        }
        if (!doneLatch.await(60, TimeUnit.SECONDS)) {
            AppState.update { it.copy(transferLine = "The laptop did not confirm the file") }
            return
        }
        val failure = failMessage.get()
        if (failure != null) {
            AppState.update { it.copy(transferLine = failure) }
            return
        }
        AppState.update { it.copy(transferLine = "Sent ${prepared.name}") }
    }

    private fun publish(name: String, temp: File): String {
        if (Build.VERSION.SDK_INT >= 29) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, name)
                put(MediaStore.Downloads.MIME_TYPE, mime(name))
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/PhoneRemote")
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: error("Could not create the download")
            context.contentResolver.openOutputStream(uri)?.use { output ->
                temp.inputStream().use { it.copyTo(output) }
            } ?: error("Could not write the download")
            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            context.contentResolver.update(uri, values, null, null)
            return "Downloads/PhoneRemote/$name"
        }
        val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: context.filesDir
        dir.mkdirs()
        val dest = uniqueFile(dir, name)
        temp.copyTo(dest, overwrite = false)
        return dest.absolutePath
    }

    companion object {
        private const val CHUNK = 48 * 1024
        private const val MAX_BYTES = 8L * 1024 * 1024 * 1024
    }
}

private fun displayName(context: Context, uri: Uri): String {
    context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) {
            val name = cursor.getString(0)
            if (!name.isNullOrBlank()) return safeName(name)
        }
    }
    return "file"
}

private fun safeName(raw: String): String {
    val base = raw.substringAfterLast('/').substringAfterLast('\\').trim().replace("\u0000", "")
    if (base.isEmpty() || base == "." || base == "..") return "file"
    return base.take(180)
}

private fun uniqueFile(directory: File, name: String): File {
    val clean = safeName(name)
    val direct = File(directory, clean)
    if (!direct.exists()) return direct
    val dot = clean.lastIndexOf('.')
    val stem = if (dot > 0) clean.substring(0, dot) else clean
    val suffix = if (dot > 0) clean.substring(dot) else ""
    for (number in 2..999) {
        val candidate = File(directory, "$stem ($number)$suffix")
        if (!candidate.exists()) return candidate
    }
    return File(directory, "$stem-${UUID.randomUUID()}$suffix")
}

private fun mime(name: String): String {
    val lower = name.lowercase()
    return when {
        lower.endsWith(".jpg") || lower.endsWith(".jpeg") -> "image/jpeg"
        lower.endsWith(".png") -> "image/png"
        lower.endsWith(".txt") -> "text/plain"
        lower.endsWith(".pdf") -> "application/pdf"
        else -> "application/octet-stream"
    }
}

private fun MessageDigest.hex(): String = digest().joinToString("") { "%02x".format(it) }

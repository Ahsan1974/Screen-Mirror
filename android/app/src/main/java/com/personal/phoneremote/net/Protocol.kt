package com.personal.phoneremote.net

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.StandardCharsets

/**
 * Binary messages match laptop/network/protocol.py.
 *
 * JPEG frame, 25-byte big-endian header, then the JPEG bytes:
 * type=1, capture width, capture height, screen width, screen height, timestamp ms.
 *
 * File chunk, 42-byte header, then the payload:
 * type=2, 36-byte UUID, sequence, flags (bit 0 = last chunk).
 */
object Protocol {
    const val VERSION = 1
    const val FRAME = 1
    const val FILE_CHUNK = 2
    const val FRAME_HEADER = 25
    const val FILE_HEADER = 42

    fun packFrame(
        captureW: Int,
        captureH: Int,
        screenW: Int,
        screenH: Int,
        timestampMs: Long,
        jpeg: ByteArray,
    ): ByteArray {
        val out = ByteBuffer.allocate(FRAME_HEADER + jpeg.size).order(ByteOrder.BIG_ENDIAN)
        out.put(FRAME.toByte())
        out.putInt(captureW)
        out.putInt(captureH)
        out.putInt(screenW)
        out.putInt(screenH)
        out.putLong(timestampMs)
        out.put(jpeg)
        return out.array()
    }

    fun packChunk(id: String, sequence: Int, last: Boolean, payload: ByteArray): ByteArray {
        val identity = id.toByteArray(StandardCharsets.US_ASCII)
        require(identity.size == 36) { "file id must be a 36-character UUID" }
        val out = ByteBuffer.allocate(FILE_HEADER + payload.size).order(ByteOrder.BIG_ENDIAN)
        out.put(FILE_CHUNK.toByte())
        out.put(identity)
        out.putInt(sequence)
        out.put(if (last) 1 else 0)
        out.put(payload)
        return out.array()
    }

    fun parseChunk(data: ByteArray): FileChunk? {
        if (data.size < FILE_HEADER || data[0].toInt() != FILE_CHUNK) return null
        val buffer = ByteBuffer.wrap(data).order(ByteOrder.BIG_ENDIAN)
        buffer.get()
        val identity = ByteArray(36)
        buffer.get(identity)
        val sequence = buffer.int
        val flags = buffer.get().toInt() and 0xFF
        val payload = ByteArray(buffer.remaining())
        buffer.get(payload)
        return FileChunk(
            id = String(identity, StandardCharsets.US_ASCII),
            sequence = sequence,
            last = flags and 1 == 1,
            payload = payload,
        )
    }
}

data class FileChunk(
    val id: String,
    val sequence: Int,
    val last: Boolean,
    val payload: ByteArray,
)

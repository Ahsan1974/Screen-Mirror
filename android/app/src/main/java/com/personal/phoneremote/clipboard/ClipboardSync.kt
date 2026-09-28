package com.personal.phoneremote.clipboard

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context

/** Clipboard reads from the background are blocked on Android 10 and newer. */
object ClipboardSync {
    const val MAX_CHARS = 256_000

    fun write(context: Context, text: String) {
        val manager = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        manager.setPrimaryClip(ClipData.newPlainText("Phone Remote", text.take(MAX_CHARS)))
    }

    fun read(context: Context): String? {
        val manager = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        if (!manager.hasPrimaryClip()) return null
        val clip = manager.primaryClip ?: return null
        if (clip.itemCount == 0) return null
        return clip.getItemAt(0).coerceToText(context)?.toString()?.take(MAX_CHARS)
    }
}

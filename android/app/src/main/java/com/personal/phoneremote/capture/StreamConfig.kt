package com.personal.phoneremote.capture

/** Maximum capture box. The real aspect ratio is kept inside it. */
data class StreamConfig(
    val maxWidth: Int = 1280,
    val maxHeight: Int = 1280,
    val fps: Int = 15,
    val quality: Int = 60,
)

fun fit(screenW: Int, screenH: Int, maxW: Int, maxH: Int): Pair<Int, Int> {
    if (screenW <= 0 || screenH <= 0) return 2 to 2
    val scale = minOf(maxW.toFloat() / screenW, maxH.toFloat() / screenH, 1f)
    var width = (screenW * scale).toInt().coerceAtLeast(2)
    var height = (screenH * scale).toInt().coerceAtLeast(2)
    if (width % 2 != 0) width -= 1
    if (height % 2 != 0) height -= 1
    return width.coerceAtLeast(2) to height.coerceAtLeast(2)
}

package com.personal.phoneremote

import com.personal.phoneremote.capture.ScreenCapturer
import com.personal.phoneremote.capture.StreamConfig
import com.personal.phoneremote.net.RemoteServer
import java.util.concurrent.atomic.AtomicInteger

/** Process-wide links between the socket service and the capture service. */
object Hub {
    @Volatile
    var server: RemoteServer? = null

    @Volatile
    var capturer: ScreenCapturer? = null

    @Volatile
    var stream: StreamConfig = StreamConfig()

    @Volatile
    var swapRedBlue: Boolean = false

    @Volatile
    var transfersBusy: Boolean = false

    val frameCount: AtomicInteger = AtomicInteger(0)

    /** Set by the capture service so the system cast chip can stop that service. */
    @Volatile
    var onCaptureStopped: (() -> Unit)? = null

    fun isAuthed(): Boolean = server?.isAuthed == true
}

package com.personal.phoneremote

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.personal.phoneremote.service.ScreenCaptureService

object Notifications {
    const val CHANNEL_ID = "phone_remote"

    fun ensure(context: Context) {
        if (Build.VERSION.SDK_INT < 26) return
        val manager = context.getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Phone Remote",
            NotificationManager.IMPORTANCE_DEFAULT,
        )
        channel.description = "Shows when Phone Remote is running or sharing your screen"
        channel.setSound(null, null)
        manager.createNotificationChannel(channel)
    }

    fun build(context: Context, title: String, text: String, stopSharing: Boolean): Notification {
        ensure(context)
        val open = PendingIntent.getActivity(
            context,
            1,
            Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
        if (stopSharing) {
            val stop = PendingIntent.getService(
                context,
                2,
                Intent(context, ScreenCaptureService::class.java).setAction(ScreenCaptureService.ACTION_STOP),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            builder.addAction(0, "Stop sharing", stop)
        }
        return builder.build()
    }
}

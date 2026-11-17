
package com.troit.assistant.link

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.provider.Settings
import androidx.core.app.NotificationCompat
import com.troit.assistant.FreakyyyAccessibilityService
import com.troit.assistant.R

/**
 * Android blocks apps in the background from opening screens. When the laptop
 * asks the phone to open something while Freakyyy isn't visible, Freakyyy either
 * opens it directly (if the user allowed "Display over other apps" or the
 * accessibility helper - both Android-sanctioned exemptions) or posts a
 * notification the user can tap. It never pretends the screen opened.
 */
object LaunchGate {

    @Volatile private var startedActivities = 0

    val freakyyyVisible: Boolean get() = startedActivities > 0

    @Synchronized fun activityStarted() { startedActivities++ }

    @Synchronized fun activityStopped() { startedActivities = (startedActivities - 1).coerceAtLeast(0) }

    /** Set when the last launch was turned into a notification. */
    @Volatile var lastWasNotified = false
        private set

    fun resetNotified() {
        lastWasNotified = false
    }

    fun canOpenDirectly(context: Context): Boolean =
        freakyyyVisible || Settings.canDrawOverlays(context) || FreakyyyAccessibilityService.isRunning

    fun start(context: Context, intent: Intent, label: String): Boolean {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (canOpenDirectly(context)) {
            lastWasNotified = false
            context.startActivity(intent)
            return true
        }
        notifyToOpen(context, intent, label)
        lastWasNotified = true
        return true
    }

    private fun notifyToOpen(context: Context, intent: Intent, label: String) {
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, "Requests from your laptop", NotificationManager.IMPORTANCE_HIGH)
        )
        val pi = PendingIntent.getActivity(
            context, label.hashCode(), intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val n = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("Open $label")
            .setContentText("Your laptop asked Freakyyy to open this. Tap to continue.")
            .setContentIntent(pi)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        try {
            nm.notify(label.hashCode(), n)
        } catch (_: SecurityException) {
            // Notification permission denied; nothing else Android allows here.
        }
    }

    const val CHANNEL = "freakyyy_remote_open"
}

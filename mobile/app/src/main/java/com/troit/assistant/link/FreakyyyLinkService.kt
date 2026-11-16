
package com.troit.assistant.link

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.troit.assistant.FreakyyyAssistant
import com.troit.assistant.MainActivity
import com.troit.assistant.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Keeps the Freakyyy Link connection open while Freakyyy is in the background, so
 * the laptop can reach the phone. Visible as an ongoing notification with a
 * Disconnect action; it only runs while a laptop is paired and the user hasn't
 * turned the link off.
 */
class FreakyyyLinkService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            FreakyyyLink.disconnect()
            linkPrefs(this).edit().putBoolean("enabled", false).apply()
            stopSelf()
            return START_NOT_STICKY
        }
        FreakyyyAssistant.initialize(applicationContext)
        FreakyyyLink.init(applicationContext)
        if (!FreakyyyLink.isPaired) {
            stopSelf()
            return START_NOT_STICKY
        }
        createChannel()
        val first = notification("Connecting to your laptop…")
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, first, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        } else {
            startForeground(NOTIFICATION_ID, first)
        }
        FreakyyyLink.connect()
        scope.launch {
            FreakyyyLink.status.collectLatest { s ->
                val text = when (s.state) {
                    FreakyyyLink.State.CONNECTED -> "Connected to ${s.laptopName}"
                    FreakyyyLink.State.CONNECTING -> "Connecting to ${s.laptopName}…"
                    else -> s.message
                }
                getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(text))
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    private fun createChannel() {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, "Freakyyy Link", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Shows while Freakyyy is connected to your laptop"
            }
        )
    }

    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, FreakyyyLinkService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("Freakyyy Link")
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(open)
            .addAction(0, "Disconnect", stop)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    companion object {
        private const val CHANNEL = "freakyyy_link"
        private const val NOTIFICATION_ID = 4711
        private const val ACTION_STOP = "com.troit.assistant.link.STOP"

        fun linkPrefs(context: Context) = context.getSharedPreferences("dexter_link_service", Context.MODE_PRIVATE)

        /** Starts the link if a laptop is paired and the user hasn't disabled it. */
        fun startIfWanted(context: Context) {
            FreakyyyLink.init(context)
            if (FreakyyyLink.isPaired && linkPrefs(context).getBoolean("enabled", true)) {
                linkPrefs(context).edit().putBoolean("enabled", true).apply()
                ContextCompat.startForegroundService(context, Intent(context, FreakyyyLinkService::class.java))
            }
        }

        fun stop(context: Context) {
            context.startService(Intent(context, FreakyyyLinkService::class.java).setAction(ACTION_STOP))
        }
    }
}

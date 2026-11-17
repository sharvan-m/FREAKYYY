
package com.troit.assistant

import android.content.ComponentName
import android.content.Context
import android.provider.Settings
import android.service.notification.NotificationListenerService

/**
 * Optional notification access. Freakyyy only counts active notifications per
 * app so it can answer "how many notifications do I have?" and clear them
 * on request. Titles and message content are never read or stored.
 */
class FreakyyyNotificationListener : NotificationListenerService() {

    override fun onListenerConnected() {
        super.onListenerConnected()
        instance = this
    }

    override fun onListenerDisconnected() {
        if (instance === this) instance = null
        super.onListenerDisconnected()
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    /** Package name → number of dismissible notifications. */
    fun countsByApp(): Map<String, Int> = try {
        activeNotifications
            .filter { it.isClearable && it.packageName != packageName }
            .groupingBy { it.packageName }
            .eachCount()
    } catch (_: SecurityException) {
        emptyMap()
    }

    fun clearAll(): Boolean = try {
        cancelAllNotifications()
        true
    } catch (_: SecurityException) {
        false
    }

    companion object {
        @Volatile
        var instance: FreakyyyNotificationListener? = null
            private set

        fun isEnabled(context: Context): Boolean {
            val flat = Settings.Secure.getString(
                context.contentResolver,
                "enabled_notification_listeners"
            ) ?: return false
            val me = ComponentName(context, FreakyyyNotificationListener::class.java)
            return flat.split(":").any { ComponentName.unflattenFromString(it) == me }
        }
    }
}

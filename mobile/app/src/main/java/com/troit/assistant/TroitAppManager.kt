
package com.troit.assistant

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.core.content.ContextCompat
import java.util.concurrent.Executors

data class TroitApp(
    val name: String,
    val packageName: String
)

class TroitAppManager(private val context: Context) {

    private val packageManager = context.packageManager

    init {
        watchPackageChanges(context.applicationContext)
    }

    /**
     * Installed launcher apps. Labels are loaded once and cached; the cache
     * is dropped whenever an app is installed, removed or updated.
     */
    fun getInstalledApps(): List<TroitApp> {
        cachedApps?.let { return it }

        synchronized(lock) {
            cachedApps?.let { return it }
            val apps = loadInstalledApps()
            cachedApps = apps
            return apps
        }
    }

    /** Warms the cache off the main thread so the first command is instant. */
    fun preload() {
        if (cachedApps != null) return
        loader.execute { getInstalledApps() }
    }

    private fun loadInstalledApps(): List<TroitApp> {
        val intent = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
        }

        return packageManager.queryIntentActivities(intent, 0)
            .mapNotNull { info ->
                val activity = info.activityInfo
                if (activity.packageName == context.packageName) {
                    null
                } else {
                    TroitApp(
                        name = info.loadLabel(packageManager).toString(),
                        packageName = activity.packageName
                    )
                }
            }
            .distinctBy { it.packageName }
            .sortedBy { it.name.lowercase() }
    }

    fun findApps(command: String): List<TroitApp> {
        val query = command.lowercase()
            .replace("open", "")
            .replace("launch", "")
            .replace("start", "")
            .trim()

        if (query.isBlank()) return emptyList()

        return getInstalledApps().filter { app ->
            app.name.lowercase().contains(query) ||
                    query.contains(app.name.lowercase())
        }
    }

    fun launchApp(app: TroitApp): Boolean {
        return try {
            val launchIntent =
                packageManager.getLaunchIntentForPackage(app.packageName)
                    ?: return false

            com.troit.assistant.link.LaunchGate.start(context, launchIntent, app.name)
        } catch (e: Exception) {
            false
        }
    }

    companion object {
        private val lock = Any()
        private val loader = Executors.newSingleThreadExecutor()

        @Volatile
        private var cachedApps: List<TroitApp>? = null

        @Volatile
        private var watching = false

        private fun watchPackageChanges(appContext: Context) {
            if (watching) return
            synchronized(lock) {
                if (watching) return

                val filter = IntentFilter().apply {
                    addAction(Intent.ACTION_PACKAGE_ADDED)
                    addAction(Intent.ACTION_PACKAGE_REMOVED)
                    addAction(Intent.ACTION_PACKAGE_CHANGED)
                    addAction(Intent.ACTION_PACKAGE_REPLACED)
                    addDataScheme("package")
                }

                ContextCompat.registerReceiver(
                    appContext,
                    object : BroadcastReceiver() {
                        override fun onReceive(context: Context, intent: Intent) {
                            cachedApps = null
                        }
                    },
                    filter,
                    ContextCompat.RECEIVER_NOT_EXPORTED
                )
                watching = true
            }
        }
    }
}

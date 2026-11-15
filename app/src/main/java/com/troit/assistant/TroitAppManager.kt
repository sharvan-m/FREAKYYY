
package com.troit.assistant

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager

data class TroitApp(
    val name: String,
    val packageName: String
)

class TroitAppManager(private val context: Context) {

    private val packageManager = context.packageManager

    fun getInstalledApps(): List<TroitApp> {
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

            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(launchIntent)
            true
        } catch (e: Exception) {
            false
        }
    }
}

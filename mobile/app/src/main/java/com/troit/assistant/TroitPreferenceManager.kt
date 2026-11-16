
package com.troit.assistant

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri

class TroitPreferenceManager(context: Context) {

    private val appContext = context.applicationContext

    private val preferences = appContext.getSharedPreferences(
        "troit_app_preferences",
        Context.MODE_PRIVATE
    )

    // Save the user's preferred app
    fun setPreferredApp(category: String, app: TroitApp) {
        preferences.edit()
            .putString(category.lowercase(), app.packageName)
            .apply()
    }

    // Retrieve the saved preferred app
    fun getPreferredPackage(category: String): String? {
        return preferences.getString(category.lowercase(), null)
    }

    // Clear a saved preference
    fun clearPreference(category: String) {
        preferences.edit()
            .remove(category.lowercase())
            .apply()
    }

    // Detect the browser Android resolves as the default
    fun getDefaultBrowserPackage(): String? {
        return try {
            val intent = Intent(
                Intent.ACTION_VIEW,
                Uri.parse("https://example.com")
            ).apply {
                addCategory(Intent.CATEGORY_BROWSABLE)
            }

            val resolved = appContext.packageManager.resolveActivity(
                intent,
                PackageManager.MATCH_DEFAULT_ONLY
            )

            val activity = resolved?.activityInfo
                ?: return null

            val className = activity.name

            if (
                className.contains("ResolverActivity") ||
                className.contains("ChooserActivity")
            ) {
                null
            } else {
                activity.packageName
            }

        } catch (e: Exception) {
            null
        }
    }
}

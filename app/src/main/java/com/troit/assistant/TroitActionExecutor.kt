
package com.troit.assistant

import android.content.Context

object TroitActionExecutor {

    fun execute(
        context: Context,
        command: TroitCommand
    ): String {

        if (command.type == TroitCommandType.UNKNOWN) {
            return "I didn't understand that command."
        }

        val appManager = TroitAppManager(context)
        val preferenceManager = TroitPreferenceManager(context)

        val matcher = TroitAppMatcher(
            appManager,
            preferenceManager
        )

        val result = matcher.match(command.appName)

        return when (result.type) {

            AppMatchType.DIRECT -> {
                val app = result.apps.firstOrNull()
                    ?: return "I couldn't identify that app."

                if (appManager.launchApp(app)) {
                    "Opening ${app.name}"
                } else {
                    "I couldn't open ${app.name}."
                }
            }

            AppMatchType.SUGGESTION -> {
                result.message
            }

            AppMatchType.MULTIPLE -> {
                result.message
            }

            AppMatchType.NOT_FOUND -> {
                result.message
            }
        }
    }
}


package com.troit.assistant

enum class AppMatchType {
    DIRECT,
    SUGGESTION,
    MULTIPLE,
    NOT_FOUND
}

data class AppMatchResult(
    val type: AppMatchType,
    val apps: List<TroitApp> = emptyList(),
    val message: String,
    val requiresConfirmation: Boolean = false
)

class TroitAppMatcher(
    private val appManager: TroitAppManager,
    private val preferenceManager: TroitPreferenceManager
) {

    private val categories = mapOf(
        "music" to listOf(
            "music",
            "music player",
            "audio player",
            "audio",
            "songs"
        ),
        "browser" to listOf(
            "browser",
            "internet",
            "web browser"
        ),
        "gallery" to listOf(
            "gallery",
            "albums",
            "album",
            "photos",
            "photo"
        ),
        "camera" to listOf("camera"),
        "video" to listOf(
            "video",
            "video player"
        ),
        "maps" to listOf(
            "maps",
            "map",
            "navigation"
        ),
        "messaging" to listOf(
            "messaging",
            "messages",
            "message",
            "chat",
            "messenger"
        )
    )

    private val actionWords = listOf(
        "open pannunga please",
        "open pannunga",
        "launch pannunga",
        "start pannunga",
        "open pannu",
        "launch pannu",
        "start pannu",
        "pannunga",
        "pannuda",
        "pannu",
        "thiranthu vidu",
        "thiranthu",
        "launch",
        "start",
        "open",
        "show me",
        "go to",
        "run"
    ).sortedByDescending { it.length }

    private val removableWords = listOf(
        "my",
        "the",
        "default",
        "preferred",
        "app",
        "application",
        "please",
        "ah",
        "a",
        "va"
    )

    fun match(input: String): AppMatchResult {

        val query = normalizeQuery(input)

        if (query.isBlank()) {
            return notFound(
                "Which app would you like me to open?"
            )
        }

        val installedApps = appManager.getInstalledApps()
            .distinctBy { it.packageName }

        // 1. Identify preferred app category requests

        val category = categories.entries.firstOrNull { entry ->
            query == entry.key ||
                    query in entry.value
        }

        if (category != null) {

            val categoryName = category.key

            // Check the user's saved preferred app first
            val savedPackage =
                preferenceManager.getPreferredPackage(categoryName)

            var preferredApp = installedApps.firstOrNull {
                it.packageName == savedPackage
            }

            // Use Android's default browser if no saved browser exists
            if (preferredApp == null && categoryName == "browser") {

                val defaultBrowserPackage =
                    preferenceManager.getDefaultBrowserPackage()

                preferredApp = installedApps.firstOrNull {
                    it.packageName == defaultBrowserPackage
                }
            }

            if (preferredApp != null) {
                return AppMatchResult(
                    type = AppMatchType.DIRECT,
                    apps = listOf(preferredApp),
                    message = "Do you want me to open ${preferredApp.name}?",
                    requiresConfirmation = true
                )
            }

            // Find possible installed apps using available app names
            val candidates = installedApps.filter { app ->
                category.value.any { keyword ->
                    app.name.contains(keyword, ignoreCase = true)
                }
            }

            return when (candidates.size) {

                0 -> notFound(
                    "I couldn't find a preferred $categoryName app. Please select one in App Hub."
                )

                1 -> AppMatchResult(
                    type = AppMatchType.SUGGESTION,
                    apps = candidates,
                    message = "Do you want me to open ${candidates.first().name}?",
                    requiresConfirmation = true
                )

                else -> AppMatchResult(
                    type = AppMatchType.MULTIPLE,
                    apps = candidates,
                    message = "I found multiple $categoryName apps. Please choose one."
                )
            }
        }

        // 2. Exact installed app name matching

        val exactMatches = installedApps.filter {
            it.name.equals(query, ignoreCase = true)
        }

        if (exactMatches.size == 1) {
            return AppMatchResult(
                type = AppMatchType.DIRECT,
                apps = exactMatches,
                message = "Opening ${exactMatches.first().name}"
            )
        }

        if (exactMatches.size > 1) {
            return multipleMatches(exactMatches)
        }

        // 3. Partial app name matching

        val partialMatches = installedApps.filter {
            it.name.contains(query, ignoreCase = true)
        }

        return when (partialMatches.size) {

            0 -> notFound(
                "I couldn't find $query on your phone."
            )

            1 -> AppMatchResult(
                type = AppMatchType.SUGGESTION,
                apps = partialMatches,
                message = "Do you mean ${partialMatches.first().name}?",
                requiresConfirmation = true
            )

            else -> multipleMatches(partialMatches)
        }
    }

    private fun normalizeQuery(input: String): String {

        var query = input
            .lowercase()
            .trim()
            .replace(Regex("[.!?,]+"), " ")
            .replace(Regex("\\s+"), " ")

        // Remove wake words
        listOf(
            "hey troit",
            "hi troit",
            "hello troit",
            "troit"
        ).forEach { phrase ->

            if (query.startsWith("$phrase ")) {
                query = query.removePrefix(phrase).trim()
            }
        }

        // Remove opening actions from the beginning
        listOf(
            "open up",
            "show me",
            "could you",
            "can you",
            "launch",
            "start",
            "open",
            "go to",
            "run"
        ).forEach { phrase ->

            if (query.startsWith("$phrase ")) {
                query = query.removePrefix(phrase).trim()
                return@forEach
            }
        }

        // Remove Tanglish and English actions from the end
        var changed = true

        while (changed) {
            changed = false

            val suffix = actionWords.firstOrNull { word ->
                query == word || query.endsWith(" $word")
            }

            if (suffix != null) {
                query = query.removeSuffix(suffix).trim()
                changed = true
            }
        }

        // Remove unnecessary conversational words
        removableWords.forEach { word ->
            query = query.replace(
                Regex("""\b${Regex.escape(word)}\b"""),
                " "
            )
        }

        return query
            .replace(Regex("\\s+"), " ")
            .trim()
    }

    private fun multipleMatches(
        apps: List<TroitApp>
    ): AppMatchResult {
        return AppMatchResult(
            type = AppMatchType.MULTIPLE,
            apps = apps,
            message = "I found multiple matching apps. Please choose one."
        )
    }

    private fun notFound(message: String): AppMatchResult {
        return AppMatchResult(
            type = AppMatchType.NOT_FOUND,
            message = message
        )
    }
}

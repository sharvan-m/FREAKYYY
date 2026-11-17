
package com.troit.assistant

enum class TroitCommandType {
    OPEN_APP,
    UNKNOWN
}

data class TroitCommand(
    val type: TroitCommandType,
    val appName: String = ""
)

object TroitCommandHandler {

    private val commandPrefixes = listOf(
        "open up",
        "show me",
        "could you",
        "can you",
        "launch",
        "start",
        "open",
        "go to",
        "run"
    )

    private val actionSuffixes = listOf(
        "open pannunga please",
        "open pannunga",
        "launch pannunga",
        "start pannunga",
        "open pannuda",
        "launch pannu",
        "start pannu",
        "open pannu",
        "pannunga",
        "pannuda",
        "pannu",
        "thiranthu vidu",
        "thiranthu",
        "launch",
        "start",
        "open",
        "thira",
        "kaatu",
        "kattu"
    ).sortedByDescending { it.length }

    private val removableParticles = listOf(
        " ah",
        " a",
        " va",
        " da"
    )

    private val introductions = listOf(
        "hey freakyyy",
        "hey freaky",
        "hi freakyyy",
        "hi freaky",
        "hello freakyyy",
        "hello freaky",
        "ok freakyyy",
        "ok freaky",
        "okay freakyyy",
        "okay freaky",
        "freakyyy",
        "freaky",
        "hey troit",
        "hi troit",
        "hello troit",
        "troit"
    )

    private val politePrefixes = listOf(
        "please",
        "can you",
        "could you"
    )

    private val appRequestPhrases = listOf(
        "default browser",
        "my browser",
        "preferred browser",
        "browser app",
        "internet browser",

        "default gallery",
        "my default gallery",
        "my gallery",
        "default photos",
        "my photos",
        "photos app",
        "gallery app",
        "albums app",

        "default music",
        "my default music",
        "my music",
        "music app",
        "music player",
        "audio player",

        "default messaging",
        "my messages",
        "my messaging app",
        "messaging app",
        "messages app",
        "chat app",

        "default video",
        "my video app",
        "video app",
        "video player",

        "default camera",
        "my camera",
        "camera app",

        "default maps",
        "my maps",
        "maps app",
        "navigation app"
    )

    fun detectCommand(input: String): TroitCommand {

        var command = input
            .lowercase()
            .trim()
            .replace(Regex("[.!?,]+"), " ")
            .replace(Regex("\\s+"), " ")
            .trim()

        if (command.isBlank()) {
            return unknown()
        }

        // Remove wake words
        introductions.forEach { phrase ->
            if (command.startsWith("$phrase ")) {
                command = command.removePrefix(phrase).trim()
            }
        }

        // Remove polite introductions
        politePrefixes.forEach { phrase ->
            if (command.startsWith("$phrase ")) {
                command = command.removePrefix(phrase).trim()
            }
        }

        if (command.isBlank()) {
            return unknown()
        }

        // Preferred app/category requests must retain their context
        if (appRequestPhrases.any { phrase ->
                Regex("""\b${Regex.escape(phrase)}\b""")
                    .containsMatchIn(command)
            }
        ) {
            return openApp(command)
        }

        // Remove an action prefix
        val prefix = commandPrefixes.firstOrNull { phrase ->
            command.startsWith("$phrase ")
        }

        val hadPrefix = prefix != null

        if (prefix != null) {
            command = command.removePrefix(prefix).trim()
        }

        // Handle repeated commands:
        // "instagram open instagram" -> "instagram"
        val repeatedCommand = Regex(
            """^(.+?)\s+(?:open|launch|start)\s+\1$"""
        )

        val repeatedMatch = repeatedCommand.matchEntire(command)

        if (repeatedMatch != null) {
            command = repeatedMatch.groupValues[1].trim()
        }

        // Remove action suffixes, including Tanglish
        var suffixRemoved = true

        while (suffixRemoved) {
            suffixRemoved = false

            val suffix = actionSuffixes.firstOrNull { action ->
                command == action || command.endsWith(" $action")
            }

            if (suffix != null) {
                command = command
                    .removeSuffix(suffix)
                    .trim()

                suffixRemoved = true
            }
        }

        // Remove conversational particles
        removableParticles.forEach { particle ->
            if (command.endsWith(particle)) {
                command = command.removeSuffix(particle).trim()
            }
        }

        command = command
            .replace(Regex("\\s+"), " ")
            .trim()

        // Reject incomplete commands
        if (command.isBlank()) {
            return unknown()
        }

        // A command must contain an opening action at the
        // beginning or an action word at the end.
        if (!hadPrefix && command == input.lowercase().trim()) {
            return unknown()
        }

        return openApp(command)
    }

    private fun openApp(name: String): TroitCommand {
        return if (name.isNotBlank()) {
            TroitCommand(
                type = TroitCommandType.OPEN_APP,
                appName = name.trim()
            )
        } else {
            unknown()
        }
    }

    private fun unknown(): TroitCommand {
        return TroitCommand(
            type = TroitCommandType.UNKNOWN
        )
    }
}

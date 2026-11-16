
package com.troit.assistant

/**
 * Turns a spoken or typed command into one [FreakyyyAction].
 *
 * Fully local and deterministic: rules run in priority order and the first
 * one that recognises the text wins. Open-app commands fall through to the
 * existing [TroitCommandHandler], so its Tanglish support is preserved.
 */
object FreakyyyIntentParser {

    private val leadingFillers = listOf(
        "hey freakyyy", "hi freakyyy", "hello freakyyy", "ok freakyyy", "okay freakyyy", "freakyyy",
        "hey troit", "hi troit", "hello troit", "troit",
        "please", "kindly", "can you", "could you", "would you", "will you",
        "i want you to", "i want to", "i would like to", "i'd like to", "i need to",
        "just", "now"
    ).sortedByDescending { it.length }

    private val trailingFillers = listOf("please", "for me", "now", "right now", "thanks", "thank you")

    private val settingsSuffix = Regex("""\b(settings?|options|preferences)$""")

    private val rules: List<(String) -> FreakyyyAction?> = listOf(
        ::stopOrWait,
        ::laptop,
        ::conversation,
        ::freakyyyScreens,
        ::notifications,
        ::accessibility,
        ::flashlight,
        ::quietModes,
        ::radios,
        ::brightness,
        ::volume,
        ::deviceInfo,
        ::routine,
        ::appNotificationToggle,
        ::settingsPages,
        ::openApp
    )

    fun parse(input: String): FreakyyyAction {
        val text = normalize(input)
        if (text.isBlank()) return FreakyyyAction.Unknown(input)

        for (rule in rules) {
            rule(text)?.let { return it }
        }
        return FreakyyyAction.Unknown(input)
    }

    fun normalize(input: String): String {
        var text = input
            .lowercase()
            .replace("’", "'")
            // Speech recognisers write the name as "freaky", "freakie", "freaky's"…: all mean the assistant.
            .replace(Regex("""\b(freak(y+|ie|ey|i|ee)|freeky|frikki|friki)('s)?\b"""), "freakyyy")
            .replace(Regex("""[.!?,;:"]+"""), " ")
            .replace("wi-fi", "wifi")
            .replace("wi fi", "wifi")
            .replace(Regex("""\s+"""), " ")
            .trim()

        var changed = true
        while (changed) {
            changed = false
            for (filler in leadingFillers) {
                if (text == filler) {
                    // Saying only the wake word is a greeting.
                    return if (filler.contains("freakyyy") || filler.contains("troit")) "hello" else text
                }
                if (text.startsWith("$filler ")) {
                    text = text.removePrefix(filler).trim()
                    changed = true
                }
            }
            for (filler in trailingFillers) {
                if (text.endsWith(" $filler")) {
                    text = text.removeSuffix(filler).trim()
                    changed = true
                }
            }
        }
        return text
    }

    // =====================================================
    // RULES
    // =====================================================

    private fun stopOrWait(t: String): FreakyyyAction? {
        if (Regex("""^(stop|cancel|halt|abort|end)( (all|everything|it|that|this|the|current|my|any))*( (automation|automations|routine|routines|actions?|tasks?|talking|speaking|now))*$""").matches(t) ||
            Regex("""^(be quiet|quiet|shut up|stop talking|enough|never mind|nevermind)$""").matches(t)
        ) return FreakyyyAction.StopAll

        Regex("""^(wait|pause|delay)( for)? (\d{1,3}) ?(seconds?|secs?|s)?$""").matchEntire(t)?.let {
            return FreakyyyAction.Wait(it.groupValues[3].toInt().coerceIn(1, 120))
        }
        return null
    }

    private val laptopWords = """(laptop|computer|pc|desktop)"""

    /** Commands for the paired laptop; the laptop's own engine interprets them. */
    private fun laptop(t: String): FreakyyyAction? {
        if (Regex("""^(pair|connect|link|add)( (to|with))?( my| a| the)? $laptopWords|^(show |open )?(my )?devices$|^freakyyy link$""").matches(t))
            return FreakyyyAction.Navigate(FreakyyyScreen.DEVICES)
        if (Regex("""^(find|locate|ring|where is|where's)( my| the)? $laptopWords$""").matches(t))
            return FreakyyyAction.LaptopRing
        if (Regex("""^(send|share|copy|push)( my| the)? clipboard to( my| the)? $laptopWords$""").matches(t))
            return FreakyyyAction.ClipboardToLaptop
        if (Regex("""^(get|read|pull|paste|show)( my| the)? $laptopWords('s)? clipboard( here)?$""").matches(t))
            return FreakyyyAction.ClipboardFromLaptop

        Regex("""^(start|run|begin|activate|enable)( my| the)? (.+?)( routine| mode)? on (both|all)( my)?( devices| phone and laptop| laptop and phone)$""").matchEntire(t)?.let {
            return FreakyyyAction.RoutineBoth(it.groupValues[3].trim())
        }

        // "open vscode on my laptop", "lock my laptop", "check my laptop battery"
        Regex("""\s(on|in|from|using) (my |the )?(laptop|computer|pc|desktop|windows)( instead| too)?$""").find(t)?.let { m ->
            val rest = t.removeRange(m.range).trim()
            if (rest.isNotEmpty()) return FreakyyyAction.Laptop(rest)
        }
        Regex("""\b(my |the )?$laptopWords('s)?\b""").find(t)?.let { m ->
            if (Regex("""\b(phone|mobile)\b""").containsMatchIn(t)) return null
            val rest = t.removeRange(m.range).replace(Regex("""\s+"""), " ").trim()
            return FreakyyyAction.Laptop(rest.ifEmpty { "status" })
        }
        return null
    }

    private fun conversation(t: String): FreakyyyAction? {
        val topic = when {
            Regex("""^(hi|hello|hey|yo|good (morning|afternoon|evening)|namaste|vanakkam)( there)?$""").matches(t) -> InfoTopic.GREETING
            Regex("""\b(what('s| is)? the time|what time is it|current time|tell me the time|time now|time is it)\b""").containsMatchIn(t) -> InfoTopic.TIME
            Regex("""\b(what('s| is)? (the |today's )?date|what day is (it|today)|today's date|which day is today)\b""").containsMatchIn(t) -> InfoTopic.DATE
            Regex("""\b(who are you|what('s| is) your name|introduce yourself|your name)\b""").containsMatchIn(t) -> InfoTopic.IDENTITY
            Regex("""^(help|help me|what can you do|what do you do|commands|show commands|what can i say)$""").matches(t) -> InfoTopic.HELP
            Regex("""^(thank you|thanks|thank you so much|thanks a lot|great|awesome|nice|cool)( freakyyy)?$""").matches(t) -> InfoTopic.THANKS
            Regex("""\bhow are you\b""").containsMatchIn(t) -> InfoTopic.WELLBEING
            else -> null
        }
        return topic?.let { FreakyyyAction.Info(it) }
    }

    private fun freakyyyScreens(t: String): FreakyyyAction? {
        val screen = when {
            Regex("""^((show|open|list|see)( me)?( all)?( my)? )?(installed (apps|applications)|app hub|my apps|all apps|all applications|my applications)$""").matches(t) -> FreakyyyScreen.APPS
            Regex("""^((show|open|manage|see)( me)?( my)? )?(routines|automations|automation list|my routines)$""").matches(t) -> FreakyyyScreen.ROUTINES
            Regex("""^((show|open|see)( me)?( my)? )?((command|automation|action) )?history$""").matches(t) -> FreakyyyScreen.HISTORY
            Regex("""^((show|open|see)( me)?( the)? )?(permission (center|centre)|freakyyy permissions|permissions center|permissions centre)$""").matches(t) -> FreakyyyScreen.PERMISSIONS
            Regex("""^((show|open|see)( me)?( the)? )?(voice settings|voice engine|voice configuration|freakyyy settings|freakyyy voice|your voice settings)$""").matches(t) -> FreakyyyScreen.VOICE
            else -> null
        }
        return screen?.let { FreakyyyAction.Navigate(it) }
    }

    private fun notifications(t: String): FreakyyyAction? {
        if (settingsSuffix.containsMatchIn(t)) return null
        if (Regex("""^(read|check|show|list|summari[sz]e|tell me|what are|do i have any|any|how many)( me)?( all)?( my)?( new| unread| recent)? notifications?( do i have)?$""").matches(t))
            return FreakyyyAction.NotificationSummary
        if (Regex("""^(clear|dismiss|remove|delete)( all)?( my)?( the)? notifications$""").matches(t))
            return FreakyyyAction.ClearNotifications
        return null
    }

    private fun accessibility(t: String): FreakyyyAction? {
        val global = when {
            Regex("""^(go )?back$|^press back$""").matches(t) -> FreakyyyGlobalAction.BACK
            Regex("""^(go )?(to )?(the )?home( screen)?$|^go home$""").matches(t) -> FreakyyyGlobalAction.HOME
            Regex("""^((show|open) )?(the )?(recent apps|recents|recent applications|overview|app switcher|recent screens)$""").matches(t) -> FreakyyyGlobalAction.RECENTS
            Regex("""^((open|show|pull down|expand) )?(the )?notification (shade|panel|bar|drawer)$""").matches(t) -> FreakyyyGlobalAction.NOTIFICATIONS
            Regex("""^((open|show|pull down|expand) )?(the )?quick (settings|toggles|panel)$""").matches(t) -> FreakyyyGlobalAction.QUICK_SETTINGS
            Regex("""^(take (a )?screen ?shot|screen ?shot|capture (the )?screen)$""").matches(t) -> FreakyyyGlobalAction.SCREENSHOT
            Regex("""^lock (the |my )?(screen|phone|device)$""").matches(t) -> FreakyyyGlobalAction.LOCK_SCREEN
            else -> null
        }
        if (global != null) return FreakyyyAction.GlobalAction(global)

        Regex("""^scroll (down|up|forward|back(ward)?)$""").matchEntire(t)?.let {
            val forward = it.groupValues[1] == "down" || it.groupValues[1] == "forward"
            return FreakyyyAction.Scroll(forward)
        }

        Regex("""^(tap|click|press|touch|hit)( on)?( the)? (.+?)( button| option| tab)?$""").matchEntire(t)?.let {
            val target = it.groupValues[4].trim()
            if (target.isNotEmpty()) return FreakyyyAction.TapOnScreen(target)
        }
        return null
    }

    private fun flashlight(t: String): FreakyyyAction? {
        if (!Regex("""\b(flashlight|flash light|torch|torchlight)\b""").containsMatchIn(t)) return null
        return FreakyyyAction.SetFlashlight(onOff(t))
    }

    private fun quietModes(t: String): FreakyyyAction? {
        if (settingsSuffix.containsMatchIn(t)) return null

        if (Regex("""\b(do not disturb|don't disturb|dont disturb|dnd|focus mode)\b""").containsMatchIn(t)) {
            return FreakyyyAction.SetDoNotDisturb(onOff(t) ?: true)
        }

        if (Regex("""\b(dark (theme|mode)|night (theme|mode))\b""").containsMatchIn(t)) {
            return FreakyyyAction.SetDarkTheme(onOff(t) ?: true)
        }
        if (Regex("""\blight (theme|mode)\b""").containsMatchIn(t)) {
            return FreakyyyAction.SetDarkTheme(onOff(t) == false)
        }

        val explicitOff = onOff(t) == false
        return when {
            Regex("""\b(silent|silence my phone|silence the phone|put (my |the )?phone on silent)\b""").containsMatchIn(t) ->
                FreakyyyAction.SetRingerMode(if (explicitOff) RingerMode.NORMAL else RingerMode.SILENT)
            Regex("""\b(vibrate|vibration) mode\b|^vibrate$|on vibrate$""").containsMatchIn(t) ->
                FreakyyyAction.SetRingerMode(if (explicitOff) RingerMode.NORMAL else RingerMode.VIBRATE)
            Regex("""\b(ring|ringer|normal|general|sound) mode\b""").containsMatchIn(t) ->
                FreakyyyAction.SetRingerMode(RingerMode.NORMAL)
            else -> null
        }
    }

    private fun radios(t: String): FreakyyyAction? {
        if (settingsSuffix.containsMatchIn(t)) return null
        val state = onOff(t) ?: return null
        return when {
            Regex("""\b(bluetooth|blue tooth)\b""").containsMatchIn(t) -> FreakyyyAction.SetBluetooth(state)
            Regex("""\bwifi\b""").containsMatchIn(t) -> FreakyyyAction.SetWifi(state)
            Regex("""\b(battery saver|power saving|power saver)\b""").containsMatchIn(t) ->
                FreakyyyAction.OpenSystemSettings(SystemSettingsPage.BATTERY_SAVER)
            Regex("""\b(airplane|aeroplane|flight) mode\b""").containsMatchIn(t) ->
                FreakyyyAction.OpenSystemSettings(SystemSettingsPage.AIRPLANE)
            Regex("""\b(hotspot|hot spot|tethering)\b""").containsMatchIn(t) ->
                FreakyyyAction.OpenSystemSettings(SystemSettingsPage.HOTSPOT)
            Regex("""\b(mobile data|cellular data)\b""").containsMatchIn(t) ->
                FreakyyyAction.OpenSystemSettings(SystemSettingsPage.INTERNET)
            Regex("""\b(location|gps)\b""").containsMatchIn(t) ->
                FreakyyyAction.OpenSystemSettings(SystemSettingsPage.LOCATION)
            Regex("""\bnfc\b""").containsMatchIn(t) ->
                FreakyyyAction.OpenSystemSettings(SystemSettingsPage.NFC)
            else -> null
        }
    }

    private fun brightness(t: String): FreakyyyAction? {
        if (settingsSuffix.containsMatchIn(t)) return null
        val mentions = Regex("""\b(brightness|bright|brighter|dimmer|dim the screen|dim screen|screen light)\b""").containsMatchIn(t)
        if (!mentions) return null
        val change = level(t, upWords = "brighter|bright up", downWords = "dimmer|dim")
            ?: return FreakyyyAction.OpenSystemSettings(SystemSettingsPage.DISPLAY)
        if (change == LevelChange.Mute || change == LevelChange.Unmute) return null
        return FreakyyyAction.SetBrightness(change)
    }

    private fun volume(t: String): FreakyyyAction? {
        if (settingsSuffix.containsMatchIn(t)) return null
        val mentions = Regex("""\b(volume|louder|quieter|softer)\b""").containsMatchIn(t) ||
                Regex("""^(un)?mute( the)?( (phone|media|music|sound|audio|volume|video))?$""").matches(t)
        if (!mentions) return null

        val stream = when {
            Regex("""\b(ring|ringer|ringtone|ringing)\b""").containsMatchIn(t) -> VolumeStream.RING
            Regex("""\balarms?\b""").containsMatchIn(t) -> VolumeStream.ALARM
            Regex("""\bnotifications?\b""").containsMatchIn(t) -> VolumeStream.NOTIFICATION
            Regex("""\b(call|in-call|voice call)\b""").containsMatchIn(t) -> VolumeStream.CALL
            else -> VolumeStream.MEDIA
        }
        val change = level(t, upWords = "louder", downWords = "quieter|softer")
            ?: return FreakyyyAction.OpenSystemSettings(SystemSettingsPage.SOUND)
        return FreakyyyAction.SetVolume(stream, change)
    }

    private fun deviceInfo(t: String): FreakyyyAction? {
        if (settingsSuffix.containsMatchIn(t)) return null

        if (Regex("""\b(most (storage|space)|(apps?|applications?) (using|taking|by|with|eating) (the )?(most )?(storage|space)|storage (by|per) app|biggest apps|largest apps)\b""").containsMatchIn(t))
            return FreakyyyAction.StorageByApp

        if (Regex("""\b(storage|space|memory)\b""").containsMatchIn(t) &&
            Regex("""\b(how much|free|left|available|status|remaining|used|check|full)\b""").containsMatchIn(t)
        ) return FreakyyyAction.StorageStatus

        if (Regex("""^((show|check|get|what's|what is)( my| the)? )?(battery|battery level|battery status|battery percentage)$""").matches(t) ||
            (Regex("""\b(battery|charge|charging)\b""").containsMatchIn(t) &&
                    Regex("""\b(level|status|percent|percentage|how much|left|remaining|check|charged|charging|what)\b""").containsMatchIn(t))
        ) return FreakyyyAction.BatteryStatus

        return null
    }

    private fun routine(t: String): FreakyyyAction? {
        Regex("""^(start|run|begin|activate|launch|do|execute|play|enable|turn on|switch to)( my| the)? (.+?)( routine| mode| automation)$""").matchEntire(t)?.let {
            return FreakyyyAction.RunRoutine(it.groupValues[3].trim())
        }
        Regex("""^(my )?(.+?) routine$""").matchEntire(t)?.let {
            return FreakyyyAction.RunRoutine(it.groupValues[2].trim())
        }
        Regex("""^(start|run|begin|activate)( my| the)? (study|sleep|work|focus|morning|night|gym|drive|driving)( time)?$""").matchEntire(t)?.let {
            return FreakyyyAction.RunRoutine(it.groupValues[3].trim())
        }
        return null
    }

    private fun appNotificationToggle(t: String): FreakyyyAction? {
        Regex("""^(turn off|turn on|disable|enable|mute|unmute|block|unblock|stop|allow|silence|manage)( all)? (.+?) notifications?$""").matchEntire(t)?.let {
            return appOrSystemNotifications(it.groupValues[3])
        }
        Regex("""^(turn off|turn on|disable|enable|mute|unmute|block|unblock|stop|allow|silence|manage)( all)? notifications? (for|from|of) (.+)$""").matchEntire(t)?.let {
            return appOrSystemNotifications(it.groupValues[4])
        }
        return null
    }

    private fun appOrSystemNotifications(rawName: String): FreakyyyAction {
        val name = cleanAppName(rawName)
        return if (name.isEmpty() || name in listOf("all", "my", "phone", "the", "app", "apps")) {
            FreakyyyAction.OpenSystemSettings(SystemSettingsPage.NOTIFICATIONS)
        } else {
            FreakyyyAction.OpenAppSettings(name, AppSettingsPage.NOTIFICATIONS)
        }
    }

    private fun settingsPages(t: String): FreakyyyAction? {
        val opener = """(?:(?:open|show|go to|launch|take me to|bring up|display|manage|check|view)(?: me)? )?(?:the |my )?"""

        // "<x> settings"
        Regex("""^$opener(.*?) ?(?:settings?|options|preferences|page)$""").matchEntire(t)?.let {
            val phrase = it.groupValues[1].trim()
            return resolveSettingsPhrase(phrase)
        }

        // "settings for <app>"
        Regex("""^$opener(?:settings?|options|info|information|details|app info|application info|app information|application information|app details)(?: for| of| about) (.+)$""").matchEntire(t)?.let {
            return FreakyyyAction.OpenAppSettings(cleanAppName(it.groupValues[1]), AppSettingsPage.DETAILS)
        }

        // "<app> app info"
        Regex("""^$opener(.+?) (?:app |application )?(?:info|information|details)$""").matchEntire(t)?.let {
            return FreakyyyAction.OpenAppSettings(cleanAppName(it.groupValues[1]), AppSettingsPage.DETAILS)
        }

        // "<app> permissions" / "permissions for <app>"
        Regex("""^$opener(.+?) (?:app )?permissions?$""").matchEntire(t)?.let {
            val name = cleanAppName(it.groupValues[1])
            return if (name in listOf("app", "apps", "all", "")) FreakyyyAction.OpenSystemSettings(SystemSettingsPage.PRIVACY)
            else FreakyyyAction.OpenAppSettings(name, AppSettingsPage.PERMISSIONS)
        }
        Regex("""^$opener(?:app )?permissions? (?:for|of) (.+)$""").matchEntire(t)?.let {
            return FreakyyyAction.OpenAppSettings(cleanAppName(it.groupValues[1]), AppSettingsPage.PERMISSIONS)
        }

        // "<app> storage" (app storage), unless it's the system page
        Regex("""^$opener(.+?) (?:app )?(?:storage|cache|data)$""").matchEntire(t)?.let {
            val name = cleanAppName(it.groupValues[1])
            if (SystemSettingsPage.find(name) == null && name !in listOf("phone", "internal", "device", "free")) {
                return FreakyyyAction.OpenAppSettings(name, AppSettingsPage.STORAGE)
            }
            return FreakyyyAction.OpenSystemSettings(SystemSettingsPage.STORAGE)
        }

        // "<x> notifications" with an opener: "open whatsapp notifications"
        Regex("""^(?:open|show|manage) (?:the |my )?(.+?) notifications?$""").matchEntire(t)?.let {
            return appOrSystemNotifications(it.groupValues[1])
        }

        return null
    }

    private fun resolveSettingsPhrase(rawPhrase: String): FreakyyyAction {
        val phrase = rawPhrase.removeSuffix(" app").trim()
        if (phrase.isEmpty()) return FreakyyyAction.OpenSystemSettings(SystemSettingsPage.MAIN)

        SystemSettingsPage.find(phrase)?.let { return FreakyyyAction.OpenSystemSettings(it) }

        Regex("""^(.+?) (notifications?|notification)$""").matchEntire(phrase)?.let {
            return appOrSystemNotifications(it.groupValues[1])
        }
        Regex("""^(.+?) (permissions?)$""").matchEntire(phrase)?.let {
            return FreakyyyAction.OpenAppSettings(cleanAppName(it.groupValues[1]), AppSettingsPage.PERMISSIONS)
        }
        Regex("""^(.+?) (storage)$""").matchEntire(phrase)?.let {
            return FreakyyyAction.OpenAppSettings(cleanAppName(it.groupValues[1]), AppSettingsPage.STORAGE)
        }
        Regex("""^(app|apps|application|applications) (.+)$""").matchEntire(phrase)?.let {
            SystemSettingsPage.find(phrase)?.let { page -> return FreakyyyAction.OpenSystemSettings(page) }
            return FreakyyyAction.OpenAppSettings(cleanAppName(it.groupValues[2]), AppSettingsPage.DETAILS)
        }
        return FreakyyyAction.OpenAppSettings(cleanAppName(phrase), AppSettingsPage.DETAILS)
    }

    private fun openApp(t: String): FreakyyyAction? {
        val command = TroitCommandHandler.detectCommand(t)
        if (command.type == TroitCommandType.OPEN_APP && command.appName.isNotBlank()) {
            return FreakyyyAction.OpenApp(command.appName)
        }
        return null
    }

    // =====================================================
    // HELPERS
    // =====================================================

    /** Off is checked first so "turn off" never reads as "on". */
    private fun onOff(t: String): Boolean? = when {
        Regex("""\b(off|disable|deactivate|turn off|switch off|stop|kill)\b""").containsMatchIn(t) -> false
        Regex("""\b(on|enable|activate|turn on|switch on|start)\b""").containsMatchIn(t) -> true
        else -> null
    }

    private fun level(t: String, upWords: String, downWords: String): LevelChange? {
        if (Regex("""\bunmute\b""").containsMatchIn(t)) return LevelChange.Unmute
        if (Regex("""\bmute\b""").containsMatchIn(t)) return LevelChange.Mute

        Regex("""(\d{1,3})\s*(%|percent|per cent)?""").find(t)?.let {
            return LevelChange.Percent(it.groupValues[1].toInt().coerceIn(0, 100))
        }
        return when {
            Regex("""\bhalf\b""").containsMatchIn(t) -> LevelChange.Percent(50)
            Regex("""\b(max|maximum|full|highest|100)\b""").containsMatchIn(t) -> LevelChange.Max
            Regex("""\b(min|minimum|lowest|zero)\b""").containsMatchIn(t) -> LevelChange.Min
            Regex("""\b(increase|raise|up|higher|more|turn up|boost|$upWords)\b""").containsMatchIn(t) -> LevelChange.Up
            Regex("""\b(decrease|lower|reduce|down|less|turn down|$downWords)\b""").containsMatchIn(t) -> LevelChange.Down
            else -> null
        }
    }

    private fun cleanAppName(raw: String): String = raw
        .trim()
        .removePrefix("the ")
        .removePrefix("my ")
        .removeSuffix(" app")
        .removeSuffix(" application")
        .removeSuffix("'s")
        .trim()
}

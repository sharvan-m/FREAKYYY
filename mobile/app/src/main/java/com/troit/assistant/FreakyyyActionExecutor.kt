
package com.troit.assistant

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import android.provider.AlarmClock
import android.provider.MediaStore
import android.provider.Settings
import androidx.core.content.ContextCompat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Executes one structured [FreakyyyAction] with official Android APIs and
 * reports what really happened: DONE only when the change was made,
 * OPENED when the user still has to finish it on a system screen.
 *
 * Routines, waiting and "stop" are handled by [FreakyyyAssistant].
 */
class FreakyyyActionExecutor(
    context: Context,
    private val appManager: TroitAppManager,
    private val appMatcher: TroitAppMatcher,
    private val device: FreakyyyDeviceController
) {

    private val appContext = context.applicationContext

    fun execute(action: FreakyyyAction, confirmed: Boolean = false): FreakyyyResult = when (action) {
        is FreakyyyAction.OpenApp -> openApp(action.appName)
        is FreakyyyAction.LaunchResolvedApp -> launch(action.app)
        is FreakyyyAction.OpenAppSettings -> openAppSettings(action.appName, action.page)
        is FreakyyyAction.ResolvedAppSettings -> appSettingsFor(action.app, action.page)
        is FreakyyyAction.OpenSystemSettings -> openSystemPage(action.page)
        is FreakyyyAction.SetBrightness -> device.setBrightness(action.change)
        is FreakyyyAction.SetVolume -> device.setVolume(action.stream, action.change)
        is FreakyyyAction.SetFlashlight -> device.setFlashlight(action.on)
        is FreakyyyAction.SetBluetooth -> bluetooth(action.on)
        is FreakyyyAction.SetWifi -> wifi(action.on)
        is FreakyyyAction.SetRingerMode -> device.setRingerMode(action.mode)
        is FreakyyyAction.SetDoNotDisturb -> device.setDoNotDisturb(action.on)
        is FreakyyyAction.SetDarkTheme -> darkTheme(action.on)
        FreakyyyAction.BatteryStatus -> device.batteryStatus()
        FreakyyyAction.StorageStatus -> device.storageStatus()
        FreakyyyAction.StorageByApp -> storageByApp()
        FreakyyyAction.NotificationSummary -> notificationSummary()
        FreakyyyAction.ClearNotifications -> clearNotifications(confirmed)
        is FreakyyyAction.Info -> info(action.topic)
        is FreakyyyAction.GlobalAction -> globalAction(action.action)
        is FreakyyyAction.TapOnScreen -> tap(action.text, confirmed)
        is FreakyyyAction.Scroll -> scroll(action.forward)
        is FreakyyyAction.Navigate -> navigate(action.screen)
        is FreakyyyAction.Unknown -> FreakyyyResult(
            Outcome.FAILED,
            "I didn't catch a command in that. Try \"open WhatsApp\", \"set brightness to 40 percent\" or say \"help\".",
            spoken = "Sorry, I didn't catch a command in that. Say help to hear what I can do."
        )
        is FreakyyyAction.RunRoutine,
        is FreakyyyAction.Wait,
        FreakyyyAction.StopAll,
        is FreakyyyAction.Laptop,
        FreakyyyAction.LaptopRing,
        FreakyyyAction.ClipboardToLaptop,
        FreakyyyAction.ClipboardFromLaptop,
        is FreakyyyAction.RoutineBoth,
        is FreakyyyAction.LaptopConfirm -> FreakyyyResult(Outcome.FAILED, "That's handled by the assistant.")
    }

    // =====================================================
    // APPLICATIONS
    // =====================================================

    private fun openApp(name: String): FreakyyyResult {
        val result = appMatcher.match(name)
        return when (result.type) {
            AppMatchType.DIRECT -> {
                val app = result.apps.firstOrNull()
                    ?: return FreakyyyResult(Outcome.FAILED, "I couldn't identify that app.")
                if (result.requiresConfirmation) {
                    confirm("Do you want me to open ${app.name}?", FreakyyyAction.LaunchResolvedApp(app))
                } else {
                    launch(app)
                }
            }

            AppMatchType.SUGGESTION -> {
                val app = result.apps.firstOrNull()
                if (app != null) confirm("Do you want me to open ${app.name}?", FreakyyyAction.LaunchResolvedApp(app))
                else FreakyyyResult(Outcome.FAILED, result.message)
            }

            AppMatchType.MULTIPLE -> multiple(result.apps, "open")

            AppMatchType.NOT_FOUND -> {
                // "open bluetooth" -> Bluetooth settings
                SystemSettingsPage.find(name)?.let { return openSystemPage(it) }
                launchByCategory(name) ?: FreakyyyResult(Outcome.FAILED, result.message)
            }
        }
    }

    private fun launch(app: TroitApp): FreakyyyResult =
        if (appManager.launchApp(app)) FreakyyyResult(Outcome.DONE, "Opening ${app.name}")
        else FreakyyyResult(Outcome.FAILED, "I couldn't open ${app.name}.")

    /** Standard Android category intents for apps the user didn't name. */
    private fun launchByCategory(name: String): FreakyyyResult? {
        val key = name.lowercase().trim()
        val (label, intent) = when (key) {
            "camera", "the camera", "photo camera" ->
                "Camera" to Intent(MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA)
            "video camera", "camcorder" ->
                "Video camera" to Intent(MediaStore.INTENT_ACTION_VIDEO_CAMERA)
            "phone", "dialer", "dial pad", "dialpad", "phone app" ->
                "Phone" to Intent(Intent.ACTION_DIAL)
            "browser", "internet", "web browser" ->
                "Browser" to Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_BROWSER)
            "maps", "map", "navigation" ->
                "Maps" to Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_MAPS)
            "contacts", "contact" ->
                "Contacts" to Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_CONTACTS)
            "calendar" ->
                "Calendar" to Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_CALENDAR)
            "email", "mail", "e-mail" ->
                "Email" to Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_EMAIL)
            "messages", "messaging", "sms", "text messages" ->
                "Messages" to Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_MESSAGING)
            "music", "music player" ->
                "Music" to Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_MUSIC)
            "gallery", "photos", "pictures" ->
                "Gallery" to Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_GALLERY)
            "calculator" ->
                "Calculator" to Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_CALCULATOR)
            "alarm", "alarms", "clock" ->
                "Alarms" to Intent(AlarmClock.ACTION_SHOW_ALARMS)
            else -> return null
        }
        return if (start(intent)) FreakyyyResult(Outcome.DONE, "Opening $label")
        else null
    }

    private fun openAppSettings(name: String, page: AppSettingsPage): FreakyyyResult {
        val result = appMatcher.match(name)
        val app = result.apps.firstOrNull()
        return when {
            result.type == AppMatchType.MULTIPLE -> multiple(result.apps, "show settings for")
            app == null -> {
                SystemSettingsPage.find(name)?.let { return openSystemPage(it) }
                FreakyyyResult(Outcome.FAILED, "I couldn't find $name on your phone.")
            }
            result.type == AppMatchType.SUGGESTION ->
                confirm("Do you mean ${app.name}?", FreakyyyAction.ResolvedAppSettings(app, page))
            else -> appSettingsFor(app, page)
        }
    }

    private fun appSettingsFor(app: TroitApp, page: AppSettingsPage): FreakyyyResult {
        val details = Intent(
            Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
            Uri.fromParts("package", app.packageName, null)
        )

        return when (page) {
            AppSettingsPage.NOTIFICATIONS -> {
                val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                    .putExtra(Settings.EXTRA_APP_PACKAGE, app.packageName)
                if (start(intent) || start(details)) {
                    FreakyyyResult(
                        Outcome.OPENED,
                        "I've opened ${app.name}'s notification settings. Switch them on or off there — " +
                                "Android doesn't let other apps change another app's notifications.",
                        spoken = "I've opened ${app.name} notification settings. You can switch them there."
                    )
                } else failedToOpen()
            }

            AppSettingsPage.PERMISSIONS -> if (start(details)) {
                FreakyyyResult(
                    Outcome.OPENED,
                    "I've opened ${app.name}'s app info. Tap Permissions to review them.",
                )
            } else failedToOpen()

            AppSettingsPage.STORAGE -> if (start(details)) {
                FreakyyyResult(
                    Outcome.OPENED,
                    "I've opened ${app.name}'s app info. Tap Storage to see or clear its storage and cache.",
                )
            } else failedToOpen()

            AppSettingsPage.DETAILS -> if (start(details)) {
                FreakyyyResult(
                    Outcome.OPENED,
                    "I've opened Android's app settings for ${app.name}. Settings inside ${app.name} itself, " +
                            "like account or privacy options, have no public shortcut — open the app's own menu for those.",
                    spoken = "I've opened the app settings for ${app.name}."
                )
            } else failedToOpen()
        }
    }

    private fun multiple(apps: List<TroitApp>, verb: String): FreakyyyResult {
        val names = apps.take(3).joinToString(", ") { it.name }
        val more = if (apps.size > 3) " and ${apps.size - 3} more" else ""
        return FreakyyyResult(
            Outcome.FAILED,
            "I found several matches: $names$more. Say the full name of the one you want me to $verb."
        )
    }

    // =====================================================
    // SYSTEM SETTINGS
    // =====================================================

    fun openSystemPage(page: SystemSettingsPage): FreakyyyResult {
        for (action in page.actions()) {
            if (start(Intent(action))) {
                return FreakyyyResult(Outcome.OPENED, "Opening ${page.title}.")
            }
        }
        return if (start(Intent(Settings.ACTION_SETTINGS))) {
            FreakyyyResult(Outcome.OPENED, "This phone has no direct ${page.title} page, so I've opened Settings.")
        } else failedToOpen()
    }

    private fun bluetooth(on: Boolean): FreakyyyResult {
        val adapter = appContext.getSystemService(BluetoothManager::class.java)?.adapter
            ?: return FreakyyyResult(Outcome.NOT_SUPPORTED, "This device doesn't have Bluetooth.")

        val enabled = try { adapter.isEnabled } catch (_: SecurityException) { null }
        if (enabled == on) {
            return FreakyyyResult(Outcome.DONE, if (on) "Bluetooth is already on." else "Bluetooth is already off.")
        }

        if (!on) {
            openSystemPage(SystemSettingsPage.BLUETOOTH)
            return FreakyyyResult(
                Outcome.OPENED,
                "Android doesn't let apps switch Bluetooth off. I've opened Bluetooth settings so you can turn it off."
            )
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.BLUETOOTH_CONNECT) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return FreakyyyResult(
                Outcome.NEEDS_PERMISSION,
                "I need the Nearby devices permission to ask Android to turn Bluetooth on.",
                permission = Manifest.permission.BLUETOOTH_CONNECT
            )
        }

        return try {
            if (start(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))) {
                FreakyyyResult(Outcome.OPENED, "Android is asking to turn Bluetooth on. Tap Allow to confirm.")
            } else {
                openSystemPage(SystemSettingsPage.BLUETOOTH)
            }
        } catch (_: SecurityException) {
            openSystemPage(SystemSettingsPage.BLUETOOTH)
        }
    }

    private fun wifi(on: Boolean): FreakyyyResult {
        val manager = appContext.getSystemService(WifiManager::class.java)
        val enabled = try { manager?.isWifiEnabled } catch (_: SecurityException) { null }
        if (enabled == on) {
            return FreakyyyResult(Outcome.DONE, if (on) "Wi-Fi is already on." else "Wi-Fi is already off.")
        }

        val opened = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            start(Intent(Settings.Panel.ACTION_WIFI)) || start(Intent(Settings.ACTION_WIFI_SETTINGS))
        } else {
            start(Intent(Settings.ACTION_WIFI_SETTINGS))
        }
        return if (opened) {
            FreakyyyResult(
                Outcome.OPENED,
                "Android only lets you switch Wi-Fi yourself. I've opened the Wi-Fi controls — tap the switch to turn it ${if (on) "on" else "off"}."
            )
        } else failedToOpen()
    }

    private fun darkTheme(on: Boolean): FreakyyyResult {
        val uiMode = appContext.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK
        val isDark = uiMode == Configuration.UI_MODE_NIGHT_YES
        if (isDark == on) {
            return FreakyyyResult(Outcome.DONE, if (on) "Dark theme is already on." else "Dark theme is already off.")
        }

        // Changing the system theme requires a privileged permission.
        val opened = start(Intent("android.settings.DARK_THEME_SETTINGS")) ||
                start(Intent(Settings.ACTION_DISPLAY_SETTINGS))
        return if (opened) {
            FreakyyyResult(
                Outcome.OPENED,
                "Android doesn't let apps change the system theme. I've opened the display settings — switch Dark theme ${if (on) "on" else "off"} there."
            )
        } else failedToOpen()
    }

    private fun storageByApp(): FreakyyyResult {
        val opened = start(Intent(Settings.ACTION_INTERNAL_STORAGE_SETTINGS))
        return if (opened) {
            FreakyyyResult(
                Outcome.OPENED,
                "I've opened Storage. Android lists apps by size there. Reading every app's size directly would need extra usage access, which Freakyyy doesn't request."
            )
        } else failedToOpen()
    }

    // =====================================================
    // NOTIFICATIONS
    // =====================================================

    private fun notificationSummary(): FreakyyyResult {
        val listener = FreakyyyNotificationListener.instance
            ?: return FreakyyyResult(
                Outcome.NEEDS_PERMISSION,
                "To count your notifications I need notification access. Freakyyy only counts them per app and never reads their content. You can turn it on in Permissions.",
                navigate = FreakyyyScreen.PERMISSIONS
            )

        val counts = listener.countsByApp()
        if (counts.isEmpty()) return FreakyyyResult(Outcome.INFO, "You have no notifications.")

        val total = counts.values.sum()
        val top = counts.entries.sortedByDescending { it.value }.take(3).joinToString(", ") {
            "${it.value} from ${labelFor(it.key)}"
        }
        return FreakyyyResult(Outcome.INFO, "You have $total notification${if (total == 1) "" else "s"}: $top.")
    }

    private fun clearNotifications(confirmed: Boolean): FreakyyyResult {
        val listener = FreakyyyNotificationListener.instance
            ?: return FreakyyyResult(
                Outcome.NEEDS_PERMISSION,
                "Clearing notifications needs notification access. You can turn it on in Permissions.",
                navigate = FreakyyyScreen.PERMISSIONS
            )

        val total = listener.countsByApp().values.sum()
        if (total == 0) return FreakyyyResult(Outcome.INFO, "There are no notifications to clear.")

        if (!confirmed) {
            return confirm(
                "Clear all $total notification${if (total == 1) "" else "s"}? This can't be undone.",
                FreakyyyAction.ClearNotifications
            )
        }
        return if (listener.clearAll()) FreakyyyResult(Outcome.DONE, "Cleared your notifications.")
        else FreakyyyResult(Outcome.FAILED, "Android didn't let me clear the notifications.")
    }

    private fun labelFor(packageName: String): String {
        appManager.getInstalledApps().firstOrNull { it.packageName == packageName }?.let { return it.name }
        return try {
            val pm = appContext.packageManager
            pm.getApplicationLabel(pm.getApplicationInfo(packageName, 0)).toString()
        } catch (_: Exception) {
            "System"
        }
    }

    // =====================================================
    // ACCESSIBILITY (optional)
    // =====================================================

    private fun accessibilityMissing() = FreakyyyResult(
        Outcome.NEEDS_PERMISSION,
        "That needs Freakyyy's optional accessibility helper, which is off. You can enable it in Permissions.",
        navigate = FreakyyyScreen.PERMISSIONS
    )

    private fun globalAction(action: FreakyyyGlobalAction): FreakyyyResult {
        val service = FreakyyyAccessibilityService.instance ?: return accessibilityMissing()
        val ok = service.perform(action)
        val name = when (action) {
            FreakyyyGlobalAction.BACK -> "Going back."
            FreakyyyGlobalAction.HOME -> "Going home."
            FreakyyyGlobalAction.RECENTS -> "Showing recent apps."
            FreakyyyGlobalAction.NOTIFICATIONS -> "Opening the notification shade."
            FreakyyyGlobalAction.QUICK_SETTINGS -> "Opening quick settings."
            FreakyyyGlobalAction.SCREENSHOT -> "Screenshot taken."
            FreakyyyGlobalAction.LOCK_SCREEN -> "Locking the screen."
        }
        return if (ok) FreakyyyResult(Outcome.DONE, name)
        else FreakyyyResult(Outcome.NOT_SUPPORTED, "This version of Android doesn't support that action.")
    }

    private fun tap(label: String, confirmed: Boolean): FreakyyyResult {
        val service = FreakyyyAccessibilityService.instance ?: return accessibilityMissing()
        return when (service.tap(label, confirmed)) {
            FreakyyyAccessibilityService.TapResult.TAPPED -> FreakyyyResult(Outcome.DONE, "Tapped $label.")
            FreakyyyAccessibilityService.TapResult.NOT_FOUND -> FreakyyyResult(Outcome.FAILED, "I couldn't find \"$label\" on the screen.")
            FreakyyyAccessibilityService.TapResult.NO_WINDOW -> FreakyyyResult(Outcome.FAILED, "I can't see the current screen right now.")
            FreakyyyAccessibilityService.TapResult.SENSITIVE -> confirm(
                "\"$label\" looks like a sensitive action. Should I tap it?",
                FreakyyyAction.TapOnScreen(label)
            )
        }
    }

    private fun scroll(forward: Boolean): FreakyyyResult {
        val service = FreakyyyAccessibilityService.instance ?: return accessibilityMissing()
        return if (service.scroll(forward)) FreakyyyResult(Outcome.DONE, if (forward) "Scrolled down." else "Scrolled up.")
        else FreakyyyResult(Outcome.FAILED, "There's nothing to scroll here.")
    }

    // =====================================================
    // FREAKYYY SCREENS AND CONVERSATION
    // =====================================================

    private fun navigate(screen: FreakyyyScreen): FreakyyyResult {
        val message = when (screen) {
            FreakyyyScreen.APPS -> "Here are your installed apps."
            FreakyyyScreen.ROUTINES -> "Here are your routines."
            FreakyyyScreen.HISTORY -> "Here's your command history."
            FreakyyyScreen.PERMISSIONS -> "Here's the permission center."
            FreakyyyScreen.VOICE -> "Here are my voice settings."
            FreakyyyScreen.HOME -> "Back home."
            FreakyyyScreen.DEVICES -> "Here's Freakyyy Link."
        }
        return FreakyyyResult(Outcome.INFO, message, navigate = screen)
    }

    private fun info(topic: InfoTopic): FreakyyyResult {
        val now = Date()
        val message = when (topic) {
            InfoTopic.TIME -> "It's ${SimpleDateFormat("h:mm a", Locale.getDefault()).format(now)}."
            InfoTopic.DATE -> "Today is ${SimpleDateFormat("EEEE, d MMMM yyyy", Locale.getDefault()).format(now)}."
            InfoTopic.IDENTITY -> "I'm Freakyyy, your on-device assistant. I open apps, change settings Android allows, and run your routines."
            InfoTopic.GREETING -> greeting()
            InfoTopic.THANKS -> "Anytime."
            InfoTopic.WELLBEING -> "All systems running. How can I help?"
            InfoTopic.HELP -> "I can open apps and their settings, open any Android settings page, set brightness and volume, " +
                    "switch the flashlight, silent mode and Do Not Disturb, tell you battery and storage, and run routines like \"start my study routine\"."
        }
        return FreakyyyResult(Outcome.INFO, message)
    }

    private fun greeting(): String {
        val hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
        val part = when (hour) {
            in 5..11 -> "Good morning"
            in 12..16 -> "Good afternoon"
            in 17..21 -> "Good evening"
            else -> "Hello"
        }
        return "$part. I'm Freakyyy. What can I do for you?"
    }

    // =====================================================
    // HELPERS
    // =====================================================

    private fun confirm(question: String, action: FreakyyyAction) =
        FreakyyyResult(Outcome.NEEDS_CONFIRMATION, question, confirm = action)

    private fun failedToOpen() =
        FreakyyyResult(Outcome.FAILED, "I couldn't open that screen on this phone.")

    /** Starts an activity; returns false if nothing on the device handles it. */
    fun start(intent: Intent): Boolean = try {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (com.troit.assistant.link.LaunchGate.canOpenDirectly(appContext)) {
            appContext.startActivity(intent)
            true
        } else {
            // In the background (request from the laptop): Android only allows a tap-to-open notification.
            intent.resolveActivity(appContext.packageManager) != null &&
                    com.troit.assistant.link.LaunchGate.start(appContext, intent, "the requested screen")
        }
    } catch (_: ActivityNotFoundException) {
        false
    } catch (_: SecurityException) {
        false
    }
}

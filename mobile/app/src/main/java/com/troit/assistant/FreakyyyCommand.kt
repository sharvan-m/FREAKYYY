
package com.troit.assistant

/**
 * Structured actions produced by [FreakyyyIntentParser]. Every spoken or typed
 * command becomes exactly one of these before anything is executed, so the
 * executor never has to look at raw text.
 */
sealed class FreakyyyAction {

    /** Short label used in history ("OPEN_APP · WhatsApp"). */
    abstract val label: String

    // ---------- Applications ----------

    data class OpenApp(val appName: String) : FreakyyyAction() {
        override val label get() = "OPEN_APP · $appName"
    }

    data class OpenAppSettings(
        val appName: String,
        val page: AppSettingsPage
    ) : FreakyyyAction() {
        override val label get() = "OPEN_APP_SETTINGS · $appName · ${page.name}"
    }

    /** An app already resolved to a package (used after "yes"). */
    data class LaunchResolvedApp(val app: TroitApp) : FreakyyyAction() {
        override val label get() = "OPEN_APP · ${app.name}"
    }

    data class ResolvedAppSettings(
        val app: TroitApp,
        val page: AppSettingsPage
    ) : FreakyyyAction() {
        override val label get() = "OPEN_APP_SETTINGS · ${app.name} · ${page.name}"
    }

    // ---------- Android settings ----------

    data class OpenSystemSettings(val page: SystemSettingsPage) : FreakyyyAction() {
        override val label get() = "OPEN_SETTINGS · ${page.name}"
    }

    data class SetBrightness(val change: LevelChange) : FreakyyyAction() {
        override val label get() = "CHANGE_SETTING · BRIGHTNESS · $change"
    }

    data class SetVolume(
        val stream: VolumeStream,
        val change: LevelChange
    ) : FreakyyyAction() {
        override val label get() = "CHANGE_SETTING · VOLUME_${stream.name} · $change"
    }

    data class SetFlashlight(val on: Boolean?) : FreakyyyAction() {
        override val label get() = "DEVICE · FLASHLIGHT · ${on ?: "TOGGLE"}"
    }

    data class SetBluetooth(val on: Boolean) : FreakyyyAction() {
        override val label get() = "CHANGE_SETTING · BLUETOOTH · ${if (on) "ON" else "OFF"}"
    }

    data class SetWifi(val on: Boolean) : FreakyyyAction() {
        override val label get() = "CHANGE_SETTING · WIFI · ${if (on) "ON" else "OFF"}"
    }

    data class SetRingerMode(val mode: RingerMode) : FreakyyyAction() {
        override val label get() = "CHANGE_SETTING · RINGER · ${mode.name}"
    }

    data class SetDoNotDisturb(val on: Boolean) : FreakyyyAction() {
        override val label get() = "CHANGE_SETTING · DND · ${if (on) "ON" else "OFF"}"
    }

    data class SetDarkTheme(val on: Boolean) : FreakyyyAction() {
        override val label get() = "CHANGE_SETTING · DARK_THEME · ${if (on) "ON" else "OFF"}"
    }

    // ---------- Information ----------

    object BatteryStatus : FreakyyyAction() {
        override val label get() = "INFO · BATTERY"
    }

    object StorageStatus : FreakyyyAction() {
        override val label get() = "INFO · STORAGE"
    }

    object StorageByApp : FreakyyyAction() {
        override val label get() = "INFO · STORAGE_BY_APP"
    }

    object NotificationSummary : FreakyyyAction() {
        override val label get() = "NOTIFICATIONS · SUMMARY"
    }

    object ClearNotifications : FreakyyyAction() {
        override val label get() = "NOTIFICATIONS · CLEAR"
    }

    data class Info(val topic: InfoTopic) : FreakyyyAction() {
        override val label get() = "INFO · ${topic.name}"
    }

    // ---------- Accessibility (optional, user-enabled) ----------

    data class GlobalAction(val action: FreakyyyGlobalAction) : FreakyyyAction() {
        override val label get() = "ACCESSIBILITY · ${action.name}"
    }

    data class TapOnScreen(val text: String) : FreakyyyAction() {
        override val label get() = "ACCESSIBILITY · TAP · $text"
    }

    data class Scroll(val forward: Boolean) : FreakyyyAction() {
        override val label get() = "ACCESSIBILITY · SCROLL · ${if (forward) "DOWN" else "UP"}"
    }

    // ---------- Freakyyy itself ----------

    data class Navigate(val screen: FreakyyyScreen) : FreakyyyAction() {
        override val label get() = "NAVIGATE · ${screen.name}"
    }

    data class RunRoutine(val name: String) : FreakyyyAction() {
        override val label get() = "ROUTINE · $name"
    }

    data class Wait(val seconds: Int) : FreakyyyAction() {
        override val label get() = "WAIT · ${seconds}s"
    }

    // ---------- Laptop (Freakyyy Link) ----------

    /** Any command for the laptop, run by the laptop's own engine. */
    data class Laptop(val text: String) : FreakyyyAction() {
        override val label get() = "LAPTOP · $text"
    }

    object LaptopRing : FreakyyyAction() {
        override val label get() = "LAPTOP · RING"
    }

    object ClipboardToLaptop : FreakyyyAction() {
        override val label get() = "LAPTOP · CLIPBOARD_PUSH"
    }

    object ClipboardFromLaptop : FreakyyyAction() {
        override val label get() = "LAPTOP · CLIPBOARD_PULL"
    }

    data class RoutineBoth(val name: String) : FreakyyyAction() {
        override val label get() = "ROUTINE · $name · BOTH"
    }

    /** Answers a confirmation question the laptop asked. */
    data class LaptopConfirm(val token: String) : FreakyyyAction() {
        override val label get() = "LAPTOP · CONFIRM"
    }

    object StopAll : FreakyyyAction() {
        override val label get() = "STOP_ALL"
    }

    data class Unknown(val text: String) : FreakyyyAction() {
        override val label get() = "UNKNOWN"
    }
}

/** Either an absolute percentage or a relative step. */
sealed class LevelChange {
    data class Percent(val value: Int) : LevelChange() {
        override fun toString() = "$value%"
    }
    object Up : LevelChange() { override fun toString() = "UP" }
    object Down : LevelChange() { override fun toString() = "DOWN" }
    object Max : LevelChange() { override fun toString() = "MAX" }
    object Min : LevelChange() { override fun toString() = "MIN" }
    object Mute : LevelChange() { override fun toString() = "MUTE" }
    object Unmute : LevelChange() { override fun toString() = "UNMUTE" }
}

enum class VolumeStream { MEDIA, RING, ALARM, NOTIFICATION, CALL }

enum class RingerMode { NORMAL, VIBRATE, SILENT }

enum class AppSettingsPage { DETAILS, NOTIFICATIONS, PERMISSIONS, STORAGE }

enum class InfoTopic { TIME, DATE, IDENTITY, HELP, GREETING, THANKS, WELLBEING }

enum class FreakyyyGlobalAction {
    BACK, HOME, RECENTS, NOTIFICATIONS, QUICK_SETTINGS, SCREENSHOT, LOCK_SCREEN
}

enum class FreakyyyScreen { HOME, APPS, ROUTINES, HISTORY, PERMISSIONS, VOICE, DEVICES }

/** Result of executing one action. */
enum class Outcome {
    /** The change was actually made (and verified where possible). */
    DONE,
    /** A screen was opened; the user still has to finish the change. */
    OPENED,
    /** Information was provided. */
    INFO,
    /** A permission or special access is required first. */
    NEEDS_PERMISSION,
    /** The user must confirm before Freakyyy continues. */
    NEEDS_CONFIRMATION,
    /** Android does not allow this for ordinary apps. */
    NOT_SUPPORTED,
    /** The other device (laptop) isn't connected. */
    DEVICE_OFFLINE,
    FAILED
}

data class FreakyyyResult(
    val outcome: Outcome,
    val message: String,
    val navigate: FreakyyyScreen? = null,
    /** Runtime permission to request, if [outcome] is NEEDS_PERMISSION. */
    val permission: String? = null,
    /** The action awaiting a yes/no, if [outcome] is NEEDS_CONFIRMATION. */
    val confirm: FreakyyyAction? = null,
    val spoken: String = message
)

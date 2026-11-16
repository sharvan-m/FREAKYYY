
package com.troit.assistant

import android.os.Build
import android.provider.Settings

/**
 * Android settings screens Freakyyy can open. Each page lists intent actions
 * in order of preference; the first one the device can handle is used, and
 * the main Settings screen is the final fallback.
 */
enum class SystemSettingsPage(
    val title: String,
    val keywords: List<String>,
    val actions: () -> List<String>
) {
    WIFI(
        "Wi-Fi settings",
        listOf("wifi", "wi-fi", "wi fi", "wireless network", "wlan"),
        { listOf(Settings.ACTION_WIFI_SETTINGS) }
    ),
    INTERNET(
        "Internet settings",
        listOf("internet", "network", "networks", "network and internet", "mobile network", "mobile data", "data"),
        {
            buildList {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    add(Settings.Panel.ACTION_INTERNET_CONNECTIVITY)
                }
                add(Settings.ACTION_DATA_ROAMING_SETTINGS)
                add(Settings.ACTION_WIRELESS_SETTINGS)
            }
        }
    ),
    BLUETOOTH(
        "Bluetooth settings",
        listOf("bluetooth", "blue tooth"),
        { listOf(Settings.ACTION_BLUETOOTH_SETTINGS) }
    ),
    HOTSPOT(
        "Hotspot and tethering",
        listOf("hotspot", "hot spot", "tethering"),
        // No public hotspot action exists; wireless settings is the nearest page.
        { listOf("android.settings.TETHER_SETTINGS", Settings.ACTION_WIRELESS_SETTINGS) }
    ),
    AIRPLANE(
        "Airplane mode settings",
        listOf("airplane", "airplane mode", "aeroplane", "flight mode"),
        { listOf(Settings.ACTION_AIRPLANE_MODE_SETTINGS) }
    ),
    NFC(
        "NFC settings",
        listOf("nfc"),
        { listOf(Settings.ACTION_NFC_SETTINGS) }
    ),
    DATA_USAGE(
        "Data usage",
        listOf("data usage", "data saver"),
        { listOf(Settings.ACTION_DATA_USAGE_SETTINGS, Settings.ACTION_WIRELESS_SETTINGS) }
    ),
    DISPLAY(
        "Display settings",
        listOf("display", "screen", "brightness", "dark theme", "dark mode", "wallpaper", "font size"),
        { listOf(Settings.ACTION_DISPLAY_SETTINGS) }
    ),
    SOUND(
        "Sound settings",
        listOf("sound", "sounds", "volume", "ringtone", "vibration", "audio"),
        { listOf(Settings.ACTION_SOUND_SETTINGS) }
    ),
    NOTIFICATIONS(
        "Notification settings",
        listOf("notification", "notifications"),
        { listOf("android.settings.NOTIFICATION_SETTINGS", Settings.ACTION_SETTINGS) }
    ),
    DO_NOT_DISTURB(
        "Do Not Disturb settings",
        listOf("do not disturb", "dnd", "zen mode"),
        { listOf("android.settings.ZEN_MODE_SETTINGS", Settings.ACTION_SOUND_SETTINGS) }
    ),
    BATTERY(
        "Battery settings",
        listOf("battery", "power", "battery usage"),
        { listOf(Intent_ACTION_POWER_USAGE_SUMMARY, Settings.ACTION_BATTERY_SAVER_SETTINGS) }
    ),
    BATTERY_SAVER(
        "Battery saver",
        listOf("battery saver", "power saving", "power saver"),
        { listOf(Settings.ACTION_BATTERY_SAVER_SETTINGS) }
    ),
    STORAGE(
        "Storage settings",
        listOf("storage", "memory", "space"),
        { listOf(Settings.ACTION_INTERNAL_STORAGE_SETTINGS, Settings.ACTION_MEMORY_CARD_SETTINGS) }
    ),
    LOCATION(
        "Location settings",
        listOf("location", "gps"),
        { listOf(Settings.ACTION_LOCATION_SOURCE_SETTINGS) }
    ),
    ACCESSIBILITY(
        "Accessibility settings",
        listOf("accessibility"),
        { listOf(Settings.ACTION_ACCESSIBILITY_SETTINGS) }
    ),
    LANGUAGE(
        "Language settings",
        listOf("language", "languages", "locale", "keyboard", "input"),
        { listOf(Settings.ACTION_LOCALE_SETTINGS) }
    ),
    DATE_TIME(
        "Date and time settings",
        listOf("date", "time", "date and time", "clock", "time zone"),
        { listOf(Settings.ACTION_DATE_SETTINGS) }
    ),
    APPS(
        "App settings",
        listOf("apps", "applications", "app management", "manage apps", "installed apps settings", "application manager"),
        { listOf(Settings.ACTION_MANAGE_APPLICATIONS_SETTINGS, Settings.ACTION_APPLICATION_SETTINGS) }
    ),
    DEFAULT_APPS(
        "Default apps",
        listOf("default apps", "default applications", "default app"),
        { listOf(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS, Settings.ACTION_MANAGE_APPLICATIONS_SETTINGS) }
    ),
    PRIVACY(
        "Privacy settings",
        listOf("privacy", "permission manager", "permissions"),
        { listOf(Settings.ACTION_PRIVACY_SETTINGS, Settings.ACTION_SECURITY_SETTINGS) }
    ),
    SECURITY(
        "Security settings",
        listOf("security", "lock screen", "screen lock", "fingerprint", "face unlock"),
        { listOf(Settings.ACTION_SECURITY_SETTINGS) }
    ),
    DEVELOPER(
        "Developer options",
        listOf("developer", "developer options"),
        { listOf(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS) }
    ),
    ABOUT(
        "About phone",
        listOf("about phone", "about device", "device info", "phone info"),
        { listOf(Settings.ACTION_DEVICE_INFO_SETTINGS) }
    ),
    MAIN(
        "Settings",
        listOf("settings", "setting", "phone settings", "system settings", "android settings"),
        { listOf(Settings.ACTION_SETTINGS) }
    );

    companion object {
        // Intent.ACTION_POWER_USAGE_SUMMARY, kept as a literal for clarity.
        private const val Intent_ACTION_POWER_USAGE_SUMMARY =
            "android.intent.action.POWER_USAGE_SUMMARY"

        /** Longest keyword wins, so "battery saver" beats "battery". */
        fun find(phrase: String): SystemSettingsPage? {
            val text = phrase.trim()
            if (text.isEmpty()) return null
            return entries
                .flatMap { page -> page.keywords.map { it to page } }
                .filter { (keyword, _) -> text == keyword }
                .maxByOrNull { it.first.length }
                ?.second
        }
    }
}

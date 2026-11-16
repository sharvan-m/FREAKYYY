
package com.troit.assistant

import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.media.AudioManager
import android.os.BatteryManager
import android.os.Environment
import android.os.StatFs
import android.provider.Settings
import kotlin.math.roundToInt

/**
 * Direct device controls that Android allows an ordinary app to perform.
 * Each method makes the change, reads the value back to verify it and
 * reports what actually happened.
 */
class FreakyyyDeviceController(context: Context) {

    private val appContext = context.applicationContext
    private val audio = appContext.getSystemService(AudioManager::class.java)
    private val notifications = appContext.getSystemService(NotificationManager::class.java)
    private val camera = appContext.getSystemService(CameraManager::class.java)

    // =====================================================
    // BRIGHTNESS (needs "Modify system settings")
    // =====================================================

    fun canWriteSettings(): Boolean = Settings.System.canWrite(appContext)

    fun setBrightness(change: LevelChange): FreakyyyResult {
        if (!canWriteSettings()) {
            return FreakyyyResult(
                Outcome.NEEDS_PERMISSION,
                "To change brightness I need the \"Modify system settings\" permission.",
                permission = PERMISSION_WRITE_SETTINGS
            )
        }

        val resolver = appContext.contentResolver
        return try {
            val current = Settings.System.getInt(resolver, Settings.System.SCREEN_BRIGHTNESS, 128)
            val currentPercent = (current / 255f * 100).roundToInt()
            val targetPercent = when (change) {
                is LevelChange.Percent -> change.value
                LevelChange.Up -> currentPercent + 20
                LevelChange.Down -> currentPercent - 20
                LevelChange.Max -> 100
                LevelChange.Min -> 0
                else -> currentPercent
            }.coerceIn(1, 100)

            val raw = (targetPercent / 100f * 255).roundToInt().coerceIn(1, 255)

            // Manual mode, otherwise adaptive brightness overrides the value.
            Settings.System.putInt(
                resolver,
                Settings.System.SCREEN_BRIGHTNESS_MODE,
                Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL
            )
            Settings.System.putInt(resolver, Settings.System.SCREEN_BRIGHTNESS, raw)

            val verified = Settings.System.getInt(resolver, Settings.System.SCREEN_BRIGHTNESS, -1)
            if (verified == raw) {
                FreakyyyResult(Outcome.DONE, "Brightness set to $targetPercent percent.")
            } else {
                FreakyyyResult(Outcome.FAILED, "I tried to set brightness, but the system kept it at a different level.")
            }
        } catch (e: Exception) {
            FreakyyyResult(Outcome.FAILED, "I couldn't change the brightness: ${e.message}")
        }
    }

    // =====================================================
    // VOLUME
    // =====================================================

    fun setVolume(stream: VolumeStream, change: LevelChange): FreakyyyResult {
        val streamType = when (stream) {
            VolumeStream.MEDIA -> AudioManager.STREAM_MUSIC
            VolumeStream.RING -> AudioManager.STREAM_RING
            VolumeStream.ALARM -> AudioManager.STREAM_ALARM
            VolumeStream.NOTIFICATION -> AudioManager.STREAM_NOTIFICATION
            VolumeStream.CALL -> AudioManager.STREAM_VOICE_CALL
        }
        val name = when (stream) {
            VolumeStream.MEDIA -> "Media volume"
            VolumeStream.RING -> "Ring volume"
            VolumeStream.ALARM -> "Alarm volume"
            VolumeStream.NOTIFICATION -> "Notification volume"
            VolumeStream.CALL -> "Call volume"
        }

        return try {
            val max = audio.getStreamMaxVolume(streamType)
            val min = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
                audio.getStreamMinVolume(streamType)
            } else {
                0
            }
            val flags = AudioManager.FLAG_SHOW_UI

            when (change) {
                LevelChange.Mute -> audio.adjustStreamVolume(streamType, AudioManager.ADJUST_MUTE, flags)
                LevelChange.Unmute -> audio.adjustStreamVolume(streamType, AudioManager.ADJUST_UNMUTE, flags)
                LevelChange.Up -> repeat(2) { audio.adjustStreamVolume(streamType, AudioManager.ADJUST_RAISE, flags) }
                LevelChange.Down -> repeat(2) { audio.adjustStreamVolume(streamType, AudioManager.ADJUST_LOWER, flags) }
                LevelChange.Max -> audio.setStreamVolume(streamType, max, flags)
                LevelChange.Min -> audio.setStreamVolume(streamType, min, flags)
                is LevelChange.Percent -> {
                    val index = (change.value / 100f * max).roundToInt().coerceIn(min, max)
                    audio.setStreamVolume(streamType, index, flags)
                }
            }

            val now = audio.getStreamVolume(streamType)
            val percent = if (max == 0) 0 else (now * 100f / max).roundToInt()
            val muted = audio.isStreamMute(streamType)

            when {
                change == LevelChange.Mute && muted -> FreakyyyResult(Outcome.DONE, "$name muted.")
                change == LevelChange.Mute -> FreakyyyResult(Outcome.FAILED, "Android didn't allow muting the ${name.lowercase()}.")
                else -> FreakyyyResult(Outcome.DONE, "$name is now at $percent percent.")
            }
        } catch (e: SecurityException) {
            // Ring/notification changes can be blocked while Do Not Disturb is on.
            FreakyyyResult(
                Outcome.NEEDS_PERMISSION,
                "Android blocked that while Do Not Disturb is active, which needs Do Not Disturb access.",
                permission = PERMISSION_DND_ACCESS
            )
        } catch (e: Exception) {
            FreakyyyResult(Outcome.FAILED, "I couldn't change the volume: ${e.message}")
        }
    }

    // =====================================================
    // FLASHLIGHT
    // =====================================================

    @Volatile private var torchOn = false
    private var torchCameraId: String? = null

    init {
        try {
            torchCameraId = camera.cameraIdList.firstOrNull { id ->
                val c = camera.getCameraCharacteristics(id)
                c.get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true &&
                        c.get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
            } ?: camera.cameraIdList.firstOrNull { id ->
                camera.getCameraCharacteristics(id).get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
            }
            torchCameraId?.let { id ->
                camera.registerTorchCallback(object : CameraManager.TorchCallback() {
                    override fun onTorchModeChanged(cameraId: String, enabled: Boolean) {
                        if (cameraId == id) torchOn = enabled
                    }
                }, null)
            }
        } catch (_: Exception) {
            torchCameraId = null
        }
    }

    fun setFlashlight(on: Boolean?): FreakyyyResult {
        val id = torchCameraId
            ?: return FreakyyyResult(Outcome.NOT_SUPPORTED, "This device doesn't have a flashlight I can control.")
        val target = on ?: !torchOn
        return try {
            camera.setTorchMode(id, target)
            torchOn = target
            FreakyyyResult(Outcome.DONE, if (target) "Flashlight on." else "Flashlight off.")
        } catch (e: Exception) {
            FreakyyyResult(Outcome.FAILED, "I couldn't switch the flashlight. The camera may be in use by another app.")
        }
    }

    // =====================================================
    // RINGER MODE / DO NOT DISTURB (needs DND access)
    // =====================================================

    fun hasDndAccess(): Boolean = notifications.isNotificationPolicyAccessGranted

    fun setRingerMode(mode: RingerMode): FreakyyyResult {
        if (mode == RingerMode.SILENT && !hasDndAccess()) {
            return FreakyyyResult(
                Outcome.NEEDS_PERMISSION,
                "Android needs Do Not Disturb access before I can silence the phone.",
                permission = PERMISSION_DND_ACCESS
            )
        }
        return try {
            audio.ringerMode = when (mode) {
                RingerMode.NORMAL -> AudioManager.RINGER_MODE_NORMAL
                RingerMode.VIBRATE -> AudioManager.RINGER_MODE_VIBRATE
                RingerMode.SILENT -> AudioManager.RINGER_MODE_SILENT
            }
            val actual = audio.ringerMode
            val label = when (actual) {
                AudioManager.RINGER_MODE_SILENT -> "silent"
                AudioManager.RINGER_MODE_VIBRATE -> "vibrate"
                else -> "ring"
            }
            val expected = when (mode) {
                RingerMode.NORMAL -> AudioManager.RINGER_MODE_NORMAL
                RingerMode.VIBRATE -> AudioManager.RINGER_MODE_VIBRATE
                RingerMode.SILENT -> AudioManager.RINGER_MODE_SILENT
            }
            if (actual == expected) FreakyyyResult(Outcome.DONE, "Phone set to $label mode.")
            else FreakyyyResult(Outcome.FAILED, "Android kept the phone in $label mode.")
        } catch (e: SecurityException) {
            FreakyyyResult(
                Outcome.NEEDS_PERMISSION,
                "Android needs Do Not Disturb access for that.",
                permission = PERMISSION_DND_ACCESS
            )
        }
    }

    fun setDoNotDisturb(on: Boolean): FreakyyyResult {
        if (!hasDndAccess()) {
            return FreakyyyResult(
                Outcome.NEEDS_PERMISSION,
                "I need Do Not Disturb access to change that.",
                permission = PERMISSION_DND_ACCESS
            )
        }
        val filter = if (on) NotificationManager.INTERRUPTION_FILTER_PRIORITY
        else NotificationManager.INTERRUPTION_FILTER_ALL
        notifications.setInterruptionFilter(filter)
        val nowOn = notifications.currentInterruptionFilter != NotificationManager.INTERRUPTION_FILTER_ALL
        return if (nowOn == on) {
            FreakyyyResult(Outcome.DONE, if (on) "Do Not Disturb is on." else "Do Not Disturb is off.")
        } else {
            FreakyyyResult(Outcome.FAILED, "Android didn't apply the Do Not Disturb change.")
        }
    }

    // =====================================================
    // INFORMATION
    // =====================================================

    fun batteryStatus(): FreakyyyResult {
        val manager = appContext.getSystemService(BatteryManager::class.java)
        val level = manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        val sticky = appContext.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val status = sticky?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val charging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                status == BatteryManager.BATTERY_STATUS_FULL
        val tempTenths = sticky?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE) ?: Int.MIN_VALUE

        val parts = mutableListOf("Battery is at $level percent")
        parts += if (charging) "and charging" else "and not charging"
        var message = parts.joinToString(" ") + "."
        if (tempTenths != Int.MIN_VALUE && tempTenths > 0) {
            message += " Temperature ${tempTenths / 10} degrees."
        }
        return FreakyyyResult(Outcome.INFO, message)
    }

    fun storageStatus(): FreakyyyResult {
        val stat = StatFs(Environment.getDataDirectory().path)
        val total = stat.totalBytes
        val free = stat.availableBytes
        val usedPercent = if (total == 0L) 0 else ((total - free) * 100 / total).toInt()
        return FreakyyyResult(
            Outcome.INFO,
            "You have ${gb(free)} free out of ${gb(total)}. Storage is $usedPercent percent full."
        )
    }

    private fun gb(bytes: Long): String {
        val value = bytes / 1_000_000_000.0
        return if (value >= 10) "${value.roundToInt()} gigabytes"
        else "${"%.1f".format(value)} gigabytes"
    }

    companion object {
        const val PERMISSION_WRITE_SETTINGS = "special:write_settings"
        const val PERMISSION_DND_ACCESS = "special:dnd_access"
        const val PERMISSION_NOTIFICATION_LISTENER = "special:notification_listener"
        const val PERMISSION_ACCESSIBILITY = "special:accessibility"
    }
}

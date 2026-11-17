
package com.troit.assistant

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.ClipData
import android.content.ClipboardManager
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.VibrationEffect
import android.os.Vibrator
import androidx.core.app.NotificationCompat
import com.troit.assistant.link.FreakyyyLink
import com.troit.assistant.link.LaunchGate
import org.json.JSONObject
import java.util.UUID

/**
 * Freakyyy's brain. Voice and typed input both arrive at [submit]:
 *
 *   text → [FreakyyyIntentParser] → FreakyyyAction
 *        → confirmation / permission checks
 *        → [FreakyyyActionExecutor] (Android APIs)
 *        → reply in the UI + Kokoro voice + history
 *
 * Lives for the whole process so routines keep running when Freakyyy opens
 * another app.
 */
object FreakyyyAssistant {

    data class ChatMessage(
        val id: Long,
        val fromUser: Boolean,
        val text: String,
        val outcome: Outcome? = null
    )

    data class PermissionRequest(
        val permission: String,
        val retryCommand: String
    )

    data class RoutineProgress(
        val name: String,
        val step: Int,
        val total: Int,
        val current: String
    )

    private data class Pending(
        val question: String,
        val action: FreakyyyAction
    )

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private val _messages = MutableStateFlow<List<ChatMessage>>(emptyList())
    val messages: StateFlow<List<ChatMessage>> = _messages.asStateFlow()

    private val _routine = MutableStateFlow<RoutineProgress?>(null)
    val routine: StateFlow<RoutineProgress?> = _routine.asStateFlow()

    private val _awaitingAnswer = MutableStateFlow<String?>(null)
    val awaitingAnswer: StateFlow<String?> = _awaitingAnswer.asStateFlow()

    /** One-shot events consumed by the UI. */
    val permissionRequest = MutableStateFlow<PermissionRequest?>(null)
    val navigation = MutableStateFlow<FreakyyyScreen?>(null)

    private lateinit var appContext: Context
    lateinit var appManager: TroitAppManager
        private set
    lateinit var preferences: TroitPreferenceManager
        private set
    lateinit var routines: FreakyyyRoutineStore
        private set
    lateinit var history: FreakyyyHistoryStore
        private set
    lateinit var device: FreakyyyDeviceController
        private set
    private lateinit var executor: FreakyyyActionExecutor
    private lateinit var speaker: TroitSpeaker

    private var pending: Pending? = null
    private var routineJob: Job? = null
    private var nextId = 0L

    private val yesWords = setOf(
        "yes", "yeah", "yep", "yup", "correct", "sure", "okay", "ok", "open it",
        "do it", "go ahead", "yes please", "please do", "confirm", "tap it",
        "clear them", "right", "affirmative", "of course", "s", "aama", "seri"
    )

    private val noWords = setOf(
        "no", "nope", "cancel", "don't", "dont", "stop", "not now", "no thanks",
        "never mind", "nevermind", "leave it", "illa", "vendam"
    )

    fun initialize(context: Context) {
        if (::appContext.isInitialized) return
        appContext = context.applicationContext
        appManager = TroitAppManager(appContext)
        preferences = TroitPreferenceManager(appContext)
        routines = FreakyyyRoutineStore(appContext)
        history = FreakyyyHistoryStore(appContext)
        device = FreakyyyDeviceController(appContext)
        executor = FreakyyyActionExecutor(
            appContext,
            appManager,
            TroitAppMatcher(appManager, preferences),
            device
        )
        speaker = TroitSpeaker(appContext)
        appManager.preload()

        FreakyyyLink.init(appContext)
        FreakyyyLink.requestHandler = { action, params ->
            withContext(Dispatchers.Main) { handleLinkRequest(action, params) }
        }
        FreakyyyLink.onFileReceived = { name ->
            scope.launch {
                addMessage(false, "Received $name from your laptop. It's in Download/Freakyyy.", Outcome.DONE)
                speaker.speak("Received a file from your laptop.")
            }
        }
    }

    // =====================================================
    // INPUT
    // =====================================================

    fun submit(input: String, silent: Boolean = false) {
        val text = input.trim()
        if (text.isEmpty()) return
        if (!silent) addMessage(fromUser = true, text = text)

        val answer = text.lowercase()
            .replace(Regex("""[.!?,]+"""), " ")
            .replace(Regex("""\s+"""), " ")
            .trim()

        pending?.let { waiting ->
            when {
                answer in yesWords -> {
                    clearPending()
                    if (waiting.action is FreakyyyAction.LaptopConfirm) {
                        run(text, waiting.action)
                    } else {
                        handleResult(text, waiting.action, executor.execute(waiting.action, confirmed = true))
                    }
                    return
                }
                answer in noWords -> {
                    clearPending()
                    reply(text, "CANCELLED", FreakyyyResult(Outcome.INFO, "Okay, I cancelled that action."))
                    return
                }
                else -> {
                    val action = FreakyyyIntentParser.parse(text)
                    if (action is FreakyyyAction.Unknown) {
                        reply(text, "AWAITING_ANSWER", FreakyyyResult(Outcome.NEEDS_CONFIRMATION, "Please say yes or no."))
                        return
                    }
                    // A new command replaces the pending question.
                    clearPending()
                }
            }
        }

        run(text, FreakyyyIntentParser.parse(text))
    }

    fun answer(yes: Boolean) = submit(if (yes) "yes" else "no")

    /** Runs an already-structured action from the UI (e.g. App Hub taps). */
    fun perform(action: FreakyyyAction) {
        clearPending()
        run(action.label, action)
    }

    private fun run(command: String, action: FreakyyyAction) {
        when (action) {
            FreakyyyAction.StopAll -> {
                val hadRoutine = routineJob?.isActive == true
                stopAll()
                reply(
                    command, action.label,
                    FreakyyyResult(Outcome.DONE, if (hadRoutine) "Stopped the routine." else "Stopped.")
                )
            }

            is FreakyyyAction.RunRoutine -> {
                val routine = routines.find(action.name)
                if (routine == null) {
                    reply(
                        command, action.label,
                        FreakyyyResult(
                            Outcome.FAILED,
                            "I don't have a routine called ${action.name}. You can create it in Routines.",
                            navigate = FreakyyyScreen.ROUTINES
                        )
                    )
                } else {
                    runRoutine(routine, command)
                }
            }

            is FreakyyyAction.Laptop,
            FreakyyyAction.LaptopRing,
            FreakyyyAction.ClipboardToLaptop,
            FreakyyyAction.ClipboardFromLaptop,
            is FreakyyyAction.LaptopConfirm -> {
                scope.launch { handleResult(command, action, laptopRequest(action)) }
            }

            is FreakyyyAction.RoutineBoth -> {
                val routine = routines.find(action.name)
                if (routine != null) {
                    runRoutine(routine, command)
                } else {
                    addMessage(false, "This phone has no ${action.name} routine; asking the laptop to run its own.", Outcome.INFO)
                }
                scope.launch {
                    val r = laptopRequest(FreakyyyAction.Laptop("start ${action.name} routine"))
                    addMessage(false, "Laptop: ${r.message}", r.outcome)
                    if (routine == null) speaker.speak("Laptop: ${r.spoken}")
                }
            }

            is FreakyyyAction.Wait -> reply(
                command, action.label,
                FreakyyyResult(Outcome.INFO, "Waiting is only used between routine steps.")
            )

            else -> handleResult(command, action, executor.execute(action))
        }
    }

    private fun handleResult(command: String, action: FreakyyyAction, result: FreakyyyResult) {
        var shown = result
        when (result.outcome) {
            Outcome.NEEDS_CONFIRMATION -> {
                result.confirm?.let { setPending(Pending(result.message, it)) }
            }
            Outcome.NEEDS_PERMISSION -> {
                if (requestPermission(result.permission, command)) {
                    val note = " I've opened that page — allow Freakyyy, then ask me again."
                    shown = result.copy(message = result.message + note, spoken = result.spoken + note)
                }
            }
            else -> {}
        }
        reply(command, action.label, shown)
    }

    /** Returns true when a special-access settings page was opened. */
    private fun requestPermission(permission: String?, command: String): Boolean {
        when (permission) {
            null -> return false
            FreakyyyDeviceController.PERMISSION_WRITE_SETTINGS -> openWriteSettingsAccess()
            FreakyyyDeviceController.PERMISSION_DND_ACCESS -> openDndAccess()
            FreakyyyDeviceController.PERMISSION_NOTIFICATION_LISTENER -> openNotificationAccess()
            FreakyyyDeviceController.PERMISSION_ACCESSIBILITY -> openAccessibilitySettings()
            else -> {
                permissionRequest.value = PermissionRequest(permission, command)
                return false
            }
        }
        return true
    }

    // =====================================================
    // ROUTINES
    // =====================================================

    fun runRoutine(routine: FreakyyyRoutine, command: String = "Run ${routine.name}") {
        stopAll()
        addMessage(false, "Starting ${routine.name} routine.", Outcome.INFO)
        speaker.speak("Starting ${routine.name} routine.")

        routineJob = scope.launch {
            var done = 0
            val needsYou = mutableListOf<String>()
            val failed = mutableListOf<String>()

            for ((index, step) in routine.steps.withIndex()) {
                _routine.value = RoutineProgress(routine.name, index + 1, routine.steps.size, step)
                val action = FreakyyyIntentParser.parse(step)

                when (action) {
                    is FreakyyyAction.Wait -> {
                        delay(action.seconds * 1000L)
                        continue
                    }
                    is FreakyyyAction.RunRoutine, FreakyyyAction.StopAll -> {
                        failed += "\"$step\" (routines can't start other routines)"
                        continue
                    }
                    is FreakyyyAction.Unknown -> {
                        failed += "\"$step\" (not understood)"
                        continue
                    }
                    else -> {}
                }

                val result = if (isLaptopAction(action)) laptopRequest(action) else executor.execute(action)
                history.add(FreakyyyHistoryEntry(System.currentTimeMillis(), "[${routine.name}] $step", action.label, result.outcome, result.message))

                when (result.outcome) {
                    Outcome.DONE, Outcome.INFO -> done++
                    Outcome.OPENED -> needsYou += step
                    Outcome.NEEDS_PERMISSION -> needsYou += "$step (needs permission)"
                    Outcome.NEEDS_CONFIRMATION -> {
                        // Sensitive steps always wait for the user.
                        result.confirm?.let { setPending(Pending(result.message, it)) }
                        addMessage(false, "${routine.name} paused: ${result.message}", Outcome.NEEDS_CONFIRMATION)
                        speaker.speak(result.spoken)
                        _routine.value = null
                        return@launch
                    }
                    Outcome.NOT_SUPPORTED, Outcome.FAILED -> failed += "\"$step\""
                    Outcome.DEVICE_OFFLINE -> failed += "\"$step\" (laptop offline)"
                }
                delay(STEP_GAP_MS)
            }

            _routine.value = null
            val summary = buildString {
                append("${routine.name} routine finished. $done of ${routine.steps.size} steps done")
                if (needsYou.isNotEmpty()) append("; waiting on you: ${needsYou.joinToString(", ")}")
                if (failed.isNotEmpty()) append("; couldn't do: ${failed.joinToString(", ")}")
                append(".")
            }
            val outcome = if (failed.isEmpty() && needsYou.isEmpty()) Outcome.DONE else Outcome.OPENED
            lastRoutineSummary = summary to outcome
            addMessage(false, summary, outcome)
            history.add(FreakyyyHistoryEntry(System.currentTimeMillis(), command, "ROUTINE · ${routine.name}", outcome, summary))
            speaker.speak(
                if (failed.isEmpty() && needsYou.isEmpty()) "${routine.name} routine complete."
                else "${routine.name} routine finished. Some steps need your attention."
            )
        }
    }

    fun stopAll() {
        stopRinging()
        routineJob?.cancel()
        routineJob = null
        _routine.value = null
        clearPending()
        speaker.stop()
    }

    // =====================================================
    // SPECIAL ACCESS PAGES
    // =====================================================

    fun openWriteSettingsAccess() {
        executor.start(
            Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS, Uri.parse("package:${appContext.packageName}"))
        ) || executor.start(Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS))
    }

    fun openDndAccess() {
        executor.start(Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS))
    }

    fun openNotificationAccess() {
        executor.start(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
    }

    fun openAccessibilitySettings() {
        executor.start(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
    }

    fun openAppDetails() {
        executor.start(
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", appContext.packageName, null))
        )
    }

    // =====================================================
    // OUTPUT
    // =====================================================

    /** Shows and speaks a reply, records it, and triggers navigation. */
    private fun reply(command: String, label: String, result: FreakyyyResult) {
        addMessage(fromUser = false, text = result.message, outcome = result.outcome)
        speaker.speak(result.spoken)
        result.navigate?.let { navigation.value = it }
        history.add(
            FreakyyyHistoryEntry(
                time = System.currentTimeMillis(),
                command = command,
                action = label,
                outcome = result.outcome,
                result = result.message
            )
        )
    }

    /** Speaks a message from the UI (e.g. permission results). */
    fun say(text: String, outcome: Outcome = Outcome.INFO) {
        addMessage(false, text, outcome)
        speaker.speak(text)
    }

    fun speak(text: String) = speaker.speak(text)

    fun stopSpeaking() = speaker.stop()

    private fun addMessage(fromUser: Boolean, text: String, outcome: Outcome? = null) {
        _messages.update { (it + ChatMessage(nextId++, fromUser, text, outcome)).takeLast(40) }
    }

    fun clearConversation() {
        _messages.value = emptyList()
    }

    private fun setPending(value: Pending) {
        pending = value
        _awaitingAnswer.value = value.question
    }

    private fun clearPending() {
        pending = null
        _awaitingAnswer.value = null
    }

    // =====================================================
    // FREAKYYY LINK — requests to and from the laptop
    // =====================================================

    private var lastRoutineSummary: Pair<String, Outcome>? = null
    private val remotePending = mutableMapOf<String, Pair<Long, FreakyyyAction>>()
    private var ringtone: android.media.Ringtone? = null

    private fun isLaptopAction(a: FreakyyyAction) = a is FreakyyyAction.Laptop || a == FreakyyyAction.LaptopRing ||
            a == FreakyyyAction.ClipboardToLaptop || a == FreakyyyAction.ClipboardFromLaptop || a is FreakyyyAction.LaptopConfirm

    private fun fromLink(r: JSONObject): FreakyyyResult {
        val outcome = when (r.optString("outcome")) {
            "COMPLETED" -> Outcome.DONE
            "OPENED" -> Outcome.OPENED
            "INFO" -> Outcome.INFO
            "NEEDS_PERMISSION" -> Outcome.NEEDS_PERMISSION
            "NEEDS_CONFIRMATION", "CLARIFY" -> Outcome.NEEDS_CONFIRMATION
            "NOT_SUPPORTED" -> Outcome.NOT_SUPPORTED
            "DEVICE_OFFLINE" -> Outcome.DEVICE_OFFLINE
            else -> Outcome.FAILED
        }
        val msg = r.optString("message").ifBlank { "The laptop didn't say what happened." }
        val token = r.optString("confirm_token")
        return if (outcome == Outcome.NEEDS_CONFIRMATION && token.isNotBlank()) {
            FreakyyyResult(Outcome.NEEDS_CONFIRMATION, "Laptop asks: $msg", confirm = FreakyyyAction.LaptopConfirm(token))
        } else {
            FreakyyyResult(outcome, msg)
        }
    }

    private suspend fun laptopRequest(action: FreakyyyAction): FreakyyyResult = when (action) {
        is FreakyyyAction.Laptop -> fromLink(FreakyyyLink.request("run_command", JSONObject().put("text", action.text)))
        FreakyyyAction.LaptopRing -> fromLink(FreakyyyLink.request("ring", JSONObject().put("seconds", 15)))
        is FreakyyyAction.LaptopConfirm -> fromLink(
            FreakyyyLink.request("confirm", JSONObject().put("confirm_token", action.token).put("accept", true))
        )
        FreakyyyAction.ClipboardToLaptop -> {
            val cm = appContext.getSystemService(ClipboardManager::class.java)
            val text = cm.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(appContext)?.toString()
            if (text.isNullOrBlank()) FreakyyyResult(Outcome.INFO, "Your clipboard has no text to send.")
            else fromLink(FreakyyyLink.request("clipboard_push", JSONObject().put("text", text.take(100_000))))
        }
        FreakyyyAction.ClipboardFromLaptop -> {
            val r = FreakyyyLink.request("clipboard_pull")
            val text = r.optJSONObject("data")?.optString("text")
            if (r.optString("outcome") == "COMPLETED" && text != null) {
                appContext.getSystemService(ClipboardManager::class.java)
                    .setPrimaryClip(ClipData.newPlainText("From laptop", text))
                FreakyyyResult(
                    Outcome.DONE, "Copied your laptop's clipboard: ${text.take(120)}",
                    spoken = "Copied your laptop's clipboard to this phone."
                )
            } else {
                fromLink(r)
            }
        }
        else -> FreakyyyResult(Outcome.FAILED, "Not a laptop action.")
    }

    private fun toLink(r: FreakyyyResult): JSONObject {
        val o = JSONObject()
            .put("outcome", if (r.outcome == Outcome.DONE) "COMPLETED" else r.outcome.name)
            .put("message", r.message)
        if (r.outcome == Outcome.NEEDS_CONFIRMATION && r.confirm != null) {
            val token = UUID.randomUUID().toString()
            remotePending[token] = System.currentTimeMillis() to r.confirm
            o.put("confirm_token", token)
        }
        return o
    }

    /** A request from the laptop. Runs the phone's own engine; never a shell. */
    suspend fun handleLinkRequest(action: String, params: JSONObject): JSONObject = when (action) {
        "run_command" -> {
            val text = params.optString("text").take(300)
            addMessage(true, "From laptop: $text")
            val parsed = FreakyyyIntentParser.parse(text)
            val result = when {
                isLaptopAction(parsed) || parsed is FreakyyyAction.RoutineBoth ->
                    FreakyyyResult(Outcome.NOT_SUPPORTED, "That command is meant for the laptop itself.")
                parsed is FreakyyyAction.RunRoutine -> {
                    val routine = routines.find(parsed.name)
                    if (routine == null) {
                        FreakyyyResult(Outcome.FAILED, "The phone has no ${parsed.name} routine.")
                    } else {
                        lastRoutineSummary = null
                        runRoutine(routine, "From laptop: $text")
                        routineJob?.join()
                        lastRoutineSummary?.let { FreakyyyResult(it.second, it.first) }
                            ?: FreakyyyResult(Outcome.FAILED, "The routine stopped early.")
                    }
                }
                parsed == FreakyyyAction.StopAll -> {
                    stopAll()
                    FreakyyyResult(Outcome.DONE, "Stopped on the phone.")
                }
                parsed is FreakyyyAction.Unknown ->
                    FreakyyyResult(Outcome.FAILED, "The phone doesn't know how to \"$text\".")
                else -> {
                    LaunchGate.resetNotified()
                    var r = executor.execute(parsed)
                    if (r.outcome == Outcome.NEEDS_PERMISSION) {
                        r = r.copy(message = r.message + " Open Freakyyy on the phone to grant it.")
                    }
                    if ((r.outcome == Outcome.DONE || r.outcome == Outcome.OPENED) && LaunchGate.lastWasNotified) {
                        r = FreakyyyResult(
                            Outcome.OPENED,
                            "Android doesn't let Freakyyy open screens while it's in the background, so I sent a notification " +
                                    "to your phone — tap it to open. Allow \"Display over other apps\" in Freakyyy's permissions to open things directly."
                        )
                    }
                    r
                }
            }
            addMessage(false, result.message, result.outcome)
            history.add(FreakyyyHistoryEntry(System.currentTimeMillis(), "[laptop] $text", parsed.label, result.outcome, result.message))
            toLink(result)
        }

        "confirm" -> {
            val item = remotePending.remove(params.optString("confirm_token"))
            when {
                item == null || System.currentTimeMillis() - item.first > 60_000 ->
                    JSONObject().put("outcome", "FAILED").put("message", "That confirmation expired.")
                !params.optBoolean("accept") -> JSONObject().put("outcome", "INFO").put("message", "Cancelled.")
                else -> toLink(executor.execute(item.second, confirmed = true))
            }
        }

        "get_status" -> {
            val s = FreakyyyLink.localStatus()
            val counts = FreakyyyNotificationListener.instance?.countsByApp()
            if (counts != null) s.put("notifications", counts.values.sum())
            val msg = "Phone battery ${s.getInt("battery")}%" + (if (s.getBoolean("charging")) ", charging" else "") +
                    ", ${"%.0f".format(s.getDouble("storage_free_gb"))} GB free" +
                    (counts?.let { ", ${it.values.sum()} notifications" } ?: "") + "."
            JSONObject().put("outcome", "INFO").put("message", msg).put("data", s)
        }

        "open_url" -> {
            val url = params.optString("url")
            if (!Regex("""^https?://\S+$""").matches(url)) {
                JSONObject().put("outcome", "FAILED").put("message", "Only web links can be opened.")
            } else {
                LaunchGate.resetNotified()
                LaunchGate.start(appContext, Intent(Intent.ACTION_VIEW, Uri.parse(url)), "link from laptop")
                val notified = LaunchGate.lastWasNotified
                JSONObject().put("outcome", if (notified) "OPENED" else "COMPLETED")
                    .put("message", if (notified) "Sent to your phone as a notification; tap it to open." else "Opened on your phone.")
            }
        }

        "ring" -> {
            ring(params.optInt("seconds", 15).coerceIn(3, 30))
            JSONObject().put("outcome", "COMPLETED").put("message", "Your phone is ringing.")
        }

        "clipboard_push" -> {
            if (!FreakyyyLink.store.clipboardAcceptFromLaptop) {
                JSONObject().put("outcome", "NEEDS_PERMISSION").put("message", "Clipboard sharing is off on the phone.")
            } else {
                appContext.getSystemService(ClipboardManager::class.java)
                    .setPrimaryClip(ClipData.newPlainText("From laptop", params.optString("text").take(100_000)))
                addMessage(false, "Your laptop sent text to this phone's clipboard.", Outcome.DONE)
                JSONObject().put("outcome", "COMPLETED").put("message", "Copied to your phone's clipboard.")
            }
        }

        "clipboard_pull" -> when {
            !FreakyyyLink.store.clipboardShareToLaptop -> JSONObject().put("outcome", "NEEDS_PERMISSION")
                .put("message", "The phone doesn't share its clipboard. Turn it on in Freakyyy → Devices on the phone.")
            !LaunchGate.freakyyyVisible -> JSONObject().put("outcome", "NEEDS_PERMISSION")
                .put("message", "Android only lets Freakyyy read the clipboard while it's open on the phone. Open Freakyyy and try again.")
            else -> {
                val cm = appContext.getSystemService(ClipboardManager::class.java)
                val text = cm.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(appContext)?.toString() ?: ""
                JSONObject().put("outcome", "COMPLETED").put("message", "Here's your phone's clipboard.")
                    .put("data", JSONObject().put("text", text))
            }
        }

        "notify" -> {
            notifyFromLaptop(params.optString("title", "Freakyyy"), params.optString("text"))
            JSONObject().put("outcome", "COMPLETED").put("message", "Shown on your phone.")
        }

        "routine_run" -> handleLinkRequest("run_command", JSONObject().put("text", "start ${params.optString("name")} routine"))

        else -> JSONObject().put("outcome", "NOT_SUPPORTED").put("message", "Not supported.")
    }

    private fun ring(seconds: Int) {
        stopRinging()
        val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
        ringtone = RingtoneManager.getRingtone(appContext, uri)?.apply {
            audioAttributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build()
            play()
        }
        appContext.getSystemService(Vibrator::class.java)
            ?.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 600, 400), 0))
        addMessage(false, "Your laptop is looking for this phone. Say stop to silence it.", Outcome.INFO)
        scope.launch {
            delay(seconds * 1000L)
            stopRinging()
        }
    }

    private fun stopRinging() {
        ringtone?.stop()
        ringtone = null
        if (::appContext.isInitialized) appContext.getSystemService(Vibrator::class.java)?.cancel()
    }

    private fun notifyFromLaptop(title: String, text: String) {
        val nm = appContext.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel("freakyyy_laptop", "Messages from your laptop", NotificationManager.IMPORTANCE_DEFAULT)
        )
        try {
            nm.notify(
                title.hashCode(), NotificationCompat.Builder(appContext, "freakyyy_laptop")
                    .setSmallIcon(R.mipmap.ic_launcher).setContentTitle(title.take(80)).setContentText(text.take(300))
                    .setAutoCancel(true).build()
            )
        } catch (_: SecurityException) {
        }
    }

    private const val STEP_GAP_MS = 450L
}


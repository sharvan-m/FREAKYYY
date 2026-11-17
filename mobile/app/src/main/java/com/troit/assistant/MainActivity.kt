
package com.troit.assistant

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.*
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.troit.assistant.ui.Freakyyy
import com.troit.assistant.ui.FreakyyyBackground
import com.troit.assistant.ui.GlassCard
import com.troit.assistant.ui.GlassChip
import com.troit.assistant.ui.SectionLabel
import com.troit.assistant.ui.StatusPill
import com.troit.assistant.ui.glass
import com.troit.assistant.ui.theme.TroitTheme
import com.troit.assistant.link.FreakyyyLink
import com.troit.assistant.link.FreakyyyLinkService
import com.troit.assistant.link.LaunchGate
import androidx.compose.ui.graphics.graphicsLayer

class MainActivity : ComponentActivity() {

    /** Bumped on every resume so permission states refresh. */
    private val resumeTick = mutableIntStateOf(0)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Freakyyy is always dark, so system bar icons are always light.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)
        )

        FreakyyyAssistant.initialize(applicationContext)
        FreakyyyVoiceEngine.initialize(applicationContext)

        // Reconnect to the paired laptop (needs the local-network permission on Android 17).
        val canReachLan = linkPermissions().take(1).all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
        if (canReachLan) FreakyyyLinkService.startIfWanted(applicationContext)
        handlePairingLink(intent)

        setContent {
            TroitTheme(darkTheme = true, dynamicColor = false) {
                FreakyyyApp(resumeTick.intValue)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        resumeTick.intValue++
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        handlePairingLink(intent)
    }

    /** freakyyylink://pair?d=... opened from a QR app, browser or chat. */
    private fun handlePairingLink(intent: android.content.Intent?) {
        android.util.Log.i("FreakyyyLink", "launch intent action=${intent?.action} data=${intent?.data?.toString()?.take(40)}")
        val data = intent?.data ?: return
        if (data.scheme != "freakyyylink") return
        FreakyyyAssistant.navigation.value = FreakyyyScreen.DEVICES
        val missing = linkPermissions().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) {
            FreakyyyLink.startPairing(data.toString())
        } else {
            pendingPairLink = data.toString()
            requestPermissions(missing.toTypedArray(), 77)
        }
    }

    private var pendingPairLink: String? = null

    @Deprecated("Activity result API is used elsewhere; this one is a single permission prompt")
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 77) {
            pendingPairLink?.let { FreakyyyLink.startPairing(it) }
            pendingPairLink = null
        }
    }

    override fun onStart() {
        super.onStart()
        LaunchGate.activityStarted()
    }

    override fun onStop() {
        LaunchGate.activityStopped()
        super.onStop()
    }

    override fun onDestroy() {
        if (isFinishing) {
            FreakyyyAssistant.stopAll()
            FreakyyyVoiceEngine.release()
        }
        super.onDestroy()
    }
}

@Composable
fun FreakyyyApp(resumeTick: Int) {

    val context = LocalContext.current

    var screen by rememberSaveable { mutableStateOf(FreakyyyScreen.HOME) }
    var listening by remember { mutableStateOf(ListeningState.IDLE) }
    var speechStatus by remember { mutableStateOf("Tap the mic or type a command") }

    val speechRecognizer = remember(context) {
        TroitSpeechRecognizer(
            context = context.applicationContext,
            onResult = { spokenText ->
                speechStatus = "Tap the mic or type a command"
                FreakyyyAssistant.submit(spokenText)
            },
            onStatus = { speechStatus = it },
            onError = { speechStatus = it },
            onStateChange = { listening = it }
        )
    }

    DisposableEffect(speechRecognizer) {
        onDispose {
            speechRecognizer.destroy()
            FreakyyyAssistant.stopSpeaking()
        }
    }

    // In-app navigation requested by commands ("show installed apps").
    val navigation by FreakyyyAssistant.navigation.collectAsState()
    LaunchedEffect(navigation) {
        navigation?.let {
            screen = it
            FreakyyyAssistant.navigation.value = null
        }
    }

    // Runtime permissions a command needs (e.g. Nearby devices for Bluetooth).
    val permissionRequest by FreakyyyAssistant.permissionRequest.collectAsState()
    var waitingRequest by remember { mutableStateOf<FreakyyyAssistant.PermissionRequest?>(null) }

    val commandPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        val request = waitingRequest
        waitingRequest = null
        if (granted && request != null) {
            FreakyyyAssistant.submit(request.retryCommand, silent = true)
        } else if (!granted) {
            FreakyyyAssistant.say("Permission wasn't granted, so I can't do that yet.", Outcome.NEEDS_PERMISSION)
        }
    }

    LaunchedEffect(permissionRequest) {
        permissionRequest?.let {
            FreakyyyAssistant.permissionRequest.value = null
            waitingRequest = it
            commandPermissionLauncher.launch(it.permission)
        }
    }

    val micPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            speechRecognizer.startListening("en-IN")
        } else {
            speechStatus = "Microphone permission denied"
        }
    }

    fun toggleVoiceInput() {
        if (listening != ListeningState.IDLE) {
            speechRecognizer.stopListening()
            return
        }
        // Never let Freakyyy hear itself.
        FreakyyyAssistant.stopSpeaking()

        val permissionGranted = ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED

        if (permissionGranted) {
            speechRecognizer.startListening("en-IN")
        } else {
            micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    BackHandler(enabled = screen != FreakyyyScreen.HOME) {
        screen = FreakyyyScreen.HOME
    }

    val goHome = { screen = FreakyyyScreen.HOME }

    Crossfade(targetState = screen, animationSpec = tween(220), label = "screen") { current ->
        when (current) {
            FreakyyyScreen.HOME -> FreakyyyHome(
                listening = listening,
                speechStatus = speechStatus,
                onMic = ::toggleVoiceInput,
                onNavigate = { screen = it }
            )

            FreakyyyScreen.APPS -> TroitPreferencesScreen(
                appManager = FreakyyyAssistant.appManager,
                preferenceManager = FreakyyyAssistant.preferences,
                onBack = goHome
            )

            FreakyyyScreen.ROUTINES -> RoutinesScreen(onBack = goHome)
            FreakyyyScreen.HISTORY -> HistoryScreen(onBack = goHome)
            FreakyyyScreen.PERMISSIONS -> PermissionsScreen(resumeTick = resumeTick, onBack = goHome)
            FreakyyyScreen.VOICE -> VoiceScreen(onBack = goHome)
            FreakyyyScreen.DEVICES -> DevicesScreen(onBack = goHome)
        }
    }
}

// =====================================================
// HOME
// =====================================================

private enum class OrbMode { IDLE, LISTENING, THINKING, SPEAKING }

private val quickActions = listOf(
    Triple("Flashlight", "✦", "toggle flashlight"),
    Triple("Battery", "▮", "battery status"),
    Triple("Wi-Fi", "◠", "open wifi settings"),
    Triple("Bluetooth", "ᛒ", "open bluetooth settings"),
    Triple("Brightness 50%", "☀", "set brightness to 50 percent"),
    Triple("Volume +", "♪", "increase volume"),
    Triple("Volume −", "♪", "decrease volume"),
    Triple("Silent", "◌", "silent mode"),
    Triple("Do Not Disturb", "☾", "turn on do not disturb"),
    Triple("Storage", "▤", "how much storage is free"),
    Triple("Notifications", "✉", "how many notifications do i have")
)

private val suggestions = listOf(
    "Open WhatsApp",
    "Set brightness to 40 percent",
    "Open YouTube notification settings",
    "Start my study routine",
    "What can you do?"
)

@Composable
private fun FreakyyyHome(
    listening: ListeningState,
    speechStatus: String,
    onMic: () -> Unit,
    onNavigate: (FreakyyyScreen) -> Unit
) {
    val voice by FreakyyyVoiceEngine.status.collectAsState()
    val messages by FreakyyyAssistant.messages.collectAsState()
    val routine by FreakyyyAssistant.routine.collectAsState()
    val awaiting by FreakyyyAssistant.awaitingAnswer.collectAsState()

    val link by FreakyyyLink.status.collectAsState()

    // Entrance: header drops in, the orb assembles, controls fade up (first launch only).
    val intro = remember { Animatable(if (FreakyyyIntro.played) 1f else 0f) }
    LaunchedEffect(Unit) {
        if (!FreakyyyIntro.played) {
            FreakyyyIntro.played = true
            intro.animateTo(1f, tween(1400, easing = FastOutSlowInEasing))
        }
    }
    fun stage(start: Float) = ((intro.value - start) / (1f - start)).coerceIn(0f, 1f)

    val orbMode = when {
        listening == ListeningState.LISTENING -> OrbMode.LISTENING
        listening == ListeningState.PROCESSING -> OrbMode.THINKING
        voice.state == FreakyyyVoiceEngine.State.SPEAKING -> OrbMode.SPEAKING
        routine != null -> OrbMode.THINKING
        else -> OrbMode.IDLE
    }

    FreakyyyBackground {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .imePadding()
                .padding(horizontal = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {

            Spacer(Modifier.height(14.dp))

            // HEADER
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .graphicsLayer {
                        alpha = stage(0.1f)
                        translationY = (1f - stage(0.1f)) * -40f
                    },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        "FREAKYYY",
                        color = Freakyyy.White,
                        fontSize = 22.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 6.sp
                    )
                    Text(
                        "AI ASSISTANT",
                        color = Freakyyy.Ice.copy(alpha = 0.6f),
                        fontSize = 9.sp,
                        letterSpacing = 3.sp
                    )
                }
                Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    VoicePill(voice) { onNavigate(FreakyyyScreen.VOICE) }
                    LinkPill(link) { onNavigate(FreakyyyScreen.DEVICES) }
                }
            }

            Spacer(Modifier.height(14.dp))

            // NAVIGATION
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .graphicsLayer { alpha = stage(0.35f) }
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                GlassChip("Apps", icon = "▦") { onNavigate(FreakyyyScreen.APPS) }
                GlassChip("Devices", icon = "⇄") { onNavigate(FreakyyyScreen.DEVICES) }
                GlassChip("Routines", icon = "↻") { onNavigate(FreakyyyScreen.ROUTINES) }
                GlassChip("History", icon = "≡") { onNavigate(FreakyyyScreen.HISTORY) }
                GlassChip("Permissions", icon = "⚿") { onNavigate(FreakyyyScreen.PERMISSIONS) }
                GlassChip("Voice", icon = "◉") { onNavigate(FreakyyyScreen.VOICE) }
            }

            val compact = messages.isNotEmpty()
            val orbSize by animateDpAsState(if (compact) 128.dp else 230.dp, tween(400), label = "orb")

            Spacer(Modifier.height(if (compact) 10.dp else 36.dp))

            FreakyyyOrb(
                mode = orbMode,
                modifier = Modifier
                    .size(orbSize)
                    .graphicsLayer {
                        val v = stage(0f)
                        alpha = v
                        scaleX = 0.55f + 0.45f * v
                        scaleY = 0.55f + 0.45f * v
                        rotationZ = (1f - v) * -90f
                    }
            )

            Spacer(Modifier.height(10.dp))

            Text(
                when (orbMode) {
                    OrbMode.LISTENING -> "LISTENING"
                    OrbMode.THINKING -> if (routine != null) "RUNNING ROUTINE" else "PROCESSING"
                    OrbMode.SPEAKING -> "SPEAKING"
                    OrbMode.IDLE -> if (compact) "READY" else "HELLO, I'M FREAKYYY"
                },
                color = Freakyyy.Ice.copy(alpha = 0.75f),
                fontSize = 12.sp,
                letterSpacing = 3.sp
            )

            if (!compact) {
                Spacer(Modifier.height(16.dp))
                Text(
                    "How can I help\nyou today?",
                    color = Freakyyy.White,
                    fontSize = 34.sp,
                    lineHeight = 42.sp,
                    fontWeight = FontWeight.SemiBold,
                    textAlign = TextAlign.Center,
                    letterSpacing = (-1).sp
                )
                Spacer(Modifier.height(22.dp))
                Column(
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    suggestions.forEach { s ->
                        Text(
                            "“$s”",
                            color = Freakyyy.Ice.copy(alpha = 0.55f),
                            fontSize = 13.sp,
                            modifier = Modifier.clickable { FreakyyyAssistant.submit(s) }
                        )
                    }
                }
                Spacer(Modifier.weight(1f))
            } else {
                Spacer(Modifier.height(10.dp))
                Conversation(messages, Modifier.weight(1f))
            }

            // ROUTINE PROGRESS
            AnimatedVisibility(routine != null, enter = fadeIn(), exit = fadeOut()) {
                routine?.let { progress ->
                    GlassCard(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 8.dp),
                        highlighted = true,
                        padding = 14.dp
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(
                                    "${progress.name} · step ${progress.step} of ${progress.total}",
                                    color = Freakyyy.White,
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.SemiBold
                                )
                                Text(progress.current, color = Freakyyy.Ice.copy(alpha = 0.7f), fontSize = 12.sp, maxLines = 1)
                            }
                            GlassChip("Stop", icon = "■") { FreakyyyAssistant.submit("stop") }
                        }
                        Spacer(Modifier.height(10.dp))
                        Box(
                            Modifier
                                .fillMaxWidth()
                                .height(3.dp)
                                .clip(CircleShape)
                                .background(Color.White.copy(alpha = 0.08f))
                        ) {
                            Box(
                                Modifier
                                    .fillMaxWidth(progress.step / progress.total.toFloat())
                                    .fillMaxHeight()
                                    .background(Brush.horizontalGradient(listOf(Freakyyy.Blue, Freakyyy.Cyan)))
                            )
                        }
                    }
                }
            }

            // YES / NO
            AnimatedVisibility(awaiting != null, enter = fadeIn(), exit = fadeOut()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    GlassChip("Yes", icon = "✓", active = true, modifier = Modifier.weight(1f)) {
                        FreakyyyAssistant.answer(true)
                    }
                    GlassChip("No", icon = "✕", modifier = Modifier.weight(1f)) {
                        FreakyyyAssistant.answer(false)
                    }
                }
            }

            Spacer(Modifier.height(10.dp))

            // QUICK ACTIONS
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                quickActions.forEach { (label, icon, command) ->
                    GlassChip(label, icon = icon) { FreakyyyAssistant.submit(command) }
                }
            }

            Spacer(Modifier.height(12.dp))

            CommandCapsule(
                listening = listening,
                statusText = speechStatus,
                onMic = onMic
            )

            Spacer(Modifier.height(16.dp))
        }
    }
}

/** Whether the first-launch entrance animation already played in this process. */
private object FreakyyyIntro {
    var played = false
}

@Composable
private fun LinkPill(status: FreakyyyLink.Status, onClick: () -> Unit) {
    val (label, color) = when (status.state) {
        FreakyyyLink.State.CONNECTED -> "LAPTOP · ONLINE" to Freakyyy.Success
        FreakyyyLink.State.CONNECTING, FreakyyyLink.State.PAIRING -> "LAPTOP · LINKING" to Freakyyy.Warning
        FreakyyyLink.State.OFFLINE -> "LAPTOP · OFFLINE" to Freakyyy.Danger
        FreakyyyLink.State.NOT_PAIRED -> "PAIR LAPTOP" to Freakyyy.Muted
    }
    StatusPill(label, color, Modifier.clickable(onClick = onClick))
}

@Composable
private fun VoicePill(status: FreakyyyVoiceEngine.Status, onClick: () -> Unit) {
    val (label, color) = when (status.state) {
        FreakyyyVoiceEngine.State.READY -> "VOICE READY" to Freakyyy.Success
        FreakyyyVoiceEngine.State.SPEAKING -> "SPEAKING" to Freakyyy.Cyan
        FreakyyyVoiceEngine.State.PREPARING, FreakyyyVoiceEngine.State.NOT_STARTED -> "VOICE LOADING" to Freakyyy.Warning
        FreakyyyVoiceEngine.State.FAILED -> "VOICE OFFLINE" to Freakyyy.Danger
    }
    StatusPill(label, color, Modifier.clickable(onClick = onClick))
}

@Composable
private fun Conversation(
    messages: List<FreakyyyAssistant.ChatMessage>,
    modifier: Modifier = Modifier
) {
    val listState = rememberLazyListState()
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }

    LazyColumn(
        state = listState,
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        contentPadding = PaddingValues(vertical = 4.dp)
    ) {
        items(messages, key = { it.id }) { message ->
            if (message.fromUser) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    Text(
                        message.text,
                        color = Freakyyy.White,
                        fontSize = 14.sp,
                        modifier = Modifier
                            .widthIn(max = 280.dp)
                            .clip(RoundedCornerShape(18.dp, 18.dp, 4.dp, 18.dp))
                            .background(
                                Brush.linearGradient(
                                    listOf(Freakyyy.Blue.copy(alpha = 0.55f), Freakyyy.Electric.copy(alpha = 0.35f))
                                )
                            )
                            .padding(horizontal = 14.dp, vertical = 10.dp)
                    )
                }
            } else {
                Column(
                    modifier = Modifier
                        .widthIn(max = 320.dp)
                        .glass(RoundedCornerShape(18.dp, 18.dp, 18.dp, 4.dp))
                        .padding(horizontal = 14.dp, vertical = 10.dp)
                ) {
                    Text(
                        Freakyyy.outcomeLabel(message.outcome),
                        color = Freakyyy.outcomeColor(message.outcome),
                        fontSize = 9.sp,
                        letterSpacing = 1.5.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(message.text, color = Freakyyy.White.copy(alpha = 0.92f), fontSize = 14.sp, lineHeight = 20.sp)
                }
            }
        }
    }
}

@Composable
private fun CommandCapsule(
    listening: ListeningState,
    statusText: String,
    onMic: () -> Unit
) {
    var text by rememberSaveable { mutableStateOf("") }
    val focus = LocalFocusManager.current

    fun send() {
        val command = text.trim()
        if (command.isNotEmpty()) {
            FreakyyyAssistant.submit(command)
            text = ""
            focus.clearFocus()
        }
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(68.dp)
            .glass(CircleShape, highlighted = listening != ListeningState.IDLE)
            .padding(start = 22.dp, end = 7.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.weight(1f)) {
            if (text.isEmpty()) {
                Text(
                    if (listening == ListeningState.IDLE) statusText.ifBlank { "Type a command…" } else statusText,
                    color = Freakyyy.White.copy(alpha = 0.5f),
                    fontSize = 15.sp,
                    maxLines = 1
                )
            }
            BasicTextField(
                value = text,
                onValueChange = { text = it },
                singleLine = true,
                textStyle = TextStyle(color = Freakyyy.White, fontSize = 15.sp),
                cursorBrush = SolidColor(Freakyyy.Cyan),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { send() }),
                modifier = Modifier.fillMaxWidth()
            )
        }

        if (text.isNotBlank()) {
            Box(
                modifier = Modifier
                    .size(54.dp)
                    .clip(CircleShape)
                    .background(Brush.linearGradient(listOf(Freakyyy.Blue, Freakyyy.Cyan)))
                    .clickable { send() },
                contentAlignment = Alignment.Center
            ) {
                Text("➤", color = Freakyyy.White, fontSize = 20.sp)
            }
        } else {
            MicButton(listening = listening, onClick = onMic)
        }
    }
}

@Composable
private fun MicButton(listening: ListeningState, onClick: () -> Unit) {
    val active = listening != ListeningState.IDLE
    Box(
        modifier = Modifier.size(54.dp),
        contentAlignment = Alignment.Center
    ) {
        if (active) {
            val transition = rememberInfiniteTransition(label = "mic")
            val ring by transition.animateFloat(
                initialValue = 1f,
                targetValue = 1.35f,
                animationSpec = infiniteRepeatable(tween(900, easing = FastOutSlowInEasing), RepeatMode.Reverse),
                label = "ring"
            )
            Box(
                Modifier
                    .size(54.dp)
                    .scale(ring)
                    .border(1.5.dp, Freakyyy.Cyan.copy(alpha = 0.5f), CircleShape)
            )
        }
        Box(
            modifier = Modifier
                .size(50.dp)
                .clip(CircleShape)
                .background(
                    if (active) Brush.linearGradient(listOf(Freakyyy.Cyan, Freakyyy.Blue))
                    else Brush.linearGradient(listOf(Freakyyy.Blue.copy(alpha = 0.8f), Freakyyy.Electric.copy(alpha = 0.6f)))
                )
                .clickable(onClick = onClick),
            contentAlignment = Alignment.Center
        ) {
            MicGlyph(color = Freakyyy.White)
        }
    }
}

@Composable
private fun MicGlyph(color: Color) {
    Canvas(Modifier.size(22.dp)) {
        val w = size.width
        val h = size.height
        drawRoundRect(
            color = color,
            topLeft = androidx.compose.ui.geometry.Offset(w * 0.34f, 0f),
            size = androidx.compose.ui.geometry.Size(w * 0.32f, h * 0.62f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(w * 0.16f)
        )
        drawArc(
            color = color,
            startAngle = 0f,
            sweepAngle = 180f,
            useCenter = false,
            topLeft = androidx.compose.ui.geometry.Offset(w * 0.18f, h * 0.22f),
            size = androidx.compose.ui.geometry.Size(w * 0.64f, h * 0.56f),
            style = Stroke(width = w * 0.08f)
        )
        drawLine(
            color = color,
            start = androidx.compose.ui.geometry.Offset(w * 0.5f, h * 0.78f),
            end = androidx.compose.ui.geometry.Offset(w * 0.5f, h * 0.95f),
            strokeWidth = w * 0.08f
        )
    }
}

// =====================================================
// LIQUID GLASS ORB
// =====================================================

@Composable
private fun FreakyyyOrb(mode: OrbMode, modifier: Modifier = Modifier) {
    if (mode == OrbMode.IDLE) {
        // Static when idle: no continuous animation draining the battery.
        OrbVisual(mode, rotation = 25f, pulse = 1f, modifier = modifier)
    } else {
        val transition = rememberInfiniteTransition(label = "orb")
        val rotation by transition.animateFloat(
            initialValue = 0f,
            targetValue = 360f,
            animationSpec = infiniteRepeatable(
                tween(if (mode == OrbMode.THINKING) 2600 else 9000, easing = LinearEasing)
            ),
            label = "rotation"
        )
        val pulse by transition.animateFloat(
            initialValue = 0.94f,
            targetValue = if (mode == OrbMode.LISTENING) 1.1f else 1.05f,
            animationSpec = infiniteRepeatable(
                tween(if (mode == OrbMode.SPEAKING) 420 else 1100, easing = FastOutSlowInEasing),
                repeatMode = RepeatMode.Reverse
            ),
            label = "pulse"
        )
        OrbVisual(mode, rotation, pulse, modifier)
    }
}

@Composable
private fun OrbVisual(mode: OrbMode, rotation: Float, pulse: Float, modifier: Modifier) {
    val accent = when (mode) {
        OrbMode.LISTENING -> Freakyyy.Cyan
        OrbMode.SPEAKING -> Color(0xFF8FB8FF)
        else -> Freakyyy.Blue
    }

    BoxWithConstraints(modifier = modifier, contentAlignment = Alignment.Center) {
        val full = maxWidth

        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .rotate(rotation)
        ) {
            val c = center
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(accent.copy(alpha = 0.28f), Color(0xFF126BFF).copy(alpha = 0.10f), Color.Transparent),
                    center = c,
                    radius = size.minDimension * 0.5f * pulse
                ),
                radius = size.minDimension * 0.5f * pulse
            )
            drawArc(
                brush = Brush.sweepGradient(
                    listOf(Color.Transparent, Color(0xFF248CFF), Color(0xFFC5F4FF), Color(0xFF356DFF), Color.Transparent)
                ),
                startAngle = 25f,
                sweepAngle = 285f,
                useCenter = false,
                style = Stroke(width = 3.5f)
            )
            drawArc(
                color = accent.copy(alpha = 0.85f),
                startAngle = 190f,
                sweepAngle = 85f,
                useCenter = false,
                style = Stroke(width = 2f)
            )
        }

        Box(
            Modifier
                .size(full * 0.76f)
                .background(
                    Brush.radialGradient(listOf(Color(0xFF103C79), Color(0xFF071B3C), Color(0xFF030B1B))),
                    CircleShape
                )
        )

        Box(
            Modifier
                .size(full * 0.63f)
                .scale(pulse)
                .rotate(rotation * -0.65f)
                .background(
                    Brush.linearGradient(
                        listOf(
                            Color(0xFFB5EDFF).copy(alpha = 0.35f),
                            Color(0xFF278CFF).copy(alpha = 0.10f),
                            Color(0xFF7D8DFF).copy(alpha = 0.30f)
                        )
                    ),
                    RoundedCornerShape(full * 0.18f)
                )
                .border(
                    1.5.dp,
                    Brush.linearGradient(listOf(Freakyyy.Ice, Color.Transparent, Freakyyy.Blue, Color.Transparent, Freakyyy.Ice)),
                    RoundedCornerShape(full * 0.18f)
                )
        )

        Box(
            Modifier
                .size(full * 0.43f)
                .background(
                    Brush.radialGradient(
                        listOf(accent.copy(alpha = 0.55f), Color(0xFF176DFF).copy(alpha = 0.15f), Color.Transparent)
                    ),
                    CircleShape
                )
        )

        if (mode == OrbMode.SPEAKING || mode == OrbMode.LISTENING) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(3.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                listOf(0.35f, 0.7f, 1f, 0.6f, 0.85f, 0.4f).forEachIndexed { i, h ->
                    val wobble = if (i % 2 == 0) pulse else 2f - pulse
                    Box(
                        Modifier
                            .width(3.dp)
                            .height(full * 0.16f * h * wobble)
                            .clip(CircleShape)
                            .background(Freakyyy.Ice)
                    )
                }
            }
        } else {
            Text(
                "D",
                color = Freakyyy.White,
                fontSize = (full.value * 0.24f).sp,
                fontWeight = FontWeight.ExtraLight
            )
        }
    }
}

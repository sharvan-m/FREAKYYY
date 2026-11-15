
package com.troit.assistant

import android.os.Bundle
import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.troit.assistant.ui.theme.TroitTheme
import androidx.activity.compose.BackHandler

private val Black = Color(0xFF02040A)
private val Navy = Color(0xFF07152C)
private val Blue = Color(0xFF238CFF)
private val Ice = Color(0xFFBDEBFF)
private val White = Color(0xFFF8FAFF)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            TroitTheme {
                TroitHome()
            }
        }
    }
}

@Composable
fun TroitHome() {

    val context = LocalContext.current

    val troitSpeaker = remember(context) {
        TroitSpeaker(context.applicationContext)
    }

    val appManager = remember(context) {
        TroitAppManager(context.applicationContext)
    }

    val preferenceManager = remember(context) {
        TroitPreferenceManager(context.applicationContext)
    }

    val appMatcher = remember(appManager, preferenceManager) {
        TroitAppMatcher(appManager, preferenceManager)
    }

    var showPreferences by remember {
        mutableStateOf(false)
    }

    var recognizedText by remember {
        mutableStateOf("")
    }

    var speechStatus by remember {
        mutableStateOf("Tap to speak")
    }

    var pendingApp by remember {
        mutableStateOf<TroitApp?>(null)
    }

    var awaitingConfirmation by remember {
        mutableStateOf(false)
    }

    val speechRecognizer = remember(context) {
        TroitSpeechRecognizer(
            context = context.applicationContext,

            onResult = { spokenText ->

                recognizedText = spokenText

                val answer = spokenText
                    .lowercase()
                    .trim()
                    .replace(Regex("[.!?,]+$"), "")

                val command =
                    TroitCommandHandler.detectCommand(spokenText)

                // =====================================
                // HANDLE YES / NO CONFIRMATION
                // =====================================

                if (
                    awaitingConfirmation &&
                    command.type != TroitCommandType.OPEN_APP
                ) {

                    when (answer) {

                        "yes",
                        "yeah",
                        "yep",
                        "correct",
                        "sure",
                        "okay",
                        "ok",
                        "open it",
                        "do it",
                        "go ahead" -> {

                            val app = pendingApp

                            if (app != null) {

                                if (appManager.launchApp(app)) {

                                    speechStatus = "Opening ${app.name}"
                                    recognizedText = ""

                                    troitSpeaker.speak(
                                        "Opening ${app.name}"
                                    )

                                } else {

                                    speechStatus =
                                        "Unable to open ${app.name}"

                                    recognizedText = ""

                                    troitSpeaker.speak(
                                        "I couldn't open ${app.name}."
                                    )
                                }

                            } else {

                                speechStatus = "No pending app found"
                                recognizedText = ""

                                troitSpeaker.speak(
                                    "I couldn't find the pending app."
                                )
                            }

                            pendingApp = null
                            awaitingConfirmation = false
                        }

                        "no",
                        "nope",
                        "cancel",
                        "don't",
                        "dont",
                        "stop",
                        "not now" -> {

                            pendingApp = null
                            awaitingConfirmation = false

                            speechStatus = "Action cancelled"
                            recognizedText = ""

                            troitSpeaker.speak(
                                "Okay, I cancelled that action."
                            )
                        }

                        else -> {

                            speechStatus = "Please say yes or no"
                            recognizedText = ""

                            troitSpeaker.speak(
                                "Please say yes or no."
                            )
                        }
                    }

                } else {

                    // =====================================
                    // HANDLE NEW APP COMMAND
                    // =====================================

                    if (command.type == TroitCommandType.OPEN_APP) {

                        // A new app command replaces a pending request.
                        pendingApp = null
                        awaitingConfirmation = false

                        val result = appMatcher.match(command.appName)

                        when (result.type) {

                            AppMatchType.DIRECT -> {

                                val app = result.apps.firstOrNull()

                                if (app == null) {

                                    speechStatus =
                                        "I couldn't identify that app."

                                    recognizedText = ""
                                    troitSpeaker.speak(speechStatus)

                                } else if (result.requiresConfirmation) {

                                    pendingApp = app
                                    awaitingConfirmation = true

                                    val question =
                                        "Do you want me to open ${app.name}?"

                                    speechStatus = question
                                    recognizedText = ""

                                    troitSpeaker.speak(question)

                                } else {

                                    if (appManager.launchApp(app)) {

                                        speechStatus =
                                            "Opening ${app.name}"

                                        recognizedText = ""

                                        troitSpeaker.speak(
                                            "Opening ${app.name}"
                                        )

                                    } else {

                                        speechStatus =
                                            "I couldn't open ${app.name}."

                                        recognizedText = ""
                                        troitSpeaker.speak(speechStatus)
                                    }
                                }
                            }

                            AppMatchType.SUGGESTION -> {

                                val app = result.apps.firstOrNull()

                                if (app != null) {

                                    pendingApp = app
                                    awaitingConfirmation = true

                                    val question =
                                        "Do you want me to open ${app.name}?"

                                    speechStatus = question
                                    recognizedText = ""

                                    troitSpeaker.speak(question)

                                } else {

                                    speechStatus = result.message
                                    recognizedText = ""

                                    troitSpeaker.speak(result.message)
                                }
                            }

                            AppMatchType.MULTIPLE -> {

                                speechStatus = result.message
                                recognizedText = ""

                                troitSpeaker.speak(result.message)
                            }

                            AppMatchType.NOT_FOUND -> {

                                speechStatus = result.message
                                recognizedText = ""

                                troitSpeaker.speak(result.message)
                            }
                        }

                    } else {

                        speechStatus =
                            "I didn't understand that command."

                        recognizedText = ""

                        troitSpeaker.speak(speechStatus)
                    }
                }
            },

            onStatus = {
                speechStatus = it
            },

            onError = {
                speechStatus = it
            }
        )
    }

    DisposableEffect(speechRecognizer, troitSpeaker) {
        onDispose {
            speechRecognizer.destroy()
            troitSpeaker.shutdown()
        }
    }

    val permissionLauncher =
        rememberLauncherForActivityResult(
            ActivityResultContracts.RequestPermission()
        ) { granted ->

            if (granted) {
                speechRecognizer.startListening("en-IN")
            } else {
                speechStatus = "Microphone permission denied"
            }
        }

    fun startVoiceInput() {

        val permissionGranted =
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.RECORD_AUDIO
            ) == PackageManager.PERMISSION_GRANTED

        if (permissionGranted) {

            recognizedText = ""
            speechRecognizer.startListening("en-IN")

        } else {

            recognizedText = ""

            permissionLauncher.launch(
                Manifest.permission.RECORD_AUDIO
            )
        }
    }

    // =====================================
    // APP HUB SCREEN
    // =====================================

    if (showPreferences) {

        TroitPreferencesScreen(
            appManager = appManager,
            preferenceManager = preferenceManager,
            onBack = {
                showPreferences = false
            }
        )

        return
    }

    // =====================================
    // HOME SCREEN ANIMATIONS
    // =====================================

    val transition = rememberInfiniteTransition(label = "liquid")

    val rotation by transition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            tween(16000, easing = LinearEasing)
        ),
        label = "rotation"
    )

    val pulse by transition.animateFloat(
        initialValue = 0.94f,
        targetValue = 1.06f,
        animationSpec = infiniteRepeatable(
            tween(2400, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulse"
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(
                        Color(0xFF020611),
                        Black,
                        Color(0xFF030D20),
                        Color(0xFF071D3D)
                    )
                )
            )
            .padding(horizontal = 27.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {

        Spacer(Modifier.height(65.dp))

        // HEADER

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {

            Text(
                "TROIT",
                color = White,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 5.sp
            )

            Row(
                verticalAlignment = Alignment.CenterVertically
            ) {

                Text(
                    "AI ASSISTANT",
                    color = Ice.copy(alpha = 0.65f),
                    fontSize = 10.sp,
                    letterSpacing = 2.sp
                )

                Spacer(Modifier.width(6.dp))

                TextButton(
                    onClick = {
                        showPreferences = true
                    }
                ) {
                    Text(
                        "APPS",
                        color = Ice,
                        fontSize = 11.sp
                    )
                }
            }
        }

        Spacer(Modifier.weight(0.7f))

        // =====================================
        // LIQUID GLASS AI ORB
        // =====================================

        Box(
            modifier = Modifier.size(270.dp),
            contentAlignment = Alignment.Center
        ) {

            Canvas(
                modifier = Modifier
                    .fillMaxSize()
                    .rotate(rotation)
            ) {

                val center = this.center

                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            Color(0xFF55BFFF).copy(alpha = 0.25f),
                            Color(0xFF126BFF).copy(alpha = 0.10f),
                            Color.Transparent
                        ),
                        center = center,
                        radius = size.minDimension * 0.5f
                    ),
                    radius = size.minDimension * 0.5f
                )

                drawArc(
                    brush = Brush.sweepGradient(
                        listOf(
                            Color.Transparent,
                            Color(0xFF248CFF),
                            Color(0xFFC5F4FF),
                            Color(0xFF356DFF),
                            Color.Transparent
                        )
                    ),
                    startAngle = 25f,
                    sweepAngle = 285f,
                    useCenter = false,
                    style = Stroke(width = 3.5f)
                )

                drawArc(
                    color = Color(0xFF70D9FF).copy(alpha = 0.8f),
                    startAngle = 190f,
                    sweepAngle = 85f,
                    useCenter = false,
                    style = Stroke(width = 2f)
                )
            }

            Box(
                modifier = Modifier
                    .size(205.dp)
                    .background(
                        Brush.radialGradient(
                            colors = listOf(
                                Color(0xFF103C79),
                                Color(0xFF071B3C),
                                Color(0xFF030B1B)
                            )
                        ),
                        CircleShape
                    )
            )

            Box(
                modifier = Modifier
                    .size(170.dp)
                    .rotate(rotation * -0.65f)
                    .background(
                        Brush.linearGradient(
                            colors = listOf(
                                Color(0xFFB5EDFF).copy(alpha = 0.35f),
                                Color(0xFF278CFF).copy(alpha = 0.10f),
                                Color(0xFF7D8DFF).copy(alpha = 0.30f)
                            )
                        ),
                        RoundedCornerShape(48.dp)
                    )
                    .border(
                        1.5.dp,
                        Brush.linearGradient(
                            listOf(
                                Ice,
                                Color.Transparent,
                                Blue,
                                Color.Transparent,
                                Ice
                            )
                        ),
                        RoundedCornerShape(48.dp)
                    )
            )

            Box(
                modifier = Modifier
                    .size(115.dp)
                    .background(
                        Brush.radialGradient(
                            listOf(
                                Color(0xFF6DD9FF).copy(alpha = 0.55f),
                                Color(0xFF176DFF).copy(alpha = 0.15f),
                                Color.Transparent
                            )
                        ),
                        CircleShape
                    )
            )

            Text(
                "T",
                color = White,
                fontSize = 65.sp,
                fontWeight = FontWeight.ExtraLight
            )
        }

        Spacer(Modifier.height(45.dp))

        Text(
            "HELLO, I'M TROIT",
            color = Ice.copy(alpha = 0.75f),
            fontSize = 14.sp,
            letterSpacing = 3.sp
        )

        Spacer(Modifier.height(20.dp))

        Text(
            "How can I help\nyou today?",
            color = White,
            fontSize = 36.sp,
            lineHeight = 44.sp,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center,
            letterSpacing = (-1).sp
        )

        Spacer(Modifier.weight(1f))

        // =====================================
        // GLASS INPUT CAPSULE
        // =====================================

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(78.dp)
                .clip(CircleShape)
                .background(
                    Brush.verticalGradient(
                        listOf(
                            Color.White.copy(alpha = 0.09f),
                            Color(0xFF278BFF).copy(alpha = 0.19f),
                            Color.White.copy(alpha = 0.07f)
                        )
                    )
                )
                .border(
                    1.dp,
                    Brush.verticalGradient(
                        listOf(
                            Color.White.copy(alpha = 0.42f),
                            Blue.copy(alpha = 0.35f),
                            Ice.copy(alpha = 0.15f)
                        )
                    ),
                    CircleShape
                )
                .clickable {
                    startVoiceInput()
                }
                .padding(horizontal = 25.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {

            Text(
                text = recognizedText.ifBlank {
                    speechStatus
                },
                modifier = Modifier.weight(1f),
                color = White.copy(alpha = 0.85f),
                fontSize = 15.sp,
                maxLines = 2
            )

            // WAVEFORM

            Row(
                horizontalArrangement = Arrangement.spacedBy(3.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {

                listOf(12, 23, 34, 19, 28, 13)
                    .forEach { height ->

                        Box(
                            modifier = Modifier
                                .width(3.dp)
                                .height((height * pulse).dp)
                                .clip(CircleShape)
                                .background(Ice)
                        )
                    }
            }
        }

        Spacer(Modifier.height(30.dp))
    }
}


// =====================================================
// TROIT APP HUB
// =====================================================

@Composable
fun TroitPreferencesScreen(
    appManager: TroitAppManager,
    preferenceManager: TroitPreferenceManager,
    onBack: () -> Unit
) {

    val categories = listOf(
        Triple("gallery", "Gallery", "▧"),
        Triple("browser", "Browser", "◎"),
        Triple("music", "Music", "♫"),
        Triple("messaging", "Messaging", "✉"),
        Triple("video", "Video", "▷")
    )

    val installedApps = remember(appManager) {
        appManager.getInstalledApps()
            .sortedBy { it.name.lowercase() }
    }

    var activeCategory by remember {
        mutableStateOf<String?>(null)
    }

    var searchQuery by remember {
        mutableStateOf("")
    }

    val selectedCategory = activeCategory

    BackHandler {
        if (activeCategory != null) {
            activeCategory = null
            searchQuery = ""
        } else {
            onBack()
        }
    }

    val filteredApps = remember(installedApps, searchQuery) {
        installedApps.filter {
            it.name.contains(
                searchQuery.trim(),
                ignoreCase = true
            )
        }
    }

    val backgroundBrush = Brush.verticalGradient(
        listOf(
            Color(0xFF020611),
            Black,
            Color(0xFF071D3D)
        )
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(backgroundBrush)
            .padding(horizontal = 20.dp, vertical = 16.dp)
    ) {

        // =====================================
        // HEADER
        // =====================================

        TextButton(
            onClick = {
                if (activeCategory != null) {
                    activeCategory = null
                    searchQuery = ""
                } else {
                    onBack()
                }
            }
        ){
            Text(
                "← BACK",
                color = Ice
            )
        }

        Spacer(Modifier.height(16.dp))

        if (selectedCategory == null) {

            // =====================================
            // APP HUB DASHBOARD
            // =====================================

            Text(
                "App Hub",
                color = White,
                fontSize = 30.sp,
                fontWeight = FontWeight.Bold
            )

            Spacer(Modifier.height(7.dp))

            Text(
                "Your apps. Your choice.",
                color = Ice.copy(alpha = 0.7f),
                fontSize = 14.sp
            )

            Spacer(Modifier.height(28.dp))

            Text(
                "PREFERRED APPS",
                color = Ice,
                fontSize = 11.sp,
                letterSpacing = 2.sp
            )

            Spacer(Modifier.height(14.dp))

            categories.chunked(2).forEach { categoryRow ->

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {

                    categoryRow.forEach { item ->

                        val category = item.first
                        val categoryName = item.second
                        val categoryIcon = item.third

                        val preferredPackage =
                            preferenceManager.getPreferredPackage(
                                category
                            )

                        val preferredApp =
                            installedApps.firstOrNull {
                                it.packageName == preferredPackage
                            }

                        Column(
                            modifier = Modifier
                                .weight(1f)
                                .clip(RoundedCornerShape(22.dp))
                                .background(Color(0xFF0D1B30))
                                .border(
                                    1.dp,
                                    Blue.copy(alpha = 0.25f),
                                    RoundedCornerShape(22.dp)
                                )
                                .clickable {
                                    activeCategory = category
                                    searchQuery = ""
                                }
                                .padding(16.dp)
                        ) {

                            Box(
                                modifier = Modifier
                                    .size(43.dp)
                                    .clip(RoundedCornerShape(14.dp))
                                    .background(Color(0xFF174B83)),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    categoryIcon,
                                    color = White,
                                    fontSize = 23.sp
                                )
                            }

                            Spacer(Modifier.height(15.dp))

                            Text(
                                categoryName,
                                color = White,
                                fontSize = 16.sp,
                                fontWeight = FontWeight.SemiBold
                            )

                            Spacer(Modifier.height(5.dp))

                            Text(
                                preferredApp?.name ?: "Not selected",
                                color = if (preferredApp != null)
                                    Color(0xFF65DDAA)
                                else
                                    Color.Gray,
                                fontSize = 12.sp,
                                maxLines = 1
                            )

                            Spacer(Modifier.height(13.dp))

                            Text(
                                "Change app  →",
                                color = Ice,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Medium
                            )
                        }
                    }

                    if (categoryRow.size == 1) {
                        Spacer(Modifier.weight(1f))
                    }
                }

                Spacer(Modifier.height(12.dp))
            }

            Spacer(Modifier.height(16.dp))

            Text(
                "Choose a category to set the app Troit should use.",
                color = Ice.copy(alpha = 0.55f),
                fontSize = 12.sp
            )

        } else {

            // =====================================
            // SEARCHABLE APP PICKER
            // =====================================

            val categoryName = categories.firstOrNull {
                it.first == selectedCategory
            }?.second ?: selectedCategory.replaceFirstChar {
                it.uppercase()
            }

            Text(
                "Choose $categoryName",
                color = White,
                fontSize = 27.sp,
                fontWeight = FontWeight.Bold
            )

            Spacer(Modifier.height(6.dp))

            Text(
                "Find any installed app on your device.",
                color = Ice.copy(alpha = 0.7f),
                fontSize = 13.sp
            )

            Spacer(Modifier.height(20.dp))

            OutlinedTextField(
                value = searchQuery,
                onValueChange = {
                    searchQuery = it
                },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                placeholder = {
                    Text(
                        "Search apps...",
                        color = Color.Gray
                    )
                },
                leadingIcon = {
                    Text(
                        "⌕",
                        color = Ice,
                        fontSize = 23.sp
                    )
                }
            )

            Spacer(Modifier.height(14.dp))

            Text(
                "${filteredApps.size} APPS FOUND",
                color = Ice,
                fontSize = 11.sp,
                letterSpacing = 1.5.sp
            )

            Spacer(Modifier.height(10.dp))

            if (filteredApps.isEmpty()) {

                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentAlignment = Alignment.Center
                ) {

                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {

                        Text(
                            "No apps found",
                            color = White,
                            fontSize = 19.sp,
                            fontWeight = FontWeight.SemiBold
                        )

                        Spacer(Modifier.height(7.dp))

                        Text(
                            "Try another app name.",
                            color = Color.Gray,
                            fontSize = 13.sp
                        )
                    }
                }

            } else {

                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(9.dp)
                ) {

                    items(
                        items = filteredApps,
                        key = { it.packageName }
                    ) { app ->

                        val isPreferred =
                            preferenceManager.getPreferredPackage(
                                selectedCategory
                            ) == app.packageName

                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(17.dp))
                                .background(Color(0xFF0D1B30))
                                .border(
                                    1.dp,
                                    if (isPreferred)
                                        Blue.copy(alpha = 0.8f)
                                    else
                                        Ice.copy(alpha = 0.12f),
                                    RoundedCornerShape(17.dp)
                                )
                                .clickable {

                                    preferenceManager.setPreferredApp(
                                        selectedCategory,
                                        app
                                    )

                                    activeCategory = null
                                    searchQuery = ""
                                }
                                .padding(15.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {

                            Box(
                                modifier = Modifier
                                    .size(42.dp)
                                    .clip(RoundedCornerShape(13.dp))
                                    .background(Color(0xFF174B83)),
                                contentAlignment = Alignment.Center
                            ) {

                                Text(
                                    app.name.firstOrNull()?.uppercase() ?: "?",
                                    color = White,
                                    fontSize = 19.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }

                            Spacer(Modifier.width(13.dp))

                            Column(
                                modifier = Modifier.weight(1f)
                            ) {

                                Text(
                                    app.name,
                                    color = White,
                                    fontSize = 15.sp,
                                    fontWeight = FontWeight.SemiBold
                                )

                                Spacer(Modifier.height(4.dp))

                                Text(
                                    if (isPreferred)
                                        "Currently selected"
                                    else
                                        "Installed app",
                                    color = if (isPreferred)
                                        Color(0xFF65DDAA)
                                    else
                                        Color.Gray,
                                    fontSize = 11.sp
                                )
                            }

                            Text(
                                if (isPreferred) "✓" else "›",
                                color = if (isPreferred)
                                    Color(0xFF65DDAA)
                                else
                                    Ice,
                                fontSize = 22.sp
                            )
                        }
                    }
                }
            }
        }
    }
}

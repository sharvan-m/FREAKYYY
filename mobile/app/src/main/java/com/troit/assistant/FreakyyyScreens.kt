
package com.troit.assistant

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.troit.assistant.ui.Freakyyy
import com.troit.assistant.ui.FreakyyyScreenFrame
import com.troit.assistant.ui.GlassCard
import com.troit.assistant.ui.GlassChip
import com.troit.assistant.ui.SectionLabel
import com.troit.assistant.ui.StatusPill
import com.troit.assistant.ui.glass
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// =====================================================
// APP HUB (preferred apps + all installed apps)
// =====================================================

private const val ALL_APPS = "__all__"

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

    var activeCategory by remember { mutableStateOf<String?>(null) }
    var searchQuery by remember { mutableStateOf("") }
    // Bumped when a preference changes so the dashboard re-reads it.
    var preferenceVersion by remember { mutableIntStateOf(0) }

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
        installedApps.filter { it.name.contains(searchQuery.trim(), ignoreCase = true) }
    }

    val back = {
        if (activeCategory != null) {
            activeCategory = null
            searchQuery = ""
        } else {
            onBack()
        }
    }

    if (selectedCategory == null) {

        FreakyyyScreenFrame(
            title = "App Hub",
            subtitle = "Your apps. Your choice.",
            onBack = back
        ) {
            GlassCard(
                modifier = Modifier.fillMaxWidth(),
                highlighted = true,
                onClick = {
                    activeCategory = ALL_APPS
                    searchQuery = ""
                }
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Installed apps", color = Freakyyy.White, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "${installedApps.size} apps · open or view app info",
                            color = Freakyyy.Ice.copy(alpha = 0.7f),
                            fontSize = 12.sp
                        )
                    }
                    Text("→", color = Freakyyy.Cyan, fontSize = 22.sp)
                }
            }

            Spacer(Modifier.height(22.dp))
            SectionLabel("Preferred apps")
            Spacer(Modifier.height(12.dp))

            key(preferenceVersion) {
                categories.chunked(2).forEach { categoryRow ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        categoryRow.forEach { (category, categoryName, categoryIcon) ->

                            val preferredPackage = preferenceManager.getPreferredPackage(category)
                            val preferredApp = installedApps.firstOrNull { it.packageName == preferredPackage }

                            GlassCard(
                                modifier = Modifier.weight(1f),
                                onClick = {
                                    activeCategory = category
                                    searchQuery = ""
                                }
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(40.dp)
                                        .clip(RoundedCornerShape(13.dp))
                                        .background(Freakyyy.Blue.copy(alpha = 0.35f)),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(categoryIcon, color = Freakyyy.White, fontSize = 21.sp)
                                }
                                Spacer(Modifier.height(13.dp))
                                Text(categoryName, color = Freakyyy.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    preferredApp?.name ?: "Not selected",
                                    color = if (preferredApp != null) Freakyyy.Success else Color.Gray,
                                    fontSize = 12.sp,
                                    maxLines = 1
                                )
                                Spacer(Modifier.height(11.dp))
                                Text("Change app  →", color = Freakyyy.Ice, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                            }
                        }
                        if (categoryRow.size == 1) Spacer(Modifier.weight(1f))
                    }
                    Spacer(Modifier.height(12.dp))
                }
            }

            Spacer(Modifier.height(8.dp))
            Text(
                "Choose a category to set the app Freakyyy should use.",
                color = Freakyyy.Ice.copy(alpha = 0.55f),
                fontSize = 12.sp
            )
        }

    } else {

        val browsingAll = selectedCategory == ALL_APPS
        val categoryName = categories.firstOrNull { it.first == selectedCategory }?.second
            ?: selectedCategory.replaceFirstChar { it.uppercase() }

        FreakyyyScreenFrame(
            title = if (browsingAll) "Installed apps" else "Choose $categoryName",
            subtitle = if (browsingAll) "Tap to open · ⓘ for app info and settings."
            else "Find any installed app on your device.",
            onBack = back
        ) {
            GlassSearchField(searchQuery, onChange = { searchQuery = it }, placeholder = "Search apps...")

            Spacer(Modifier.height(14.dp))
            SectionLabel("${filteredApps.size} apps found")
            Spacer(Modifier.height(10.dp))

            if (filteredApps.isEmpty()) {
                Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("No apps found", color = Freakyyy.White, fontSize = 19.sp, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(7.dp))
                        Text("Try another app name.", color = Color.Gray, fontSize = 13.sp)
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(9.dp)
                ) {
                    items(items = filteredApps, key = { it.packageName }) { app ->

                        val isPreferred = !browsingAll &&
                                preferenceManager.getPreferredPackage(selectedCategory) == app.packageName

                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .glass(RoundedCornerShape(17.dp), highlighted = isPreferred)
                                .clickable {
                                    if (browsingAll) {
                                        FreakyyyAssistant.perform(FreakyyyAction.LaunchResolvedApp(app))
                                    } else {
                                        preferenceManager.setPreferredApp(selectedCategory, app)
                                        preferenceVersion++
                                        activeCategory = null
                                        searchQuery = ""
                                    }
                                }
                                .padding(15.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(42.dp)
                                    .clip(RoundedCornerShape(13.dp))
                                    .background(Freakyyy.Blue.copy(alpha = 0.35f)),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    app.name.firstOrNull()?.uppercase() ?: "?",
                                    color = Freakyyy.White,
                                    fontSize = 19.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }

                            Spacer(Modifier.width(13.dp))

                            Column(Modifier.weight(1f)) {
                                Text(app.name, color = Freakyyy.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    when {
                                        isPreferred -> "Currently selected"
                                        browsingAll -> app.packageName
                                        else -> "Installed app"
                                    },
                                    color = if (isPreferred) Freakyyy.Success else Color.Gray,
                                    fontSize = 11.sp,
                                    maxLines = 1
                                )
                            }

                            if (browsingAll) {
                                Text(
                                    "ⓘ",
                                    color = Freakyyy.Cyan,
                                    fontSize = 22.sp,
                                    modifier = Modifier
                                        .clip(CircleShape)
                                        .clickable {
                                            FreakyyyAssistant.perform(
                                                FreakyyyAction.ResolvedAppSettings(app, AppSettingsPage.DETAILS)
                                            )
                                        }
                                        .padding(6.dp)
                                )
                            } else {
                                Text(
                                    if (isPreferred) "✓" else "›",
                                    color = if (isPreferred) Freakyyy.Success else Freakyyy.Ice,
                                    fontSize = 22.sp
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun GlassSearchField(value: String, onChange: (String) -> Unit, placeholder: String) {
    GlassInput(
        value = value,
        onChange = onChange,
        placeholder = placeholder,
        leading = "⌕"
    )
}

@Composable
private fun GlassInput(
    value: String,
    onChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    leading: String? = null
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .glass(RoundedCornerShape(16.dp))
            .padding(horizontal = 14.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (leading != null) {
            Text(leading, color = Freakyyy.Ice, fontSize = 19.sp)
            Spacer(Modifier.width(10.dp))
        }
        Box(Modifier.weight(1f)) {
            if (value.isEmpty()) Text(placeholder, color = Color.Gray, fontSize = 15.sp)
            BasicTextField(
                value = value,
                onValueChange = onChange,
                singleLine = true,
                textStyle = TextStyle(color = Freakyyy.White, fontSize = 15.sp),
                cursorBrush = SolidColor(Freakyyy.Cyan),
                modifier = Modifier.fillMaxWidth()
            )
        }
    }
}

// =====================================================
// ROUTINES
// =====================================================

@Composable
fun RoutinesScreen(onBack: () -> Unit) {
    val store = FreakyyyAssistant.routines
    var routines by remember { mutableStateOf(store.all()) }
    var editing by remember { mutableStateOf<FreakyyyRoutine?>(null) }
    val running by FreakyyyAssistant.routine.collectAsState()

    val current = editing
    if (current != null) {
        RoutineEditor(
            initial = current,
            onCancel = { editing = null },
            onSave = {
                store.upsert(it)
                routines = store.all()
                editing = null
            }
        )
        return
    }

    FreakyyyScreenFrame(
        title = "Routines",
        subtitle = "Ordered steps Freakyyy runs for you. Each step is any command Freakyyy understands.",
        onBack = onBack,
        action = {
            GlassChip("New", icon = "+", active = true) {
                editing = FreakyyyRoutine(name = "", steps = listOf(""))
            }
        }
    ) {
        running?.let {
            GlassCard(Modifier.fillMaxWidth(), highlighted = true, padding = 14.dp) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "Running ${it.name} · ${it.step}/${it.total}",
                        color = Freakyyy.White,
                        modifier = Modifier.weight(1f),
                        fontWeight = FontWeight.SemiBold
                    )
                    GlassChip("Stop", icon = "■") { FreakyyyAssistant.submit("stop") }
                }
            }
            Spacer(Modifier.height(12.dp))
        }

        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            items(routines, key = { it.id }) { routine ->
                GlassCard(Modifier.fillMaxWidth()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(routine.name, color = Freakyyy.White, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                            Text(
                                "Say “start my ${routine.name.lowercase()} routine”",
                                color = Freakyyy.Ice.copy(alpha = 0.6f),
                                fontSize = 12.sp
                            )
                        }
                        GlassChip("Run", icon = "▶", active = true) { FreakyyyAssistant.runRoutine(routine) }
                    }
                    Spacer(Modifier.height(12.dp))
                    routine.steps.forEachIndexed { i, step ->
                        Text("${i + 1}.  $step", color = Freakyyy.White.copy(alpha = 0.8f), fontSize = 13.sp, lineHeight = 20.sp)
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        GlassChip("Edit", icon = "✎") { editing = routine }
                        GlassChip("Delete", icon = "✕") {
                            store.delete(routine.id)
                            routines = store.all()
                        }
                    }
                }
            }
            item {
                Text(
                    "Steps that only open a settings screen leave the final switch to you, and sensitive steps always ask first. " +
                            "Use “wait 3 seconds” between steps to give an app time to open.",
                    color = Freakyyy.Ice.copy(alpha = 0.5f),
                    fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }
        }
    }
}

@Composable
private fun RoutineEditor(
    initial: FreakyyyRoutine,
    onCancel: () -> Unit,
    onSave: (FreakyyyRoutine) -> Unit
) {
    var name by remember { mutableStateOf(initial.name) }
    val steps = remember { mutableStateListOf(*initial.steps.toTypedArray()) }
    var error by remember { mutableStateOf<String?>(null) }

    BackHandler(onBack = onCancel)

    FreakyyyScreenFrame(
        title = if (initial.name.isEmpty()) "New routine" else "Edit routine",
        subtitle = "Write each step the way you'd say it to Freakyyy.",
        onBack = onCancel,
        action = {
            GlassChip("Save", icon = "✓", active = true) {
                val cleanSteps = steps.map { it.trim() }.filter { it.isNotEmpty() }
                val cleanName = name.trim()
                error = when {
                    cleanName.isEmpty() -> "Give the routine a name."
                    cleanSteps.isEmpty() -> "Add at least one step."
                    else -> cleanSteps.firstOrNull { FreakyyyIntentParser.parse(it) is FreakyyyAction.Unknown }
                        ?.let { "Freakyyy doesn't understand “$it”." }
                }
                if (error == null) onSave(initial.copy(name = cleanName, steps = cleanSteps))
            }
        }
    ) {
        SectionLabel("Name")
        Spacer(Modifier.height(8.dp))
        GlassInput(name, { name = it }, "e.g. Gym")
        Spacer(Modifier.height(18.dp))
        SectionLabel("Steps")
        Spacer(Modifier.height(8.dp))

        error?.let {
            Text(it, color = Freakyyy.Danger, fontSize = 13.sp)
            Spacer(Modifier.height(8.dp))
        }

        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            itemsIndexed(steps) { index, step ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("${index + 1}", color = Freakyyy.Cyan, modifier = Modifier.width(22.dp))
                    GlassInput(
                        value = step,
                        onChange = { steps[index] = it },
                        placeholder = "e.g. set volume to 20 percent",
                        modifier = Modifier.weight(1f)
                    )
                    TextButton(onClick = { if (steps.size > 1) steps.removeAt(index) else steps[0] = "" }) {
                        Text("✕", color = Freakyyy.Muted)
                    }
                }
            }
            item {
                GlassChip("Add step", icon = "+") { steps.add("") }
                Spacer(Modifier.height(12.dp))
                Text(
                    "Examples: open spotify · wait 3 seconds · set brightness to 30 percent · " +
                            "turn on do not disturb · vibrate mode · turn on flashlight · open calendar",
                    color = Freakyyy.Ice.copy(alpha = 0.5f),
                    fontSize = 12.sp
                )
            }
        }
    }
}

// =====================================================
// HISTORY
// =====================================================

@Composable
fun HistoryScreen(onBack: () -> Unit) {
    val store = FreakyyyAssistant.history
    var entries by remember { mutableStateOf(store.all()) }
    val format = remember { SimpleDateFormat("d MMM · h:mm a", Locale.getDefault()) }

    FreakyyyScreenFrame(
        title = "History",
        subtitle = "What you asked, what Freakyyy understood and what happened. Stored only on this phone.",
        onBack = onBack,
        action = {
            if (entries.isNotEmpty()) {
                GlassChip("Clear", icon = "✕") {
                    store.clear()
                    entries = emptyList()
                }
            }
        }
    ) {
        if (entries.isEmpty()) {
            Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                Text("No commands yet.", color = Freakyyy.Ice.copy(alpha = 0.6f))
            }
        } else {
            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(entries) { entry ->
                    GlassCard(Modifier.fillMaxWidth(), padding = 14.dp) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                entry.command,
                                color = Freakyyy.White,
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 14.sp,
                                modifier = Modifier.weight(1f)
                            )
                            Text(format.format(Date(entry.time)), color = Freakyyy.Muted, fontSize = 11.sp)
                        }
                        Spacer(Modifier.height(4.dp))
                        Text(entry.action, color = Freakyyy.Cyan.copy(alpha = 0.8f), fontSize = 11.sp, letterSpacing = 0.5.sp)
                        Spacer(Modifier.height(6.dp))
                        Text(
                            Freakyyy.outcomeLabel(entry.outcome),
                            color = Freakyyy.outcomeColor(entry.outcome),
                            fontSize = 10.sp,
                            letterSpacing = 1.2.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                        Text(entry.result, color = Freakyyy.White.copy(alpha = 0.75f), fontSize = 13.sp)
                    }
                }
            }
        }
    }
}

// =====================================================
// PERMISSION CENTER
// =====================================================

@Composable
fun PermissionsScreen(resumeTick: Int, onBack: () -> Unit) {
    val context = LocalContext.current
    var refresh by remember { mutableIntStateOf(0) }

    val runtimeLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { refresh++ }

    fun granted(permission: String) =
        ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

    // Re-read every time the user comes back from a system settings page.
    val tick = resumeTick + refresh
    val mic = remember(tick) { granted(Manifest.permission.RECORD_AUDIO) }
    val bluetooth = remember(tick) {
        Build.VERSION.SDK_INT < Build.VERSION_CODES.S || granted(Manifest.permission.BLUETOOTH_CONNECT)
    }
    val writeSettings = remember(tick) { FreakyyyAssistant.device.canWriteSettings() }
    val dnd = remember(tick) { FreakyyyAssistant.device.hasDndAccess() }
    val listener = remember(tick) { FreakyyyNotificationListener.isEnabled(context) }
    val accessibility = remember(tick) { FreakyyyAccessibilityService.isRunning }
    val localNetwork = remember(tick) { Build.VERSION.SDK_INT < 37 || granted(Manifest.permission.ACCESS_LOCAL_NETWORK) }
    val notificationsOk = remember(tick) { Build.VERSION.SDK_INT < 33 || granted(Manifest.permission.POST_NOTIFICATIONS) }
    val overlay = remember(tick) { android.provider.Settings.canDrawOverlays(context) }

    FreakyyyScreenFrame(
        title = "Permissions",
        subtitle = "Freakyyy asks only for what a feature needs. Optional helpers stay off until you turn them on.",
        onBack = onBack
    ) {
        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item { SectionLabel("Core") }
            item {
                PermissionCard(
                    title = "Microphone",
                    purpose = "Hear your voice commands. Audio goes to Android's speech recognizer only while the mic button is active.",
                    granted = mic,
                    action = if (mic) null else "Allow" to { runtimeLauncher.launch(Manifest.permission.RECORD_AUDIO) }
                )
            }
            item {
                PermissionCard(
                    title = "Modify system settings",
                    purpose = "Set screen brightness when you ask (“set brightness to 40 percent”).",
                    granted = writeSettings,
                    action = (if (writeSettings) "Manage" else "Allow") to { FreakyyyAssistant.openWriteSettingsAccess() }
                )
            }
            item {
                PermissionCard(
                    title = "Do Not Disturb access",
                    purpose = "Turn Do Not Disturb on or off and switch to silent mode.",
                    granted = dnd,
                    action = (if (dnd) "Manage" else "Allow") to { FreakyyyAssistant.openDndAccess() }
                )
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                item {
                    PermissionCard(
                        title = "Nearby devices",
                        purpose = "Ask Android to turn Bluetooth on (Android shows its own confirmation).",
                        granted = bluetooth,
                        action = if (bluetooth) null else "Allow" to { runtimeLauncher.launch(Manifest.permission.BLUETOOTH_CONNECT) }
                    )
                }
            }

            if (Build.VERSION.SDK_INT >= 37) {
                item {
                    PermissionCard(
                        title = "Local network",
                        purpose = "Reach your paired laptop over Wi-Fi with Freakyyy Link. Freakyyy never contacts other devices on your network.",
                        granted = localNetwork,
                        action = if (localNetwork) null else "Allow" to { runtimeLauncher.launch(Manifest.permission.ACCESS_LOCAL_NETWORK) }
                    )
                }
            }
            if (Build.VERSION.SDK_INT >= 33) {
                item {
                    PermissionCard(
                        title = "Notifications",
                        purpose = "Show the Freakyyy Link status, files received from the laptop, and tap-to-open requests.",
                        granted = notificationsOk,
                        action = if (notificationsOk) null else "Allow" to { runtimeLauncher.launch(Manifest.permission.POST_NOTIFICATIONS) }
                    )
                }
            }

            item { Spacer(Modifier.height(4.dp)); SectionLabel("Optional helpers") }
            item {
                PermissionCard(
                    title = "Display over other apps",
                    purpose = "Lets requests from your laptop (\"open WhatsApp on my phone\") open apps directly even while Freakyyy is in the background. " +
                            "Without it, Freakyyy shows a tap-to-open notification instead.",
                    granted = overlay,
                    optional = true,
                    action = (if (overlay) "Manage" else "Turn on") to {
                        context.startActivity(android.content.Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            android.net.Uri.parse("package:${context.packageName}")).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                    }
                )
            }
            item {
                PermissionCard(
                    title = "Notification access",
                    purpose = "Count notifications per app and clear them on request. Freakyyy never reads titles or message content.",
                    granted = listener,
                    optional = true,
                    action = (if (listener) "Turn off" else "Turn on") to { FreakyyyAssistant.openNotificationAccess() }
                )
            }
            item {
                PermissionCard(
                    title = "Accessibility helper",
                    purpose = "Go back, go home, recent apps, open notifications or quick settings, lock screen, screenshots, " +
                            "scrolling and tapping a named button during routines. It acts only on your commands, " +
                            "never reads passwords, stores nothing, and asks before tapping payment, send or delete buttons.",
                    granted = accessibility,
                    optional = true,
                    action = if (accessibility) {
                        "Turn off" to {
                            FreakyyyAccessibilityService.disable()
                            refresh++
                        }
                    } else {
                        "Turn on" to { FreakyyyAssistant.openAccessibilitySettings() }
                    }
                )
            }
            item {
                Text(
                    "Not requested: location, contacts, SMS, call logs, usage access, root. Network access is used only for the paired laptop. " +
                            "Wi-Fi, mobile data, dark theme and Bluetooth-off can only be switched by you on Android's own screens — Freakyyy opens them for you.",
                    color = Freakyyy.Ice.copy(alpha = 0.5f),
                    fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }
        }
    }
}

@Composable
private fun PermissionCard(
    title: String,
    purpose: String,
    granted: Boolean,
    optional: Boolean = false,
    action: Pair<String, () -> Unit>?
) {
    GlassCard(Modifier.fillMaxWidth(), highlighted = granted) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, color = Freakyyy.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            StatusPill(
                when {
                    granted -> "ON"
                    optional -> "OFF · OPTIONAL"
                    else -> "NOT GRANTED"
                },
                when {
                    granted -> Freakyyy.Success
                    optional -> Freakyyy.Muted
                    else -> Freakyyy.Warning
                }
            )
        }
        Spacer(Modifier.height(8.dp))
        Text(purpose, color = Freakyyy.Ice.copy(alpha = 0.75f), fontSize = 13.sp, lineHeight = 19.sp)
        action?.let { (label, onClick) ->
            Spacer(Modifier.height(12.dp))
            GlassChip(label, active = !granted, onClick = onClick)
        }
    }
}

// =====================================================
// VOICE
// =====================================================

@Composable
fun VoiceScreen(onBack: () -> Unit) {
    val status by FreakyyyVoiceEngine.status.collectAsState()
    val context = LocalContext.current

    FreakyyyScreenFrame(
        title = "Voice",
        subtitle = "Freakyyy speaks with Kokoro, entirely on this phone.",
        onBack = onBack
    ) {
        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                GlassCard(Modifier.fillMaxWidth(), highlighted = status.state == FreakyyyVoiceEngine.State.READY) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Engine", color = Freakyyy.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        StatusPill(
                            status.state.name.replace('_', ' '),
                            when (status.state) {
                                FreakyyyVoiceEngine.State.READY, FreakyyyVoiceEngine.State.SPEAKING -> Freakyyy.Success
                                FreakyyyVoiceEngine.State.FAILED -> Freakyyy.Danger
                                else -> Freakyyy.Warning
                            }
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Text(status.message, color = Freakyyy.Ice.copy(alpha = 0.8f), fontSize = 13.sp)
                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        GlassChip("Test voice", icon = "▶", active = true) {
                            FreakyyyAssistant.speak("Good morning. Freakyyy is online, and all systems are ready.")
                        }
                        GlassChip("Stop", icon = "■") { FreakyyyAssistant.stopSpeaking() }
                        if (status.state == FreakyyyVoiceEngine.State.FAILED) {
                            GlassChip("Retry", icon = "↻") { FreakyyyVoiceEngine.initialize(context) }
                        }
                    }
                }
            }
            item {
                GlassCard(Modifier.fillMaxWidth()) {
                    SectionLabel("Voice")
                    Spacer(Modifier.height(10.dp))
                    VoiceRow("Model", "Kokoro-82M · int8 (LiteRT-LM bundle)")
                    VoiceRow("Runtime", "MediaPipe Text-to-Speech · CPU (XNNPACK)")
                    VoiceRow("Voice", FreakyyyVoiceEngine.VOICE_ID)
                    VoiceRow("Speed", "${FreakyyyVoiceEngine.SPEAKING_RATE}×")
                    VoiceRow("Output", "24 kHz mono, streamed")
                }
            }
            item {
                GlassCard(Modifier.fillMaxWidth()) {
                    SectionLabel("Sound profile")
                    Spacer(Modifier.height(10.dp))
                    VoiceRow("High-pass", "80 Hz")
                    VoiceRow("EQ 1", "180 Hz · Q 1 · −2 dB")
                    VoiceRow("EQ 2", "3 kHz · Q 1 · +2 dB")
                    VoiceRow("Compressor", "thr 0.08 · 2:1 · 15/120 ms · makeup 1.5")
                    VoiceRow("Loudness", "−16 LUFS · TP −1.5 dB · LRA 7")
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "Matches the FFmpeg chain behind freakyyy-morning-v5.wav, processed live on-device.",
                        color = Freakyyy.Ice.copy(alpha = 0.5f),
                        fontSize = 12.sp
                    )
                }
            }
        }
    }
}

@Composable
private fun VoiceRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(label, color = Freakyyy.Muted, fontSize = 13.sp, modifier = Modifier.width(100.dp))
        Text(value, color = Freakyyy.White, fontSize = 13.sp)
    }
}

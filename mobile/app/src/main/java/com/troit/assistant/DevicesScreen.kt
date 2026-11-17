
package com.troit.assistant

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import com.troit.assistant.link.FreakyyyLink
import com.troit.assistant.link.FreakyyyLinkService
import com.troit.assistant.ui.Freakyyy
import com.troit.assistant.ui.FreakyyyScreenFrame
import com.troit.assistant.ui.GlassCard
import com.troit.assistant.ui.GlassChip
import com.troit.assistant.ui.SectionLabel
import com.troit.assistant.ui.StatusPill
import com.troit.assistant.ui.glass

/** Permissions Freakyyy Link needs before it can reach the laptop. */
fun linkPermissions(): Array<String> = buildList {
    if (Build.VERSION.SDK_INT >= 37) add(Manifest.permission.ACCESS_LOCAL_NETWORK)
    if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
}.toTypedArray()

@Composable
fun DevicesScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    val status by FreakyyyLink.status.collectAsState()
    var link by remember { mutableStateOf("") }
    var clipIn by remember { mutableStateOf(FreakyyyLink.store.clipboardAcceptFromLaptop) }
    var clipOut by remember { mutableStateOf(FreakyyyLink.store.clipboardShareToLaptop) }
    var pendingLink by remember { mutableStateOf<String?>(null) }

    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
        val localOk = Build.VERSION.SDK_INT < 37 || result[Manifest.permission.ACCESS_LOCAL_NETWORK] != false
        pendingLink?.let { if (localOk) FreakyyyLink.startPairing(it) }
        pendingLink = null
        if (localOk && FreakyyyLink.isPaired) FreakyyyLinkService.startIfWanted(context)
    }

    fun withPermissions(then: () -> Unit) {
        val missing = linkPermissions().filter {
            ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) then() else permissionLauncher.launch(missing.toTypedArray())
    }

    fun pair(uri: String) {
        pendingLink = uri
        withPermissions {
            pendingLink = null
            FreakyyyLink.startPairing(uri)
        }
    }

    val scanner = rememberLauncherForActivityResult(ScanContract()) { r ->
        r.contents?.let { if (it.startsWith("freakyyylink://")) pair(it) else FreakyyyAssistant.say("That QR code isn't a Freakyyy pairing code.", Outcome.FAILED) }
    }

    FreakyyyScreenFrame(
        title = "Devices",
        subtitle = "Freakyyy Link connects this phone and your laptop over your Wi-Fi — encrypted, paired, no cloud.",
        onBack = onBack
    ) {
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                GlassCard(Modifier.fillMaxWidth(), highlighted = status.state == FreakyyyLink.State.CONNECTED) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(status.laptopName ?: "No laptop", color = Freakyyy.White, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                            Text("💻 Freakyyy Desktop", color = Freakyyy.Muted, fontSize = 12.sp)
                        }
                        StatusPill(
                            status.state.name.replace('_', ' '),
                            when (status.state) {
                                FreakyyyLink.State.CONNECTED -> Freakyyy.Success
                                FreakyyyLink.State.CONNECTING, FreakyyyLink.State.PAIRING -> Freakyyy.Warning
                                FreakyyyLink.State.OFFLINE -> Freakyyy.Danger
                                FreakyyyLink.State.NOT_PAIRED -> Freakyyy.Muted
                            }
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Text(status.message, color = Freakyyy.Ice.copy(alpha = 0.8f), fontSize = 13.sp)
                    status.laptopStats?.let { s ->
                        Spacer(Modifier.height(8.dp))
                        Text(
                            buildString {
                                if (s.has("battery") && !s.isNull("battery")) append("Battery ${s.optInt("battery")}%  ·  ")
                                append("CPU ${s.optDouble("cpu").toInt()}%  ·  RAM ${s.optDouble("mem").toInt()}%")
                            },
                            color = Freakyyy.Cyan, fontSize = 12.sp
                        )
                    }
                    status.transfer?.let {
                        Spacer(Modifier.height(6.dp))
                        Text(it, color = Freakyyy.Cyan, fontSize = 12.sp)
                    }
                }
            }

            when (status.state) {
                FreakyyyLink.State.PAIRING -> item {
                    GlassCard(Modifier.fillMaxWidth(), highlighted = true) {
                        SectionLabel("Confirm pairing")
                        Spacer(Modifier.height(10.dp))
                        Text(
                            status.pairingCode?.chunked(3)?.joinToString(" ") ?: "",
                            color = Freakyyy.Cyan, fontSize = 34.sp, fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace, modifier = Modifier.align(Alignment.CenterHorizontally)
                        )
                        Spacer(Modifier.height(8.dp))
                        Text("Pair only if your laptop shows exactly this code. Then approve it on the laptop too.",
                            color = Freakyyy.Ice.copy(alpha = 0.8f), fontSize = 13.sp)
                        Spacer(Modifier.height(12.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            GlassChip("Codes match — pair", icon = "✓", active = true) { FreakyyyLink.confirmPairing(true) }
                            GlassChip("Cancel", icon = "✕") { FreakyyyLink.confirmPairing(false) }
                        }
                    }
                }

                FreakyyyLink.State.NOT_PAIRED -> item {
                    GlassCard(Modifier.fillMaxWidth()) {
                        SectionLabel("Pair your laptop")
                        Spacer(Modifier.height(8.dp))
                        Text("On the laptop: Freakyyy → Add device. Then scan the code it shows.",
                            color = Freakyyy.Ice.copy(alpha = 0.8f), fontSize = 13.sp)
                        Spacer(Modifier.height(12.dp))
                        GlassChip("Scan pairing code", icon = "▣", active = true) {
                            scanner.launch(ScanOptions().setPrompt("Scan the code on your laptop")
                                .setDesiredBarcodeFormats(ScanOptions.QR_CODE).setBeepEnabled(false).setOrientationLocked(false))
                        }
                        Spacer(Modifier.height(14.dp))
                        Text("No camera? Paste the pairing link:", color = Freakyyy.Muted, fontSize = 12.sp)
                        Spacer(Modifier.height(6.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.weight(1f).glass(RoundedCornerShape(14.dp)).padding(12.dp)) {
                                if (link.isEmpty()) Text("freakyyylink://pair?d=…", color = Color.Gray, fontSize = 13.sp)
                                BasicTextField(link, { link = it.trim() }, singleLine = true,
                                    textStyle = TextStyle(color = Freakyyy.White, fontSize = 13.sp), cursorBrush = SolidColor(Freakyyy.Cyan),
                                    modifier = Modifier.fillMaxWidth())
                            }
                            Spacer(Modifier.width(8.dp))
                            GlassChip("Pair", active = link.startsWith("freakyyylink://")) { if (link.isNotBlank()) pair(link) }
                        }
                    }
                }

                else -> item {
                    GlassCard(Modifier.fillMaxWidth()) {
                        SectionLabel("Laptop controls")
                        Spacer(Modifier.height(10.dp))
                        val chips = listOf(
                            "Laptop status" to "laptop status",
                            "Find my laptop" to "find my laptop",
                            "Send clipboard" to "send clipboard to laptop",
                            "Get laptop clipboard" to "get laptop clipboard",
                            "Lock laptop" to "lock my laptop",
                            "Laptop screenshot" to "take a screenshot on my laptop"
                        )
                        chips.chunked(2).forEach { row ->
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(bottom = 8.dp)) {
                                row.forEach { (label, cmd) -> GlassChip(label) { FreakyyyAssistant.submit(cmd) } }
                            }
                        }
                        Text("Tip: say “open VS Code on my laptop”, or share any file or link to Freakyyy to send it to the laptop.",
                            color = Freakyyy.Ice.copy(alpha = 0.55f), fontSize = 12.sp)
                        Spacer(Modifier.height(10.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (status.state == FreakyyyLink.State.CONNECTED) {
                                GlassChip("Disconnect", icon = "■") { FreakyyyLinkService.stop(context) }
                            } else {
                                GlassChip("Connect", icon = "⟳", active = true) {
                                    FreakyyyLinkService.linkPrefs(context).edit().putBoolean("enabled", true).apply()
                                    withPermissions { FreakyyyLinkService.startIfWanted(context) }
                                }
                            }
                            GlassChip("Remove laptop", icon = "✕") {
                                FreakyyyLinkService.stop(context)
                                FreakyyyLink.unpair()
                            }
                        }
                    }
                }
            }

            item {
                GlassCard(Modifier.fillMaxWidth()) {
                    SectionLabel("Clipboard sharing")
                    Spacer(Modifier.height(8.dp))
                    ToggleRow("Accept text the laptop sends", clipIn) {
                        clipIn = it
                        FreakyyyLink.store.clipboardAcceptFromLaptop = it
                    }
                    ToggleRow("Let the laptop read this phone's clipboard when I ask (only while Freakyyy is open)", clipOut) {
                        clipOut = it
                        FreakyyyLink.store.clipboardShareToLaptop = it
                    }
                }
            }
            item {
                Text(
                    "Security: the pairing code works once, the connection is TLS-pinned to your laptop's certificate, and each " +
                            "side proves it holds the device key. The laptop can only ask for things Freakyyy's own commands allow — never a shell.",
                    color = Freakyyy.Ice.copy(alpha = 0.5f), fontSize = 12.sp, modifier = Modifier.padding(vertical = 6.dp)
                )
            }
        }
    }
}

@Composable
private fun ToggleRow(label: String, value: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = Freakyyy.White, fontSize = 13.sp, modifier = Modifier.weight(1f))
        Spacer(Modifier.width(10.dp))
        GlassChip(if (value) "On" else "Off", active = value) { onChange(!value) }
    }
}

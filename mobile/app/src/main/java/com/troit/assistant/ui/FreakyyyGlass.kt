
package com.troit.assistant.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.troit.assistant.Outcome

object Freakyyy {
    val Black = Color(0xFF02040A)
    val Navy = Color(0xFF07152C)
    val DeepNavy = Color(0xFF040B19)
    val Blue = Color(0xFF238CFF)
    val Electric = Color(0xFF3D7BFF)
    val Cyan = Color(0xFF6DDCFF)
    val Ice = Color(0xFFBDEBFF)
    val White = Color(0xFFF8FAFF)
    val Muted = Color(0xFF8DA3C2)
    val Success = Color(0xFF65DDAA)
    val Warning = Color(0xFFFFC46B)
    val Danger = Color(0xFFFF7A8A)

    val GlassFill = Brush.verticalGradient(
        listOf(
            Color.White.copy(alpha = 0.09f),
            Color(0xFF278BFF).copy(alpha = 0.08f),
            Color.White.copy(alpha = 0.04f)
        )
    )

    val GlassEdge = Brush.verticalGradient(
        listOf(
            Color.White.copy(alpha = 0.32f),
            Blue.copy(alpha = 0.18f),
            Ice.copy(alpha = 0.06f)
        )
    )

    fun outcomeColor(outcome: Outcome?): Color = when (outcome) {
        Outcome.DONE -> Success
        Outcome.OPENED -> Cyan
        Outcome.INFO, null -> Ice
        Outcome.NEEDS_PERMISSION, Outcome.NEEDS_CONFIRMATION -> Warning
        Outcome.NOT_SUPPORTED, Outcome.FAILED -> Danger
        Outcome.DEVICE_OFFLINE -> Warning
    }

    fun outcomeLabel(outcome: Outcome?): String = when (outcome) {
        Outcome.DONE -> "DONE"
        Outcome.OPENED -> "OPENED · YOUR TURN"
        Outcome.INFO, null -> "FREAKYYY"
        Outcome.NEEDS_PERMISSION -> "NEEDS PERMISSION"
        Outcome.NEEDS_CONFIRMATION -> "CONFIRM"
        Outcome.NOT_SUPPORTED -> "NOT ALLOWED BY ANDROID"
        Outcome.FAILED -> "COULDN'T DO IT"
        Outcome.DEVICE_OFFLINE -> "LAPTOP OFFLINE"
    }
}

/** Translucent glass surface with a thin light edge. */
fun Modifier.glass(
    shape: Shape = RoundedCornerShape(24.dp),
    highlighted: Boolean = false
): Modifier = this
    .clip(shape)
    .background(Freakyyy.GlassFill)
    .border(
        BorderStroke(
            1.dp,
            if (highlighted) Brush.verticalGradient(listOf(Freakyyy.Cyan, Freakyyy.Blue.copy(alpha = 0.4f)))
            else Freakyyy.GlassEdge
        ),
        shape
    )

/** Deep navy backdrop with two soft, static light pools. */
@Composable
fun FreakyyyBackground(content: @Composable BoxScope.() -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(Color(0xFF020611), Freakyyy.Black, Color(0xFF030D20), Color(0xFF071D3D))
                )
            )
    ) {
        // Radial gradients instead of blur: soft edges on every API level, no offscreen pass.
        Box(
            Modifier
                .offset(x = (-140).dp, y = 0.dp)
                .size(420.dp)
                .background(
                    Brush.radialGradient(listOf(Freakyyy.Blue.copy(alpha = 0.20f), Color.Transparent))
                )
        )
        Box(
            Modifier
                .align(Alignment.BottomEnd)
                .offset(x = 150.dp, y = (-60).dp)
                .size(440.dp)
                .background(
                    Brush.radialGradient(listOf(Freakyyy.Cyan.copy(alpha = 0.11f), Color.Transparent))
                )
        )
        content()
    }
}

@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    highlighted: Boolean = false,
    onClick: (() -> Unit)? = null,
    padding: Dp = 16.dp,
    content: @Composable ColumnScope.() -> Unit
) {
    Column(
        modifier = modifier
            .glass(highlighted = highlighted)
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(padding),
        content = content
    )
}

@Composable
fun GlassChip(
    text: String,
    modifier: Modifier = Modifier,
    icon: String? = null,
    active: Boolean = false,
    onClick: () -> Unit
) {
    Row(
        modifier = modifier
            .glass(CircleShape, highlighted = active)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (icon != null) {
            Text(icon, color = Freakyyy.Cyan, fontSize = 14.sp)
            Spacer(Modifier.width(7.dp))
        }
        Text(text, color = Freakyyy.White, fontSize = 13.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(
        text.uppercase(),
        modifier = modifier,
        color = Freakyyy.Ice.copy(alpha = 0.7f),
        fontSize = 11.sp,
        letterSpacing = 2.sp,
        fontWeight = FontWeight.Medium
    )
}

@Composable
fun StatusPill(text: String, color: Color, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .glass(CircleShape)
            .padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(7.dp).background(color, CircleShape))
        Spacer(Modifier.width(6.dp))
        Text(text, color = Freakyyy.Ice, fontSize = 10.sp, letterSpacing = 1.sp)
    }
}

/** Standard secondary screen: back button, title, subtitle, content. */
@Composable
fun FreakyyyScreenFrame(
    title: String,
    subtitle: String,
    onBack: () -> Unit,
    action: (@Composable () -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit
) {
    FreakyyyBackground {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .padding(horizontal = 20.dp, vertical = 12.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                TextButton(onClick = onBack) {
                    Text("← BACK", color = Freakyyy.Ice, letterSpacing = 1.sp)
                }
                action?.invoke()
            }
            Spacer(Modifier.height(8.dp))
            Text(title, color = Freakyyy.White, fontSize = 30.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text(subtitle, color = Freakyyy.Ice.copy(alpha = 0.7f), fontSize = 14.sp)
            Spacer(Modifier.height(20.dp))
            content()
        }
    }
}

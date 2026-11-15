
package com.troit.assistant

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.troit.assistant.ui.theme.TroitTheme

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

            Text(
                "AI ASSISTANT",
                color = Ice.copy(alpha = 0.65f),
                fontSize = 10.sp,
                letterSpacing = 2.sp
            )
        }

        Spacer(Modifier.weight(0.7f))

        // LIQUID GLASS AI ORB
        Box(
            modifier = Modifier
                .size(270.dp),
            contentAlignment = Alignment.Center
        ) {

            Canvas(
                modifier = Modifier
                    .fillMaxSize()
                    .rotate(rotation)
            ) {
                val center = this.center
                val radius = size.minDimension * 0.43f

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

        // GLASS INPUT CAPSULE
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
                .padding(horizontal = 25.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {

            Text(
                "Ask anything...",
                modifier = Modifier.weight(1f),
                color = White.copy(alpha = 0.85f),
                fontSize = 17.sp
            )

            // WAVEFORM PLACEHOLDER
            Row(
                horizontalArrangement = Arrangement.spacedBy(3.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                listOf(12, 23, 34, 19, 28, 13).forEachIndexed { index, height ->
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


package com.troit.assistant

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.math.tan

/**
 * Freakyyy's voice finishing chain, a native port of the FFmpeg filter graph
 * used to produce freakyyy-morning-v5.wav:
 *
 *   highpass=f=80,
 *   equalizer=f=180:width_type=q:w=1:g=-2,
 *   equalizer=f=3000:width_type=q:w=1:g=2,
 *   acompressor=threshold=0.08:ratio=2:attack=15:release=120:makeup=1.5,
 *   loudnorm=I=-16:TP=-1.5:LRA=7
 *
 * Everything runs in-process on float PCM, so no FFmpeg process is started.
 * Filter state is kept between chunks of one utterance so streamed chunks
 * join seamlessly; [reset] is called at the start of every utterance.
 */
class FreakyyyAudioProcessor(private val sampleRate: Int) {

    private val highPass = Biquad.highPass(sampleRate, 80.0, 0.707)
    private val lowMidCut = Biquad.peaking(sampleRate, 180.0, 1.0, -2.0)
    private val presenceBoost = Biquad.peaking(sampleRate, 3000.0, 1.0, 2.0)

    private val compressor = Compressor(
        sampleRate = sampleRate,
        threshold = 0.08,
        ratio = 2.0,
        attackMs = 15.0,
        releaseMs = 120.0,
        makeup = 1.5
    )

    private val loudness = LoudnessNormalizer(
        sampleRate = sampleRate,
        targetLufs = -16.0,
        truePeakDb = -1.5
    )

    fun reset() {
        highPass.reset()
        lowMidCut.reset()
        presenceBoost.reset()
        compressor.reset()
        loudness.resetUtterance()
    }

    /** Processes one chunk in place and returns it. */
    fun process(samples: FloatArray): FloatArray {
        for (i in samples.indices) {
            var x = samples[i].toDouble()
            x = highPass.process(x)
            x = lowMidCut.process(x)
            x = presenceBoost.process(x)
            x = compressor.process(x)
            samples[i] = x.toFloat()
        }
        loudness.process(samples)
        return samples
    }

    // =====================================================
    // RBJ biquad (same coefficients FFmpeg's biquads use)
    // =====================================================

    private class Biquad(
        private val b0: Double,
        private val b1: Double,
        private val b2: Double,
        private val a1: Double,
        private val a2: Double
    ) {
        private var z1 = 0.0
        private var z2 = 0.0

        fun process(x: Double): Double {
            val y = b0 * x + z1
            z1 = b1 * x - a1 * y + z2
            z2 = b2 * x - a2 * y
            return y
        }

        fun reset() {
            z1 = 0.0
            z2 = 0.0
        }

        companion object {

            fun highPass(sampleRate: Int, frequency: Double, q: Double): Biquad {
                val w0 = 2.0 * PI * frequency / sampleRate
                val alpha = sin(w0) / (2.0 * q)
                val cosW = cos(w0)
                val a0 = 1.0 + alpha
                return Biquad(
                    b0 = (1.0 + cosW) / 2.0 / a0,
                    b1 = -(1.0 + cosW) / a0,
                    b2 = (1.0 + cosW) / 2.0 / a0,
                    a1 = -2.0 * cosW / a0,
                    a2 = (1.0 - alpha) / a0
                )
            }

            fun peaking(
                sampleRate: Int,
                frequency: Double,
                q: Double,
                gainDb: Double
            ): Biquad {
                val a = 10.0.pow(gainDb / 40.0)
                val w0 = 2.0 * PI * frequency / sampleRate
                val alpha = sin(w0) / (2.0 * q)
                val cosW = cos(w0)
                val a0 = 1.0 + alpha / a
                return Biquad(
                    b0 = (1.0 + alpha * a) / a0,
                    b1 = -2.0 * cosW / a0,
                    b2 = (1.0 - alpha * a) / a0,
                    a1 = -2.0 * cosW / a0,
                    a2 = (1.0 - alpha / a) / a0
                )
            }

            fun of(b0: Double, b1: Double, b2: Double, a1: Double, a2: Double) =
                Biquad(b0, b1, b2, a1, a2)
        }
    }

    // =====================================================
    // acompressor port (RMS detection, 2.828 soft knee)
    // =====================================================

    private class Compressor(
        sampleRate: Int,
        threshold: Double,
        private val ratio: Double,
        attackMs: Double,
        releaseMs: Double,
        private val makeup: Double,
        knee: Double = 2.82843
    ) {
        private val attackCoeff = min(1.0, 1.0 / (attackMs * sampleRate / 4000.0))
        private val releaseCoeff = min(1.0, 1.0 / (releaseMs * sampleRate / 4000.0))

        private val thres = ln(threshold)
        private val kneeOn = knee > 1.0
        private val linKneeStart = threshold / sqrt(knee)
        private val adjKneeStart = linKneeStart * linKneeStart
        private val kneeStart = ln(linKneeStart)
        private val kneeStop = ln(threshold * sqrt(knee))
        private val compressedKneeStop = (kneeStop - thres) / ratio + thres

        private var linSlope = 0.0

        fun reset() {
            linSlope = 0.0
        }

        fun process(x: Double): Double {
            val detector = x * x
            val coeff = if (detector > linSlope) attackCoeff else releaseCoeff
            linSlope += (detector - linSlope) * coeff

            var gain = 1.0
            if (linSlope > 0.0 && linSlope > adjKneeStart) {
                gain = outputGain(linSlope)
            }
            return x * gain * makeup
        }

        private fun outputGain(lin: Double): Double {
            val slope = ln(lin) * 0.5
            var gain = (slope - thres) / ratio + thres
            val delta = 1.0 / ratio
            if (kneeOn && slope < kneeStop) {
                gain = hermite(slope, kneeStart, kneeStop, kneeStart, compressedKneeStop, 1.0, delta)
            }
            return exp(gain - slope)
        }

        private fun hermite(
            x: Double,
            x0: Double,
            x1: Double,
            p0: Double,
            p1: Double,
            m0In: Double,
            m1In: Double
        ): Double {
            val width = x1 - x0
            val t = (x - x0) / width
            val m0 = m0In * width
            val m1 = m1In * width
            val t2 = t * t
            val t3 = t2 * t
            val ct2 = -3 * p0 - 2 * m0 + 3 * p1 - m1
            val ct3 = 2 * p0 + m0 - 2 * p1 + m1
            return ct3 * t3 + ct2 * t2 + m0 * t + p0
        }
    }

    // =====================================================
    // EBU R128 loudness normalisation + true-peak ceiling
    // =====================================================

    /**
     * Streaming stand-in for FFmpeg's loudnorm. Each chunk is measured with
     * BS.1770 K-weighting and gated 400 ms blocks *before* it is played, so
     * the gain is effectively look-ahead over the whole sentence. The gain
     * glides between chunks (no pumping) and remembers the level of previous
     * utterances so short phrases start at the right loudness. A look-ahead
     * limiter enforces the -1.5 dBTP ceiling (with margin for inter-sample
     * peaks). The compressor upstream already holds the range well inside
     * LRA 7, so no further range compression is applied.
     */
    private class LoudnessNormalizer(
        private val sampleRate: Int,
        private val targetLufs: Double,
        truePeakDb: Double
    ) {
        // Sample-peak ceiling with 0.3 dB of inter-sample headroom.
        private val ceiling = 10.0.pow((truePeakDb - 0.3) / 20.0)

        private val shelf: Biquad
        private val rlb: Biquad

        init {
            // BS.1770-4 pre-filter, derived for the actual sample rate.
            val g = 3.999843853973347
            val qs = 0.7071752369554196
            val fs = 1681.974450955533
            var k = tan(PI * fs / sampleRate)
            val vh = 10.0.pow(g / 20.0)
            val vb = vh.pow(0.4996667741545416)
            var a0 = 1.0 + k / qs + k * k
            shelf = Biquad.of(
                (vh + vb * k / qs + k * k) / a0,
                2.0 * (k * k - vh) / a0,
                (vh - vb * k / qs + k * k) / a0,
                2.0 * (k * k - 1.0) / a0,
                (1.0 - k / qs + k * k) / a0
            )

            val qh = 0.5003270373238773
            val fh = 38.13547087602444
            k = tan(PI * fh / sampleRate)
            a0 = 1.0 + k / qh + k * k
            rlb = Biquad.of(
                1.0, -2.0, 1.0,
                2.0 * (k * k - 1.0) / a0,
                (1.0 - k / qh + k * k) / a0
            )
        }

        private val blockSize = (sampleRate * 0.4).toInt()
        private val hopSize = (sampleRate * 0.1).toInt()

        // Loudness memory across utterances (energy domain).
        private var historyEnergy = 0.0
        private var historyWeight = 0.0

        private var currentGain = Double.NaN
        private val minGainDb = -12.0
        private val maxGainDb = 18.0

        // Limiter state carried across chunks.
        private val lookahead = max(1, sampleRate / 200) // 5 ms
        private val releaseCoeff = 1.0 - exp(-1.0 / (0.06 * sampleRate))
        private var limiterEnv = 1.0
        private val holdTail = DoubleArray(lookahead) { 1.0 }

        fun resetUtterance() {
            shelf.reset()
            rlb.reset()
            limiterEnv = 1.0
            holdTail.fill(1.0)
        }

        fun process(samples: FloatArray) {
            if (samples.isEmpty()) return

            val targetGain = gainFor(measure(samples))
            val startGain = if (currentGain.isNaN()) targetGain else currentGain

            // Glide to the new gain over ~150 ms (or the chunk, if shorter).
            val ramp = min(samples.size, (sampleRate * 0.15).toInt()).coerceAtLeast(1)
            for (i in samples.indices) {
                val g = if (i < ramp) {
                    startGain + (targetGain - startGain) * (i + 1) / ramp
                } else {
                    targetGain
                }
                samples[i] = (samples[i] * g).toFloat()
            }
            currentGain = targetGain

            limit(samples)
        }

        /** Returns the gated mean-square energy of the K-weighted chunk. */
        private fun measure(samples: FloatArray): Double {
            val weighted = DoubleArray(samples.size)
            for (i in samples.indices) {
                weighted[i] = rlb.process(shelf.process(samples[i].toDouble()))
            }

            val blocks = ArrayList<Double>()
            if (weighted.size < blockSize) {
                blocks += meanSquare(weighted, 0, weighted.size)
            } else {
                var start = 0
                while (start + blockSize <= weighted.size) {
                    blocks += meanSquare(weighted, start, blockSize)
                    start += hopSize
                }
            }

            // Absolute gate (-70 LUFS), then relative gate (-10 LU).
            val absGate = energyOf(-70.0)
            val passed = blocks.filter { it > absGate }
            if (passed.isEmpty()) return 0.0
            val relGate = passed.average() * 10.0.pow(-1.0)
            val gated = passed.filter { it > relGate }
            return if (gated.isEmpty()) passed.average() else gated.average()
        }

        private fun gainFor(chunkEnergy: Double): Double {
            if (chunkEnergy > 0.0) {
                // Weight the new chunk heavily; history only steadies it.
                historyEnergy = historyEnergy * 0.5 + chunkEnergy
                historyWeight = historyWeight * 0.5 + 1.0
            }
            if (historyWeight == 0.0) {
                return if (currentGain.isNaN()) 1.0 else currentGain
            }
            val measuredLufs = -0.691 + 10.0 * log10(historyEnergy / historyWeight)
            val gainDb = (targetLufs - measuredLufs).coerceIn(minGainDb, maxGainDb)
            return 10.0.pow(gainDb / 20.0)
        }

        private fun limit(samples: FloatArray) {
            val n = samples.size
            val required = DoubleArray(n)
            for (i in 0 until n) {
                val a = abs(samples[i].toDouble())
                required[i] = if (a > ceiling) ceiling / a else 1.0
            }

            // Forward minimum over the look-ahead window.
            val held = DoubleArray(n)
            val deque = ArrayDeque<Int>()
            var next = 0
            for (i in 0 until n) {
                val end = min(n - 1, i + lookahead)
                while (next <= end) {
                    while (deque.isNotEmpty() && required[deque.last()] >= required[next]) {
                        deque.removeLast()
                    }
                    deque.addLast(next)
                    next++
                }
                while (deque.first() < i) deque.removeFirst()
                held[i] = required[deque.first()]
            }

            // Box-smooth the held gain so it reaches the target before the peak.
            var sum = holdTail.sum()
            val window = ArrayDeque<Double>(lookahead + 1)
            holdTail.forEach { window.addLast(it) }
            for (i in 0 until n) {
                window.addLast(held[i])
                sum += held[i] - window.removeFirst()
                val smooth = sum / lookahead
                limiterEnv = if (smooth < limiterEnv) {
                    smooth
                } else {
                    limiterEnv + (smooth - limiterEnv) * releaseCoeff
                }
                // The clamp guarantees the ceiling even right after a chunk edge.
                samples[i] = (samples[i] * min(limiterEnv, required[i])).toFloat()
            }
            for (i in 0 until lookahead) {
                holdTail[i] = window.elementAt(i)
            }
        }

        private fun meanSquare(data: DoubleArray, start: Int, length: Int): Double {
            var acc = 0.0
            for (i in start until start + length) acc += data[i] * data[i]
            return acc / length
        }

        private fun energyOf(lufs: Double) = 10.0.pow((lufs + 0.691) / 10.0)
    }
}

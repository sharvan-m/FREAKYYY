
package com.troit.assistant

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.os.Process
import android.os.SystemClock
import android.util.Log
import android.util.LruCache
import com.google.mediapipe.tasks.audio.texttospeech.SynthesisOptions
import com.google.mediapipe.tasks.audio.texttospeech.TextToSpeech
import com.google.mediapipe.tasks.audio.texttospeech.TextToSpeechOptions
import com.google.mediapipe.tasks.audio.texttospeech.TtsStream
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File
import java.util.concurrent.Executors
import kotlin.coroutines.coroutineContext

/**
 * Freakyyy's voice: Kokoro-82M (int8 acoustic model) with the am_onyx voice,
 * run by the MediaPipe Text-to-Speech task from the bundled .litertlm file.
 *
 * - The model is loaded once per process and reused for every sentence.
 * - Inference runs on its own thread; playback on another, so the next
 *   chunk is synthesised while the current one plays.
 * - speak() replaces whatever is being said (like QUEUE_FLUSH).
 * - There is deliberately no fallback to Android's system TTS.
 */
object FreakyyyVoiceEngine {

    const val MODEL_ASSET = "kokoro_int8_fp16.litertlm"
    const val VOICE_ID = "am_onyx"
    const val SPEAKING_RATE = 1.08f

    private const val TAG = "FreakyyyVoice"
    private const val SAMPLE_RATE = 24_000
    private const val MAX_TEXT_LENGTH = 1_500
    private const val CACHEABLE_LENGTH = 60
    private const val WRITE_BLOCK = 2_048

    enum class State {
        NOT_STARTED,
        PREPARING,
        READY,
        SPEAKING,
        FAILED
    }

    data class Status(
        val state: State,
        val message: String
    )

    private val _status = MutableStateFlow(
        Status(State.NOT_STARTED, "Voice not started")
    )
    val status: StateFlow<Status> = _status.asStateFlow()

    private val inferenceDispatcher = Executors.newSingleThreadExecutor { runnable ->
        Thread({
            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
            runnable.run()
        }, "freakyyy-kokoro").apply { isDaemon = true }
    }.asCoroutineDispatcher()

    private val playbackDispatcher = Executors.newSingleThreadExecutor { runnable ->
        Thread({
            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
            runnable.run()
        }, "freakyyy-playback").apply { isDaemon = true }
    }.asCoroutineDispatcher()

    private val scope = CoroutineScope(SupervisorJob() + inferenceDispatcher)

    private lateinit var appContext: Context
    private var audioManager: AudioManager? = null
    private var focusRequest: AudioFocusRequest? = null

    // Touched only on the inference thread.
    private var tts: TextToSpeech? = null
    @Volatile private var track: AudioTrack? = null
    private val processor = FreakyyyAudioProcessor(SAMPLE_RATE)

    private val synthesisOptions = SynthesisOptions(VOICE_ID, null)

    @Volatile private var activeStream: TtsStream? = null
    @Volatile private var initJob: Job? = null
    @Volatile private var speakJob: Job? = null
    @Volatile private var lastText: String? = null
    @Volatile private var lastTextAt = 0L

    // Finished (processed) audio for short, frequently repeated phrases.
    private val phraseCache = object : LruCache<String, FloatArray>(4 * 1024 * 1024) {
        override fun sizeOf(key: String, value: FloatArray) = value.size * 4
    }

    private val warmPhrases = listOf(
        "Please say yes or no.",
        "Okay, I cancelled that action.",
        "I didn't understand that command."
    )

    // =====================================================
    // LIFECYCLE
    // =====================================================

    /** Starts loading the model in the background. Safe to call repeatedly. */
    @Synchronized
    fun initialize(context: Context) {
        if (!::appContext.isInitialized) {
            appContext = context.applicationContext
            audioManager = appContext.getSystemService(AudioManager::class.java)
        }

        val state = _status.value.state
        if (state == State.PREPARING || state == State.READY || state == State.SPEAKING) {
            return
        }

        _status.value = Status(State.PREPARING, "Preparing Freakyyy's voice…")

        initJob = scope.launch {
            try {
                val started = SystemClock.elapsedRealtime()
                val modelFile = installModel()

                val baseOptions = BaseOptions.builder()
                    .setModelAssetPath(modelFile.absolutePath)
                    // This bundle's vocoder is CPU-constrained; the int8
                    // acoustic model runs on XNNPACK.
                    .setDelegate(Delegate.CPU)
                    .build()

                val cacheDir = File(appContext.cacheDir, "kokoro").apply { mkdirs() }

                val options = TextToSpeechOptions(
                    baseOptions,
                    VOICE_ID,
                    null,
                    SPEAKING_RATE,
                    0,
                    cacheDir.absolutePath
                )

                tts = TextToSpeech.create(options)
                track = createTrack()

                Log.i(TAG, "Kokoro ready in ${SystemClock.elapsedRealtime() - started} ms")
                _status.value = Status(State.READY, "Voice ready")

                // Separate job: a first real request never waits on warm-up.
                scope.launch { warmUp() }

            } catch (t: Throwable) {
                Log.e(TAG, "Kokoro initialisation failed", t)
                releaseNative()
                _status.value = Status(
                    State.FAILED,
                    "Voice engine unavailable: ${t.message ?: t.javaClass.simpleName}"
                )
            }
        }
    }

    /** Releases the model and audio resources. */
    @Synchronized
    fun release() {
        stop()
        initJob?.cancel()
        scope.launch {
            releaseNative()
            phraseCache.evictAll()
            _status.value = Status(State.NOT_STARTED, "Voice not started")
        }
    }

    private fun releaseNative() {
        try { tts?.close() } catch (_: Throwable) {}
        try { track?.release() } catch (_: Throwable) {}
        tts = null
        track = null
    }

    // =====================================================
    // SPEAKING
    // =====================================================

    /** Speaks [message], replacing anything currently being said. */
    fun speak(message: String) {
        val text = message
            .replace(Regex("\\s+"), " ")
            .trim()
            .take(MAX_TEXT_LENGTH)

        if (text.isEmpty()) return

        // Drop accidental double-triggers of the same reply.
        val now = SystemClock.elapsedRealtime()
        if (text == lastText && now - lastTextAt < 700) return
        lastText = text
        lastTextAt = now

        if (::appContext.isInitialized && _status.value.state == State.FAILED) {
            // Give the engine another chance (e.g. after storage was freed).
            initialize(appContext)
        }

        stop()

        speakJob = scope.launch {
            // Queued behind initialisation if the model is still loading.
            initJob?.join()
            ensureActive()

            val engine = tts ?: return@launch
            val audioTrack = track ?: return@launch

            _status.value = Status(State.SPEAKING, "Speaking")
            try {
                val cached = phraseCache.get(text)
                if (cached != null) {
                    playClip(audioTrack, cached)
                } else {
                    synthesizeAndPlay(engine, audioTrack, text)
                }
            } catch (t: Throwable) {
                if (t !is kotlinx.coroutines.CancellationException) {
                    Log.e(TAG, "Speech failed", t)
                }
            } finally {
                activeStream = null
                abandonFocus()
                if (_status.value.state == State.SPEAKING) {
                    _status.value = Status(State.READY, "Voice ready")
                }
            }
        }
    }

    /** Stops current speech immediately. */
    fun stop() {
        speakJob?.cancel()
        try { activeStream?.cancel() } catch (_: Throwable) {}
        try {
            track?.let {
                it.pause()
                it.flush()
            }
        } catch (_: Throwable) {}
    }

    val isSpeaking: Boolean
        get() = _status.value.state == State.SPEAKING

    private suspend fun synthesizeAndPlay(
        engine: TextToSpeech,
        audioTrack: AudioTrack,
        text: String
    ) {
        processor.reset()

        val cacheable = text.length <= CACHEABLE_LENGTH
        val collected = if (cacheable) ArrayList<FloatArray>() else null

        coroutineScope {
            val chunks = Channel<FloatArray>(Channel.UNLIMITED)
            launch(playbackDispatcher) {
                playStream(audioTrack, chunks)
            }

            val stream = engine.openStream(text, synthesisOptions, true)
            activeStream = stream
            try {
                while (isActive) {
                    val chunk = stream.readNext() ?: break
                    val samples = chunk.samples
                    if (samples.isNotEmpty()) {
                        val processed = processor.process(samples.copyOf())
                        collected?.add(processed)
                        chunks.send(processed)
                    }
                    if (chunk.isFinal) break
                }
            } finally {
                activeStream = null
                try { stream.close() } catch (_: Throwable) {}
                chunks.close()
            }
        }

        if (collected != null && coroutineContext.isActive) {
            val total = collected.sumOf { it.size }
            val clip = FloatArray(total)
            var offset = 0
            collected.forEach {
                it.copyInto(clip, offset)
                offset += it.size
            }
            phraseCache.put(text, clip)
        }
    }

    private suspend fun playClip(audioTrack: AudioTrack, clip: FloatArray) {
        val chunks = Channel<FloatArray>(1)
        chunks.send(clip)
        chunks.close()
        withContext(playbackDispatcher) {
            playStream(audioTrack, chunks)
        }
    }

    /** Writes chunks as they arrive and waits until the last one is heard. */
    private suspend fun playStream(audioTrack: AudioTrack, chunks: Channel<FloatArray>) {
        var started = false
        var startHead = 0L
        var written = 0L

        for (pcm in chunks) {
            if (!started) {
                requestFocus()
                audioTrack.flush()
                audioTrack.play()
                startHead = audioTrack.playbackHeadPosition.toLong() and 0xFFFFFFFFL
                started = true
            }

            var offset = 0
            while (offset < pcm.size) {
                coroutineContext.ensureActive()
                val count = minOf(WRITE_BLOCK, pcm.size - offset)
                val result = audioTrack.write(
                    pcm, offset, count, AudioTrack.WRITE_BLOCKING
                )
                if (result <= 0) return
                offset += result
                written += result
            }
        }

        if (!started) return

        // Let the tail play out before releasing focus.
        val deadline = SystemClock.elapsedRealtime() + written * 1000 / SAMPLE_RATE + 500
        while (coroutineContext.isActive && SystemClock.elapsedRealtime() < deadline) {
            val head = (audioTrack.playbackHeadPosition.toLong() and 0xFFFFFFFFL) - startHead
            if (head >= written) break
            delay(15)
        }
        audioTrack.pause()
    }

    /** Pre-synthesises a few fixed prompts so they play instantly later. */
    private suspend fun warmUp() {
        for (phrase in warmPhrases) {
            if (speakJob?.isActive == true) return
            val engine = tts ?: return
            try {
                val started = SystemClock.elapsedRealtime()
                processor.reset()
                val parts = ArrayList<FloatArray>()
                val stream = engine.openStream(phrase, synthesisOptions, true)
                // Registered so a real request can cancel warm-up mid-phrase.
                activeStream = stream
                try {
                    while (coroutineContext.isActive && speakJob?.isActive != true) {
                        val chunk = stream.readNext() ?: break
                        if (chunk.samples.isNotEmpty()) {
                            parts += processor.process(chunk.samples.copyOf())
                        }
                        if (chunk.isFinal) break
                    }
                } finally {
                    if (activeStream === stream) activeStream = null
                    stream.close()
                }
                if (speakJob?.isActive == true) return
                val clip = FloatArray(parts.sumOf { it.size })
                var offset = 0
                parts.forEach { it.copyInto(clip, offset); offset += it.size }
                if (clip.isNotEmpty()) phraseCache.put(phrase, clip)
                logLevels(phrase, clip, SystemClock.elapsedRealtime() - started)
            } catch (t: Throwable) {
                Log.w(TAG, "Warm-up skipped", t)
                return
            }
        }
    }

    private fun logLevels(phrase: String, clip: FloatArray, elapsedMs: Long) {
        var peak = 0f
        var energy = 0.0
        for (s in clip) {
            val a = kotlin.math.abs(s)
            if (a > peak) peak = a
            energy += s * s
        }
        val rms = if (clip.isEmpty()) 0.0 else kotlin.math.sqrt(energy / clip.size)
        val seconds = clip.size / SAMPLE_RATE.toFloat()
        Log.i(
            TAG,
            "Synthesised \"$phrase\": %.2f s audio in %d ms (RTF %.2f), peak %.1f dBFS, RMS %.1f dBFS".format(
                seconds, elapsedMs, elapsedMs / 1000f / seconds.coerceAtLeast(0.01f),
                20 * kotlin.math.log10(peak.coerceAtLeast(1e-6f)), 20 * kotlin.math.log10(rms.coerceAtLeast(1e-9))
            )
        )
    }

    // =====================================================
    // MODEL INSTALLATION
    // =====================================================

    /**
     * The task needs a real file path, so the bundled (uncompressed) asset is
     * copied once into app-private storage, keeping its original file name,
     * which MediaPipe uses to detect the model type.
     */
    private fun installModel(): File {
        val dir = File(appContext.filesDir, "models").apply { mkdirs() }
        val target = File(dir, MODEL_ASSET)

        val assetLength = try {
            appContext.assets.openFd(MODEL_ASSET).use { it.length }
        } catch (_: Exception) {
            -1L // Compressed or missing; fall back to a size-less check.
        }

        if (target.exists() && target.length() > 0 &&
            (assetLength < 0 || target.length() == assetLength)
        ) {
            return target
        }

        _status.value = Status(State.PREPARING, "Installing Freakyyy's voice (first run)…")

        val temp = File(dir, "$MODEL_ASSET.part")
        try {
            appContext.assets.open(MODEL_ASSET).use { input ->
                temp.outputStream().use { output ->
                    input.copyTo(output, 1 shl 20)
                }
            }
        } catch (e: java.io.FileNotFoundException) {
            temp.delete()
            throw IllegalStateException("Kokoro model is missing from the app package", e)
        } catch (e: java.io.IOException) {
            temp.delete()
            throw IllegalStateException("Couldn't install the voice model (storage full?)", e)
        }

        if (assetLength > 0 && temp.length() != assetLength) {
            temp.delete()
            throw IllegalStateException("Voice model copy was incomplete")
        }

        target.delete()
        if (!temp.renameTo(target)) {
            temp.delete()
            throw IllegalStateException("Couldn't finalise the voice model")
        }
        return target
    }

    // =====================================================
    // AUDIO OUTPUT
    // =====================================================

    private fun createTrack(): AudioTrack {
        val format = AudioFormat.Builder()
            .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
            .setSampleRate(SAMPLE_RATE)
            .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
            .build()

        val minBuffer = AudioTrack.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_FLOAT
        )

        return AudioTrack.Builder()
            .setAudioAttributes(speechAttributes)
            .setAudioFormat(format)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .setBufferSizeInBytes(maxOf(minBuffer * 2, SAMPLE_RATE / 5 * 4))
            .build()
    }

    private val speechAttributes = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_ASSISTANT)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
        .build()

    private fun requestFocus() {
        val manager = audioManager ?: return
        val request = focusRequest ?: AudioFocusRequest.Builder(
            AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK
        )
            .setAudioAttributes(speechAttributes)
            .build()
            .also { focusRequest = it }
        manager.requestAudioFocus(request)
    }

    private fun abandonFocus() {
        val manager = audioManager ?: return
        focusRequest?.let { manager.abandonAudioFocusRequest(it) }
    }
}

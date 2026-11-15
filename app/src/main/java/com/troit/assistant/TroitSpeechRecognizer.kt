
package com.troit.assistant

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

class TroitSpeechRecognizer(
    private val context: Context,
    private val onResult: (String) -> Unit,
    private val onStatus: (String) -> Unit,
    private val onError: (String) -> Unit
) {

    private var recognizer: SpeechRecognizer? = null
    private var isListening = false

    private fun createRecognizer(): Boolean {

        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            onError("Speech recognition is unavailable on this device.")
            return false
        }

        return try {

            recognizer?.destroy()
            recognizer = SpeechRecognizer.createSpeechRecognizer(context)

            recognizer?.setRecognitionListener(
                object : RecognitionListener {

                    override fun onReadyForSpeech(params: Bundle?) {
                        isListening = true
                        onStatus("Listening...")
                    }

                    override fun onBeginningOfSpeech() {
                        onStatus("Hearing your voice...")
                    }

                    override fun onRmsChanged(rmsdB: Float) {}

                    override fun onBufferReceived(buffer: ByteArray?) {}

                    override fun onEndOfSpeech() {
                        onStatus("Processing speech...")
                    }

                    override fun onError(error: Int) {

                        isListening = false

                        val message = when (error) {

                            SpeechRecognizer.ERROR_NO_MATCH ->
                                "I didn't catch that. Please try again."

                            SpeechRecognizer.ERROR_SPEECH_TIMEOUT ->
                                "I couldn't hear anything. Please speak again."

                            SpeechRecognizer.ERROR_AUDIO ->
                                "Microphone audio error. Please try again."

                            SpeechRecognizer.ERROR_NETWORK ->
                                "Network error. Check your internet connection."

                            SpeechRecognizer.ERROR_NETWORK_TIMEOUT ->
                                "Speech recognition timed out."

                            SpeechRecognizer.ERROR_RECOGNIZER_BUSY ->
                                "Speech recognizer is busy. Please try again."

                            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS ->
                                "Microphone permission is required."

                            SpeechRecognizer.ERROR_CLIENT ->
                                "Speech recognition was interrupted. Try again."

                            SpeechRecognizer.ERROR_SERVER ->
                                "Speech recognition service error. Try again."

                            else ->
                                "Speech recognition error: $error"
                        }

                        onStatus("Ready")
                        onError(message)

                        // Recreate on the next listening attempt.
                        // This helps recover from recognizer errors.
                        releaseRecognizer()
                    }

                    override fun onResults(results: Bundle?) {

                        isListening = false

                        val matches = results?.getStringArrayList(
                            SpeechRecognizer.RESULTS_RECOGNITION
                        )

                        val spokenText = matches?.firstOrNull {
                            it.isNotBlank()
                        }

                        if (!spokenText.isNullOrBlank()) {

                            onResult(spokenText.trim())
                            onStatus("Command received")

                        } else {

                            onError("I didn't catch that. Please try again.")
                        }
                    }

                    override fun onPartialResults(
                        partialResults: Bundle?
                    ) {
                        // Wait for final results before executing commands.
                    }

                    override fun onEvent(
                        eventType: Int,
                        params: Bundle?
                    ) {}
                }
            )

            true

        } catch (e: Exception) {

            releaseRecognizer()
            onError("Unable to start speech recognition.")
            false
        }
    }

    fun startListening(languageTag: String = "en-IN") {

        if (isListening) {
            return
        }

        if (recognizer == null) {
            if (!createRecognizer()) {
                return
            }
        }

        val intent = Intent(
            RecognizerIntent.ACTION_RECOGNIZE_SPEECH
        ).apply {

            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
            )

            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE,
                languageTag
            )

            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE,
                languageTag
            )

            putExtra(
                RecognizerIntent.EXTRA_PARTIAL_RESULTS,
                true
            )

            putExtra(
                RecognizerIntent.EXTRA_MAX_RESULTS,
                5
            )

            putExtra(
                RecognizerIntent.EXTRA_PREFER_OFFLINE,
                false
            )

            // Give short answers enough time to be recognised.
            putExtra(
                RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS,
                1800L
            )

            putExtra(
                RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS,
                1200L
            )
        }

        try {

            onStatus("Starting microphone...")

            recognizer?.startListening(intent)

        } catch (e: Exception) {

            isListening = false
            releaseRecognizer()

            onError("Couldn't start microphone. Please try again.")
        }
    }

    fun stopListening() {

        if (isListening) {
            try {
                recognizer?.stopListening()
            } catch (e: Exception) {
                releaseRecognizer()
            }
        }

        onStatus("Ready")
    }

    private fun releaseRecognizer() {

        try {
            recognizer?.cancel()
            recognizer?.destroy()
        } catch (e: Exception) {
            // Ignore cleanup errors.
        }

        recognizer = null
        isListening = false
    }

    fun destroy() {
        releaseRecognizer()
    }
}


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

    fun startListening(languageTag: String = "en-IN") {

        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            onError("Speech recognition unavailable")
            return
        }

        if (recognizer == null) {
            recognizer = SpeechRecognizer.createSpeechRecognizer(context)

            recognizer?.setRecognitionListener(
                object : RecognitionListener {

                    override fun onReadyForSpeech(params: Bundle?) {
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
                        onStatus("Ready")
                        this@TroitSpeechRecognizer.onError(
                            "Speech error: $error"
                        )
                    }

                    override fun onResults(results: Bundle?) {
                        val matches = results?.getStringArrayList(
                            SpeechRecognizer.RESULTS_RECOGNITION
                        )

                        val spokenText = matches?.firstOrNull()

                        if (!spokenText.isNullOrBlank()) {
                            onResult(spokenText)
                            onStatus("Command received")
                        } else {
                            onError("No speech detected")
                        }
                    }

                    override fun onPartialResults(partialResults: Bundle?) {}

                    override fun onEvent(
                        eventType: Int,
                        params: Bundle?
                    ) {}
                }
            )
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
                RecognizerIntent.EXTRA_PARTIAL_RESULTS,
                true
            )
            putExtra(
                RecognizerIntent.EXTRA_MAX_RESULTS,
                3
            )
        }

        onStatus("Starting microphone...")
        recognizer?.startListening(intent)
    }

    fun stopListening() {
        recognizer?.stopListening()
        onStatus("Ready")
    }

    fun destroy() {
        recognizer?.destroy()
        recognizer = null
    }
}

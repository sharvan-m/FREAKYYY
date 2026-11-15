
package com.troit.assistant

import android.content.Context
import android.speech.tts.TextToSpeech
import java.util.Locale

class TroitSpeaker(context: Context) : TextToSpeech.OnInitListener {

    private val textToSpeech = TextToSpeech(
        context.applicationContext,
        this
    )

    private var isReady = false
    private var pendingText: String? = null

    override fun onInit(status: Int) {

        if (status == TextToSpeech.SUCCESS) {

            val result = textToSpeech.setLanguage(
                Locale("en", "IN")
            )

            if (
                result != TextToSpeech.LANG_MISSING_DATA &&
                result != TextToSpeech.LANG_NOT_SUPPORTED
            ) {
                isReady = true

                // JARVIS STYLE VOICE SETTINGS
                textToSpeech.setPitch(0.78f)
                textToSpeech.setSpeechRate(0.90f)

                pendingText?.let {
                    speak(it)
                    pendingText = null
                }
            }
        }
    }

    fun speak(message: String) {

        if (!isReady) {
            pendingText = message
            return
        }

        textToSpeech.speak(
            message,
            TextToSpeech.QUEUE_FLUSH,
            null,
            "TROIT_RESPONSE"
        )
    }

    fun stop() {
        textToSpeech.stop()
    }

    fun shutdown() {
        textToSpeech.stop()
        textToSpeech.shutdown()
        isReady = false
    }
}

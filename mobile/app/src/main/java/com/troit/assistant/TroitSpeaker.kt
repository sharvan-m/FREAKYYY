
package com.troit.assistant

import android.content.Context

/**
 * Freakyyy's speaking interface. Every spoken reply goes through the Kokoro
 * engine (am_onyx, 1.08x, Freakyyy sound profile). Android's system
 * TextToSpeech is intentionally not used.
 */
class TroitSpeaker(context: Context) {

    init {
        FreakyyyVoiceEngine.initialize(context.applicationContext)
    }

    val status = FreakyyyVoiceEngine.status

    fun speak(message: String) {
        FreakyyyVoiceEngine.speak(message)
    }

    fun stop() {
        FreakyyyVoiceEngine.stop()
    }

    /**
     * Stops speech for this screen. The loaded model stays in memory so a
     * configuration change doesn't reload it; MainActivity releases the
     * engine when it is finishing.
     */
    fun shutdown() {
        FreakyyyVoiceEngine.stop()
    }
}


package com.troit.assistant.link

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * "Share → Freakyyy: send to laptop". Links open in the laptop's browser,
 * other text goes to the laptop clipboard, files land in Downloads\Freakyyy.
 */
class ShareToLaptopActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        FreakyyyLink.init(applicationContext)
        FreakyyyLinkService.startIfWanted(applicationContext)

        val uris = buildList {
            if (intent.action == Intent.ACTION_SEND) {
                streamExtra(intent)?.let { add(it) }
            } else if (intent.action == Intent.ACTION_SEND_MULTIPLE) {
                addAll(streamListExtra(intent))
            }
        }
        val text = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()

        lifecycleScope.launch {
            // Give a just-started link a moment to connect.
            repeat(30) {
                if (FreakyyyLink.isConnected) return@repeat
                kotlinx.coroutines.delay(200)
            }
            val message = when {
                uris.isNotEmpty() -> {
                    toast("Sending ${uris.size} file${if (uris.size > 1) "s" else ""} to your laptop…")
                    uris.map { FreakyyyLink.sendFile(it) }.last().optString("message")
                }
                text != null && Regex("""^https?://\S+$""").matches(text) ->
                    FreakyyyLink.request("open_url", JSONObject().put("url", text)).optString("message")
                text != null ->
                    FreakyyyLink.request("clipboard_push", JSONObject().put("text", text)).optString("message")
                else -> "Nothing to send."
            }
            toast(message)
            finish()
        }
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()

    @Suppress("DEPRECATION")
    private fun streamExtra(i: Intent): Uri? =
        if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        else i.getParcelableExtra(Intent.EXTRA_STREAM)

    @Suppress("DEPRECATION")
    private fun streamListExtra(i: Intent): List<Uri> =
        (if (Build.VERSION.SDK_INT >= 33) i.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
        else i.getParcelableArrayListExtra(Intent.EXTRA_STREAM)) ?: emptyList()
}

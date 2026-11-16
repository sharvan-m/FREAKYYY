
package com.troit.assistant.link

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** The paired laptop. The shared secret is encrypted with an Android Keystore key. */
data class PairedLaptop(
    val serverId: String,
    val name: String,
    val hosts: List<String>,
    val port: Int,
    val fingerprint: String
)

class LinkStore(context: Context) {

    private val prefs = context.applicationContext.getSharedPreferences("dexter_link", Context.MODE_PRIVATE)

    val deviceId: String
        get() = prefs.getString("device_id", null) ?: UUID.randomUUID().toString().also {
            prefs.edit().putString("device_id", it).apply()
        }

    var clipboardAcceptFromLaptop: Boolean
        get() = prefs.getBoolean("clip_accept", true)
        set(v) = prefs.edit().putBoolean("clip_accept", v).apply()

    var clipboardShareToLaptop: Boolean
        get() = prefs.getBoolean("clip_share", false)
        set(v) = prefs.edit().putBoolean("clip_share", v).apply()

    fun laptop(): PairedLaptop? {
        val raw = prefs.getString("laptop", null) ?: return null
        return try {
            val o = JSONObject(raw)
            val hosts = o.getJSONArray("hosts")
            PairedLaptop(
                o.getString("server_id"), o.getString("name"),
                (0 until hosts.length()).map { hosts.getString(it) },
                o.getInt("port"), o.getString("fp")
            )
        } catch (_: Exception) {
            null
        }
    }

    fun secret(): ByteArray? {
        val enc = prefs.getString("secret", null) ?: return null
        return try {
            val bytes = Base64.decode(enc, Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
            cipher.doFinal(bytes.copyOfRange(12, bytes.size))
        } catch (_: Exception) {
            null
        }
    }

    fun save(laptop: PairedLaptop, secret: ByteArray) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val enc = cipher.iv + cipher.doFinal(secret)
        prefs.edit()
            .putString("laptop", JSONObject()
                .put("server_id", laptop.serverId).put("name", laptop.name)
                .put("hosts", JSONArray(laptop.hosts)).put("port", laptop.port)
                .put("fp", laptop.fingerprint).toString())
            .putString("secret", Base64.encodeToString(enc, Base64.NO_WRAP))
            .apply()
    }

    /** Remembers the address that worked last so reconnects try it first. */
    fun preferHost(host: String) {
        val l = laptop() ?: return
        val raw = JSONObject(prefs.getString("laptop", "{}")!!)
        raw.put("hosts", JSONArray(listOf(host) + l.hosts.filter { it != host }))
        prefs.edit().putString("laptop", raw.toString()).apply()
    }

    fun forget() {
        prefs.edit().remove("laptop").remove("secret").apply()
    }

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return gen.generateKey()
    }

    private companion object {
        const val ALIAS = "dexter_link_secret"
    }
}

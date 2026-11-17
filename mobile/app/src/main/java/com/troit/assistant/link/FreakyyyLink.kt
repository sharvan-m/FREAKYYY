
package com.troit.assistant.link

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.StatFs
import android.provider.MediaStore
import android.util.Base64
import android.util.Log
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.io.OutputStream
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/**
 * Freakyyy Link client - see protocol/FREAKYYY_LINK_PROTOCOL.md.
 * TLS is pinned to the laptop certificate from the pairing QR code; both
 * sides prove possession of the per-device secret with HMAC challenges.
 */
object FreakyyyLink {

    private const val TAG = "FreakyyyLink"

    enum class State { NOT_PAIRED, CONNECTING, CONNECTED, OFFLINE, PAIRING }

    data class Status(
        val state: State,
        val laptopName: String? = null,
        val message: String = "",
        val pairingCode: String? = null,
        val laptopStats: JSONObject? = null,
        val transfer: String? = null
    )

    private val _status = MutableStateFlow(Status(State.NOT_PAIRED, message = "No laptop paired"))
    val status: StateFlow<Status> = _status.asStateFlow()

    /** Executes requests from the laptop. Installed by FreakyyyAssistant. */
    var requestHandler: (suspend (String, JSONObject) -> JSONObject)? = null
    var onFileReceived: ((String) -> Unit)? = null

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private lateinit var appContext: Context
    lateinit var store: LinkStore
        private set

    private var socket: WebSocket? = null
    private var loopJob: Job? = null
    @Volatile private var wanted = false
    private val waiters = ConcurrentHashMap<String, CompletableDeferred<JSONObject>>()
    private val incoming = ConcurrentHashMap<String, IncomingFile>()
    private var pairingSocket: WebSocket? = null

    fun init(context: Context) {
        if (::appContext.isInitialized) return
        appContext = context.applicationContext
        store = LinkStore(appContext)
        val laptop = store.laptop()
        _status.value = if (laptop == null) Status(State.NOT_PAIRED, message = "No laptop paired")
        else Status(State.OFFLINE, laptop.name, "Not connected")
    }

    val isPaired: Boolean get() = ::appContext.isInitialized && store.laptop() != null && store.secret() != null
    val isConnected: Boolean get() = _status.value.state == State.CONNECTED

    // =====================================================
    // CONNECTION
    // =====================================================

    fun connect() {
        if (!isPaired || loopJob?.isActive == true) return
        wanted = true
        loopJob = scope.launch { connectionLoop() }
    }

    fun disconnect() {
        wanted = false
        loopJob?.cancel()
        socket?.close(1000, "bye")
        socket = null
        store.laptop()?.let { _status.value = Status(State.OFFLINE, it.name, "Disconnected") }
    }

    private suspend fun connectionLoop() {
        var backoff = 2_000L
        while (wanted && scope.isActive) {
            val laptop = store.laptop() ?: return
            val secret = store.secret() ?: return
            _status.value = _status.value.copy(state = State.CONNECTING, laptopName = laptop.name, message = "Connecting…")
            var connected = false
            for (host in laptop.hosts) {
                val session = openSocket(host, laptop.port, laptop.fingerprint) ?: continue
                if (authenticate(session, laptop, secret)) {
                    store.preferHost(host)
                    connected = true
                    backoff = 2_000L
                    _status.value = Status(State.CONNECTED, laptop.name, "Connected", laptopStats = _status.value.laptopStats)
                    sendStatus()
                    val statusJob = scope.launch {
                        while (isActive) {
                            delay(60_000)
                            sendStatus()
                        }
                    }
                    runSession(session)
                    statusJob.cancel()
                    break
                } else {
                    session.ws.close(1000, null)
                    if (session.authFailed) {
                        _status.value = Status(State.OFFLINE, laptop.name, "The laptop no longer recognises this phone. Pair again.")
                        wanted = false
                        return
                    }
                }
            }
            if (!wanted) break
            _status.value = Status(State.OFFLINE, laptop.name,
                if (connected) "Connection lost. Reconnecting…" else "Laptop not reachable. Same Wi-Fi? Freakyyy running on the laptop?")
            delay(backoff)
            backoff = (backoff * 2).coerceAtMost(30_000L)
        }
    }

    private class Session(val ws: WebSocket, val messages: Channel<String>) {
        var authFailed = false
    }

    private fun client(fingerprint: String): OkHttpClient {
        val tm = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun checkServerTrusted(chain: Array<out X509Certificate>, authType: String?) {
                val fp = sha256Hex(chain[0].encoded)
                if (!fp.equals(fingerprint, ignoreCase = true)) {
                    throw CertificateException("Laptop certificate doesn't match the paired one")
                }
            }
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        }
        val ssl = SSLContext.getInstance("TLS").apply { init(null, arrayOf(tm), SecureRandom()) }
        return OkHttpClient.Builder()
            .sslSocketFactory(ssl.socketFactory, tm)
            .hostnameVerifier { _, _ -> true }          // identity is the pinned certificate
            .connectTimeout(4, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .pingInterval(20, TimeUnit.SECONDS)
            .build()
    }

    private suspend fun openSocket(host: String, port: Int, fp: String): Session? {
        val messages = Channel<String>(Channel.UNLIMITED)
        val opened = CompletableDeferred<Boolean>()
        val ws = client(fp).newWebSocket(Request.Builder().url("wss://$host:$port/link").build(),
            object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    opened.complete(true)
                }
                override fun onMessage(webSocket: WebSocket, text: String) {
                    messages.trySend(text)
                }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.i(TAG, "Socket to $host failed: ${t.message}")
                    opened.complete(false)
                    messages.close()
                }
                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    messages.close()
                }
            })
        val ok = withTimeoutOrNull(6_000) { opened.await() } ?: false
        if (!ok) {
            ws.cancel()
            return null
        }
        return Session(ws, messages)
    }

    private suspend fun authenticate(s: Session, laptop: PairedLaptop, secret: ByteArray): Boolean {
        val challenge = withTimeoutOrNull(8_000) { s.messages.receive() }?.let { JSONObject(it) } ?: return false
        if (challenge.optString("type") != "challenge") return false
        val myNonce = randomB64()
        val deviceId = store.deviceId
        s.ws.send(JSONObject()
            .put("type", "auth").put("device_id", deviceId)
            .put("proof", hmac(secret, "client|${challenge.getString("nonce")}|$deviceId"))
            .put("nonce", myNonce).toString())
        val reply = withTimeoutOrNull(8_000) { s.messages.receive() }?.let { JSONObject(it) } ?: return false
        if (reply.optString("type") == "auth_fail") {
            s.authFailed = true
            return false
        }
        if (reply.optString("type") != "auth_ok") return false
        // The laptop proves it holds the same secret too.
        val expected = hmac(secret, "server|$myNonce|${laptop.serverId}")
        if (!MessageDigest.isEqual(expected.toByteArray(), reply.optString("proof").toByteArray())) return false
        socket = s.ws
        return true
    }

    private suspend fun runSession(s: Session) {
        try {
            for (raw in s.messages) {
                val msg = try { JSONObject(raw) } catch (_: Exception) { continue }
                when (msg.optString("type")) {
                    "ping" -> s.ws.send("""{"type":"pong"}""")
                    "response" -> waiters.remove(msg.optString("id"))?.complete(msg)
                    "request" -> scope.launch { serveRequest(s.ws, msg) }
                    "file_offer", "file_chunk", "file_end", "file_cancel" -> receiveFile(s.ws, msg)
                    "file_accept", "file_reject" -> waiters.remove("answer:" + msg.optString("id"))?.complete(msg)
                    "file_done" -> waiters.remove("done:" + msg.optString("id"))?.complete(msg)
                    "status" -> _status.value = _status.value.copy(laptopStats = msg.optJSONObject("data"))
                }
            }
        } finally {
            socket = null
            waiters.values.forEach { it.complete(JSONObject().put("outcome", "DEVICE_OFFLINE").put("message", "The laptop disconnected.")) }
            waiters.clear()
        }
    }

    private suspend fun serveRequest(ws: WebSocket, msg: JSONObject) {
        val action = msg.optString("action")
        val params = msg.optJSONObject("params") ?: JSONObject()
        val result = try {
            requestHandler?.invoke(action, params)
                ?: JSONObject().put("outcome", "FAILED").put("message", "Freakyyy isn't ready on the phone.")
        } catch (e: Exception) {
            Log.e(TAG, "Request failed", e)
            JSONObject().put("outcome", "FAILED").put("message", "The phone couldn't do that: ${e.message}")
        }
        result.put("type", "response").put("id", msg.optString("id"))
        ws.send(result.toString())
    }

    // =====================================================
    // REQUESTS TO THE LAPTOP
    // =====================================================

    suspend fun request(action: String, params: JSONObject = JSONObject(), timeoutMs: Long = 20_000): JSONObject {
        val ws = socket
        if (ws == null || _status.value.state != State.CONNECTED) {
            val why = if (!isPaired) "No laptop is paired yet. Open Devices to pair one." else "Your laptop isn't connected right now."
            return JSONObject().put("outcome", "DEVICE_OFFLINE").put("message", why)
        }
        val id = UUID.randomUUID().toString()
        val waiter = CompletableDeferred<JSONObject>()
        waiters[id] = waiter
        ws.send(JSONObject().put("type", "request").put("id", id).put("action", action).put("params", params).toString())
        return withTimeoutOrNull(timeoutMs) { waiter.await() }
            ?: JSONObject().put("outcome", "FAILED").put("message", "The laptop didn't answer in time.").also { waiters.remove(id) }
    }

    fun sendStatus() {
        val ws = socket ?: return
        ws.send(JSONObject().put("type", "status").put("data", localStatus()).toString())
    }

    fun localStatus(): JSONObject {
        val bm = appContext.getSystemService(BatteryManager::class.java)
        val sticky = appContext.registerReceiver(null, android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val st = sticky?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val fs = StatFs(Environment.getDataDirectory().path)
        return JSONObject()
            .put("battery", bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY))
            .put("charging", st == BatteryManager.BATTERY_STATUS_CHARGING || st == BatteryManager.BATTERY_STATUS_FULL)
            .put("storage_free_gb", fs.availableBytes / 1_000_000_000.0)
            .put("model", deviceName())
    }

    // =====================================================
    // PAIRING
    // =====================================================

    /** Starts pairing from a freakyyylink://pair?d=... link (QR code or pasted). */
    fun startPairing(link: String, extraHost: String? = null) {
        val payload = try {
            val d = Uri.parse(link.trim()).getQueryParameter("d") ?: error("missing data")
            JSONObject(String(Base64.decode(d, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)))
        } catch (e: Exception) {
            _status.value = Status(State.NOT_PAIRED, message = "That isn't a Freakyyy pairing code.")
            return
        }
        disconnect()
        val hostsJson = payload.getJSONArray("hosts")
        val hosts = (listOfNotNull(extraHost) + (0 until hostsJson.length()).map { hostsJson.getString(it) }).distinct()
        val port = payload.getInt("port")
        val fp = payload.getString("fp")
        val token = payload.getString("token")
        val name = payload.optString("name", "Laptop")
        _status.value = Status(State.CONNECTING, name, "Reaching $name…")
        scope.launch {
            for (host in hosts) {
                val s = openSocket(host, port, fp) ?: continue
                val challenge = withTimeoutOrNull(6_000) { s.messages.receive() }?.let { JSONObject(it) }
                if (challenge?.optString("type") != "challenge") {
                    s.ws.close(1000, null)
                    continue
                }
                pairingSocket = s.ws
                val deviceId = store.deviceId
                s.ws.send(JSONObject().put("type", "pair_request").put("token", token).put("device_id", deviceId)
                    .put("device_name", deviceName()).put("platform", "android").toString())
                for (raw in s.messages) {
                    val m = JSONObject(raw)
                    when (m.optString("type")) {
                        "pair_code" -> {
                            // Computed independently: a mismatch means we're not talking to the laptop in the QR code.
                            val local = pairingCode(token, deviceId)
                            if (m.getString("code") != local) {
                                s.ws.close(1000, "code mismatch")
                                pairingSocket = null
                                _status.value = Status(State.NOT_PAIRED, message = "Security check failed: the codes don't match. Pairing stopped.")
                                return@launch
                            }
                            _status.value = Status(State.PAIRING, name,
                                "Check that the laptop shows the same code, then confirm on both devices.", pairingCode = local)
                        }
                        "pair_ok" -> {
                            val secret = Base64.decode(m.getString("device_secret"), Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
                            store.save(PairedLaptop(m.getString("server_id"), m.optString("server_name", name), listOf(host) + hosts.filter { it != host }, port, fp), secret)
                            s.ws.close(1000, "paired")
                            pairingSocket = null
                            _status.value = Status(State.OFFLINE, m.optString("server_name", name), "Paired. Connecting…")
                            connect()
                            return@launch
                        }
                        "pair_reject" -> {
                            s.ws.close(1000, null)
                            pairingSocket = null
                            _status.value = Status(State.NOT_PAIRED, message = m.optString("reason", "Pairing was declined."))
                            return@launch
                        }
                    }
                }
                pairingSocket = null
                if (_status.value.state == State.PAIRING) {
                    _status.value = Status(State.NOT_PAIRED, message = "The laptop closed the pairing session.")
                }
                return@launch
            }
            _status.value = Status(State.NOT_PAIRED,
                message = "Couldn't reach $name. Make sure both are on the same Wi-Fi and Freakyyy is open on the laptop.")
        }
    }

    fun confirmPairing(accept: Boolean) {
        val ws = pairingSocket ?: return
        ws.send(JSONObject().put("type", if (accept) "pair_confirm" else "pair_reject").toString())
        if (accept) {
            _status.value = _status.value.copy(message = "Waiting for the laptop to confirm…")
        } else {
            ws.close(1000, null)
            pairingSocket = null
            _status.value = Status(State.NOT_PAIRED, message = "Pairing cancelled.")
        }
    }

    fun unpair() {
        disconnect()
        store.forget()
        _status.value = Status(State.NOT_PAIRED, message = "Laptop removed.")
    }

    // =====================================================
    // FILES
    // =====================================================

    private class IncomingFile(
        val name: String, val size: Long, val sha: String, val uri: Uri,
        val out: OutputStream, val digest: MessageDigest, var got: Long = 0
    )

    private fun receiveFile(ws: WebSocket, msg: JSONObject) {
        val id = msg.optString("id")
        when (msg.optString("type")) {
            "file_offer" -> {
                val name = msg.optString("name").substringAfterLast('/').substringAfterLast('\\').trim()
                val size = msg.optLong("size")
                if (name.isEmpty() || name == "." || name == ".." || size <= 0 || size > 2_000_000_000L) {
                    ws.send(JSONObject().put("type", "file_reject").put("id", id).put("reason", "Invalid file").toString())
                    return
                }
                val values = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, name)
                    put(MediaStore.Downloads.MIME_TYPE, msg.optString("mime", "application/octet-stream"))
                    put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Freakyyy")
                    put(MediaStore.Downloads.IS_PENDING, 1)
                }
                val resolver = appContext.contentResolver
                val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                val out = uri?.let { resolver.openOutputStream(it) }
                if (uri == null || out == null) {
                    ws.send(JSONObject().put("type", "file_reject").put("id", id).put("reason", "Storage unavailable").toString())
                    return
                }
                incoming[id] = IncomingFile(name, size, msg.optString("sha256"), uri, out, MessageDigest.getInstance("SHA-256"))
                ws.send(JSONObject().put("type", "file_accept").put("id", id).toString())
                _status.value = _status.value.copy(transfer = "Receiving $name…")
            }
            "file_chunk" -> {
                val f = incoming[id] ?: return
                val data = Base64.decode(msg.optString("data"), Base64.DEFAULT)
                f.out.write(data)
                f.digest.update(data)
                f.got += data.size
                _status.value = _status.value.copy(transfer = "Receiving ${f.name} · ${(100 * f.got / f.size)}%")
            }
            "file_end" -> {
                val f = incoming.remove(id) ?: return
                f.out.close()
                val ok = f.got == f.size && hex(f.digest.digest()).equals(f.sha, ignoreCase = true)
                val resolver = appContext.contentResolver
                if (ok) {
                    resolver.update(f.uri, ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }, null, null)
                    ws.send(JSONObject().put("type", "file_done").put("id", id).put("ok", true).put("path", "Download/Freakyyy/${f.name}").toString())
                    _status.value = _status.value.copy(transfer = "Received ${f.name} · Download/Freakyyy")
                    onFileReceived?.invoke(f.name)
                } else {
                    resolver.delete(f.uri, null, null)
                    ws.send(JSONObject().put("type", "file_done").put("id", id).put("ok", false).put("reason", "Integrity check failed").toString())
                    _status.value = _status.value.copy(transfer = "${f.name} failed the integrity check")
                }
            }
            "file_cancel" -> incoming.remove(id)?.let {
                it.out.close()
                appContext.contentResolver.delete(it.uri, null, null)
                _status.value = _status.value.copy(transfer = "${it.name} cancelled")
            }
        }
    }

    /** Sends a file (content:// URI) to the laptop's Downloads\Freakyyy folder. */
    suspend fun sendFile(uri: Uri): JSONObject {
        val ws = socket ?: return JSONObject().put("outcome", "DEVICE_OFFLINE").put("message", "Your laptop isn't connected.")
        val resolver = appContext.contentResolver
        var name = "shared-file"
        var size = -1L
        resolver.query(uri, arrayOf(MediaStore.MediaColumns.DISPLAY_NAME, MediaStore.MediaColumns.SIZE), null, null, null)?.use { c ->
            if (c.moveToFirst()) {
                name = c.getString(0) ?: name
                size = c.getLong(1)
            }
        }
        val digest = MessageDigest.getInstance("SHA-256")
        var counted = 0L
        resolver.openInputStream(uri)?.use { input ->
            val buf = ByteArray(1 shl 16)
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                digest.update(buf, 0, n)
                counted += n
            }
        } ?: return JSONObject().put("outcome", "FAILED").put("message", "Couldn't read that file.")
        size = counted
        val id = UUID.randomUUID().toString()
        val answer = CompletableDeferred<JSONObject>()
        val done = CompletableDeferred<JSONObject>()
        waiters["answer:$id"] = answer
        waiters["done:$id"] = done
        ws.send(JSONObject().put("type", "file_offer").put("id", id).put("name", name).put("size", size)
            .put("sha256", hex(digest.digest())).put("mime", resolver.getType(uri) ?: "application/octet-stream").toString())
        val reply = withTimeoutOrNull(60_000) { answer.await() }
        if (reply?.optString("type") != "file_accept") {
            return JSONObject().put("outcome", "FAILED").put("message", "The laptop didn't accept $name.")
        }
        var sent = 0L
        resolver.openInputStream(uri)?.use { input ->
            val buf = ByteArray(192 * 1024)
            var seq = 0
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                ws.send(JSONObject().put("type", "file_chunk").put("id", id).put("seq", seq++)
                    .put("data", Base64.encodeToString(buf, 0, n, Base64.NO_WRAP)).toString())
                sent += n
                _status.value = _status.value.copy(transfer = "Sending $name · ${100 * sent / size.coerceAtLeast(1)}%")
                while (ws.queueSize() > 4_000_000) delay(30)       // back-pressure
            }
        }
        ws.send(JSONObject().put("type", "file_end").put("id", id).toString())
        val result = withTimeoutOrNull(120_000) { done.await() }
        val ok = result?.optBoolean("ok") == true
        _status.value = _status.value.copy(transfer = if (ok) "Sent $name to the laptop" else "$name failed")
        return JSONObject().put("outcome", if (ok) "COMPLETED" else "FAILED")
            .put("message", if (ok) "Sent $name to your laptop's Downloads\\Freakyyy folder." else "The laptop couldn't save $name.")
    }

    // =====================================================
    // HELPERS
    // =====================================================

    fun deviceName(): String {
        val m = Build.MANUFACTURER.replaceFirstChar { it.uppercase() }
        return if (Build.MODEL.startsWith(m, ignoreCase = true)) Build.MODEL else "$m ${Build.MODEL}"
    }

    fun pairingCode(token: String, deviceId: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(Base64.decode(token, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP), "HmacSHA256"))
        val d = mac.doFinal(deviceId.toByteArray())
        val v = ((d[0].toLong() and 0xff) shl 24) or ((d[1].toLong() and 0xff) shl 16) or
                ((d[2].toLong() and 0xff) shl 8) or (d[3].toLong() and 0xff)
        return "%06d".format(v % 1_000_000)
    }

    private fun hmac(secret: ByteArray, message: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret, "HmacSHA256"))
        return Base64.encodeToString(mac.doFinal(message.toByteArray()), Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
    }

    private fun randomB64(): String {
        val b = ByteArray(32).also { SecureRandom().nextBytes(it) }
        return Base64.encodeToString(b, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
    }

    private fun sha256Hex(bytes: ByteArray) = hex(MessageDigest.getInstance("SHA-256").digest(bytes))

    private fun hex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it) }
}

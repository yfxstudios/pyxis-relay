package com.matthewyak.pyxisviewer

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.burgstaller.okhttp.AuthenticationCacheInterceptor
import com.burgstaller.okhttp.CachingAuthenticatorDecorator
import com.burgstaller.okhttp.DispatchingAuthenticator
import com.burgstaller.okhttp.basic.BasicAuthenticator
import com.burgstaller.okhttp.digest.CachingAuthenticator
import com.burgstaller.okhttp.digest.Credentials
import com.burgstaller.okhttp.digest.DigestAuthenticator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.security.KeyStore
import java.security.cert.X509Certificate
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager
import kotlin.math.floor

// ---- JSON helpers: forgiving reads (missing keys read as null) ----

operator fun JsonElement?.get(key: String): JsonElement? = (this as? JsonObject)?.get(key)
operator fun JsonElement?.get(index: Int): JsonElement? = (this as? JsonArray)?.getOrNull(index)
val JsonElement?.isNull get() = this == null || this is JsonNull
val JsonElement?.double get() = (this as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
val JsonElement?.int get() = double?.let { Math.round(it).toInt() }
val JsonElement?.bool get() = (this as? JsonPrimitive)?.booleanOrNull
val JsonElement?.str get() = (this as? JsonPrimitive)?.takeIf { it.isString }?.content
val JsonElement?.arr get() = (this as? JsonArray) ?: emptyList()
val JsonElement?.obj get() = (this as? JsonObject) ?: emptyMap()

/** This object with [other]'s keys merged in (recursively), for optimistic updates. */
fun JsonElement?.merged(other: JsonElement): JsonElement {
    if (this !is JsonObject || other !is JsonObject) return other
    val m = LinkedHashMap(this)
    for ((k, v) in other) m[k] = m[k].merged(v)
    return JsonObject(m)
}

fun json(vararg pairs: Pair<String, Any?>): JsonObject = buildJsonObject {
    for ((k, v) in pairs) when (v) {
        null -> put(k, JsonNull)
        is JsonElement -> put(k, v)
        is Boolean -> put(k, v)
        is Number -> put(k, v)
        is String -> put(k, v)
        is List<*> -> put(k, buildJsonArray { v.forEach { add(JsonPrimitive(it.toString())) } })
        else -> put(k, v.toString())
    }
}

/**
 * The PYXIS's control API (Blackmagic Camera Control REST API, https://<camera>/control/api/v1,
 * served by the camera's Web media manager) plus its WebSocket notifications.
 * Same behaviour as the iPhone app (Camera.swift).
 */
class Camera(private val context: Context, private val scope: CoroutineScope) {
    sealed interface Link {
        data object Off : Link
        data object Searching : Link
        data class Connecting(val host: String) : Link
        data class Connected(val host: String) : Link
        data class NeedsLogin(val host: String) : Link
        data class Failed(val message: String) : Link
    }

    private val prefs = context.getSharedPreferences("camera", Context.MODE_PRIVATE)
    private val _link = MutableStateFlow<Link>(Link.Off)
    val link: StateFlow<Link> = _link
    private val _values = MutableStateFlow<Map<String, JsonElement>>(emptyMap())
    val values: StateFlow<Map<String, JsonElement>> = _values
    private val _unsupported = MutableStateFlow<Set<String>>(emptySet())
    val unsupported: StateFlow<Set<String>> = _unsupported
    val message = MutableStateFlow<String?>(null)
    /** The camera's timecode, run locally between readings (see TimecodeClock). */
    private val _timecode = MutableStateFlow<TimecodeClock?>(null)
    val timecode: StateFlow<TimecodeClock?> = _timecode

    var manualHost: String
        get() = prefs.getString("host", "") ?: ""
        set(v) { prefs.edit().putString("host", v).apply() }
    var username: String
        get() = prefs.getString("user", "") ?: ""
        set(v) { prefs.edit().putString("user", v).apply() }
    var password: String
        get() = SecretStore.read(context, "cameraPassword")
        set(v) = SecretStore.save(context, "cameraPassword", v)

    var host = ""; private set
    private var scheme = "https"
    private var client: OkHttpClient = OkHttpClient()
    private var runner: Job? = null
    private var tcSync: Job? = null
    private var socket: WebSocket? = null
    private val pending = ConcurrentHashMap<String, JsonElement>()
    @Volatile private var flushScheduled = false
    private val liveSends = ConcurrentHashMap<String, JsonElement>()
    private val liveInFlight = ConcurrentHashMap.newKeySet<String>()
    private var lastTimecodeRead: Int? = null
    private val tcMutex = Mutex()

    companion object {
        /** Pushed several times a second; not needed live (the timecode is run locally). */
        private val skipSubscriptions = setOf("/camera/motionSensor/euler", "/camera/motionSensor/horizon", "/transports/0/timecode")
        /** Useful values that aren't published over the WebSocket: read once per connection. */
        private val extraReads = listOf(
            "/system/supportedFormats", "/monitoring/display", "/monitoring/frameGuideRatio/presets",
            "/transports/0/prerecord/supportedMaxDurations", "/media/devices/doformatSupportedFilesystems",
            "/audio/channels", "/lens/opticalImageStabilization", "/video/supportedNDFilters", "/video/ndFilter",
            "/video/detailSharpeningLevel", "/system/colorScience", "/system/supportedColorSciences", "/luts/slots", "/system/dynamicRange", "/system/supportedDynamicRanges",
        )
        private val JSON_TYPE = "application/json".toMediaType()
    }

    fun v(path: String): JsonElement? = _values.value[path]
    fun has(path: String) = !_values.value[path].isNull
    val isConnected get() = _link.value is Link.Connected
    private val hasLogin get() = username.isNotEmpty() && password.isNotEmpty()

    // ---- connection ----

    fun start(relay: String) {
        stop()
        runner = scope.launch(Dispatchers.IO) {
            while (isActive) {
                runOnce(relay)
                delay(3000)
            }
        }
    }

    fun stop() {
        runner?.cancel(); runner = null
        tcSync?.cancel(); tcSync = null
        socket?.cancel(); socket = null
        _link.value = Link.Off
    }

    /** OkHttp for the camera: trusts its self-signed certificate (only for the camera's own
     *  address), and answers its Secure Login challenge (Basic or Digest) only over HTTPS. */
    private fun makeClient(forHost: String, https: Boolean): OkHttpClient {
        val trustAll = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        }
        val ssl = SSLContext.getInstance("TLS").apply { init(null, arrayOf(trustAll), null) }
        val b = OkHttpClient.Builder()
            .connectTimeout(4, TimeUnit.SECONDS).readTimeout(6, TimeUnit.SECONDS)
            .sslSocketFactory(ssl.socketFactory, trustAll)
            .hostnameVerifier { h, _ -> h.equals(forHost, ignoreCase = true) }
        if (https && hasLogin) {
            val creds = Credentials(username, password)
            val cache = ConcurrentHashMap<String, CachingAuthenticator>()
            val auth = DispatchingAuthenticator.Builder()
                .with("digest", DigestAuthenticator(creds))
                .with("basic", BasicAuthenticator(creds))
                .build()
            b.authenticator(CachingAuthenticatorDecorator(auth, cache)).addInterceptor(AuthenticationCacheInterceptor(cache))
        }
        return b.build()
    }

    private suspend fun runOnce(relay: String) {
        // 1. where is the camera?
        var candidates = listOf<String>()
        val manual = manualHost.trim()
        if (manual.isNotEmpty()) candidates = listOf(manual) else {
            _link.value = Link.Searching
            runCatching {
                OkHttpClient.Builder().connectTimeout(3, TimeUnit.SECONDS).readTimeout(3, TimeUnit.SECONDS).build()
                    .newCall(Request.Builder().url("http://$relay/cgi-bin/pyxis-camera").build()).execute().use { r ->
                        candidates = Json.parseToJsonElement(r.body?.string() ?: "")["cameras"].arr.mapNotNull { it.str }
                    }
            }
        }
        if (candidates.isEmpty()) { _link.value = Link.Failed("No camera found on the relay's network"); return }

        // 2. which one answers the API? (HTTPS, or HTTP when there's no login to protect)
        var found = false
        loop@ for (c in candidates) {
            host = c
            _link.value = Link.Connecting(c)
            for (s in if (hasLogin) listOf("https") else listOf("https", "http")) {
                scheme = s
                client = makeClient(c, s == "https")
                val code = runCatching { raw("GET", "/system/product").first }.getOrNull() ?: continue
                if (code == 401 || code == 403) { _link.value = Link.NeedsLogin(c); return }
                if (code == 200) { found = true; break@loop }
            }
        }
        if (!found) {
            _link.value = Link.Failed("The camera at $host isn't answering. Turn on Web media manager in Blackmagic Camera Setup → Network Access.")
            return
        }

        // 3. live values over the WebSocket
        val closed = kotlinx.coroutines.CompletableDeferred<Unit>()
        val wsUrl = "${if (scheme == "https") "wss" else "ws"}://$host/control/api/v1/event/websocket"
        socket = client.newWebSocket(Request.Builder().url(wsUrl).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                webSocket.send("""{"type":"request","id":1,"data":{"action":"listProperties"}}""")
                _link.value = Link.Connected(host)
                scope.launch(Dispatchers.IO) { readExtras() }
                tcSync?.cancel()
                tcSync = scope.launch(Dispatchers.IO) {
                    syncTimecode(probe = true)
                    while (isActive) { delay(10_000); syncTimecode(probe = false) }
                }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val j = runCatching { Json.parseToJsonElement(text) }.getOrNull() ?: return
                if (j["type"].str == "event" && j["data"]["action"].str == "propertyValueChanged") {
                    val p = j["data"]["property"].str ?: return
                    queue(p, j["data"]["value"] ?: JsonNull)
                } else if (j["id"].int == 1) {
                    val props = j["data"]["properties"].arr.mapNotNull { it.str }.filter { it !in skipSubscriptions }
                    val req = buildJsonObject {
                        put("type", "request"); put("id", 2)
                        put("data", buildJsonObject { put("action", "subscribe"); put("properties", JsonArray(props.map { JsonPrimitive(it) })) })
                    }
                    webSocket.send(req.toString())
                } else if (j["id"].int == 2) {
                    _values.value = _values.value + j["data"]["values"].obj
                    scope.launch(Dispatchers.IO) { syncTimecode(probe = true) }  // now the frame rate is known
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { closed.complete(Unit) }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { closed.complete(Unit) }
        })
        closed.await()
        tcSync?.cancel(); tcSync = null
        if (runner?.isActive == true) _link.value = Link.Failed("Lost the camera connection")
    }

    /** Batches WebSocket events into ~10 UI updates a second. */
    private fun queue(path: String, value: JsonElement) {
        pending[path] = value
        // Record-run timecode starts and stops with recording; the frame rate sets its speed.
        if (path == "/transports/0/record" || path == "/system/format") scope.launch(Dispatchers.IO) { syncTimecode(probe = true) }
        if (flushScheduled) return
        flushScheduled = true
        scope.launch {
            delay(100)
            val batch = HashMap(pending)
            pending.keys.removeAll(batch.keys)
            _values.value = _values.value + batch
            flushScheduled = false
        }
    }

    private suspend fun readExtras() {
        for (p in extraReads) refresh(p)
        // Outputs the camera lists but doesn't publish over the WebSocket (the PYXIS's "Stream").
        for (d in v("/monitoring/display")["displays"].arr.mapNotNull { it.str }) {
            if (has("/monitoring/$d/cleanFeed")) continue
            for (k in listOf("cleanFeed", "displayLUT", "displayLUTSlot", "zebra", "focusAssist", "frameGuide",
                "frameGrids", "safeArea", "falseColor", "brightness")) refresh("/monitoring/$d/$k")
        }
    }

    /** Reads the camera's timecode and restarts the local clock from it. */
    suspend fun syncTimecode(probe: Boolean) = tcMutex.withLock {
        val (base, rate) = TimecodeClock.rates(v("/system/format")["frameRate"].str)
        suspend fun read(): Triple<Int, String, Long>? {
            val sent = System.nanoTime()
            val d = get("/transports/0/timecode")["display"].str ?: return null
            val (f, sep) = TimecodeClock.parse(d, base) ?: return null
            return Triple(f, sep, sent + (System.nanoTime() - sent) / 2)  // middle of the round trip
        }
        var r = read() ?: return@withLock
        var running = _timecode.value?.running ?: true
        if (probe) {
            delay(250)
            read()?.let { r2 -> running = r2.first != r.first; r = r2 }
        } else lastTimecodeRead?.let { running = r.first != it }
        lastTimecodeRead = r.first
        _timecode.value = TimecodeClock(r.first, r.third, base, rate, running, r.second)
    }

    // ---- requests ----

    private suspend fun raw(method: String, path: String, body: JsonElement? = null): Pair<Int, String> = withContext(Dispatchers.IO) {
        val rb = when {
            body != null -> body.toString().toRequestBody(JSON_TYPE)
            method == "GET" || method == "DELETE" -> null
            else -> ByteArray(0).toRequestBody(null)
        }
        client.newCall(Request.Builder().url("$scheme://$host/control/api/v1$path").method(method, rb).build()).execute().use {
            it.code to (it.body?.string() ?: "")
        }
    }

    /** Reads a path into the values (or marks it unsupported). */
    suspend fun refresh(path: String) {
        val (code, text) = runCatching { raw("GET", path) }.getOrNull() ?: return
        if (code == 200) {
            _values.value = _values.value + (path to (runCatching { Json.parseToJsonElement(text) }.getOrNull() ?: JsonNull))
            _unsupported.value = _unsupported.value - path
        } else if (code == 404 || code == 501) {
            _unsupported.value = _unsupported.value + path
            _values.value = _values.value - path
        }
    }

    /** Sets a value: updates the screen at once, then tells the camera. */
    fun put(path: String, body: JsonElement) {
        _values.value = _values.value + (path to v(path).merged(body))
        scope.launch { write("PUT", path, body) }
    }

    /** For sliders: sends the latest value only, one request at a time per path. */
    fun putLive(path: String, body: JsonElement) {
        _values.value = _values.value + (path to v(path).merged(body))
        liveSends[path] = body
        if (!liveInFlight.add(path)) return
        scope.launch {
            while (true) {
                val next = liveSends.remove(path) ?: break
                write("PUT", path, next, quiet = true)
            }
            liveInFlight.remove(path)
        }
    }

    suspend fun post(path: String, body: JsonElement? = null) = write("POST", path, body)
    suspend fun action(method: String, path: String, body: JsonElement? = null) = write(method, path, body)

    /**
     * Starts or stops recording. Current firmware: POST /transports/0/record and
     * PUT /transports/0/stop. Older firmware (and other cameras) only have
     * PUT /transports/0/record {"recording": true/false}, so that's the fallback.
     */
    suspend fun setRecording(on: Boolean): Boolean {
        val current = if (on) write("POST", "/transports/0/record", json(), quiet = true)
                      else write("PUT", "/transports/0/stop", null, quiet = true)
        return current || write("PUT", "/transports/0/record", json("recording" to on))
    }

    private suspend fun write(method: String, path: String, body: JsonElement?, quiet: Boolean = false): Boolean {
        try {
            val (code, text) = raw(method, path, body)
            if (code in 200..299) return true
            if (!quiet) message.value = "Camera: " + (runCatching { Json.parseToJsonElement(text)["error"].str }.getOrNull() ?: "HTTP $code")
        } catch (e: Exception) {
            if (!quiet) message.value = "Camera didn't answer"
        }
        if (method == "PUT") refresh(path)  // show the camera's real value again
        return false
    }

    /** GET returning the body (for one-off reads). */
    suspend fun get(path: String): JsonElement? {
        val (code, text) = runCatching { raw("GET", path) }.getOrNull() ?: return null
        return if (code == 200) runCatching { Json.parseToJsonElement(text) }.getOrNull() else null
    }
}

/**
 * The camera's timecode, run locally: one reading plus when it was taken, advanced at the
 * project frame rate; re-read every 10 s (and when recording starts or stops).
 */
data class TimecodeClock(
    val frames: Int, val atNanos: Long, val base: Int, val rate: Double, val running: Boolean, val separator: String,
) {
    private val day get() = base * 86400

    fun frames(nowNanos: Long): Int {
        if (!running) return frames
        val f = frames + floor((nowNanos - atNanos) / 1e9 * rate).toInt()
        return ((f % day) + day) % day
    }

    fun string(nowNanos: Long = System.nanoTime()): String {
        val f = frames(nowNanos)
        val s = f / base
        return "%02d:%02d:%02d%s%02d".format(s / 3600, (s / 60) % 60, s % 60, separator, f % base)
    }

    companion object {
        fun parse(s: String, base: Int): Pair<Int, String>? {
            val p = s.split(':', ';').mapNotNull { it.toIntOrNull() }
            if (p.size != 4) return null
            return ((((p[0] * 60) + p[1]) * 60 + p[2]) * base + p[3]) to (if (';' in s) ";" else ":")
        }

        fun rates(projectRate: String?): Pair<Int, Double> = when (projectRate) {
            "23.98" -> 24 to 24000.0 / 1001
            "29.97" -> 30 to 30000.0 / 1001
            "47.95" -> 48 to 48000.0 / 1001
            "59.94" -> 60 to 60000.0 / 1001
            "119.88" -> 120 to 120000.0 / 1001
            else -> { val r = projectRate?.toDoubleOrNull() ?: 24.0; maxOf(1, Math.round(r).toInt()) to r }
        }
    }
}

/** Small secrets (the camera's Secure Login password), encrypted with a key in the Android Keystore. */
object SecretStore {
    private const val ALIAS = "pyxisviewer-secrets"

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return gen.generateKey()
    }

    fun save(context: Context, name: String, value: String) {
        val p = context.getSharedPreferences("secrets", Context.MODE_PRIVATE)
        if (value.isEmpty()) { p.edit().remove(name).apply(); return }
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val enc = c.iv + c.doFinal(value.toByteArray())
        p.edit().putString(name, Base64.encodeToString(enc, Base64.NO_WRAP)).apply()
    }

    fun read(context: Context, name: String): String {
        val s = context.getSharedPreferences("secrets", Context.MODE_PRIVATE).getString(name, null) ?: return ""
        return runCatching {
            val b = Base64.decode(s, Base64.NO_WRAP)
            val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, b, 0, 12)) }
            String(c.doFinal(b, 12, b.size - 12))
        }.getOrDefault("")
    }
}

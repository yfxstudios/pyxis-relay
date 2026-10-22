package com.matthewyak.pyxisviewer

import android.util.Base64
import java.io.InputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException

enum class VideoCodec { H264, H265 }

class StreamException(message: String, val offline: Boolean = false) : Exception(message)

/**
 * Minimal RTSP client for the relay: DESCRIBE, SETUP with RTP interleaved on the same TCP
 * connection, PLAY. Video only. Blocking; run it on its own thread.
 * Same protocol handling as the iPhone app (RTSPConnection.swift) and the R5C's HDMI player.
 */
class RtspConnection(private val url: String) {
    private val host: String
    private val port: Int
    private var socket: Socket? = null
    private lateinit var input: InputStream
    private lateinit var output: OutputStream
    private var cseq = 0
    private var session = ""
    private var base = ""
    private var control = ""
    private var buf = ByteArray(1 shl 20)
    private var start = 0   // first unread byte
    private var end = 0     // one past the last byte read
    private var lastKeepalive = 0L

    var codec = VideoCodec.H264; private set
    var payloadType = -1; private set
    /** Parameter sets from the SDP (VPS/SPS/PPS), without start codes. */
    val parameterSets = mutableListOf<ByteArray>()

    init {
        require(url.startsWith("rtsp://")) { "Not an rtsp:// address" }
        val hostPort = url.removePrefix("rtsp://").substringBefore('/')
        val colon = hostPort.lastIndexOf(':')
        if (colon > 0) { host = hostPort.substring(0, colon); port = hostPort.substring(colon + 1).toIntOrNull() ?: 554 }
        else { host = hostPort; port = 554 }
    }

    private val available get() = end - start

    /** Reads more bytes. Returns false on timeout; throws when the connection closed. */
    private fun fill(timeoutMs: Int): Boolean {
        val s = socket ?: throw StreamException("Not connected")
        if (start > 0 && start == end) { start = 0; end = 0 }
        if (end == buf.size) {
            if (start > 0) { System.arraycopy(buf, start, buf, 0, available); end -= start; start = 0 }
            else buf = buf.copyOf(buf.size * 2)  // one unit bigger than the buffer (4K keyframe)
        }
        s.soTimeout = timeoutMs.coerceAtLeast(1)
        val n = try { input.read(buf, end, buf.size - end) } catch (_: SocketTimeoutException) { return false }
        if (n <= 0) throw StreamException("The relay closed the connection")
        end += n
        return true
    }

    private fun send(method: String, target: String, extra: String = "") {
        cseq++
        val sb = StringBuilder("$method $target RTSP/1.0\r\nCSeq: $cseq\r\nUser-Agent: PYXIS Viewer Android\r\n$extra")
        if (session.isNotEmpty()) sb.append("Session: $session\r\n")
        sb.append("\r\n")
        output.write(sb.toString().toByteArray())
        output.flush()
    }

    private fun headerEnd(): Int {
        var i = start
        while (i + 3 < end) {
            if (buf[i] == 13.toByte() && buf[i + 1] == 10.toByte() && buf[i + 2] == 13.toByte() && buf[i + 3] == 10.toByte()) return i + 4
            i++
        }
        return -1
    }

    private data class Response(val code: Int, val headers: Map<String, String>, val body: String)

    /** One RTSP response, skipping interleaved RTP before it. */
    private fun readResponse(timeoutMs: Int): Response {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (true) {
            while (available >= 4 && buf[start] == '$'.code.toByte()) {
                val len = ((buf[start + 2].toInt() and 0xff) shl 8) or (buf[start + 3].toInt() and 0xff)
                if (available < 4 + len) break
                start += 4 + len
            }
            if (available >= 4 && buf[start] != '$'.code.toByte()) {
                val he = headerEnd()
                if (he > 0) {
                    val head = String(buf, start, he - start)
                    val lines = head.split("\r\n")
                    val headers = HashMap<String, String>()
                    for (l in lines.drop(1)) {
                        val c = l.indexOf(':')
                        if (c > 0) headers[l.substring(0, c).lowercase()] = l.substring(c + 1).trim()
                    }
                    val blen = headers["content-length"]?.toIntOrNull() ?: 0
                    if (end - he >= blen) {
                        val body = String(buf, he, blen)
                        start = he + blen
                        val code = lines.firstOrNull()?.split(" ")?.getOrNull(1)?.toIntOrNull() ?: -1
                        return Response(code, headers, body)
                    }
                }
            }
            val left = deadline - System.currentTimeMillis()
            if (left <= 0) throw StreamException("The relay didn't answer")
            fill(left.toInt())
        }
    }

    fun open() {
        session = ""
        val s = Socket()
        s.tcpNoDelay = true
        s.receiveBufferSize = 4 shl 20  // room for 4K keyframes
        try { s.connect(InetSocketAddress(host, port), 3000) } catch (e: Exception) {
            throw StreamException("Can't reach the relay at $host")
        }
        socket = s; input = s.getInputStream(); output = s.getOutputStream()
        start = 0; end = 0

        send("DESCRIBE", url, "Accept: application/sdp\r\n")
        var r = readResponse(3000)
        if (r.code == 404) throw StreamException("The camera isn't streaming", offline = true)
        if (r.code != 200) throw StreamException("The relay answered ${r.code}")
        base = r.headers["content-base"] ?: url
        parseSdp(r.body)

        send("SETUP", control, "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n")
        r = readResponse(3000)
        if (r.code != 200) throw StreamException("The relay refused the stream (${r.code})")
        r.headers["session"]?.let { session = it.substringBefore(';') }

        send("PLAY", base, "Range: npt=0.000-\r\n")
        r = readResponse(3000)
        if (r.code != 200) throw StreamException("The relay refused to play (${r.code})")
        lastKeepalive = System.currentTimeMillis()
    }

    private fun parseSdp(sdp: String) {
        var inVideo = false
        var found = false
        var ctl = ""
        parameterSets.clear()
        payloadType = -1
        for (raw in sdp.lines()) {
            val line = raw.trim()
            if (line.startsWith("m=")) {
                if (found && inVideo) break  // done with the first video section
                inVideo = line.startsWith("m=video")
                if (inVideo) payloadType = line.split(" ").getOrNull(3)?.toIntOrNull() ?: -1
                continue
            }
            if (!inVideo) continue
            when {
                line.startsWith("a=rtpmap:") -> {
                    val f = line.removePrefix("a=rtpmap:").split(" ")
                    if (f.size >= 2 && f[0].toIntOrNull() == payloadType) {
                        when (f[1].substringBefore('/').uppercase()) {
                            "H264" -> { codec = VideoCodec.H264; found = true }
                            "H265", "HEVC" -> { codec = VideoCodec.H265; found = true }
                        }
                    }
                }
                line.startsWith("a=control:") -> ctl = line.removePrefix("a=control:")
                line.startsWith("a=fmtp:") -> for (kv in line.split(';')) {
                    val pair = kv.trim()
                    for (key in listOf("sprop-vps=", "sprop-sps=", "sprop-pps=", "sprop-parameter-sets=")) {
                        val at = pair.indexOf(key)
                        if (at < 0) continue
                        for (b64 in pair.substring(at + key.length).split(',')) {
                            runCatching { Base64.decode(b64, Base64.DEFAULT) }.getOrNull()?.takeIf { it.isNotEmpty() }?.let { parameterSets += it }
                        }
                    }
                }
            }
        }
        if (!found) throw StreamException("The stream has no H.264 or H.265 video")
        control = when {
            ctl.startsWith("rtsp://") -> ctl
            ctl.isNotEmpty() && ctl != "*" -> base + (if (base.endsWith("/")) "" else "/") + ctl
            else -> base
        }
    }

    /** Next RTP packet on the video channel (copied), or null after [timeoutMs] without one. */
    fun readRtp(timeoutMs: Int): ByteArray? {
        if (System.currentTimeMillis() - lastKeepalive > 20_000) {  // the relay drops idle sessions
            send("GET_PARAMETER", base)
            lastKeepalive = System.currentTimeMillis()
        }
        val deadline = System.currentTimeMillis() + timeoutMs
        while (true) {
            if (available >= 4) {
                val b0 = buf[start]
                if (b0 == '$'.code.toByte()) {
                    val ch = buf[start + 1].toInt()
                    val len = ((buf[start + 2].toInt() and 0xff) shl 8) or (buf[start + 3].toInt() and 0xff)
                    if (available >= 4 + len) {
                        val pkt = buf.copyOfRange(start + 4, start + 4 + len)
                        start += 4 + len
                        if (ch == 0) return pkt
                        continue  // RTCP
                    }
                } else if (b0 == 'R'.code.toByte()) {  // a reply (to the keepalive)
                    val he = headerEnd()
                    if (he > 0) {
                        val head = String(buf, start, he - start)
                        val blen = Regex("(?i)content-length:\\s*(\\d+)").find(head)?.groupValues?.get(1)?.toInt() ?: 0
                        if (end - he >= blen) { start = he + blen; continue }
                    }
                } else { start++; continue }  // resync
            }
            val left = deadline - System.currentTimeMillis()
            if (left <= 0) return null
            fill(left.toInt())
        }
    }

    fun close() {
        val s = socket ?: return
        if (session.isNotEmpty()) runCatching { send("TEARDOWN", base) }
        runCatching { s.close() }
        socket = null
    }
}

/** One picture: its NAL units (no start codes), whether it's a keyframe, its RTP time. */
class AccessUnit(val nals: List<ByteArray>, val isKey: Boolean, val rtpTimestamp: Long)

/**
 * RTP (RFC 6184 H.264 / RFC 7798 H.265) -> whole access units. After a lost packet it drops
 * pictures until the next keyframe, so a damaged picture is never shown.
 */
class Depacketizer(private val codec: VideoCodec) {
    private val nals = mutableListOf<java.io.ByteArrayOutputStream>()
    private var ts = 0L
    private var haveTs = false
    private var corrupt = false
    private var key = false
    private var fuOpen = false
    private var lastSeq = 0
    private var haveSeq = false
    private var waitingForKey = true

    private fun isKey(h: Int): Boolean =
        if (codec == VideoCodec.H264) (h and 0x1f) == 5 else ((h shr 1) and 0x3f) in 16..21

    private fun note(h: Int) { if (isKey(h)) key = true }

    private fun reset() { nals.clear(); corrupt = false; key = false; fuOpen = false; haveTs = false }

    private fun emit(): AccessUnit? {
        try {
            if (nals.isEmpty()) return null
            if (corrupt) { waitingForKey = true; return null }
            if (waitingForKey && !key) return null
            if (key) waitingForKey = false
            return AccessUnit(nals.map { it.toByteArray() }, key, ts)
        } finally { reset() }
    }

    private fun newNal(p: ByteArray, from: Int, to: Int) {
        nals += java.io.ByteArrayOutputStream(to - from + 64).apply { write(p, from, to - from) }
    }

    /** Feeds one RTP packet; returns any access units it completes (at most two). */
    fun push(p: ByteArray): List<AccessUnit> {
        val out = ArrayList<AccessUnit>(1)
        if (p.size < 12 || (p[0].toInt() and 0xff) shr 6 != 2) return out
        val b0 = p[0].toInt() and 0xff
        val marker = (p[1].toInt() and 0x80) != 0
        val seq = ((p[2].toInt() and 0xff) shl 8) or (p[3].toInt() and 0xff)
        val t = ((p[4].toLong() and 0xff) shl 24) or ((p[5].toLong() and 0xff) shl 16) or
            ((p[6].toLong() and 0xff) shl 8) or (p[7].toLong() and 0xff)
        var off = 12 + 4 * (b0 and 0x0f)
        if ((b0 and 0x10) != 0) {  // header extension
            if (p.size < off + 4) return out
            off += 4 + 4 * (((p[off + 2].toInt() and 0xff) shl 8) or (p[off + 3].toInt() and 0xff))
        }
        var end = p.size
        if ((b0 and 0x20) != 0) end -= p[p.size - 1].toInt() and 0xff  // padding
        if (off >= end) return out

        if (haveSeq && ((lastSeq + 1) and 0xffff) != seq) corrupt = true  // lost packet(s)
        lastSeq = seq; haveSeq = true

        if (haveTs && t != ts) emit()?.let { out += it }  // missed marker: new picture
        if (!haveTs) { ts = t; haveTs = true }

        val h0 = p[off].toInt() and 0xff
        if (codec == VideoCodec.H264) {
            when (val type = h0 and 0x1f) {
                in 1..23 -> { newNal(p, off, end); note(h0) }
                24 -> {  // STAP-A
                    var i = off + 1
                    while (i + 2 <= end) {
                        val sz = ((p[i].toInt() and 0xff) shl 8) or (p[i + 1].toInt() and 0xff); i += 2
                        if (sz == 0 || i + sz > end) { corrupt = true; break }
                        newNal(p, i, i + sz); note(p[i].toInt() and 0xff); i += sz
                    }
                }
                28 -> {  // FU-A
                    if (end - off < 2) return out
                    val fu = p[off + 1].toInt() and 0xff
                    if ((fu and 0x80) != 0) {
                        val h = (h0 and 0xe0) or (fu and 0x1f)
                        nals += java.io.ByteArrayOutputStream(4096).apply { write(h); write(p, off + 2, end - off - 2) }
                        note(h); fuOpen = true
                    } else if (fuOpen && nals.isNotEmpty()) {
                        nals.last().write(p, off + 2, end - off - 2)
                    } else corrupt = true
                    if ((fu and 0x40) != 0) fuOpen = false
                }
                else -> { if (type == 0) corrupt = true }
            }
        } else {
            if (end - off < 2) return out
            when ((h0 shr 1) and 0x3f) {
                in 0..47 -> { newNal(p, off, end); note(h0) }
                48 -> {  // aggregation packet
                    var i = off + 2
                    while (i + 2 <= end) {
                        val sz = ((p[i].toInt() and 0xff) shl 8) or (p[i + 1].toInt() and 0xff); i += 2
                        if (sz < 2 || i + sz > end) { corrupt = true; break }
                        newNal(p, i, i + sz); note(p[i].toInt() and 0xff); i += sz
                    }
                }
                49 -> {  // fragmentation unit
                    if (end - off < 3) return out
                    val fu = p[off + 2].toInt() and 0xff
                    if ((fu and 0x80) != 0) {
                        val h = (h0 and 0x81) or ((fu and 0x3f) shl 1)
                        nals += java.io.ByteArrayOutputStream(4096).apply { write(h); write(p[off + 1].toInt()); write(p, off + 3, end - off - 3) }
                        note(h); fuOpen = true
                    } else if (fuOpen && nals.isNotEmpty()) {
                        nals.last().write(p, off + 3, end - off - 3)
                    } else corrupt = true
                    if ((fu and 0x40) != 0) fuOpen = false
                }
            }
        }
        if (marker) emit()?.let { out += it }
        return out
    }
}

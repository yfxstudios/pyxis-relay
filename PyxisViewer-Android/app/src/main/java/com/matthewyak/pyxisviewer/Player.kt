package com.matthewyak.pyxisviewer

import android.content.Context
import android.graphics.SurfaceTexture
import android.media.MediaCodec
import android.media.MediaFormat
import android.opengl.GLES11Ext
import android.opengl.GLES30
import android.opengl.GLSurfaceView
import android.os.Build
import android.view.Surface
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

/**
 * Plays the relay's stream with the lowest delay the phone allows:
 *   RTSP over TCP from the relay (no player buffer)
 *   -> RTP depacketizer -> compressed frames
 *   -> MediaCodec hardware decoder in low-latency mode, each picture released the moment it's out
 *   -> OpenGL ES (monitor LUT applied here) -> screen.
 * Reconnects by itself when the stream stops, the Wi-Fi drops or the relay restarts.
 */
class StreamPlayer {
    sealed interface State {
        data object Idle : State
        data object Connecting : State
        data object Playing : State
        data object Offline : State
        data class Failed(val message: String) : State
    }

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state
    private val _resolution = MutableStateFlow("")
    val resolution: StateFlow<String> = _resolution
    private val _fps = MutableStateFlow(0.0)
    val fps: StateFlow<Double> = _fps

    /** The decoder's output surface, from the video view (null while it has none). */
    val surface = AtomicReference<Surface?>(null)
    /** Picture size for the view's letterboxing. */
    val videoSize = AtomicReference(Pair(16, 9))
    private val _size = MutableStateFlow(Pair(16, 9))
    /** The same, for the UI (mapping taps onto the picture). */
    val size: StateFlow<Pair<Int, Int>> = _size
    /** Called when a picture size arrives (the view relayouts). */
    @Volatile var onVideoSize: (() -> Unit)? = null

    private var worker: Thread? = null
    private var stop: AtomicBoolean? = null

    fun play(relayHost: String) {
        stop()
        val host = relayHost.trim()
        if (host.isEmpty()) return
        val flag = AtomicBoolean(false)
        stop = flag
        _state.value = State.Connecting
        worker = Thread({ run("rtsp://$host:8554/live/pyxis", flag) }, "rtsp").apply {
            priority = Thread.MAX_PRIORITY
            start()
        }
    }

    fun stop() {
        stop?.set(true)
        stop = null
        worker = null
        _state.value = State.Idle
        _fps.value = 0.0
    }

    private fun post(flag: AtomicBoolean, f: () -> Unit) { if (!flag.get()) f() }

    private fun run(url: String, flag: AtomicBoolean) {
        while (!flag.get()) {
            post(flag) { if (_state.value != State.Offline) _state.value = State.Connecting }
            var rtsp: RtspConnection? = null
            var decoder: Decoder? = null
            try {
                rtsp = RtspConnection(url).also { it.open() }
                val depay = Depacketizer(rtsp.codec)
                decoder = Decoder(rtsp.codec, this)
                decoder.setParameterSets(rtsp.parameterSets)
                var started = false
                var shown = 0
                var windowStart = System.nanoTime()
                var lastFrame = System.currentTimeMillis()
                while (!flag.get()) {
                    val pkt = rtsp.readRtp(500)
                    if (pkt == null) {
                        if (System.currentTimeMillis() - lastFrame > 5000) throw StreamException("The camera stopped sending", offline = true)
                    } else {
                        for (au in depay.push(pkt)) if (!flag.get()) decoder.feed(au)
                    }
                    val n = decoder.drain()
                    if (n > 0) {
                        lastFrame = System.currentTimeMillis()
                        shown += n
                        if (!started) {
                            started = true; shown = 0; windowStart = System.nanoTime()
                            post(flag) { _state.value = State.Playing; _resolution.value = decoder.resolution }
                        }
                        val dt = (System.nanoTime() - windowStart) / 1e9
                        if (dt >= 1) {
                            val rate = shown / dt
                            post(flag) { _fps.value = rate; _resolution.value = decoder.resolution }
                            shown = 0; windowStart = System.nanoTime()
                        }
                    }
                }
            } catch (e: StreamException) {
                android.util.Log.w("PyxisPlayer", "stream: ${e.message}")
                post(flag) { _state.value = if (e.offline) State.Offline else State.Failed(e.message ?: "Stream error"); _fps.value = 0.0 }
            } catch (e: Exception) {
                android.util.Log.w("PyxisPlayer", "stream failed", e)
                post(flag) { _state.value = State.Failed(e.message ?: e.javaClass.simpleName); _fps.value = 0.0 }
            } finally {
                decoder?.release()
                rtsp?.close()
            }
            // try again shortly (stream offline, Wi-Fi switching, relay restarting)
            repeat(10) { if (!flag.get()) Thread.sleep(100) }
        }
    }

    /** MediaCodec in low-latency mode, rendering to the video view's surface. */
    private class Decoder(private val codec: VideoCodec, private val player: StreamPlayer) {
        private var vps: ByteArray? = null
        private var sps: ByteArray? = null
        private var pps: ByteArray? = null
        private var mc: MediaCodec? = null
        private var configuredWith: List<ByteArray>? = null
        var resolution = ""; private set
        private val info = MediaCodec.BufferInfo()
        private val startCode = byteArrayOf(0, 0, 0, 1)
        /** After a frame is dropped, later frames would decode against a missing picture
         *  (smeared blocks): skip until the next keyframe. */
        private var needKey = true

        private fun nalType(n: ByteArray): Int =
            if (codec == VideoCodec.H264) n[0].toInt() and 0x1f else (n[0].toInt() shr 1) and 0x3f

        /** Notes parameter sets; returns false for NALs the decoder doesn't need (delimiters). */
        private fun absorb(n: ByteArray): Boolean {
            if (n.isEmpty()) return false
            when (codec to nalType(n)) {
                VideoCodec.H264 to 7, VideoCodec.H265 to 33 -> sps = n
                VideoCodec.H264 to 8, VideoCodec.H265 to 34 -> pps = n
                VideoCodec.H265 to 32 -> vps = n
                VideoCodec.H264 to 9, VideoCodec.H265 to 35 -> return false
            }
            return true
        }

        fun setParameterSets(sets: List<ByteArray>) { sets.forEach { absorb(it) } }

        private fun paramSets(): List<ByteArray>? {
            val s = sps ?: return null
            val p = pps ?: return null
            return if (codec == VideoCodec.H265) listOf(vps ?: return null, s, p) else listOf(s, p)
        }

        private fun annexB(parts: List<ByteArray>): ByteArray {
            val out = java.io.ByteArrayOutputStream(parts.sumOf { it.size + 4 })
            for (p in parts) { out.write(startCode); out.write(p) }
            return out.toByteArray()
        }

        private fun configure(sets: List<ByteArray>) {
            release()
            val surface = player.surface.get() ?: throw StreamException("No video surface yet")
            val mime = if (codec == VideoCodec.H264) MediaFormat.MIMETYPE_VIDEO_AVC else MediaFormat.MIMETYPE_VIDEO_HEVC
            val f = MediaFormat.createVideoFormat(mime, 1920, 1080)
            if (codec == VideoCodec.H264) {
                f.setByteBuffer("csd-0", ByteBuffer.wrap(annexB(listOf(sets[0]))))
                f.setByteBuffer("csd-1", ByteBuffer.wrap(annexB(listOf(sets[1]))))
            } else {
                f.setByteBuffer("csd-0", ByteBuffer.wrap(annexB(sets)))
            }
            f.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 8 shl 20)  // 4K keyframes
            f.setInteger(MediaFormat.KEY_PRIORITY, 0)               // real time
            if (Build.VERSION.SDK_INT >= 30) f.setInteger(MediaFormat.KEY_LOW_LATENCY, 1)
            // The stream is untagged HD video: Rec.709, so the picture converts to RGB correctly.
            f.setInteger(MediaFormat.KEY_COLOR_STANDARD, MediaFormat.COLOR_STANDARD_BT709)
            f.setInteger(MediaFormat.KEY_COLOR_RANGE, MediaFormat.COLOR_RANGE_LIMITED)
            f.setInteger(MediaFormat.KEY_COLOR_TRANSFER, MediaFormat.COLOR_TRANSFER_SDR_VIDEO)
            val c = MediaCodec.createDecoderByType(mime)
            c.configure(f, surface, null, 0)
            c.start()
            mc = c
            configuredWith = sets
        }

        fun feed(au: AccessUnit) {
            val body = au.nals.filter { absorb(it) }
            val sets = paramSets() ?: return
            if (mc == null || configuredWith?.zip(sets)?.all { (a, b) -> a.contentEquals(b) } != true) {
                if (!au.isKey) return
                configure(sets)
            }
            val c = mc ?: return
            if (needKey && !au.isKey) return
            val idx = c.dequeueInputBuffer(20_000)
            if (idx < 0) { needKey = true; android.util.Log.w("PyxisPlayer", "decoder full, waiting for a keyframe"); return }
            val buf = c.getInputBuffer(idx) ?: run { needKey = true; return }
            buf.clear()
            val data = annexB(body)
            if (data.size > buf.capacity()) { c.queueInputBuffer(idx, 0, 0, 0, 0); needKey = true; return }
            needKey = false
            buf.put(data)
            val ptsUs = au.rtpTimestamp * 1_000_000 / 90_000
            c.queueInputBuffer(idx, 0, data.size, ptsUs, if (au.isKey) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
        }

        /** Shows every finished picture at once. Returns how many. */
        fun drain(): Int {
            val c = mc ?: return 0
            var n = 0
            while (true) {
                val idx = c.dequeueOutputBuffer(info, 0)
                when {
                    idx >= 0 -> { c.releaseOutputBuffer(idx, true); n++ }
                    idx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                        val f = c.outputFormat
                        var w = f.getInteger(MediaFormat.KEY_WIDTH)
                        var h = f.getInteger(MediaFormat.KEY_HEIGHT)
                        if (f.containsKey("crop-right") && f.containsKey("crop-left")) w = f.getInteger("crop-right") - f.getInteger("crop-left") + 1
                        if (f.containsKey("crop-bottom") && f.containsKey("crop-top")) h = f.getInteger("crop-bottom") - f.getInteger("crop-top") + 1
                        resolution = "$w×$h"
                        player.videoSize.set(Pair(w, h))
                        player._size.value = Pair(w, h)
                        player.onVideoSize?.invoke()
                    }
                    else -> return n
                }
            }
        }

        fun release() {
            mc?.let { runCatching { it.stop() }; runCatching { it.release() } }
            mc = null
        }
    }
}

/**
 * The video picture: decoder output (an external OES texture) drawn letterboxed with OpenGL ES 3,
 * through the monitor LUT (a 3D texture) when one is on.
 */
class VideoView(context: Context, private val player: StreamPlayer, private val lut: LutBox,
                private val capture: Capture? = null) : GLSurfaceView(context) {
    private val renderer = Renderer()

    init {
        setEGLContextClientVersion(3)
        setEGLConfigChooser(RecordableConfigChooser())
        setRenderer(renderer)
        renderMode = RENDERMODE_WHEN_DIRTY
        player.onVideoSize = { requestRender() }
        capture?.wake = { requestRender() }
    }

    /** RGBA8888, OpenGL ES 3, and usable for a video encoder's input surface (local recording). */
    private class RecordableConfigChooser : EGLConfigChooser {
        override fun chooseConfig(egl: javax.microedition.khronos.egl.EGL10, display: javax.microedition.khronos.egl.EGLDisplay): EGLConfig {
            val none = javax.microedition.khronos.egl.EGL10.EGL_NONE
            fun pick(recordable: Boolean): EGLConfig? {
                val attrs = mutableListOf(0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 8,  // R G B A
                    0x3040, 0x40)  // EGL_RENDERABLE_TYPE: EGL_OPENGL_ES3_BIT_KHR
                if (recordable) attrs += listOf(0x3142, 1)  // EGL_RECORDABLE_ANDROID
                attrs += none
                val out = arrayOfNulls<EGLConfig>(1); val n = IntArray(1)
                return if (egl.eglChooseConfig(display, attrs.toIntArray(), out, 1, n) && n[0] > 0) out[0] else null
            }
            return pick(true) ?: pick(false) ?: error("No OpenGL ES 3 configuration")
        }
    }

    private inner class Renderer : GLSurfaceView.Renderer, SurfaceTexture.OnFrameAvailableListener {
        private var tex = 0
        private var lutTex = 0
        private var lutVersion = -1
        private var lutSize = 0f
        private var st: SurfaceTexture? = null
        private var prog = 0
        private val stMatrix = FloatArray(16)
        private var viewW = 1
        private var viewH = 1
        private val quad: FloatBuffer = ByteBuffer.allocateDirect(4 * 4 * 4).order(ByteOrder.nativeOrder()).asFloatBuffer()
        // local recording: the encoder's input surface as an EGL surface, for the recorder it belongs to
        private var encSurface: android.opengl.EGLSurface? = null
        private var encFor: Recorder? = null

        override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
            val ids = IntArray(2)
            GLES30.glGenTextures(2, ids, 0)
            tex = ids[0]; lutTex = ids[1]
            GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, tex)
            GLES30.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_MIN_FILTER, GLES30.GL_LINEAR)
            GLES30.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_MAG_FILTER, GLES30.GL_LINEAR)
            GLES30.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_WRAP_S, GLES30.GL_CLAMP_TO_EDGE)
            GLES30.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_WRAP_T, GLES30.GL_CLAMP_TO_EDGE)
            st = SurfaceTexture(tex).also {
                it.setOnFrameAvailableListener(this)
                player.surface.getAndSet(Surface(it))?.release()
            }
            prog = program(VERTEX, FRAGMENT)
            lutVersion = -1
        }

        override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) { viewW = width; viewH = height }

        override fun onFrameAvailable(surfaceTexture: SurfaceTexture?) { requestRender() }

        override fun onDrawFrame(gl: GL10?) {
            st?.updateTexImage()
            st?.getTransformMatrix(stMatrix)
            GLES30.glViewport(0, 0, viewW, viewH)
            GLES30.glClearColor(0f, 0f, 0f, 1f)
            GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT)

            val (current, version) = lut.current
            if (version != lutVersion) {
                lutVersion = version
                if (current != null) {
                    GLES30.glBindTexture(GLES30.GL_TEXTURE_3D, lutTex)
                    GLES30.glTexParameteri(GLES30.GL_TEXTURE_3D, GLES30.GL_TEXTURE_MIN_FILTER, GLES30.GL_LINEAR)
                    GLES30.glTexParameteri(GLES30.GL_TEXTURE_3D, GLES30.GL_TEXTURE_MAG_FILTER, GLES30.GL_LINEAR)
                    for (w in intArrayOf(GLES30.GL_TEXTURE_WRAP_S, GLES30.GL_TEXTURE_WRAP_T, GLES30.GL_TEXTURE_WRAP_R))
                        GLES30.glTexParameteri(GLES30.GL_TEXTURE_3D, w, GLES30.GL_CLAMP_TO_EDGE)
                    val data = ByteBuffer.allocateDirect(current.rgba.size * 4).order(ByteOrder.nativeOrder()).asFloatBuffer()
                    data.put(current.rgba).position(0)
                    GLES30.glTexImage3D(GLES30.GL_TEXTURE_3D, 0, GLES30.GL_RGBA16F, current.size, current.size, current.size,
                        0, GLES30.GL_RGBA, GLES30.GL_FLOAT, data)
                    lutSize = current.size.toFloat()
                } else lutSize = 0f
            }

            // letterbox / pillarbox the picture
            val (vw, vh) = player.videoSize.get()
            val va = vw.toFloat() / vh; val sa = viewW.toFloat() / viewH
            drawPicture(if (va > sa) 1f else va / sa, if (va > sa) sa / va else 1f)

            capture?.let { c ->
                if (c.frameWanted) c.frameGrabbed(if (player.state.value == StreamPlayer.State.Playing) grabFrame(vw, vh) else null)
                record(c, vw, vh)
            }
        }

        /** Draws the picture scaled to (sx, sy) of the current viewport. */
        private fun drawPicture(sx: Float, sy: Float) {
            quad.clear()
            quad.put(floatArrayOf(-sx, -sy, 0f, 0f, sx, -sy, 1f, 0f, -sx, sy, 0f, 1f, sx, sy, 1f, 1f)).position(0)
            GLES30.glUseProgram(prog)
            GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
            GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, tex)
            GLES30.glUniform1i(GLES30.glGetUniformLocation(prog, "tex"), 0)
            GLES30.glActiveTexture(GLES30.GL_TEXTURE1)
            GLES30.glBindTexture(GLES30.GL_TEXTURE_3D, lutTex)
            GLES30.glUniform1i(GLES30.glGetUniformLocation(prog, "lut"), 1)
            GLES30.glUniform1f(GLES30.glGetUniformLocation(prog, "lutSize"), lutSize)
            GLES30.glUniformMatrix4fv(GLES30.glGetUniformLocation(prog, "stMatrix"), 1, false, stMatrix, 0)
            val pos = GLES30.glGetAttribLocation(prog, "pos")
            val uv = GLES30.glGetAttribLocation(prog, "uvIn")
            quad.position(0)
            GLES30.glVertexAttribPointer(pos, 2, GLES30.GL_FLOAT, false, 16, quad)
            GLES30.glEnableVertexAttribArray(pos)
            quad.position(2)
            GLES30.glVertexAttribPointer(uv, 2, GLES30.GL_FLOAT, false, 16, quad)
            GLES30.glEnableVertexAttribArray(uv)
            GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)
        }

        /** The picture at its full size (as shown, LUT included), read back as a bitmap. */
        private fun grabFrame(w: Int, h: Int): android.graphics.Bitmap? = runCatching {
            val t = IntArray(1); val fb = IntArray(1)
            GLES30.glGenTextures(1, t, 0)
            GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, t[0])
            GLES30.glTexImage2D(GLES30.GL_TEXTURE_2D, 0, GLES30.GL_RGBA, w, h, 0, GLES30.GL_RGBA, GLES30.GL_UNSIGNED_BYTE, null)
            GLES30.glGenFramebuffers(1, fb, 0)
            GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, fb[0])
            GLES30.glFramebufferTexture2D(GLES30.GL_FRAMEBUFFER, GLES30.GL_COLOR_ATTACHMENT0, GLES30.GL_TEXTURE_2D, t[0], 0)
            GLES30.glViewport(0, 0, w, h)
            drawPicture(1f, 1f)
            val buf = ByteBuffer.allocateDirect(w * h * 4).order(ByteOrder.nativeOrder())
            GLES30.glReadPixels(0, 0, w, h, GLES30.GL_RGBA, GLES30.GL_UNSIGNED_BYTE, buf)
            GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, 0)
            GLES30.glDeleteFramebuffers(1, fb, 0)
            GLES30.glDeleteTextures(1, t, 0)
            GLES30.glViewport(0, 0, viewW, viewH)
            val raw = android.graphics.Bitmap.createBitmap(w, h, android.graphics.Bitmap.Config.ARGB_8888)
            buf.rewind(); raw.copyPixelsFromBuffer(buf)
            // OpenGL's rows start at the bottom
            android.graphics.Bitmap.createBitmap(raw, 0, 0, w, h, android.graphics.Matrix().apply { preScale(1f, -1f) }, false)
        }.getOrNull()

        /** Draws the picture into the recorder's encoder too, while recording. */
        private fun record(c: Capture, w: Int, h: Int) {
            val r = c.recorder
            if (encFor != null && encFor !== r) {  // stopped (or replaced): let go of its surface, finish it
                encSurface?.let { android.opengl.EGL14.eglDestroySurface(android.opengl.EGL14.eglGetCurrentDisplay(), it) }
                encSurface = null
                encFor?.endInput()
                encFor = null
            }
            if (r == null || player.state.value != StreamPlayer.State.Playing) return
            val dpy = android.opengl.EGL14.eglGetCurrentDisplay()
            val ctx = android.opengl.EGL14.eglGetCurrentContext()
            val draw = android.opengl.EGL14.eglGetCurrentSurface(android.opengl.EGL14.EGL_DRAW)
            val read = android.opengl.EGL14.eglGetCurrentSurface(android.opengl.EGL14.EGL_READ)
            if (encFor == null) {
                encFor = r
                if (!r.prepare(w, h)) return
                val id = IntArray(1)
                android.opengl.EGL14.eglQueryContext(dpy, ctx, android.opengl.EGL14.EGL_CONFIG_ID, id, 0)
                val cfg = arrayOfNulls<android.opengl.EGLConfig>(1); val n = IntArray(1)
                android.opengl.EGL14.eglChooseConfig(dpy, intArrayOf(android.opengl.EGL14.EGL_CONFIG_ID, id[0], android.opengl.EGL14.EGL_NONE), 0, cfg, 0, 1, n, 0)
                encSurface = android.opengl.EGL14.eglCreateWindowSurface(dpy, cfg[0], r.inputSurface, intArrayOf(android.opengl.EGL14.EGL_NONE), 0)
                    .takeIf { it != android.opengl.EGL14.EGL_NO_SURFACE }
                if (encSurface == null) { c.message.value = "This phone can't record the picture."; r.endInput(); return }
            }
            val es = encSurface ?: return
            val pts = r.timeFor(st?.timestamp ?: return) ?: return
            if (!android.opengl.EGL14.eglMakeCurrent(dpy, es, es, ctx)) return
            GLES30.glViewport(0, 0, w and 1.inv(), h and 1.inv())
            drawPicture(1f, 1f)
            android.opengl.EGLExt.eglPresentationTimeANDROID(dpy, es, pts)
            android.opengl.EGL14.eglSwapBuffers(dpy, es)
            android.opengl.EGL14.eglMakeCurrent(dpy, draw, read, ctx)
            GLES30.glViewport(0, 0, viewW, viewH)
        }

        private fun program(vs: String, fs: String): Int {
            fun shader(type: Int, src: String) = GLES30.glCreateShader(type).also {
                GLES30.glShaderSource(it, src); GLES30.glCompileShader(it)
                val ok = IntArray(1); GLES30.glGetShaderiv(it, GLES30.GL_COMPILE_STATUS, ok, 0)
                if (ok[0] == 0) throw RuntimeException("shader: " + GLES30.glGetShaderInfoLog(it))
            }
            return GLES30.glCreateProgram().also {
                GLES30.glAttachShader(it, shader(GLES30.GL_VERTEX_SHADER, vs))
                GLES30.glAttachShader(it, shader(GLES30.GL_FRAGMENT_SHADER, fs))
                GLES30.glLinkProgram(it)
            }
        }
    }

    private companion object {
        const val VERTEX = """#version 300 es
in vec2 pos;
in vec2 uvIn;
uniform mat4 stMatrix;
out vec2 uv;
void main() {
    gl_Position = vec4(pos, 0.0, 1.0);
    uv = (stMatrix * vec4(uvIn, 0.0, 1.0)).xy;
}"""
        // The LUT works on Rec.709-encoded values, like a LUT on a monitor's video input.
        const val FRAGMENT = """#version 300 es
#extension GL_OES_EGL_image_external_essl3 : require
precision highp float;
uniform samplerExternalOES tex;
uniform highp sampler3D lut;
uniform float lutSize;
in vec2 uv;
out vec4 color;
void main() {
    vec3 c = clamp(texture(tex, uv).rgb, 0.0, 1.0);
    if (lutSize > 1.0) c = texture(lut, (c * (lutSize - 1.0) + 0.5) / lutSize).rgb;
    color = vec4(c, 1.0);
}"""
    }
}

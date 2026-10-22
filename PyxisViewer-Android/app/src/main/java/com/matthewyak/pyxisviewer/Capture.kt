package com.matthewyak.pyxisviewer

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.MediaMuxer
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.MediaStore
import android.view.Surface
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// Local recordings and frame grabs: the picture as it's shown in the app (with the monitor LUT
// when it's on), at the stream's full resolution. Video only (the app doesn't play the sound).
// Saved to the phone's gallery: Movies/PYXIS Viewer and Pictures/PYXIS Viewer.
// Recording here doesn't record on the camera, and the camera's record button doesn't record here.
// Same as the iPhone app's Capture.swift.

class Capture(private val context: Context, private val scope: CoroutineScope) {
    private val _recordingSince = MutableStateFlow<Long?>(null)
    val recordingSince: StateFlow<Long?> = _recordingSince
    val message = MutableStateFlow<String?>(null)

    /** Read by the video view's GL thread on its next frame. */
    @Volatile var frameWanted = false; private set
    @Volatile var recorder: Recorder? = null; private set
    /** The connected camera's model, for file names ("PYXIS 12K 2026-…"); set by the app. */
    @Volatile var cameraName: () -> String? = { null }
    private fun name() = Companion.name(cameraName()?.replace('/', '-') ?: "Camera")

    /** Asks the video view to draw (so it notices a request even when the picture is still). */
    @Volatile var wake: (() -> Unit)? = null

    val isRecording get() = _recordingSince.value != null

    fun grabFrame() { frameWanted = true; wake?.invoke() }

    fun toggleRecording() = if (isRecording) stopRecording() else startRecording()

    fun startRecording() {
        if (isRecording) return
        recorder = Recorder(context, name())
        _recordingSince.value = System.currentTimeMillis()
        wake?.invoke()
    }

    /** The GL thread finishes the file once it sees the recorder has gone (Recorder.endInput). */
    fun stopRecording() {
        val r = recorder ?: return
        recorder = null
        _recordingSince.value = null
        r.onDone = { ok -> message.value = if (ok) "Recording saved to Movies › PYXIS Viewer" else "Nothing was recorded (no picture)." }
        wake?.invoke()
        // no picture coming (stream stopped): finish it from here
        scope.launch(Dispatchers.IO) { kotlinx.coroutines.delay(1500); r.endInput() }
    }

    /** A grabbed frame, from the GL thread. */
    internal fun frameGrabbed(bmp: Bitmap?) {
        frameWanted = false
        if (bmp == null) { message.value = "No picture to capture yet."; return }
        scope.launch(Dispatchers.IO) {
            message.value = runCatching { savePng(bmp); "Frame saved to Pictures › PYXIS Viewer" }
                .getOrElse { "Couldn't save the frame: ${it.message}" }
        }
    }

    /** Lossless: the stream is already compressed once; a JPEG would compress it again. */
    private fun savePng(bmp: Bitmap) {
        val cr = context.contentResolver
        val v = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, name() + ".png")
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PYXIS Viewer")
            put(MediaStore.Images.Media.IS_PENDING, 1)
        }
        val uri = cr.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v) ?: error("no storage")
        try {
            cr.openOutputStream(uri)!!.use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
            cr.update(uri, ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }, null, null)
        } catch (e: Exception) { cr.delete(uri, null, null); throw e }
    }

    companion object {
        /** "PYXIS 12K 2026-10-21 at 21.30.15" */
        fun name(prefix: String) = "$prefix " + SimpleDateFormat("yyyy-MM-dd 'at' HH.mm.ss", Locale.US).format(Date())
    }
}

/**
 * H.264 encoder fed by the video view (it draws each shown picture into [inputSurface]), written
 * to an MP4 in Movies/PYXIS Viewer. Sized by the first picture ([prepare] on the GL thread).
 */
class Recorder(private val context: Context, private val name: String) {
    var inputSurface: Surface? = null; private set
    @Volatile var onDone: ((Boolean) -> Unit)? = null
    private var codec: MediaCodec? = null
    private var muxer: MediaMuxer? = null
    private var pfd: ParcelFileDescriptor? = null
    private var uri: Uri? = null
    @Volatile private var ended = false
    private var lastSource = -1L
    private var lastOut = 0L
    private var offset = 0L

    /** Starts the encoder for pictures of this size. GL thread. */
    fun prepare(width: Int, height: Int): Boolean = runCatching {
        val w = width and 1.inv(); val h = height and 1.inv()
        val f = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BIT_RATE, w * h * 10)  // ~20 Mb/s at 1080p
            setInteger(MediaFormat.KEY_FRAME_RATE, 30)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
            setInteger(MediaFormat.KEY_COLOR_STANDARD, MediaFormat.COLOR_STANDARD_BT709)
            setInteger(MediaFormat.KEY_COLOR_RANGE, MediaFormat.COLOR_RANGE_LIMITED)
            setInteger(MediaFormat.KEY_COLOR_TRANSFER, MediaFormat.COLOR_TRANSFER_SDR_VIDEO)
        }
        val c = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        c.configure(f, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        inputSurface = c.createInputSurface()
        val cr = context.contentResolver
        val v = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, "$name.mp4")
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            put(MediaStore.Video.Media.RELATIVE_PATH, "Movies/PYXIS Viewer")
            put(MediaStore.Video.Media.IS_PENDING, 1)
        }
        val u = cr.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, v) ?: error("no storage")
        uri = u
        pfd = cr.openFileDescriptor(u, "rw")
        muxer = MediaMuxer(pfd!!.fileDescriptor, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        c.start()
        codec = c
        Thread(::drain, "recorder").start()
        true
    }.getOrElse { android.util.Log.w("PyxisCapture", "can't record", it); finish(false); false }

    /** Presentation time for a picture shown at [sourceNs]: continuous across reconnects. */
    fun timeFor(sourceNs: Long): Long? {
        if (lastSource >= 0 && (sourceNs <= lastSource || sourceNs - lastSource > 2_000_000_000L))
            offset = lastOut + 33_333_333L - sourceNs
        else if (lastSource < 0) offset = -sourceNs
        val out = sourceNs + offset
        if (lastSource >= 0 && out <= lastOut) return null
        lastSource = sourceNs; lastOut = out
        return out
    }

    /** No more pictures: finish the file. Safe to call more than once, from any thread. */
    fun endInput() {
        if (ended) return
        ended = true
        val c = codec
        if (c == null) { finish(false); return }
        runCatching { c.signalEndOfInputStream() }.onFailure { finish(false) }
    }

    private fun drain() {
        val c = codec ?: return
        val info = MediaCodec.BufferInfo()
        var track = -1
        var wrote = false
        try {
            while (true) {
                val i = c.dequeueOutputBuffer(info, 20_000)
                when {
                    i == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> { track = muxer!!.addTrack(c.outputFormat); muxer!!.start() }
                    i >= 0 -> {
                        val buf = c.getOutputBuffer(i)
                        if (buf != null && track >= 0 && info.size > 0 && info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0) {
                            buf.position(info.offset); buf.limit(info.offset + info.size)
                            muxer!!.writeSampleData(track, buf, info)
                            wrote = true
                        }
                        c.releaseOutputBuffer(i, false)
                        if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
                    }
                }
            }
        } catch (e: Exception) { android.util.Log.w("PyxisCapture", "recording", e); wrote = false }
        finish(wrote)
    }

    @Synchronized private fun finish(ok: Boolean) {
        runCatching { codec?.stop() }; runCatching { codec?.release() }; codec = null
        runCatching { if (ok) muxer?.stop() }; runCatching { muxer?.release() }; muxer = null
        runCatching { pfd?.close() }; pfd = null
        runCatching { inputSurface?.release() }; inputSurface = null
        val u = uri ?: run { onDone?.invoke(false); return }
        uri = null
        val cr = context.contentResolver
        if (ok) cr.update(u, ContentValues().apply { put(MediaStore.Video.Media.IS_PENDING, 0) }, null, null)
        else cr.delete(u, null, null)
        onDone?.invoke(ok)
    }
}

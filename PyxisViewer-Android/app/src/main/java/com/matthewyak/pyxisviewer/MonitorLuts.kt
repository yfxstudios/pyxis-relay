package com.matthewyak.pyxisviewer

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

// Monitor LUTs: applied by the app to the picture it shows, like LUTs on a field monitor.
// Nothing is sent to the camera; recordings and the camera's outputs are unaffected.

/** A 3D LUT (RGBA floats, red changing fastest, as in .cube files). */
class CubeLut(val title: String, val size: Int, val rgba: FloatArray) {
    companion object {
        /** Reads a .cube file (Adobe/Resolve format, 3D LUTs). */
        fun parse(text: String, fallbackTitle: String): CubeLut {
            var title = fallbackTitle
            var size = 0
            var values = FloatArray(0)
            var n = 0
            for (raw in text.lineSequence()) {
                val line = raw.trim()
                if (line.isEmpty() || line.startsWith("#")) continue
                when {
                    line.startsWith("TITLE") -> line.removePrefix("TITLE").trim().trim('"').takeIf { it.isNotEmpty() }?.let { title = it }
                    line.startsWith("LUT_3D_SIZE") -> {
                        size = line.split(Regex("\\s+")).last().toIntOrNull() ?: 0
                        require(size in 2..129) { "LUT size $size isn't supported." }
                        values = FloatArray(size * size * size * 4)
                    }
                    line.startsWith("LUT_1D_SIZE") -> throw IllegalArgumentException("1D LUTs aren't supported; use a 3D .cube LUT.")
                    line.startsWith("DOMAIN_MIN") || line.startsWith("DOMAIN_MAX") -> {
                        val want = if (line.startsWith("DOMAIN_MIN")) 0f else 1f
                        val v = line.split(Regex("\\s+")).drop(1).mapNotNull { it.toFloatOrNull() }
                        require(v.all { abs(it - want) < 1e-4f }) { "LUTs with an input range other than 0–1 aren't supported." }
                    }
                    line[0].isDigit() || line[0] == '-' || line[0] == '.' -> {
                        val v = line.split(Regex("\\s+")).mapNotNull { it.toFloatOrNull() }
                        require(v.size == 3) { "A line in the LUT isn't three numbers." }
                        require(size > 0) { "Not a 3D LUT (no LUT_3D_SIZE)." }
                        require(n < size * size * size) { "The LUT has more entries than a $size-point LUT." }
                        values[n * 4] = v[0]; values[n * 4 + 1] = v[1]; values[n * 4 + 2] = v[2]; values[n * 4 + 3] = 1f
                        n++
                    }
                }
            }
            require(size > 0) { "Not a 3D LUT (no LUT_3D_SIZE)." }
            require(n == size * size * size) { "The LUT has $n entries; a $size-point LUT needs ${size * size * size}." }
            return CubeLut(title, size, values)
        }
    }
}

/**
 * Built-in film looks. Input and output are Rec.709 video: the looks go on top of the camera's
 * own LUT on its Stream output, the way a look LUT goes on after a technical conversion.
 * Colour-balance moves work on light (gamma 2.4); contrast and split-toning on the signal.
 * Same maths as the iPhone app (FilmLooks.swift).
 */
enum class FilmLook(val title: String, val blurb: String) {
    PRINT("Film Print", "Print-film contrast, slightly warm highlights"),
    WARM("Warm Film", "Golden highlights, gentle contrast"),
    TEAL_ORANGE("Teal & Orange", "Cool shadows, warm skin and highlights"),
    BLEACH("Bleach Bypass", "Desaturated, high contrast, silver-retention look"),
    FADED("Faded Film", "Lifted blacks, soft highlights, muted colour"),
    MONO("Black & White", "Black and white with film-like contrast");

    fun lut(n: Int = 33): CubeLut {
        val out = FloatArray(n * n * n * 4)
        val d = (n - 1).toDouble()
        var i = 0
        for (b in 0 until n) for (g in 0 until n) for (r in 0 until n) {
            val c = apply(r / d, g / d, b / d)
            out[i++] = c.x.toFloat(); out[i++] = c.y.toFloat(); out[i++] = c.z.toFloat(); out[i++] = 1f
        }
        return CubeLut(title, n, out)
    }

    fun apply(r: Double, g: Double, b: Double): C3 {
        var v = C3(r, g, b)
        when (this) {
            PRINT -> {
                v = v.contrast(0.2)
                v = v + C3(0.018, 0.004, -0.02) * v.luma.pow(2)
                v = v.saturation(1.06)
            }
            WARM -> v = v.balance(1.06, 0.88).contrast(0.12).saturation(0.95)
            TEAL_ORANGE -> {
                v = v.saturation(1.08)
                val l = v.luma
                v = v + C3(-0.035, 0.005, 0.045) * ((1 - l).pow(2) * min(1.0, l / 0.08))  // teal shadows, black stays black
                v = v + C3(0.045, 0.012, -0.045) * l.pow(1.5)                                 // orange highlights
                v = v.contrast(0.12)
            }
            BLEACH -> { val l = v.luma; v = v.mix(C3(l, l, l), 0.55).contrast(0.45) }
            FADED -> {
                v = v.balance(1.02, 0.97).contrast(-0.1).saturation(0.8)
                v = C3(0.06 + 0.88 * v.x, 0.065 + 0.875 * v.y, 0.07 + 0.86 * v.z)
            }
            MONO -> { val l = v.luma; v = C3(l, l, l).contrast(0.25) }
        }
        return C3(v.x.coerceIn(0.0, 1.0), v.y.coerceIn(0.0, 1.0), v.z.coerceIn(0.0, 1.0))
    }
}

data class C3(val x: Double, val y: Double, val z: Double) {
    val luma get() = 0.2126 * x + 0.7152 * y + 0.0722 * z
    operator fun plus(o: C3) = C3(x + o.x, y + o.y, z + o.z)
    operator fun times(k: Double) = C3(x * k, y * k, z * k)
    fun mix(o: C3, t: Double) = this * (1 - t) + o * t
    fun saturation(s: Double): C3 { val l = luma; return C3(l + s * (x - l), l + s * (y - l), l + s * (z - l)) }
    fun contrast(k: Double): C3 {
        fun c(v0: Double): Double { val v = v0.coerceIn(0.0, 1.0); val s = v * v * (3 - 2 * v); return v + k * (s - v) }
        return C3(c(x), c(y), c(z))
    }
    fun balance(red: Double, blue: Double): C3 {
        fun f(v: Double, k: Double) = min(1.0, max(0.0, v).pow(2.4) * k).pow(1 / 2.4)
        return C3(f(x, red), y, f(z, blue))
    }
}

/** The LUT the GL thread should apply (or null), handed over between threads. */
class LutBox {
    @Volatile private var value: Pair<CubeLut?, Int> = null to 0
    fun set(l: CubeLut?) { synchronized(this) { value = l to value.second + 1 } }
    val current get() = value
}

/** The app's monitor LUT: which one is chosen, whether it's on, and the imported ones. */
class MonitorLuts(private val context: Context, private val scope: CoroutineScope) {
    sealed interface Choice {
        data class Look(val look: FilmLook) : Choice
        data class File(val name: String) : Choice
    }

    private val prefs = context.getSharedPreferences("luts", Context.MODE_PRIVATE)
    private val folder = File(context.filesDir, "luts").apply { mkdirs() }
    private val cache = HashMap<Choice, CubeLut>()
    val box = LutBox()

    private val _choice = MutableStateFlow<Choice>(Choice.Look(FilmLook.PRINT))
    val choice: StateFlow<Choice> = _choice
    private val _enabled = MutableStateFlow(prefs.getBoolean("on", false))
    val enabled: StateFlow<Boolean> = _enabled
    private val _imported = MutableStateFlow<List<String>>(emptyList())
    val imported: StateFlow<List<String>> = _imported
    val message = MutableStateFlow<String?>(null)

    init {
        val saved = prefs.getString("choice", "") ?: ""
        reloadImported()
        _choice.value = when {
            saved.startsWith("file:") && saved.removePrefix("file:") in _imported.value -> Choice.File(saved.removePrefix("file:"))
            else -> Choice.Look(FilmLook.entries.firstOrNull { it.name == saved } ?: FilmLook.PRINT)
        }
        update()
    }

    fun name(c: Choice) = when (c) {
        is Choice.Look -> c.look.title
        is Choice.File -> c.name.removeSuffix(".cube")
    }

    fun select(c: Choice) { _choice.value = c; _enabled.value = true; save(); update() }
    fun setEnabled(on: Boolean) { _enabled.value = on; save(); update() }

    private fun save() {
        prefs.edit().putBoolean("on", _enabled.value).putString("choice", when (val c = _choice.value) {
            is Choice.Look -> c.look.name
            is Choice.File -> "file:" + c.name
        }).apply()
    }

    private fun update() {
        if (!_enabled.value) { box.set(null); return }
        val c = _choice.value
        cache[c]?.let { box.set(it); return }
        scope.launch {
            val result = withContext(Dispatchers.Default) {
                runCatching {
                    when (c) {
                        is Choice.Look -> c.look.lut()
                        is Choice.File -> CubeLut.parse(File(folder, c.name).readText(), c.name.removeSuffix(".cube"))
                    }
                }
            }
            result.onSuccess { lut ->
                cache[c] = lut
                if (_choice.value == c && _enabled.value) box.set(lut)
            }.onFailure { e ->
                message.value = "LUT: ${e.message}"
                if (_choice.value == c) setEnabled(false)
            }
        }
    }

    private fun reloadImported() {
        _imported.value = (folder.list() ?: emptyArray()).filter { it.lowercase().endsWith(".cube") }.sortedBy { it.lowercase() }
    }

    /** Copies a .cube file into the app (after checking it parses) and selects it. */
    fun importLut(uri: Uri) {
        scope.launch {
            try {
                val (name, text) = withContext(Dispatchers.IO) {
                    var display = "LUT"
                    context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
                        if (it.moveToFirst()) display = it.getString(0) ?: display
                    }
                    val t = context.contentResolver.openInputStream(uri)?.use { it.readBytes().toString(Charsets.UTF_8) }
                        ?: throw IllegalArgumentException("Couldn't read the file.")
                    display to t
                }
                val base = name.removeSuffix(".cube").removeSuffix(".CUBE").replace('/', '_')
                val lut = withContext(Dispatchers.Default) { CubeLut.parse(text, base) }
                var file = "$base.cube"
                var i = 2
                while (File(folder, file).exists()) { file = "$base $i.cube"; i++ }
                withContext(Dispatchers.IO) { File(folder, file).writeText(text) }
                reloadImported()
                cache[Choice.File(file)] = lut
                select(Choice.File(file))
            } catch (e: Exception) {
                message.value = "Couldn't import that LUT: ${e.message}"
            }
        }
    }

    fun delete(file: String) {
        File(folder, file).delete()
        cache.remove(Choice.File(file))
        reloadImported()
        if (_choice.value == Choice.File(file)) { _choice.value = Choice.Look(FilmLook.PRINT); setEnabled(false) }
    }
}

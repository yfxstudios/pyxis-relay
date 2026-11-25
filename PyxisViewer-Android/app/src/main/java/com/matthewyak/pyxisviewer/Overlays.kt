package com.matthewyak.pyxisviewer

import android.content.Context
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.geometry.center
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.json.JsonElement
import kotlin.math.roundToInt

// Frame guides and exposure/focus overlays, like a field monitor's: drawn by this app over the
// picture it shows. Frame grabs and local recordings don't include them.
//
//   lines (drawn over the picture):   frame guide (2.39, 1.85, 16:9...), shade outside it,
//                                     rule of thirds, 90% safe area, centre cross
//   image (in the video shader):      false colour, zebras, focus peaking
//
// Guides sit inside the area the camera records, not the whole stream: in 6:5 or 3:2 the camera
// streams its 16:9 picture with black bars, and a 2.39 guide belongs inside the 6:5 part.

enum class FrameGuide(val label: String, val ratio: Float?) {
    OFF("Off", null), R239("2.39", 2.39f), R200("2.00", 2f), R185("1.85", 1.85f), R169("16:9", 16f / 9),
    R43("4:3", 4f / 3), R11("1:1", 1f), R45("4:5", 0.8f), R916("9:16", 9f / 16);

    /** The guide's frame: the largest rectangle of its ratio centred in the recorded area. */
    fun rect(area: Rect): Rect = ratio?.let { fit(it, area) } ?: area
}

/** The largest rectangle of `ratio` (width / height) centred in `r`. */
fun fit(ratio: Float, r: Rect): Rect {
    if (ratio <= 0 || r.width <= 0 || r.height <= 0) return r
    return if (r.width / r.height > ratio) {
        val w = r.height * ratio
        Rect(r.center.x - w / 2, r.top, r.center.x + w / 2, r.bottom)
    } else {
        val h = r.width / ratio
        Rect(r.left, r.center.y - h / 2, r.right, r.center.y + h / 2)
    }
}

/** The recorded picture's shape (width / height), if the camera says. */
fun recordedRatio(v: Map<String, JsonElement>): Float? {
    val r = v["/system/format"]["recordResolution"]
    val w = r["width"].double ?: return null
    val h = r["height"].double ?: return null
    return if (w > 0 && h > 0) (w / h).toFloat() else null
}

/**
 * Where the picture is on screen: the stream's frame, the part of it the camera records, and the
 * zoom (about the screen's centre, then a pan) that maps them to the screen.
 */
class PictureLayout(val video: Rect, recordedRatio: Float?, val bounds: Size, val scale: Float = 1f, val pan: Offset = Offset.Zero) {
    val recorded: Rect = recordedRatio?.let { fit(it, video) } ?: video

    /** A rectangle of the unzoomed picture, where it is on screen now. */
    fun shown(r: Rect): Rect {
        val c = bounds.center
        return Rect(c.x + (r.left - c.x) * scale + pan.x, c.y + (r.top - c.y) * scale + pan.y,
            c.x + (r.right - c.x) * scale + pan.x, c.y + (r.bottom - c.y) * scale + pan.y)
    }

    /** The zoom that makes `r` (of the unzoomed picture) fill the screen, centred. */
    fun filling(r: Rect): Pair<Float, Offset> {
        if (r.width <= 0 || r.height <= 0) return 1f to Offset.Zero
        val s = minOf(bounds.width / r.width, bounds.height / r.height)
        return s to Offset((bounds.center.x - r.center.x) * s, (bounds.center.y - r.center.y) * s)
    }

    /** Keeps a pan from sliding the picture off the screen. */
    fun clamped(p: Offset, s: Float): Offset {
        val mx = maxOf(0f, (video.width * s - bounds.width) / 2); val my = maxOf(0f, (video.height * s - bounds.height) / 2)
        return Offset(p.x.coerceIn(-mx, mx), p.y.coerceIn(-my, my))
    }
}


/** What's chosen. `enabled` turns them all off and on again. */
data class OverlaySettings(
    val enabled: Boolean = true,
    val guide: FrameGuide = FrameGuide.OFF,
    val shadeOpacity: Float = 0.6f,  // outside the frame guide
    val fill: Boolean = false,       // zoom so the guide fills the screen
    val thirds: Boolean = false,
    val safeArea: Boolean = false,
    val center: Boolean = false,
    val falseColor: Boolean = false,
    val zebras: Boolean = false,
    val zebraLevel: Int = 95,  // percent of the video range
    val peaking: Boolean = false,
) {
    /** Something is chosen and showing (the button lights up). */
    val active get() = enabled && (guide != FrameGuide.OFF || thirds || safeArea || center || falseColor || zebras || peaking)
}

/** The chosen overlays, remembered between launches. The GL thread reads `state.value`. */
class Overlays(context: Context) {
    private val prefs = context.getSharedPreferences("overlays", Context.MODE_PRIVATE)
    private val _state = MutableStateFlow(OverlaySettings(
        enabled = prefs.getBoolean("on", true),
        guide = FrameGuide.entries.firstOrNull { it.name == prefs.getString("guide", "") } ?: FrameGuide.OFF,
        shadeOpacity = prefs.getFloat("shadeOpacity", 0.6f),
        fill = prefs.getBoolean("fill", false),
        thirds = prefs.getBoolean("thirds", false),
        safeArea = prefs.getBoolean("safe", false),
        center = prefs.getBoolean("center", false),
        falseColor = prefs.getBoolean("falseColor", false),
        zebras = prefs.getBoolean("zebras", false),
        zebraLevel = prefs.getInt("zebraLevel", 95),
        peaking = prefs.getBoolean("peaking", false),
    ))
    val state: StateFlow<OverlaySettings> = _state

    fun update(f: (OverlaySettings) -> OverlaySettings) {
        val s = f(_state.value)
        _state.value = s
        prefs.edit().putBoolean("on", s.enabled).putString("guide", s.guide.name).putFloat("shadeOpacity", s.shadeOpacity).putBoolean("fill", s.fill)
            .putBoolean("thirds", s.thirds).putBoolean("safe", s.safeArea).putBoolean("center", s.center)
            .putBoolean("falseColor", s.falseColor).putBoolean("zebras", s.zebras).putInt("zebraLevel", s.zebraLevel)
            .putBoolean("peaking", s.peaking).apply()
    }

    /** Turns one on or off; turning one on also turns the overlays back on. */
    fun toggle(get: (OverlaySettings) -> Boolean, set: OverlaySettings.(Boolean) -> OverlaySettings) = update {
        val on = !(it.enabled && get(it))
        it.set(on).let { s -> if (on) s.copy(enabled = true) else s }
    }

    fun select(g: FrameGuide) = update {
        val guide = if (it.enabled && it.guide == g) FrameGuide.OFF else g
        it.copy(guide = guide, enabled = it.enabled || g != FrameGuide.OFF)
    }

    fun nextZebraLevel() = update {
        val l = ZEBRA_LEVELS
        it.copy(zebraLevel = l[(l.indexOf(it.zebraLevel).coerceAtLeast(0) + 1) % l.size], zebras = true, enabled = true)
    }

    companion object { val ZEBRA_LEVELS = listOf(70, 80, 90, 95, 100) }
}

/** Video levels (Rec.709 luma, 0–1) and their colours; the rest of the picture goes grey.
 *  The video shader (VideoView) has the same table. */
object FalseColor {
    class Band(val from: Float, val to: Float, val color: Color, val label: String, val range: String)
    val bands = listOf(
        Band(0f, 0.025f, Color(0.55f, 0.15f, 0.85f), "Black clip", "0–2.5%"),
        Band(0.025f, 0.05f, Color(0.10f, 0.35f, 1.00f), "Near black", "2.5–5%"),
        Band(0.38f, 0.45f, Color(0.15f, 0.80f, 0.25f), "18% grey", "38–45%"),
        Band(0.52f, 0.58f, Color(1.00f, 0.45f, 0.70f), "Skin, +1 stop", "52–58%"),
        Band(0.95f, 0.99f, Color(1.00f, 0.85f, 0.10f), "Near white", "95–99%"),
        Band(0.99f, 1.01f, Color(1.00f, 0.15f, 0.15f), "Clipped", "99%+"),
    )
}

// ---- lines over the picture ----

@Composable
fun GuidesOverlay(overlays: Overlays, layout: PictureLayout) {
    val s by overlays.state.collectAsState()
    if (!s.enabled || layout.video.width <= 0) return
    Canvas(Modifier.fillMaxSize()) {
        val video = layout.shown(layout.video)
        val frame = s.guide.rect(layout.shown(layout.recorded))
        if (s.guide != FrameGuide.OFF) {
            if (s.shadeOpacity > 0) {
                val outside = Path().apply {
                    fillType = PathFillType.EvenOdd
                    addRect(video); addRect(frame)
                }
                drawPath(outside, Color.Black.copy(alpha = s.shadeOpacity))
            }
            line(Path().apply { addRect(frame) }, 1.2f, 0.9f)
        }
        if (s.thirds) line(Path().apply {
            for (i in 1..2) {
                val x = frame.left + frame.width * i / 3; val y = frame.top + frame.height * i / 3
                moveTo(x, frame.top); lineTo(x, frame.bottom)
                moveTo(frame.left, y); lineTo(frame.right, y)
            }
        }, 1f, 0.55f)
        if (s.safeArea) {
            val safe = Rect(frame.left + frame.width * 0.05f, frame.top + frame.height * 0.05f,
                frame.right - frame.width * 0.05f, frame.bottom - frame.height * 0.05f)
            line(Path().apply { addRect(safe) }, 1f, 0.75f, dashed = true)
        }
        if (s.center) {
            val c = frame.center; val r = 12.dp.toPx()
            line(Path().apply {
                moveTo(c.x - r, c.y); lineTo(c.x + r, c.y)
                moveTo(c.x, c.y - r); lineTo(c.x, c.y + r)
            }, 1.5f, 0.9f)
        }
    }
}

/** A white line with a soft dark edge, so it shows on bright and dark pictures. */
private fun DrawScope.line(p: Path, widthDp: Float, alpha: Float, dashed: Boolean = false) {
    val w = widthDp.dp.toPx()
    val dash = if (dashed) PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 5.dp.toPx())) else null
    drawPath(p, Color.Black.copy(alpha = 0.35f * alpha), style = Stroke(w + 1.5.dp.toPx(), pathEffect = dash))
    drawPath(p, Color.White.copy(alpha = alpha), style = Stroke(w, pathEffect = dash))
}

// ---- the docked guides panel ----

@Composable
fun OverlayChooser(overlays: Overlays, recorded: String?, close: () -> Unit) {
    val s by overlays.state.collectAsState()
    val on = s.enabled
    val haptic = LocalHapticFeedback.current
    fun tap(f: () -> Unit) = { haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove); f() }
    Column(Modifier.widthIn(max = 720.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("GUIDES", style = HudStyle.text(13.sp, FontWeight.Bold, Color.White.copy(alpha = 0.75f)), maxLines = 1)
            Spacer(Modifier.weight(1f))
            if (on && s.guide != FrameGuide.OFF) {
                // how dark it is outside the frame guide
                Text("Outside", style = HudStyle.text(13.sp, FontWeight.SemiBold))
                Slider(s.shadeOpacity, { v -> overlays.update { it.copy(shadeOpacity = v) } }, Modifier.width(120.dp),
                    colors = SliderDefaults.colors(thumbColor = Color.White, activeTrackColor = Color.White))
                Text("${(s.shadeOpacity * 100).roundToInt()}%", style = HudStyle.text(13.sp), modifier = Modifier.width(38.dp))
            }
            OutlinedChip(if (on) "On" else "Off", filled = on) { overlays.update { it.copy(enabled = !on) } }
            Box(Modifier.size(36.dp).clickable(onClick = close).semantics { contentDescription = "Close" }, contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Close, null, tint = Color.White)
            }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(22.dp), verticalAlignment = Alignment.CenterVertically) {
            for (g in FrameGuide.entries) {
                val sel = (on || g == FrameGuide.OFF) && s.guide == g
                Column(Modifier.heightIn(min = 44.dp).clickable(onClick = tap { overlays.select(g) })
                    .semantics { selected = sel; contentDescription = if (g == FrameGuide.OFF) "No frame guide" else "Frame guide ${g.label}" },
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text(g.label, style = HudStyle.text(17.sp), maxLines = 1)
                    Box(Modifier.padding(top = 5.dp).size(width = 36.dp, height = 2.5.dp).background(if (sel) Color.White else Color.Transparent))
                }
            }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedChip("Fill", s.fill, tap { overlays.update { it.copy(fill = !it.fill) } })
            OutlinedChip("Thirds", on && s.thirds, tap { overlays.toggle({ it.thirds }) { copy(thirds = it) } })
            OutlinedChip("Safe 90%", on && s.safeArea, tap { overlays.toggle({ it.safeArea }) { copy(safeArea = it) } })
            OutlinedChip("Center", on && s.center, tap { overlays.toggle({ it.center }) { copy(center = it) } })
            Spacer(Modifier.width(10.dp))
            OutlinedChip("False color", on && s.falseColor, tap { overlays.toggle({ it.falseColor }) { copy(falseColor = it) } })
            OutlinedChip("Zebras", on && s.zebras, tap { overlays.toggle({ it.zebras }) { copy(zebras = it) } })
            if (on && s.zebras) OutlinedChip("${s.zebraLevel}%", false, tap { overlays.nextZebraLevel() })
            OutlinedChip("Peaking", on && s.peaking, tap { overlays.toggle({ it.peaking }) { copy(peaking = it) } })
        }
        if (on && s.falseColor) {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                for (b in FalseColor.bands) Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(12.dp).background(b.color, RoundedCornerShape(2.dp)))
                    Text(" ${b.label} ${b.range}", style = HudStyle.text(12.sp), maxLines = 1)
                }
            }
        } else Text((recorded?.let { "Frame guides sit inside the recorded $it area. " } ?: "") +
            "Shown on this phone only. Frame grabs and recordings don't include them.",
            style = HudStyle.text(12.sp, color = Color.White.copy(alpha = 0.6f)))
    }
}

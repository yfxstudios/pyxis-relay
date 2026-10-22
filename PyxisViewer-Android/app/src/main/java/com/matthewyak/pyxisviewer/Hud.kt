package com.matthewyak.pyxisviewer

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CenterFocusWeak
import androidx.compose.material.icons.filled.Power
import androidx.compose.material.icons.filled.StopCircle
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material.icons.outlined.RadioButtonChecked
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement

// The camera-style overlay: a status strip along the top (FPS, shutter, iris, timecode, ISO,
// white balance, tint, power) and one along the bottom (record, media, monitor LUT), laid out
// like the PYXIS's own touchscreen. Tapping a value opens its control. Same as the iPhone app.

object HudStyle {
    val accent = Color(0xFF2988F2)
    val record = Color(0xFFEB3333)
    val picker = Color(0xFF292E3B).copy(alpha = 0.45f)  // the camera's slate grey, see-through
    val shadow = Shadow(Color.Black.copy(alpha = 0.7f), Offset(0f, 2f), 5f)
    fun text(size: TextUnit, weight: FontWeight = FontWeight.Normal, color: Color = Color.White) =
        TextStyle(color = color, fontSize = size, fontWeight = weight, shadow = shadow, fontFeatureSettings = "tnum")
    val label = text(10.sp, FontWeight.SemiBold, Color.White.copy(alpha = 0.75f))
}

enum class QuickPanel { FPS, SHUTTER, IRIS, ISO, WB, TINT, POWER, MEDIA, RECORD, LUT }

/** Watches the camera's values (recomposes when they change). */
@Composable
fun Camera.watch(): Map<String, JsonElement> = values.collectAsState().value

// ---- value formatting ----

object Show {
    fun trim(d: Double): String = if (d == Math.rint(d)) d.toLong().toString() else "%.2f".format(d).trimEnd('0').trimEnd('.')
    fun angle(hundredths: Double) = trim(hundredths / 100) + "°"
    fun fps(v: Map<String, JsonElement>): String {
        val f = v["/system/format"]
        if (f["offSpeedEnabled"].bool == true) f["offSpeedFrameRate"].double?.let { return trim(it) }
        return f["frameRate"].str ?: "–"
    }
    fun speedMode(v: Map<String, JsonElement>) = v["/video/shutter/measurement"]["measurement"].str == "ShutterSpeed"
    fun shutterLabel(v: Map<String, JsonElement>) = if (speedMode(v)) "SHUTTER" else "SA"
    fun shutter(v: Map<String, JsonElement>): String {
        val s = v["/video/shutter"]
        return if (speedMode(v)) s["shutterSpeed"].int?.let { "1/$it" } ?: "–" else s["shutterAngle"].double?.let { angle(it) } ?: "–"
    }
    fun iris(v: Map<String, JsonElement>) = v["/lens/iris"]["apertureStop"].double?.let { "f" + trim(Math.round(it * 10) / 10.0) } ?: "–"
    fun iso(v: Map<String, JsonElement>) = v["/video/iso"]["iso"].int?.toString() ?: "–"
    fun wb(v: Map<String, JsonElement>) = v["/video/whiteBalance"]["whiteBalance"].int?.let { "${it}K" } ?: "–"
    fun tint(v: Map<String, JsonElement>) = v["/video/whiteBalanceTint"]["whiteBalanceTint"].int?.toString() ?: "–"
    fun recording(v: Map<String, JsonElement>) = v["/transports/0/record"]["recording"].bool == true
    /** Remaining record time, given in seconds by the camera. */
    fun remaining(seconds: Int) = if (seconds < 60) "${maxOf(0, seconds)}s" else "${seconds / 60}min"
}

// ---- top bar ----

@Composable
fun TopBar(cam: Camera, compact: Boolean, panel: QuickPanel?, setPanel: (QuickPanel?) -> Unit, openMenu: () -> Unit) {
    val v = cam.watch()
    fun toggle(p: QuickPanel) = setPanel(if (panel == p) null else p)
    Column(Modifier.fillMaxWidth()) {
        if (compact) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                MenuButton(openMenu)
                Spacer(Modifier.weight(1f))
                Timecode(cam, v, 28.sp) { toggle(QuickPanel.RECORD) }
                Spacer(Modifier.weight(1f))
                Box(Modifier.clickable { toggle(QuickPanel.POWER) }.padding(6.dp)) { Battery(v) }
            }
            // each setting fills its share of the row: the space around its text taps it too
            Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 2.dp)) {
                val cell = Modifier.weight(1f)
                Item("FPS", Show.fps(v), panel == QuickPanel.FPS, 18.sp, cell, Alignment.CenterStart) { toggle(QuickPanel.FPS) }
                Item(Show.shutterLabel(v), Show.shutter(v), panel == QuickPanel.SHUTTER, 18.sp, cell) { toggle(QuickPanel.SHUTTER) }
                Item("IRIS", Show.iris(v), panel == QuickPanel.IRIS, 18.sp, cell) { toggle(QuickPanel.IRIS) }
                Item("ISO", Show.iso(v), panel == QuickPanel.ISO, 18.sp, cell) { toggle(QuickPanel.ISO) }
                Item("WB", Show.wb(v), panel == QuickPanel.WB, 18.sp, cell) { toggle(QuickPanel.WB) }
                Item("TINT", Show.tint(v), panel == QuickPanel.TINT, 18.sp, cell, Alignment.CenterEnd) { toggle(QuickPanel.TINT) }
            }
        } else {
            Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                val cell = Modifier.weight(1f)
                MenuButton(openMenu)
                Item("FPS", Show.fps(v), panel == QuickPanel.FPS, modifier = cell) { toggle(QuickPanel.FPS) }
                Item(Show.shutterLabel(v), Show.shutter(v), panel == QuickPanel.SHUTTER, modifier = cell) { toggle(QuickPanel.SHUTTER) }
                Item("IRIS", Show.iris(v), panel == QuickPanel.IRIS, modifier = cell) { toggle(QuickPanel.IRIS) }
                Timecode(cam, v, 32.sp) { toggle(QuickPanel.RECORD) }
                Item("ISO", Show.iso(v), panel == QuickPanel.ISO, modifier = cell) { toggle(QuickPanel.ISO) }
                Item("WB", Show.wb(v), panel == QuickPanel.WB, modifier = cell) { toggle(QuickPanel.WB) }
                Item("TINT", Show.tint(v), panel == QuickPanel.TINT, modifier = cell) { toggle(QuickPanel.TINT) }
                Box(Modifier.clickable { toggle(QuickPanel.POWER) }.padding(6.dp)) { Battery(v) }
            }
        }
    }
}

@Composable
private fun MenuButton(open: () -> Unit) {
    Box(Modifier.size(44.dp).clickable(onClick = open).semantics { contentDescription = "Camera menu" }, contentAlignment = Alignment.Center) {
        Box(Modifier.size(40.dp, 32.dp).border(1.6.dp, Color.White, RoundedCornerShape(6.dp)), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.CenterFocusWeak, null, tint = Color.White, modifier = Modifier.size(20.dp))
        }
    }
}

@Composable
private fun Item(label: String, value: String, selected: Boolean, size: TextUnit = 21.sp, modifier: Modifier = Modifier,
                 align: Alignment = Alignment.Center, onClick: () -> Unit) {
    // the whole cell is the touch area, not just the text
    Box(modifier.clickable(onClick = onClick).padding(vertical = 6.dp).semantics(mergeDescendants = true) { contentDescription = "$label $value" },
        contentAlignment = align) {
        Column(Modifier.background(if (selected) Color.White.copy(alpha = 0.18f) else Color.Transparent, RoundedCornerShape(6.dp)).padding(4.dp)) {
            Text(label, style = HudStyle.label)
            Text(value, style = HudStyle.text(size), maxLines = 1)
        }
    }
}

/** The timecode, advanced locally at the frame rate (the camera is only asked every few seconds). */
@Composable
private fun Timecode(cam: Camera, v: Map<String, JsonElement>, size: TextUnit, onClick: () -> Unit) {
    val clock by cam.timecode.collectAsState()
    var text by remember { mutableStateOf("--:--:--:--") }
    LaunchedEffect(clock) {
        while (true) {
            text = clock?.string() ?: "--:--:--:--"
            delay((1000 / (clock?.rate ?: 24.0)).toLong().coerceAtLeast(8))
        }
    }
    Text(text, style = HudStyle.text(size, FontWeight.Light, if (Show.recording(v)) HudStyle.record else Color.White),
        maxLines = 1, modifier = Modifier.clickable(onClick = onClick).padding(horizontal = 12.dp, vertical = 6.dp))
}

@Composable
fun Battery(v: Map<String, JsonElement>) {
    val p = v["/camera/power"]
    val source = p["source"].str ?: ""
    val battery = p["batteries"][0]
    val percent = battery["chargeRemainingPercent"].int
    val volts = v["/camera/power/displayMode"]["mode"].str == "Voltage"
    Row(Modifier.sizeIn(minWidth = 44.dp, minHeight = 44.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (source == "Battery" || source.isEmpty()) {
            if (volts) (battery["milliVolt"].int ?: p["milliVolt"].int)?.let { Text("%.1fV".format(it / 1000.0), style = HudStyle.text(15.sp, FontWeight.Medium)) }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(46.dp, 24.dp).border(2.dp, Color.White, RoundedCornerShape(4.dp)).padding(start = 4.5.dp),
                    contentAlignment = Alignment.CenterStart) {
                    Row(horizontalArrangement = Arrangement.spacedBy(2.5.dp)) {
                        repeat(4) { i ->
                            val on = percent != null && percent / 100.0 > i * 0.25 + 0.05
                            Box(Modifier.size(8.dp, 15.dp).background(Color.White.copy(alpha = if (on) 1f else 0.15f), RoundedCornerShape(1.dp)))
                        }
                    }
                }
                Box(Modifier.padding(start = 1.5.dp).size(3.dp, 9.dp).background(Color.White, RoundedCornerShape(1.dp)))
            }
        } else {
            Icon(Icons.Filled.Power, null, tint = Color.White)
            Text(source, style = HudStyle.text(13.sp, FontWeight.Medium))
        }
    }
}

// ---- bottom bar ----

@Composable
fun BottomBar(cam: Camera, luts: MonitorLuts, capture: Capture, compact: Boolean, panel: QuickPanel?, setPanel: (QuickPanel?) -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = if (compact) 10.dp else 8.dp),
            horizontalArrangement = Arrangement.spacedBy(if (compact) 14.dp else 26.dp, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically) {
            RecordButton(cam)
            MediaSlots(cam, if (compact) 50.dp else 78.dp) { setPanel(if (panel == QuickPanel.MEDIA) null else QuickPanel.MEDIA) }
            LutButton(luts, showName = !compact) { setPanel(QuickPanel.LUT) }
            if (!compact) CaptureButtons(capture)  // portrait: above the bar (no room in it)
        }
    }
}

@Composable
private fun RecordButton(cam: Camera) {
    val v = cam.watch()
    val link by cam.link.collectAsState()
    val recording = Show.recording(v)
    val scope = rememberCoroutineScope()
    val haptic = LocalHapticFeedback.current
    var busy by remember { mutableStateOf(false) }
    val enabled = link is Camera.Link.Connected
    Box(Modifier.size(56.dp).alpha(if (enabled) 1f else 0.4f)
        .clickable(enabled = enabled && !busy) {
            busy = true
            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
            scope.launch {
                cam.setRecording(!recording)
                busy = false
            }
        }.semantics { contentDescription = if (recording) "Stop recording" else "Record" },
        contentAlignment = Alignment.Center) {
        Box(Modifier.size(48.dp).border(2.5.dp, Color.White, CircleShape))
        Box(Modifier.size(38.dp).background(if (recording) HudStyle.record else Color.White.copy(alpha = 0.55f), CircleShape))
    }
}

@Composable
private fun MediaSlots(cam: Camera, nameWidth: androidx.compose.ui.unit.Dp, onClick: () -> Unit) {
    val v = cam.watch()
    val ws = v["/media/workingset"]["workingset"].arr
    val slots = v["/media/slots"].arr
    val count = maxOf(ws.size, slots.size, 2)
    Row(Modifier.clickable(onClick = onClick).semantics { contentDescription = "Media" }, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        for (i in 0 until count) {
            val m = ws.getOrNull(i)
            val active = m["activeDisk"].bool == true
            val bg = if (active) HudStyle.accent else Color.White.copy(alpha = 0.3f)
            Column {
                Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    Box(Modifier.size(16.dp).background(bg), contentAlignment = Alignment.Center) {
                        Text("${i + 1}", style = HudStyle.text(11.sp, FontWeight.Bold))
                    }
                    val name = if (m.isNull) slots.getOrNull(i)["type"].str ?: "" else m["volume"].str ?: m["deviceName"].str ?: ""
                    Box(Modifier.width(nameWidth).height(16.dp).background(bg).padding(horizontal = 4.dp), contentAlignment = Alignment.CenterStart) {
                        Text(name, style = HudStyle.text(11.sp, FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                Text(if (m.isNull) "No Card" else m["remainingRecordTime"].int?.let { Show.remaining(it) } ?: "–",
                    style = HudStyle.text(19.sp, color = if (m.isNull) Color.White.copy(alpha = 0.8f) else Color.White), maxLines = 1)
            }
        }
    }
}

/** The monitor LUT (applied in this app): tap to turn on and off, hold to choose one. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun LutButton(luts: MonitorLuts, showName: Boolean, choose: () -> Unit) {
    val on by luts.enabled.collectAsState()
    val choice by luts.choice.collectAsState()
    val haptic = LocalHapticFeedback.current
    Column(Modifier.sizeIn(minWidth = 44.dp, minHeight = 44.dp)
        .combinedClickable(onClick = { haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove); luts.setEnabled(!on) },
            onLongClick = { haptic.performHapticFeedback(HapticFeedbackType.LongPress); choose() })
        .semantics { contentDescription = if (on) "Monitor LUT ${luts.name(choice)}, on. Hold to choose." else "Monitor LUT off. Hold to choose." },
        verticalArrangement = Arrangement.Center) {
        Text("LUT", style = HudStyle.text(13.sp, FontWeight.Bold, if (on) Color.Black else Color.White).copy(shadow = null),
            modifier = Modifier.background(if (on) Color.White else Color.Transparent, RoundedCornerShape(4.dp))
                .border(1.4.dp, Color.White, RoundedCornerShape(4.dp)).padding(horizontal = 7.dp, vertical = 3.dp))
        if (showName) Text(if (on) luts.name(choice) else "Off", style = HudStyle.text(11.sp, color = Color.White.copy(alpha = 0.8f)),
            maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 140.dp).padding(top = 3.dp))
    }
}

// ---- capture on this device (not on the camera) ----

/** Grab the current frame, and record the picture on this phone. */
@Composable
fun CaptureButtons(capture: Capture) {
    val since by capture.recordingSince.collectAsState()
    val haptic = LocalHapticFeedback.current
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        CaptureItem(Icons.Outlined.PhotoCamera, "FRAME", Color.White, "Capture the frame") {
            haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove); capture.grabFrame()
        }
        val on = since != null
        CaptureItem(if (on) Icons.Filled.StopCircle else Icons.Outlined.RadioButtonChecked, "LOCAL",
            if (on) HudStyle.record else Color.White, if (on) "Stop recording on this phone" else "Record on this phone") {
            haptic.performHapticFeedback(HapticFeedbackType.LongPress); capture.toggleRecording()
        }
    }
}

@Composable
private fun CaptureItem(icon: ImageVector, caption: String, tint: Color, description: String, onClick: () -> Unit) {
    Column(Modifier.sizeIn(minWidth = 44.dp, minHeight = 44.dp).clickable(onClick = onClick).semantics { contentDescription = description },
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Icon(icon, null, tint = tint, modifier = Modifier.size(24.dp))
        Text(caption, style = HudStyle.text(9.sp, FontWeight.Bold, Color.White.copy(alpha = 0.85f)))
    }
}

/** Shown while recording on this phone: so it isn't mistaken for the camera recording. */
@Composable
fun LocalRecordingPill(since: Long) {
    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(since) { while (true) { now = System.currentTimeMillis(); delay(500) } }
    val s = ((now - since) / 1000).coerceAtLeast(0)
    Row(Modifier.background(Color.Black.copy(alpha = 0.7f), RoundedCornerShape(50)).padding(horizontal = 12.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).background(HudStyle.record, CircleShape))
        Text("Recording on this phone  ${s / 60}:${"%02d".format(s % 60)}", color = Color.White, fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 7.dp))
    }
}

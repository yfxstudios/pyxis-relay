package com.matthewyak.pyxisviewer

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Cloud
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material.icons.filled.WbIncandescent
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.math.abs
import kotlin.math.pow
import kotlin.math.roundToInt

// The camera's own setting picker, docked along the bottom while a setting is selected:
//     200      800      1250     [3200]     8000        <- presets, the current one underlined
//   ‹ 3200 ›  ─────────────────────────●──────          <- step through every value, or slide

class PickerOption(val id: String, val label: String, val icon: ImageVector? = null, val badge: String? = null)

@Composable
fun DockedPanel(content: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth().background(HudStyle.picker).navigationBarsPadding()) {
        Box(Modifier.fillMaxWidth().padding(horizontal = 18.dp).padding(top = 12.dp, bottom = 10.dp), contentAlignment = Alignment.Center) {
            content()
        }
    }
}

/** Slider over a range; `snapSteps` > 0 makes it stop on each step (with a tick). */
class SliderSpec(val value: Double, val range: ClosedFloatingPointRange<Double>, val snapSteps: Int = 0, val set: (Double) -> Unit)

@Composable
fun SettingPicker(
    presets: List<PickerOption>, selected: String?, pick: (PickerOption) -> Unit, value: String,
    prev: (() -> Unit)? = null, next: (() -> Unit)? = null, slider: SliderSpec? = null,
    trailing: (@Composable () -> Unit)? = null, note: String? = null, valueBadge: String? = null,
) {
    val haptic = LocalHapticFeedback.current
    var dragging by remember { mutableStateOf<Float?>(null) }
    Column(Modifier.widthIn(max = 720.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (presets.isNotEmpty()) {
            val badges = presets.any { it.badge != null }
            Row(Modifier.fillMaxWidth()) {
                for (o in presets) {
                    val sel = o.id == selected
                    Column(Modifier.weight(1f).heightIn(min = 44.dp).clickable { pick(o) }
                        .semantics { this.selected = sel; contentDescription = o.label + (o.badge?.let { ", $it" } ?: "") },
                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Bottom) {
                        if (badges) Text(o.badge ?: " ", style = HudStyle.text(9.sp, FontWeight.Bold, Color.White.copy(alpha = if (o.badge == null) 0f else 0.75f)))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            o.icon?.let { Icon(it, null, tint = Color.White, modifier = Modifier.size(17.dp).padding(end = 3.dp)) }
                            Text(o.label, style = HudStyle.text(21.sp), maxLines = 1)
                        }
                        Box(Modifier.padding(top = 5.dp).size(width = 40.dp, height = 2.5.dp).background(if (sel) Color.White else Color.Transparent))
                    }
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (prev != null || next != null) Arrow(Icons.AutoMirrored.Filled.KeyboardArrowLeft, "Lower", prev)
            Row(Modifier.widthIn(min = 64.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.Center) {
                Text(value, style = HudStyle.text(21.sp), maxLines = 1)
                valueBadge?.let { Text(" $it", style = HudStyle.text(9.sp, FontWeight.Bold, Color.White.copy(alpha = 0.75f))) }
            }
            if (prev != null || next != null) Arrow(Icons.AutoMirrored.Filled.KeyboardArrowRight, "Higher", next)
            if (slider != null && slider.range.endInclusive > slider.range.start) {
                Slider(
                    value = dragging ?: slider.value.toFloat(),
                    onValueChange = { v ->
                        if (slider.snapSteps > 0 && v != (dragging ?: slider.value.toFloat())) haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                        dragging = v; slider.set(v.toDouble())
                    },
                    onValueChangeFinished = { dragging = null },
                    valueRange = slider.range.start.toFloat()..slider.range.endInclusive.toFloat(),
                    steps = if (slider.snapSteps > 0) slider.snapSteps else 0,
                    colors = SliderDefaults.colors(thumbColor = Color.White, activeTrackColor = Color.White,
                        inactiveTrackColor = Color.White.copy(alpha = 0.25f), activeTickColor = Color.Transparent, inactiveTickColor = Color.Transparent),
                    modifier = Modifier.weight(1f),
                )
            } else Spacer(Modifier.weight(1f))
            trailing?.invoke()
        }
        note?.let { Text(it, style = HudStyle.text(12.sp, color = Color.White.copy(alpha = 0.6f))) }
    }
}

@Composable
private fun Arrow(icon: ImageVector, label: String, onClick: (() -> Unit)?) {
    Box(Modifier.size(36.dp, 44.dp).clickable(enabled = onClick != null) { onClick?.invoke() }.semantics { contentDescription = label },
        contentAlignment = Alignment.Center) {
        Icon(icon, null, tint = Color.White.copy(alpha = if (onClick == null) 0.3f else 1f), modifier = Modifier.size(28.dp))
    }
}

@Composable
fun OutlinedChip(text: String, filled: Boolean = false, onClick: () -> Unit) {
    Text(text, style = HudStyle.text(15.sp, FontWeight.SemiBold, if (filled) Color.Black else Color.White).copy(shadow = null),
        modifier = Modifier.clickable(onClick = onClick).background(if (filled) Color.White else Color.Transparent, RoundedCornerShape(6.dp))
            .border(1.dp, Color.White.copy(alpha = 0.7f), RoundedCornerShape(6.dp)).padding(horizontal = 12.dp, vertical = 7.dp))
}

/** Up to `n` values spread across a list, preferring familiar ones. */
fun <T : Comparable<T>> presetValues(all: List<T>, preferred: List<T> = emptyList(), n: Int = 5): List<T> {
    val fav = preferred.filter { it in all }
    val pool = if (fav.size >= n) fav else all
    if (pool.size <= n) return pool
    return (0 until n).map { pool[(it * (pool.size - 1).toDouble() / (n - 1)).roundToInt()] }
}

private fun nearest(list: List<Double>, v: Double) = list.indices.minByOrNull { abs(list[it] - v) } ?: 0

/** A picker over a fixed list (ISO, shutter): presets, ‹ › through the whole list, slider snapping to each. */
@Composable
fun ListPicker(values: List<Double>, current: Double?, preferred: List<Double>, label: (Double) -> String, set: (Double) -> Unit,
               marked: List<Double> = emptyList(), markLabel: String = "BASE") {
    val i = current?.let { nearest(values, it) }
    var picks = presetValues(values, preferred).toMutableList()
    // Marked values (base ISO) and a familiar current value always get a preset.
    val keep = marked.filter { it in values }.toMutableList()
    if (current != null && current in preferred && current in values) keep += current
    for (c in keep) if (c !in picks && picks.isNotEmpty()) {
        val free = picks.indices.filter { picks[it] !in keep }
        val k = free.minByOrNull { abs(picks[it] - c) } ?: break
        picks[k] = c
        picks = picks.sorted().toMutableList()
    }
    SettingPicker(
        presets = picks.map { PickerOption(label(it), label(it), badge = if (it in marked) markLabel else null) },
        selected = current?.let(label),
        pick = { o -> values.firstOrNull { label(it) == o.id }?.let(set) },
        value = current?.let(label) ?: "–",
        prev = i?.takeIf { it > 0 }?.let { k -> { set(values[k - 1]) } },
        next = i?.takeIf { it < values.size - 1 }?.let { k -> { set(values[k + 1]) } },
        slider = if (values.size > 1) SliderSpec((i ?: 0).toDouble(), 0.0..(values.size - 1).toDouble(), values.size - 2) { idx ->
            val k = idx.roundToInt()
            if (k != i) set(values[k])  // only when the value changes
        } else null,
        valueBadge = current?.takeIf { it in marked }?.let { markLabel },
    )
}

/**
 * The camera's base (native) ISO: where its gain is 0 dB.
 *   1. ISO and gain lists that step together (as on the PYXIS): the ISO in 0 dB's place.
 *   2. Otherwise the current gain, if the camera reports it: current ISO ÷ gain (6 dB per stop).
 *   3. Otherwise Blackmagic's published native ISOs for the model.
 */
fun baseIsos(v: Map<String, JsonElement>): List<Double> {
    val isos = v["/video/supportedISOs"]["supportedISOs"].arr.mapNotNull { it.double }.sorted()
    val gains = v["/video/supportedGains"]["supportedGains"].arr.mapNotNull { it.double }.sorted()
    if (isos.isNotEmpty() && isos.size == gains.size) gains.indexOf(0.0).takeIf { it >= 0 }?.let { return listOf(isos[it]) }
    val iso = v["/video/iso"]["iso"].double
    val g = v["/video/gain"]["gain"].double
    if (isos.isNotEmpty() && iso != null && g != null) return listOf(isos[nearest(isos, iso / 10.0.pow(g / 20))])
    // whole words of the model name ("URSA Mini Pro 4.6K G2" is a 4.6K, not a 6K)
    val words = (v["/system/product"]["productName"].str ?: "").lowercase().split(' ', '-', '(', ')', '/').toSet()
    for ((key, base) in listOf("17k" to listOf(800.0), "12k" to listOf(800.0), "4.6k" to listOf(800.0),
            "6k" to listOf(400.0, 3200.0), "4k" to listOf(400.0, 3200.0)))
        if (key in words) return if (isos.isEmpty()) base else base.filter { it in isos }
    return emptyList()
}

/** Changes the recording format. The camera takes the whole format at once. */
fun setFormat(cam: Camera, change: MutableMap<String, JsonElement>.() -> Unit) {
    val f = cam.v("/system/format")
    val body = linkedMapOf<String, JsonElement>()
    for (k in listOf("codec", "frameRate", "offSpeedEnabled", "offSpeedFrameRate", "recordResolution", "sensorResolution"))
        f[k]?.let { body[k] = it }
    body.change()
    cam.put("/system/format", JsonObject(body))
}

/** The supported-format entry for the current resolution. */
fun currentFormatEntry(v: Map<String, JsonElement>): JsonElement? {
    val f = v["/system/format"]
    return v["/system/supportedFormats"]["supportedFormats"].arr.firstOrNull {
        it["recordResolution"] == f["recordResolution"] && it["sensorResolution"] == f["sensorResolution"]
    }
}

// ---- the quick panels ----

@Composable
fun QuickPanelView(cam: Camera, luts: MonitorLuts, panel: QuickPanel, close: () -> Unit) {
    DockedPanel {
        when (panel) {
            QuickPanel.ISO, QuickPanel.SHUTTER, QuickPanel.WB, QuickPanel.TINT, QuickPanel.FPS, QuickPanel.IRIS -> SettingPickerFor(cam, panel)
            QuickPanel.LUT -> LutChooser(cam, luts, close)
            else -> Column(Modifier.widthIn(max = 640.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(when (panel) { QuickPanel.POWER -> "POWER"; QuickPanel.MEDIA -> "MEDIA"; else -> "RECORD" },
                        style = HudStyle.text(13.sp, FontWeight.Bold, Color.White.copy(alpha = 0.75f)), modifier = Modifier.weight(1f))
                    Box(Modifier.size(36.dp).clickable(onClick = close).semantics { contentDescription = "Close" }, contentAlignment = Alignment.Center) {
                        Icon(Icons.Filled.Close, null, tint = Color.White)
                    }
                }
                when (panel) {
                    QuickPanel.POWER -> PowerPanel(cam)
                    QuickPanel.MEDIA -> MediaPanel(cam)
                    else -> RecordPanel(cam)
                }
            }
        }
    }
}

@Composable
private fun SettingPickerFor(cam: Camera, panel: QuickPanel) {
    val v = cam.watch()
    when (panel) {
        QuickPanel.ISO -> ListPicker(
            values = v["/video/supportedISOs"]["supportedISOs"].arr.mapNotNull { it.double },
            current = v["/video/iso"]["iso"].double,
            preferred = listOf(100.0, 200.0, 400.0, 800.0, 1250.0, 1600.0, 3200.0, 6400.0, 8000.0, 12800.0),
            label = { it.toInt().toString() }, set = { cam.put("/video/iso", json("iso" to it.toInt())) },
            marked = baseIsos(v))
        QuickPanel.SHUTTER -> {
            val s = v["/video/supportedShutters"]
            if (Show.speedMode(v)) ListPicker(s["shutterSpeeds"].arr.mapNotNull { it.double }, v["/video/shutter"]["shutterSpeed"].double,
                listOf(24.0, 48.0, 50.0, 60.0, 100.0, 125.0, 250.0, 500.0), { "1/${it.toInt()}" }, { cam.put("/video/shutter", json("shutterSpeed" to it.toInt())) })
            else ListPicker(s["shutterAngles"].arr.mapNotNull { it.double }, v["/video/shutter"]["shutterAngle"].double,
                listOf(4500.0, 9000.0, 17280.0, 18000.0, 27000.0, 36000.0), { Show.angle(it) }, { cam.put("/video/shutter", json("shutterAngle" to it.toInt())) })
        }
        QuickPanel.WB -> {
            val wb = v["/video/whiteBalance"]["whiteBalance"].double
            val d = v["/video/whiteBalance/description"]["whiteBalance"]
            val lo = d["min"].double ?: 2500.0; val hi = d["max"].double ?: 10000.0
            val set = { k: Double -> cam.put("/video/whiteBalance", json("whiteBalance" to k.coerceIn(lo, hi).toInt())) }
            val scope = rememberCoroutineScope()
            SettingPicker(
                presets = listOf(3200 to Icons.Filled.Lightbulb, 4000 to Icons.Filled.WbIncandescent, 4500 to Icons.Filled.WaterDrop,
                    5600 to Icons.Filled.WbSunny, 6500 to Icons.Filled.Cloud).map { (k, icon) -> PickerOption("$k", "${k}K", icon) },
                selected = wb?.toInt()?.toString(), pick = { set(it.id.toDouble()) },
                value = wb?.let { "${it.toInt()}K" } ?: "–",
                prev = wb?.takeIf { it > lo }?.let { w -> { set(w - 50) } }, next = wb?.takeIf { it < hi }?.let { w -> { set(w + 50) } },
                slider = SliderSpec(wb ?: 5600.0, lo..hi) { cam.putLive("/video/whiteBalance", json("whiteBalance" to ((it / 50).roundToInt() * 50))) },
                trailing = { OutlinedChip("AWB") { scope.launch {
                    cam.action("PUT", "/video/whiteBalance/doAuto"); cam.refresh("/video/whiteBalance"); cam.refresh("/video/whiteBalanceTint")
                } } })
        }
        QuickPanel.TINT -> {
            val t = v["/video/whiteBalanceTint"]["whiteBalanceTint"].double
            val d = v["/video/whiteBalanceTint/description"]["whiteBalanceTint"]
            val lo = d["min"].double ?: -50.0; val hi = d["max"].double ?: 50.0
            val set = { x: Double -> cam.put("/video/whiteBalanceTint", json("whiteBalanceTint" to x.coerceIn(lo, hi).toInt())) }
            SettingPicker(
                presets = listOf(-20, -10, 0, 10, 20).map { PickerOption("$it", "$it") },
                selected = t?.toInt()?.toString(), pick = { set(it.id.toDouble()) }, value = t?.toInt()?.toString() ?: "–",
                prev = t?.takeIf { it > lo }?.let { x -> { set(x - 1) } }, next = t?.takeIf { it < hi }?.let { x -> { set(x + 1) } },
                slider = SliderSpec(t ?: 0.0, lo..hi) { cam.putLive("/video/whiteBalanceTint", json("whiteBalanceTint" to it.roundToInt())) })
        }
        QuickPanel.FPS -> {
            val f = v["/system/format"]
            val rates = currentFormatEntry(v)["frameRates"].arr.mapNotNull { it.str }
            val off = f["offSpeedEnabled"].bool == true
            val presets = rates.map { PickerOption(it, it) }
            val pickRate = { o: PickerOption -> setFormat(cam) { this["frameRate"] = JsonPrimitive(o.id) } }
            val toggle: @Composable () -> Unit = { OutlinedChip("Off speed", filled = off) { setFormat(cam) { this["offSpeedEnabled"] = JsonPrimitive(!off) } } }
            if (off) {
                val lo = f["minOffSpeedFrameRate"].double ?: 12.0; val hi = f["maxOffSpeedFrameRate"].double ?: 60.0
                val os = f["offSpeedFrameRate"].double ?: lo
                val setOs = { x: Double -> setFormat(cam) { this["offSpeedFrameRate"] = JsonPrimitive(x.coerceIn(lo, hi).toInt()) } }
                SettingPicker(presets, f["frameRate"].str, pickRate, "${os.toInt()} fps",
                    prev = if (os > lo) ({ setOs(os - 1) }) else null, next = if (os < hi) ({ setOs(os + 1) }) else null,
                    slider = SliderSpec(os, lo..hi, (hi - lo).toInt() - 1) { x -> if (x.roundToInt().toDouble() != os) setOs(x.roundToInt().toDouble()) },
                    trailing = toggle, note = "Project ${f["frameRate"].str ?: ""} · sensor ${os.toInt()} fps")
            } else {
                val i = rates.indexOf(f["frameRate"].str ?: "")
                SettingPicker(presets, f["frameRate"].str, pickRate, f["frameRate"].str ?: "–",
                    prev = if (i > 0) ({ pickRate(presets[i - 1]) }) else null,
                    next = if (i in 0 until presets.size - 1) ({ pickRate(presets[i + 1]) }) else null, trailing = toggle)
            }
        }
        QuickPanel.IRIS -> {
            if (v["/lens/iris/description"]["controllable"].bool == true) {
                // the options follow the fitted lens's range; its widest aperture is always a preset, marked OPEN
                val d = v["/lens/iris/description"]["apertureStop"]
                val stops = irisStops(d["min"].double ?: 1.4, d["max"].double ?: 22.0)
                ListPicker(stops, v["/lens/iris"]["apertureStop"].double,
                    irisPresets(stops), { "f" + Show.trim(Math.round(it * 10) / 10.0) },
                    { cam.put("/lens/iris", json("apertureStop" to it)) }, marked = listOf(stops.first()), markLabel = "OPEN")
            } else Text("The lens has no electronic iris control. Set the iris on the lens.", style = HudStyle.text(15.sp),
                modifier = Modifier.padding(vertical = 18.dp))
        }
        else -> {}
    }
}

@Composable
private fun PowerPanel(cam: Camera) {
    val v = cam.watch()
    val p = v["/camera/power"]
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Source: ${p["source"].str ?: "–"}", style = HudStyle.text(14.sp))
        p["batteries"].arr.forEachIndexed { i, b ->
            Text("Battery ${i + 1}: ${b["chargeRemainingPercent"].int?.let { "$it%" } ?: "–"} · ${b["milliVolt"].int?.let { "%.2f V".format(it / 1000.0) } ?: "–"}",
                style = HudStyle.text(14.sp))
        }
        Text("SHOW BATTERY AS", style = HudStyle.label)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val mode = v["/camera/power/displayMode"]["mode"].str
            for (m in listOf("Percentage", "Voltage")) OutlinedChip(m, filled = mode == m) { cam.put("/camera/power/displayMode", json("mode" to m)) }
        }
    }
}

@Composable
private fun RecordPanel(cam: Camera) {
    val v = cam.watch()
    val scope = rememberCoroutineScope()
    val recording = Show.recording(v)
    val clock by cam.timecode.collectAsState()
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedChip(if (recording) "Stop" else "Record") {
                scope.launch { cam.setRecording(!recording) }
            }
            OutlinedChip("Still") { scope.launch { cam.post("/transports/0/doStillCapture") } }
            if (cam.has("/transports/0/prerecord")) OutlinedChip("Pre-record") { scope.launch { cam.post("/transports/0/prerecord") } }
        }
        val src = v["/transports/0/timecode/source"]
        Text("Timecode ${clock?.string() ?: "–"} · source ${src["timecodeInputSource"].str ?: "–"} (${src["source"].str ?: "–"})",
            style = HudStyle.text(12.sp, color = Color.White.copy(alpha = 0.7f)))
        val next = v["/slates/nextClip"]["clip"]
        Text("Next: reel ${next["reel"].int ?: 0} · scene ${next["scene"].str ?: ""} · take ${next["take"].int ?: 0}",
            style = HudStyle.text(12.sp, color = Color.White.copy(alpha = 0.7f)))
    }
}

@Composable
fun MediaPanel(cam: Camera) {
    val v = cam.watch()
    val ws = v["/media/workingset"]["workingset"].arr
    var formatTarget by remember { mutableStateOf<JsonElement?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        ws.forEachIndexed { i, m ->
            if (m.isNull) return@forEachIndexed
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("${i + 1} · ${m["volume"].str ?: m["deviceName"].str ?: ""}", style = HudStyle.text(15.sp, FontWeight.SemiBold))
                    Text("${m["clipCount"].int ?: 0} clips · ${Show.remaining(m["remainingRecordTime"].int ?: 0)} left · ${bytes(m["remainingSpace"].double)} of ${bytes(m["totalSpace"].double)} free",
                        style = HudStyle.text(12.sp, color = Color.White.copy(alpha = 0.65f)))
                }
                if (m["activeDisk"].bool == true) Text("RECORDING TO", style = HudStyle.text(10.sp, FontWeight.SemiBold).copy(shadow = null),
                    modifier = Modifier.background(HudStyle.accent, RoundedCornerShape(4.dp)).padding(5.dp))
                else OutlinedChip("Use") { cam.put("/media/active", json("workingsetIndex" to (m["index"].int ?: i))) }
                var menu by remember { mutableStateOf(false) }
                Box {
                    Box(Modifier.size(40.dp).clickable { menu = true }.semantics { contentDescription = "More" }, contentAlignment = Alignment.Center) {
                        Icon(Icons.Filled.MoreVert, null, tint = Color.White)
                    }
                    DropdownMenu(menu, { menu = false }) {
                        DropdownMenuItem(text = { Text("Format…", color = Color.Red) }, onClick = { menu = false; formatTarget = m })
                    }
                }
            }
        }
        if (ws.all { it.isNull }) Text("No media", style = HudStyle.text(14.sp))
    }
    formatTarget?.let { t -> FormatDialog(cam, t) { formatTarget = null } }
}

private fun bytes(b: Double?): String {
    if (b == null) return "–"
    val units = listOf("B", "KB", "MB", "GB", "TB"); var x = b; var u = 0
    while (x >= 1000 && u < units.size - 1) { x /= 1000; u++ }
    return "%.1f %s".format(x, units[u])
}

/** Erasing a card: the camera's two-step format (one-time key, then the format itself), behind a typed confirmation. */
@Composable
private fun FormatDialog(cam: Camera, m: JsonElement, done: () -> Unit) {
    val v = cam.watch()
    val device = m["deviceName"].str ?: ""
    var volume by remember { mutableStateOf(m["volume"].str ?: "") }
    val systems = v["/media/devices/doformatSupportedFilesystems"].arr.mapNotNull { it.str }.ifEmpty { listOf("ExFAT") }
    var fs by remember { mutableStateOf(systems.first()) }
    var confirm by remember { mutableStateOf("") }
    var working by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = done,
        title = { Text("Format $device") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Formatting erases all ${m["clipCount"].int ?: 0} clips on $device. This can't be undone.", color = Color(0xFFFF6B6B))
                OutlinedTextField(volume, { volume = it }, label = { Text("Volume name") }, singleLine = true)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { for (s in systems) OutlinedChip(s, filled = fs == s) { fs = s } }
                OutlinedTextField(confirm, { confirm = it.uppercase() }, label = { Text("Type ERASE to confirm") }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(enabled = confirm == "ERASE" && volume.isNotEmpty() && !working, onClick = {
                working = true
                scope.launch {
                    val path = "/media/devices/${android.net.Uri.encode(device)}/doformat"
                    val key = cam.get(path)["key"].str
                    if (key == null) cam.message.value = "The camera didn't give a format key"
                    else if (cam.action("PUT", path, json("key" to key, "filesystem" to fs, "volume" to volume))) done()
                    working = false
                }
            }) { Text("Format", color = Color.Red) }
        },
        dismissButton = { TextButton(onClick = done) { Text("Cancel") } },
    )
}

// ---- the monitor LUT chooser ----

private const val CAMERA_LUT = "/monitoring/Stream/displayLUT"

@Composable
fun rememberLutImporter(luts: MonitorLuts): () -> Unit {
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let { luts.importLut(it) } }
    return { launcher.launch(arrayOf("*/*")) }
}

@Composable
private fun LutChooser(cam: Camera, luts: MonitorLuts, close: () -> Unit) {
    val v = cam.watch()
    val on by luts.enabled.collectAsState()
    val choice by luts.choice.collectAsState()
    val imported by luts.imported.collectAsState()
    val import = rememberLutImporter(luts)
    val options = FilmLook.entries.map { MonitorLuts.Choice.Look(it) } + imported.map { MonitorLuts.Choice.File(it) }
    val cameraOn = v[CAMERA_LUT]["enabled"].bool == true
    Column(Modifier.widthIn(max = 720.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("MONITOR LUT", style = HudStyle.text(13.sp, FontWeight.Bold, Color.White.copy(alpha = 0.75f)), modifier = Modifier.weight(1f))
            OutlinedChip(if (on) "On" else "Off", filled = on) { luts.setEnabled(!on) }
            Box(Modifier.size(36.dp).clickable(onClick = close).semantics { contentDescription = "Close" }, contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Close, null, tint = Color.White)
            }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(22.dp), verticalAlignment = Alignment.CenterVertically) {
            for (c in options) {
                val sel = on && choice == c
                Column(Modifier.heightIn(min = 44.dp).clickable { luts.select(c) }.semantics { selected = sel },
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text(luts.name(c), style = HudStyle.text(17.sp), maxLines = 1)
                    Box(Modifier.padding(top = 5.dp).size(width = 60.dp, height = 2.5.dp).background(if (sel) Color.White else Color.Transparent))
                }
            }
            Row(Modifier.clickable(onClick = import).border(1.dp, Color.White.copy(alpha = 0.7f), RoundedCornerShape(6.dp))
                .padding(horizontal = 10.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Add, null, tint = Color.White, modifier = Modifier.size(18.dp))
                Text(" Import .cube", style = HudStyle.text(15.sp, FontWeight.SemiBold))
            }
        }
        if (on && cam.has(CAMERA_LUT) && !cameraOn) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Icon(Icons.Filled.Warning, null, tint = Color(0xFFFFD60A))
                Text("The stream is the camera's log picture: its LUT is off. The film looks are made for Rec.709.",
                    style = HudStyle.text(12.sp), modifier = Modifier.weight(1f))
                OutlinedChip("Turn camera LUT on") { cam.put(CAMERA_LUT, json("enabled" to true)) }
            }
        } else if (on && !cam.has(CAMERA_LUT) && v["/system/dynamicRange"]["dynamicRange"].str == "Film") {
            // cameras without a separate Stream output: warn from the dynamic range instead
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Icon(Icons.Filled.Warning, null, tint = Color(0xFFFFD60A))
                Text("The camera is in Film dynamic range, so the stream may be log. The film looks are made for Rec.709: " +
                    "turn on a display LUT for the output the camera streams, or use Video dynamic range.",
                    style = HudStyle.text(12.sp), modifier = Modifier.weight(1f))
            }
        } else Text("Applied in this app only, on top of the camera's Rec.709 picture.", style = HudStyle.text(12.sp, color = Color.White.copy(alpha = 0.6f)))
    }
}

/**
 * Third-stop f-numbers the lens can reach (as marked on lenses and shown by the camera). The
 * lens's widest aperture takes the place of the nearest marked stop when it isn't one (f/1.75 for f/1.8).
 */
fun irisStops(lo: Double, hi: Double): List<Double> {
    val marked = listOf(1.0, 1.1, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.2, 3.5, 4.0, 4.5, 5.0, 5.6, 6.3, 7.1, 8.0, 9.0, 10.0, 11.0,
        13.0, 14.0, 16.0, 18.0, 20.0, 22.0, 25.0, 29.0, 32.0)
    val stops = marked.filter { it > lo + 0.01 && it <= hi + 0.01 }.toMutableList()
    if (stops.isNotEmpty() && stops.first() - lo < 0.1) stops.removeAt(0)
    return listOf(lo) + stops
}

/** Iris presets: wide open, then the next four full stops at least 2/3 stop smaller
 *  (f/1.75 lens: OPEN, 2.8, 4, 5.6, 8; f/2.8 lens: OPEN, 4, 5.6, 8, 11). */
fun irisPresets(stops: List<Double>): List<Double> {
    val open = stops.firstOrNull() ?: return emptyList()
    val full = listOf(1.0, 1.4, 2.0, 2.8, 4.0, 5.6, 8.0, 11.0, 16.0, 22.0, 32.0)
    return listOf(open) + full.filter { it >= open * 1.25 && it in stops }.take(4)
}

package com.matthewyak.pyxisviewer

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlin.math.roundToInt

// The full camera menu: every control the camera's API offers that this camera supports
// (anything it answers "not supported" for is left out), grouped like the camera's own menus.
// Same sections as the iPhone app.

private val PageBg = Color(0xFF111214)
private val RowBg = Color(0xFF1E1F23)
private val Dim = Color.White.copy(alpha = 0.6f)

@Composable
fun CameraMenu(cam: Camera, luts: MonitorLuts, relayHost: String, setRelay: (String) -> Unit, ssid: String,
               rejoin: (() -> Unit)?, done: () -> Unit) {
    val stack = remember { mutableStateListOf("home") }
    BackHandler { if (stack.size > 1) stack.removeAt(stack.lastIndex) else done() }
    val page = stack.last()
    val v = cam.watch()
    val link by cam.link.collectAsState()
    Column(Modifier.fillMaxSize().background(PageBg).safeDrawingPadding()) {
        Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            if (stack.size > 1) Box(Modifier.size(44.dp).clickable { stack.removeAt(stack.lastIndex) }, contentAlignment = Alignment.Center) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = Color.White)
            } else Spacer(Modifier.width(44.dp))
            Text(if (page == "home") v["/system/product"]["productName"].str ?: "Camera" else page,
                color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f).padding(start = 8.dp))
            TextButton(onClick = done) { Text("Done", color = HudStyle.accent, fontSize = 16.sp) }
        }
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)) {
            when (page) {
                "home" -> {
                    Group {
                        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(9.dp).background(when (link) { is Camera.Link.Connected -> Color.Green
                                is Camera.Link.NeedsLogin, is Camera.Link.Failed -> Color.Red; else -> Color(0xFFFF9500) }, CircleShape))
                            Text(linkText(link, v), color = Color.White, fontSize = 14.sp, modifier = Modifier.padding(start = 10.dp))
                        }
                    }
                    if (cam.isConnected) Group {
                        for (p in listOf("Record", "Monitor", "Audio", "Color", "Lens", "Slate", "Presets & camera LUTs", "Setup", "Livestream"))
                            NavRow(p) { stack += p }
                    }
                    Group { NavRow("Monitor LUTs") { stack += "Monitor LUTs" } }
                    Footer("LUTs applied in this app to the picture you watch. The camera isn't changed.")
                    Group { NavRow("Connection") { stack += "Connection" } }
                }
                "Record" -> RecordMenu(cam, v)
                "Monitor" -> MonitorMenu(cam, v)
                "Audio" -> AudioMenu(cam, v)
                "Color" -> ColorMenu(cam, v)
                "Lens" -> LensMenu(cam, v)
                "Slate" -> SlateMenu(cam, v)
                "Presets & camera LUTs" -> PresetsMenu(cam, v)
                "Setup" -> SetupMenu(cam, v)
                "Livestream" -> StreamMenu(cam, v)
                "Monitor LUTs" -> MonitorLutMenu(cam, luts, v)
                "Connection" -> ConnectionMenu(cam, relayHost, setRelay, ssid, rejoin)
            }
            Spacer(Modifier.heightIn(min = 24.dp))
        }
    }
}

private fun linkText(link: Camera.Link, v: Map<String, JsonElement>) = when (link) {
    Camera.Link.Off -> "Camera control off"
    Camera.Link.Searching -> "Looking for the camera…"
    is Camera.Link.Connecting -> "Connecting to the camera at ${link.host}…"
    is Camera.Link.Connected -> "${v["/system/product"]["productName"].str ?: "Camera"} at ${link.host} · firmware ${v["/system/product"]["softwareVersion"].str ?: "?"}"
    is Camera.Link.NeedsLogin -> "The camera at ${link.host} needs its Secure Login (Connection)"
    is Camera.Link.Failed -> link.message
}

// ---- building blocks ----

@Composable
private fun Group(title: String? = null, content: @Composable () -> Unit) {
    title?.let { Text(it.uppercase(), color = Dim, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 4.dp, top = 14.dp, bottom = 4.dp)) }
    Column(Modifier.fillMaxWidth().background(RowBg, RoundedCornerShape(12.dp))) { content() }
}

@Composable
private fun Footer(text: String) = Text(text, color = Dim, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp))

@Composable
private fun NavRow(title: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).heightIn(min = 52.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(title, color = Color.White, fontSize = 16.sp, modifier = Modifier.weight(1f))
        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = Dim)
    }
}

@Composable
private fun ToggleRow(title: String, on: Boolean, set: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { set(!on) }.heightIn(min = 52.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(title, color = Color.White, fontSize = 16.sp, modifier = Modifier.weight(1f))
        Switch(on, set, colors = SwitchDefaults.colors(checkedTrackColor = HudStyle.accent))
    }
}

@Composable
private fun PickerRow(title: String, options: List<String>, selected: String?, label: (String) -> String = { it }, pick: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        Row(Modifier.fillMaxWidth().clickable { open = true }.heightIn(min = 52.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(title, color = Color.White, fontSize = 16.sp, modifier = Modifier.weight(1f))
            Text(selected?.let(label) ?: "–", color = HudStyle.accent, fontSize = 15.sp)
        }
        DropdownMenu(open, { open = false }) {
            for (o in options) DropdownMenuItem(text = { Text(label(o)) }, onClick = { open = false; pick(o) },
                trailingIcon = { if (o == selected) Icon(Icons.Filled.Check, null) })
        }
    }
}

@Composable
private fun SliderRow(label: String, value: Double, range: ClosedFloatingPointRange<Double>, text: (Double) -> String, set: (Double) -> Unit) {
    var dragging by remember { mutableStateOf<Float?>(null) }
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = Dim, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(72.dp))
        Slider(dragging ?: value.toFloat(), { dragging = it; set(it.toDouble()) }, Modifier.weight(1f),
            valueRange = range.start.toFloat()..range.endInclusive.toFloat(), onValueChangeFinished = { dragging = null })
        Text(text((dragging?.toDouble()) ?: value), color = Color.White, fontSize = 14.sp, modifier = Modifier.widthIn(min = 64.dp).padding(start = 8.dp))
    }
}

@Composable
private fun StepperRow(title: String, value: Int, range: IntRange, set: (Int) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Text("$title $value", color = Color.White, fontSize = 16.sp, modifier = Modifier.weight(1f))
        TextButton(enabled = value > range.first, onClick = { set(value - 1) }) { Text("−", fontSize = 20.sp) }
        TextButton(enabled = value < range.last, onClick = { set(value + 1) }) { Text("+", fontSize = 20.sp) }
    }
}

/** A text field that sends its value when editing ends. */
@Composable
private fun TextRow(title: String, value: String, commit: (String) -> Unit) {
    var text by remember(value) { mutableStateOf(value) }
    OutlinedTextField(text, { text = it }, label = { Text(title) }, singleLine = true,
        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
        keyboardActions = KeyboardActions(onDone = { if (text != value) commit(text) }),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp)
            .onFocusChanged { if (!it.isFocused && text != value) commit(text) })
}

@Composable
private fun ButtonRow(title: String, color: Color = HudStyle.accent, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).heightIn(min = 52.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(title, color = color, fontSize = 16.sp)
    }
}

@Composable
private fun InfoRow(title: String, value: String) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(title, color = Color.White, fontSize = 16.sp, modifier = Modifier.weight(1f))
        Text(value, color = Dim, fontSize = 15.sp)
    }
}

private fun flag(cam: Camera, v: Map<String, JsonElement>, path: String, key: String = "enabled") =
    (v[path][key].bool == true) to { on: Boolean -> cam.put(path, json(key to on)) }

@Composable
private fun Flag(cam: Camera, v: Map<String, JsonElement>, title: String, path: String, key: String = "enabled") {
    val (on, set) = flag(cam, v, path, key)
    ToggleRow(title, on, set)
}

fun codecName(c: String) = if (c.startsWith("BRaw:")) "BRAW " + c.removePrefix("BRaw:").replace('_', ':') else c

// ---- pages ----

@Composable
private fun RecordMenu(cam: Camera, v: Map<String, JsonElement>) {
    val scope = rememberCoroutineScope()
    val f = v["/system/format"]
    val formats = v["/system/supportedFormats"]["supportedFormats"].arr
    val entry = currentFormatEntry(v)
    Group("Format") {
        val labels = formats.map { e ->
            "${e["resolutionDescriptor"]["description"].str ?: ""} · ${e["recordResolution"]["width"].int}×${e["recordResolution"]["height"].int}" +
                if (e["sensorResolution"] != e["recordResolution"]) " (scaled)" else ""
        }
        val cur = formats.indexOfFirst { it["recordResolution"] == f["recordResolution"] && it["sensorResolution"] == f["sensorResolution"] }
        PickerRow("Resolution", labels, labels.getOrNull(cur)) { l ->
            val e = formats[labels.indexOf(l)]
            setFormat(cam) {
                this["recordResolution"] = e["recordResolution"]!!; this["sensorResolution"] = e["sensorResolution"]!!
                val codecs = e["codecs"].arr.mapNotNull { it.str }
                if (this["codec"].str !in codecs) codecs.firstOrNull()?.let { this["codec"] = JsonPrimitive(it) }
                val rates = e["frameRates"].arr.mapNotNull { it.str }
                if (this["frameRate"].str !in rates) rates.firstOrNull()?.let { this["frameRate"] = JsonPrimitive(it) }
            }
        }
        PickerRow("Codec", entry["codecs"].arr.mapNotNull { it.str }, f["codec"].str, ::codecName) { c -> setFormat(cam) { this["codec"] = JsonPrimitive(c) } }
        PickerRow("Project frame rate", entry["frameRates"].arr.mapNotNull { it.str }, f["frameRate"].str) { r -> setFormat(cam) { this["frameRate"] = JsonPrimitive(r) } }
        ToggleRow("Off-speed", f["offSpeedEnabled"].bool == true) { on -> setFormat(cam) { this["offSpeedEnabled"] = JsonPrimitive(on) } }
        if (f["offSpeedEnabled"].bool == true)
            StepperRow("Sensor frame rate", f["offSpeedFrameRate"].int ?: 24, (f["minOffSpeedFrameRate"].int ?: 12)..(f["maxOffSpeedFrameRate"].int ?: 60)) { x ->
                setFormat(cam) { this["offSpeedFrameRate"] = JsonPrimitive(x) }
            }
    }
    Group("Exposure") {
        PickerRow("Shutter shown as", listOf("ShutterAngle", "ShutterSpeed"), v["/video/shutter/measurement"]["measurement"].str,
            { if (it == "ShutterAngle") "Angle" else "Speed" }) { cam.put("/video/shutter/measurement", json("measurement" to it)) }
        if (cam.has("/video/autoExposure")) PickerRow("Auto exposure", listOf("Off", "OneShot", "Continuous"), v["/video/autoExposure"]["mode"].str,
            { if (it == "OneShot") "One shot" else it }) { cam.put("/video/autoExposure", json("mode" to it)) }
        val gains = v["/video/supportedGains"]["supportedGains"].arr.mapNotNull { it.int }
        if (gains.isNotEmpty()) PickerRow("Gain", gains.map { "$it" }, v["/video/gain"]["gain"].int?.toString(), { "${if ((it.toIntOrNull() ?: 0) > 0) "+" else ""}$it dB" }) {
            cam.put("/video/gain", json("gain" to it.toInt()))
        }
        if (cam.has("/video/ndFilter")) PickerRow("ND filter", v["/video/supportedNDFilters"]["supportedStops"].arr.mapNotNull { it.double }.map { Show.trim(it) },
            v["/video/ndFilter"]["stop"].double?.let { Show.trim(it) }, { "$it stops" }) { cam.put("/video/ndFilter", json("stop" to it.toDouble())) }
        val ff = v["/video/flickerFreeShutters"]["shutterAngles"].arr.mapNotNull { it.double }
        if (ff.isNotEmpty()) InfoRow("Flicker-free angles", ff.joinToString(", ") { Show.angle(it) })
    }
    Footer("ISO, shutter, white balance and tint are in the top bar.")
    if (cam.has("/system/dynamicRange")) Group("Image") {
        PickerRow("Dynamic range", v["/system/supportedDynamicRanges"]["supportedDynamicRanges"].arr.mapNotNull { it.str },
            v["/system/dynamicRange"]["dynamicRange"].str) { cam.put("/system/dynamicRange", json("dynamicRange" to it)) }
        if (cam.has("/system/colorScience")) PickerRow("Color science", v["/system/supportedColorSciences"]["supportedColorSciences"].arr.mapNotNull { it.str },
            v["/system/colorScience"]["colorScience"].str) { cam.put("/system/colorScience", json("colorScience" to it)) }
        if (cam.has("/video/detailSharpeningLevel")) {
            Flag(cam, v, "Detail sharpening", "/video/detailSharpening")
            PickerRow("Sharpening level", listOf("Low", "Medium", "High"), v["/video/detailSharpeningLevel"]["level"].str) {
                cam.put("/video/detailSharpeningLevel", json("level" to it))
            }
        }
    }
    Group("Recording") {
        if (cam.has("/transports/0/proxyRecording")) Flag(cam, v, "Record proxies", "/transports/0/proxyRecording")
        if (cam.has("/luts/recordWithLUT")) Flag(cam, v, "Embed LUT in clips", "/luts/recordWithLUT")
        if (cam.has("/transports/0/prerecord/auto")) {
            Flag(cam, v, "Pre-record (always buffering)", "/transports/0/prerecord/auto", "autoEnabled")
            PickerRow("Pre-record length", v["/transports/0/prerecord/supportedMaxDurations"].arr.mapNotNull { it.int }.map { "$it" },
                v["/transports/0/prerecord/maxDuration"]["maxDuration"].int?.toString(), { "$it s" }) {
                cam.put("/transports/0/prerecord/maxDuration", json("maxDuration" to it.toInt()))
            }
        }
        ButtonRow("Capture a still") { scope.launch { cam.post("/transports/0/doStillCapture") } }
    }
    Group("Media") { Box(Modifier.background(Color(0xFF16171A)).padding(12.dp)) { MediaPanel(cam) } }
}

@Composable
private fun MonitorMenu(cam: Camera, v: Map<String, JsonElement>) {
    val displays = v["/monitoring/display"]["displays"].arr.mapNotNull { it.str }.filter { cam.has("/monitoring/$it/cleanFeed") }.ifEmpty { listOf("LCD") }
    var display by remember { mutableStateOf(displays.first()) }
    val name = { d: String -> when (d) { "FrontUSBC" -> "Front USB-C"; "RearUSBC" -> "Rear USB-C"; "MainSDI" -> "SDI"; else -> d } }
    val d = "/monitoring/$display"
    Group { PickerRow("Display", displays, display, name) { display = it } }
    Footer("Overlays and LUT per camera output. \"Stream\" is the picture this app shows.")
    Group(name(display)) {
        Flag(cam, v, "Clean feed (no overlays)", "$d/cleanFeed")
        Flag(cam, v, "Display LUT", "$d/displayLUT")
        Flag(cam, v, "Zebra", "$d/zebra")
        Flag(cam, v, "Focus assist", "$d/focusAssist")
        Flag(cam, v, "Frame guide", "$d/frameGuide")
        Flag(cam, v, "Grids", "$d/frameGrids")
        Flag(cam, v, "Safe area", "$d/safeArea")
        Flag(cam, v, "False color", "$d/falseColor")
        if (v["$d/brightness"]["adjustable"].bool == true)
            SliderRow("BRIGHT", v["$d/brightness"]["brightness"].double ?: 50.0, 0.0..100.0, { "${it.roundToInt()}" }) {
                cam.putLive("$d/brightness", json("brightness" to it.roundToInt()))
            }
    }
    val z = v["/monitoring/zebra"]
    Group("Zebra") {
        PickerRow("Highlight level", listOf("75", "80", "85", "90", "95", "100"), z["highlight"]["level"].int?.toString(), { "$it%" }) {
            cam.put("/monitoring/zebra", json("highlight" to json("level" to it.toInt(), "enabled" to (z["highlight"]["enabled"].bool ?: true))))
        }
        ToggleRow("Highlight zebra", z["highlight"]["enabled"].bool == true) {
            cam.put("/monitoring/zebra", json("highlight" to json("enabled" to it, "level" to (z["highlight"]["level"].int ?: 100))))
        }
        PickerRow("Skin tone", listOf("None", "Middle Grey", "Middle Grey +1", "Blowout Threshold"), z["skinTone"]["type"].str) {
            cam.put("/monitoring/zebra", json("skinTone" to json("type" to it, "enabled" to (it != "None"))))
        }
    }
    val fa = v["/monitoring/focusAssist"]
    Group("Focus assist") {
        PickerRow("Style", listOf("Peak", "ColoredLines"), fa["mode"].str, { if (it == "ColoredLines") "Colored lines" else it }) {
            cam.put("/monitoring/focusAssist", json("mode" to it))
        }
        PickerRow("Line color", listOf("Red", "Green", "Blue", "White", "Black"), fa["color"].str) { cam.put("/monitoring/focusAssist", json("color" to it)) }
        SliderRow("LEVEL", fa["intensity"].double ?: 50.0, 0.0..100.0, { "${it.roundToInt()}%" }) { cam.putLive("/monitoring/focusAssist", json("intensity" to it.roundToInt())) }
    }
    Group("Guides") {
        PickerRow("Frame guide", v["/monitoring/frameGuideRatio/presets"]["presets"].arr.mapNotNull { it.str }, v["/monitoring/frameGuideRatio"]["ratio"].str) {
            cam.put("/monitoring/frameGuideRatio", json("ratio" to it))
        }
        val grids = v["/monitoring/frameGrids"]["frameGrids"].arr.mapNotNull { it.str }
        for (g in listOf("Thirds", "Crosshair", "Dot", "Horizon")) ToggleRow("Grid: ${g.lowercase()}", g in grids) { on ->
            val new = if (on) grids + g else grids - g
            cam.put("/monitoring/frameGrids", json("frameGrids" to JsonArray(new.map { JsonPrimitive(it) })))
        }
        SliderRow("SAFE", v["/monitoring/safeAreaPercent"]["percent"].double ?: 90.0, 50.0..100.0, { "${it.roundToInt()}%" }) {
            cam.putLive("/monitoring/safeAreaPercent", json("percent" to it.roundToInt()))
        }
    }
}

@Composable
private fun AudioMenu(cam: Camera, v: Map<String, JsonElement>) {
    val count = v["/audio/channels"]["channels"].int ?: 2
    for (ch in 0 until count) {
        val base = "/audio/channel/$ch"
        if (!cam.has("$base/input")) continue
        val desc = v["$base/input/description"]["description"]
        val caps = desc["capabilities"][0]
        val lo = desc["gainRange"]["Min"].double ?: -6.0; val hi = desc["gainRange"]["Max"].double ?: 6.0
        Group("Channel ${ch + 1}") {
            PickerRow("Input", v["$base/supportedInputs"].arr.filter { it["available"].bool != false }.mapNotNull { it["input"].str },
                v["$base/input"]["input"].str) { cam.put("$base/input", json("input" to it)) }
            if (hi > lo) SliderRow("GAIN", v["$base/level"]["gain"].double ?: 0.0, lo..hi, { (if (it > 0) "+" else "") + Show.trim(Math.round(it * 2) / 2.0) + " dB" }) {
                cam.putLive("$base/level", json("gain" to Math.round(it * 2) / 2.0))
            }
            if (caps["PhantomPower"].bool == true) Flag(cam, v, "Phantom power (+48V)", "$base/phantomPower")
            if (caps["Padding"]["available"].bool == true) Flag(cam, v, "Pad", "$base/padding")
            if (caps["LowCutFilter"].bool == true) Flag(cam, v, "Low cut filter", "$base/lowCutFilter")
        }
    }
}

@Composable
private fun ColorMenu(cam: Camera, v: Map<String, JsonElement>) {
    for ((title, path, range, neutral) in listOf(
        Quad("Lift", "/colorCorrection/lift", -2.0..2.0, 0.0), Quad("Gamma", "/colorCorrection/gamma", -4.0..4.0, 0.0),
        Quad("Gain", "/colorCorrection/gain", 0.0..16.0, 1.0), Quad("Offset", "/colorCorrection/offset", -8.0..8.0, 0.0))) {
        Group(title) {
            for (k in listOf("red", "green", "blue", "luma"))
                SliderRow(k.uppercase(), v[path][k].double ?: neutral, range, { "%.2f".format(it) }) { cam.putLive(path, json(k to it)) }
        }
    }
    val c = v["/colorCorrection/contrast"]
    Group("Contrast") {
        SliderRow("PIVOT", c["pivot"].double ?: 0.5, 0.0..1.0, { "%.2f".format(it) }) { cam.putLive("/colorCorrection/contrast", json("pivot" to it)) }
        SliderRow("ADJUST", c["adjust"].double ?: 1.0, 0.0..2.0, { "%.2f".format(it) }) { cam.putLive("/colorCorrection/contrast", json("adjust" to it)) }
    }
    val col = v["/colorCorrection/color"]
    Group("Color") {
        SliderRow("HUE", col["hue"].double ?: 0.0, -1.0..1.0, { "%.0f°".format(it * 180) }) { cam.putLive("/colorCorrection/color", json("hue" to it)) }
        SliderRow("SAT", col["saturation"].double ?: 1.0, 0.0..2.0, { "%.0f%%".format(it * 100) }) { cam.putLive("/colorCorrection/color", json("saturation" to it)) }
        SliderRow("LUMA MIX", v["/colorCorrection/lumaContribution"]["lumaContribution"].double ?: 1.0, 0.0..1.0, { "%.0f%%".format(it * 100) }) {
            cam.putLive("/colorCorrection/lumaContribution", json("lumaContribution" to it))
        }
    }
    Group {
        ButtonRow("Reset all color correction", Color(0xFFFF6B6B)) {
            for ((p, n) in listOf("/colorCorrection/lift" to 0.0, "/colorCorrection/gamma" to 0.0, "/colorCorrection/gain" to 1.0, "/colorCorrection/offset" to 0.0))
                cam.put(p, json("red" to n, "green" to n, "blue" to n, "luma" to n))
            cam.put("/colorCorrection/contrast", json("pivot" to 0.5, "adjust" to 1.0))
            cam.put("/colorCorrection/color", json("hue" to 0.0, "saturation" to 1.0))
            cam.put("/colorCorrection/lumaContribution", json("lumaContribution" to 1.0))
        }
    }
}

private data class Quad(val a: String, val b: String, val c: ClosedFloatingPointRange<Double>, val d: Double)

@Composable
private fun LensMenu(cam: Camera, v: Map<String, JsonElement>) {
    val scope = rememberCoroutineScope()
    val irisOk = v["/lens/iris/description"]["controllable"].bool == true
    val focusOk = v["/lens/focus/description"]["controllable"].bool == true
    val zoomOk = v["/lens/zoom/description"]["controllable"].bool == true
    val af = v["/lens/focus/autoFocus/description"]
    if (!irisOk && !focusOk && !zoomOk) Footer("The lens on the camera has no electronic control (or isn't reporting it). Iris, focus and zoom are set on the lens.")
    Group {
        if (irisOk) SliderRow("IRIS", v["/lens/iris"]["normalised"].double ?: v["/lens/iris"]["normalized"].double ?: 0.0, 0.0..1.0, { Show.iris(v) }) {
            cam.putLive("/lens/iris", json("normalised" to it))
        }
        if (focusOk) SliderRow("FOCUS", v["/lens/focus"]["normalised"].double ?: v["/lens/focus"]["normalized"].double ?: 0.0, 0.0..1.0, { "%.0f%%".format(it * 100) }) {
            cam.putLive("/lens/focus", json("normalised" to it))
        }
        if (af["supported"].bool == true) {
            ButtonRow("Autofocus") { scope.launch { cam.action("PUT", "/lens/focus/doAutoFocus", json("position" to json("x" to 0.5, "y" to 0.5))) } }
            PickerRow("Autofocus mode", af["supportedModes"].arr.mapNotNull { it.str }, v["/lens/focus/autoFocus"]["mode"].str) {
                cam.put("/lens/focus/autoFocus", json("mode" to it))
            }
        }
        if (zoomOk) SliderRow("ZOOM", v["/lens/zoom"]["normalised"].double ?: v["/lens/zoom"]["normalized"].double ?: 0.0, 0.0..1.0,
            { v["/lens/zoom"]["focalLength"].double?.let { f -> "${f.toInt()}mm" } ?: "" }) { cam.putLive("/lens/zoom", json("normalised" to it)) }
        if (v["/lens/opticalImageStabilization"]["controlAvailable"].bool == true) Flag(cam, v, "Image stabilisation", "/lens/opticalImageStabilization")
    }
}

@Composable
private fun SlateMenu(cam: Camera, v: Map<String, JsonElement>) {
    val scope = rememberCoroutineScope()
    val s = v["/slates/nextClip"]
    val clip = s["clip"]; val lens = s["lens"]; val project = s["project"]
    fun put(section: String, key: String, value: Any) = cam.put("/slates/nextClip", json(section to json(key to value)))
    Group("Next clip") {
        StepperRow("Reel", clip["reel"].int ?: 1, 1..999) { put("clip", "reel", it) }
        TextRow("Scene", clip["scene"].str ?: "") { put("clip", "scene", it) }
        StepperRow("Take", clip["take"].int ?: 1, 1..99) { put("clip", "take", it) }
        Flag(cam, v, "Auto-increment take", "/slates/takeAutoIncrement")
        PickerRow("Shot", listOf("None", "WS", "MS", "MCU", "CU", "BCU", "ECU"), clip["shotType"].str) { put("clip", "shotType", it) }
        PickerRow("Take type", listOf("None", "PU", "VFX", "SER"), clip["takeType"].str) { put("clip", "takeType", it) }
        PickerRow("Location", listOf("Interior", "Exterior"), clip["sceneLocation"].str) { put("clip", "sceneLocation", it) }
        PickerRow("Time", listOf("Day", "Night"), clip["sceneTime"].str) { put("clip", "sceneTime", it) }
        ToggleRow("Good take", clip["goodTake"].bool == true) { put("clip", "goodTake", it) }
    }
    Group("Project") {
        for ((k, t) in listOf("projectName" to "Project", "director" to "Director", "camera" to "Camera", "cameraOperator" to "Operator"))
            TextRow(t, project[k].str ?: "") { put("project", k, it) }
        ButtonRow("Clear project details") { scope.launch { cam.post("/slates/nextClip/resetProjectData"); cam.refresh("/slates/nextClip") } }
    }
    Group("Lens") {
        for ((k, t) in listOf("lensType" to "Lens", "iris" to "Iris", "focalLength" to "Focal length", "distance" to "Distance", "filter" to "Filter"))
            TextRow(t, lens[k].str ?: "") { put("lens", k, it) }
        ButtonRow("Clear lens details") { scope.launch { cam.post("/slates/nextClip/resetLensData"); cam.refresh("/slates/nextClip") } }
    }
}

@Composable
private fun PresetsMenu(cam: Camera, v: Map<String, JsonElement>) {
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { cam.refresh("/presets"); cam.refresh("/luts/slots/0") }
    val presets = v["/presets"]["presets"].arr.mapNotNull { it.str }
    val active = v["/presets/active"]["preset"].str
    var newName by remember { mutableStateOf("") }
    fun enc(s: String) = android.net.Uri.encode(s)
    Group("Presets") {
        if (presets.isEmpty()) InfoRow("No presets saved on the camera", "")
        for (p in presets) Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(start = 16.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(p, color = Color.White, fontSize = 16.sp, modifier = Modifier.weight(1f).clickable { cam.put("/presets/active", json("preset" to p)) })
            if (p == active) Icon(Icons.Filled.Check, null, tint = HudStyle.accent)
            TextButton(onClick = { scope.launch { cam.action("PUT", "/presets/${enc(p)}") } }) { Text("Update") }
            Box(Modifier.size(44.dp).clickable { scope.launch { cam.action("DELETE", "/presets/${enc(p)}"); cam.refresh("/presets") } }, contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Delete, "Delete $p", tint = Color(0xFFFF6B6B))
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(newName, { newName = it }, label = { Text("New preset name") }, singleLine = true, modifier = Modifier.weight(1f).padding(8.dp))
            TextButton(enabled = newName.isNotBlank(), onClick = {
                val n = newName.trim()
                scope.launch { if (cam.action("PUT", "/presets/${enc(n)}")) { newName = ""; cam.refresh("/presets") } }
            }) { Text("Save current") }
        }
    }
    Footer("Tap a preset to load it. Update saves the camera's current settings into it.")
    val slot0 = v["/luts/slots/0"]
    Group("Camera LUT (slot 1)") {
        for (l in v["/luts"]["luts"].arr) {
            val file = l["fileName"].str ?: continue
            Row(Modifier.fillMaxWidth().clickable { cam.put("/luts/slots/0", json("fileName" to file)) }.heightIn(min = 56.dp).padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(l["title"].str ?: file, color = Color.White, fontSize = 16.sp)
                    Text("${l["inputColorScience"].str ?: ""} → ${l["outputGamut"].str ?: ""} ${l["outputGamma"].str ?: ""}", color = Dim, fontSize = 12.sp)
                }
                if (slot0["fileName"].str == file) Icon(Icons.Filled.Check, null, tint = HudStyle.accent)
            }
        }
    }
    Footer("The LUT loaded in the camera. Turn it on per output in Monitor (the Stream output feeds this app).")
}

@Composable
private fun SetupMenu(cam: Camera, v: Map<String, JsonElement>) {
    val scope = rememberCoroutineScope()
    val p = v["/system/product"]
    Group("Camera") {
        Flag(cam, v, "Color bars", "/camera/colorBars")
        Flag(cam, v, "Program feed on LCD", "/camera/programFeedDisplay")
        PickerRow("Tally", listOf("None", "Preview", "Program"), v["/camera/tallyStatus"]["status"].str) { cam.put("/camera/tallyStatus", json("status" to it)) }
        PickerRow("Battery shown as", listOf("Percentage", "Voltage"), v["/camera/power/displayMode"]["mode"].str) { cam.put("/camera/power/displayMode", json("mode" to it)) }
    }
    val buttons = v["/panel/devices"].arr.filter { it["enabled"].bool != false }
    if (buttons.isNotEmpty()) {
        Group("Function buttons") {
            for (b in buttons) ButtonRow("Press ${b["label"].str ?: ""} (${b["name"].str ?: ""})") {
                scope.launch { cam.action("PUT", "/panel/devices/${b["name"].str}/state", json("action" to "press")) }
            }
        }
        Footer("Does whatever the button is assigned to on the camera.")
    }
    Group("Info") {
        InfoRow("Model", p["productName"].str ?: "–")
        InfoRow("Name", p["deviceName"].str ?: "–")
        InfoRow("Firmware", p["softwareVersion"].str ?: "–")
        InfoRow("Camera ID", v["/camera/id"]["id"].int?.toString() ?: "–")
        InfoRow("Reference lock", if (v["/camera/timingReferenceLock"]["locked"].bool == true) "Locked" else "Not locked")
        InfoRow("Timecode source", v["/transports/0/timecode/source"]["timecodeInputSource"].str ?: "–")
        InfoRow("Network access", v["/access/status"]["availability"].str ?: "–")
    }
    val projects = v["/cloud/projects"].arr
    if (projects.isNotEmpty()) Group("Blackmagic Cloud") {
        InfoRow("Active project", v["/cloud/projects/active"]["name"].str ?: "None")
        for (pr in projects) InfoRow(pr["name"].str ?: "", (pr["status"]["uploadPercent"].int ?: -1).let { if (it >= 0) "$it% uploaded" else "Idle" })
    }
}

@Composable
private fun StreamMenu(cam: Camera, v: Map<String, JsonElement>) {
    val scope = rememberCoroutineScope()
    val s = v["/livestreams/0"]
    val a = v["/livestreams/0/activePlatform"]
    val streaming = s["status"].str == "Streaming" || s["status"].str == "Connecting"
    var profiles by remember { mutableStateOf(listOf<String>()) }
    suspend fun load(platform: String) {
        profiles = cam.get("/livestreams/platforms/${android.net.Uri.encode(platform)}")["profiles"].arr.mapNotNull { it["profile"].str }
    }
    LaunchedEffect(a["platform"].str) { a["platform"].str?.let { load(it) } }
    Group("Status") {
        InfoRow("State", s["status"].str ?: "–")
        s["bitrate"].double?.takeIf { it > 0 }?.let { InfoRow("Bitrate", "%.1f Mb/s".format(it / 1e6)) }
        s["effectiveVideoFormat"].str?.let { InfoRow("Format", it) }
        s["cache"].double?.let { InfoRow("Cache", "%.0f%%".format(it)) }
        ButtonRow(if (streaming) "Stop streaming" else "Start streaming", if (streaming) Color(0xFFFF6B6B) else HudStyle.accent) {
            scope.launch { cam.action("PUT", if (streaming) "/livestreams/0/stop" else "/livestreams/0/start") }
        }
    }
    Footer("This app watches the camera through this stream: stopping it stops the picture here.")
    Group("Destination") {
        PickerRow("Platform", v["/livestreams/platforms"].arr.mapNotNull { it.str }, a["platform"].str) { p ->
            cam.put("/livestreams/0/activePlatform", json("platform" to p)); scope.launch { load(p) }
        }
        if (profiles.isNotEmpty()) PickerRow("Quality", profiles, a["quality"].str) { cam.put("/livestreams/0/activePlatform", json("quality" to it)) }
        a["server"].str?.let { InfoRow("Server", it) }
    }
}

@Composable
private fun MonitorLutMenu(cam: Camera, luts: MonitorLuts, v: Map<String, JsonElement>) {
    val on by luts.enabled.collectAsState()
    val choice by luts.choice.collectAsState()
    val imported by luts.imported.collectAsState()
    val import = rememberLutImporter(luts)
    Group { ToggleRow("Monitor LUT", on) { luts.setEnabled(it) } }
    Footer("Applied by this app to the picture you watch, like a LUT on a field monitor. The camera, its outputs and recordings aren't changed. Tap the LUT button to switch it on and off; hold it to choose.")
    @Composable fun row(c: MonitorLuts.Choice, sub: String?, delete: (() -> Unit)? = null) {
        Row(Modifier.fillMaxWidth().clickable { luts.select(c) }.heightIn(min = 56.dp).padding(start = 16.dp, end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(luts.name(c), color = Color.White, fontSize = 16.sp)
                sub?.let { Text(it, color = Dim, fontSize = 12.sp) }
            }
            if (on && choice == c) Icon(Icons.Filled.Check, null, tint = HudStyle.accent)
            delete?.let { d -> Box(Modifier.size(44.dp).clickable(onClick = d), contentAlignment = Alignment.Center) { Icon(Icons.Filled.Delete, "Delete", tint = Color(0xFFFF6B6B)) } }
        }
    }
    Group("Film looks") { for (l in FilmLook.entries) row(MonitorLuts.Choice.Look(l), l.blurb) }
    Footer("Made for Rec.709: they go on top of the camera's own LUT on its Stream output (e.g. Film to Extended Video), like a look LUT after a technical conversion.")
    Group("Your LUTs") {
        for (f in imported) row(MonitorLuts.Choice.File(f), null) { luts.delete(f) }
        ButtonRow("Import a .cube LUT…", onClick = import)
    }
    Footer("3D .cube LUTs from your files, up to 129 points.")
    if (cam.has("/monitoring/Stream/displayLUT")) {
        Group { Flag(cam, v, "Camera LUT on the stream", "/monitoring/Stream/displayLUT") }
        Footer("The camera's own LUT on its Stream output: it turns the camera's log picture into Rec.709. Keep it on for the film looks here.")
    }
}

@Composable
private fun ConnectionMenu(cam: Camera, relayHost: String, setRelay: (String) -> Unit, ssid: String, rejoin: (() -> Unit)?) {
    var user by remember { mutableStateOf(cam.username) }
    var pass by remember { mutableStateOf(cam.password) }
    Group {
        InfoRow("Relay", relayHost.ifBlank { WiFi.RELAY_NAME })
        InfoRow("Camera", cam.host.ifBlank { "Looking for it…" })
    }
    Footer("Found by themselves: the relay on the PYXIS-Stream Wi-Fi, the camera through the relay.")
    Group("Camera control") {
        OutlinedTextField(user, { user = it }, singleLine = true, label = { Text("Secure Login username (if used)") }, modifier = Modifier.fillMaxWidth().padding(8.dp))
        OutlinedTextField(pass, { pass = it }, singleLine = true, label = { Text("Secure Login password") },
            visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth().padding(8.dp))
    }
    Footer("Needs Web media manager on (Blackmagic Camera Setup → Network Access). A login is only needed when it's set to \"Enabled with security only\"; it's stored encrypted on this phone and only sent over HTTPS.")
    if (ssid.isNotEmpty()) Group("Wi-Fi") {
        InfoRow("Network", ssid)
        rejoin?.let { ButtonRow("Join $ssid again", onClick = it) }
    }
    Group {
        ButtonRow("Save and reconnect") {
            cam.manualHost = ""; cam.username = user; cam.password = pass
            cam.start(relayHost)
        }
    }
}

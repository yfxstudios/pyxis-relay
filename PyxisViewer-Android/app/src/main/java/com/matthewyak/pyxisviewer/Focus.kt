package com.matthewyak.pyxisviewer

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.GpsFixed
import androidx.compose.material.icons.outlined.Face
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Color
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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlin.math.hypot

// Autofocus: tap the picture to focus there, and a thin rail (swipe in from the right edge)
// to pick the mode. Only shown when the camera reports autofocus for the fitted lens.
// Same as the iPhone app's Focus.swift.
//
// Camera coordinates are 0...1 across the picture. A target is set by its centre point; the
// camera reports its target box (and detected faces) by top-left corner and size, as
// measured on the PYXIS (point 0.5,0.5 -> box x 0.441, y 0.411, w 0.118, h 0.178).

enum class AFMode(val api: String, val title: String) {
    SINGLE("OneShot", "Single autofocus (AF-S)"),
    CONTINUOUS("Continuous", "Continuous autofocus (AF-C)"),
    FACE("TrackFace", "Face tracking"),
    OBJECT("TrackObject", "Object tracking");
}

object AF {
    const val STATUS = "/lens/focus/autoFocus"
    const val TARGET = "/lens/focus/autoFocus/target"
    const val FACES = "/lens/focus/autoFocus/detectedFaces"

    fun supported(cam: Camera, v: Map<String, JsonElement>) =
        cam.isConnected && v["/lens/focus/autoFocus/description"]["supported"].bool == true

    fun modes(v: Map<String, JsonElement>): List<AFMode> {
        val listed = v["/lens/focus/autoFocus/description"]["supportedModes"].arr.mapNotNull { it.str }
        return AFMode.entries.filter { listed.isEmpty() || it.api in listed }
    }

    fun mode(v: Map<String, JsonElement>) = v[STATUS]["mode"].str?.let { m -> AFMode.entries.firstOrNull { it.api == m } }
    fun state(v: Map<String, JsonElement>) = v[STATUS]["state"].str ?: "Idle"

    fun setMode(cam: Camera, m: AFMode) = cam.put(STATUS, json("mode" to m.api, "enabled" to true))

    /** Focus on a point of the picture (0...1), the way the current mode does it. */
    fun focus(cam: Camera, scope: CoroutineScope, px: Double, py: Double) {
        val x = px.coerceIn(0.0, 1.0); val y = py.coerceIn(0.0, 1.0)
        val point = json("x" to x, "y" to y)
        val v = cam.values.value
        when (mode(v) ?: AFMode.SINGLE) {
            AFMode.SINGLE -> scope.launch { cam.action("PUT", "/lens/focus/doAutoFocus", json("position" to point)) }
            AFMode.CONTINUOUS -> cam.put(TARGET, point)  // continuous AF follows the target area
            AFMode.OBJECT -> scope.launch {
                cam.action("PUT", TARGET, point)
                cam.action("PUT", "/lens/focus/autoFocus/retrigger")  // start tracking what's there
            }
            AFMode.FACE -> {
                // the detected face under (or nearest) the tap; no faces: focus on the point instead
                val nearest = v[FACES]["detectedFaces"].arr.minByOrNull { distance(it, x, y) }
                val i = nearest?.get("index")?.int
                if (i != null) scope.launch { cam.action("PUT", "/lens/focus/autoFocus/trackFace", json("faceIndex" to i)) }
                else cam.put(TARGET, point)
            }
        }
    }

    private fun distance(face: JsonElement, x: Double, y: Double): Double {
        val b = face["position"]
        val cx = (b["x"].double ?: 0.0) + (b["width"].double ?: 0.0) / 2
        val cy = (b["y"].double ?: 0.0) + (b["height"].double ?: 0.0) / 2
        return hypot(cx - x, cy - y)
    }

    /** A camera box (top-left + size, 0...1) in view pixels. */
    fun rect(b: JsonElement?, video: Rect): Rect? {
        val x = b["x"].double ?: return null; val y = b["y"].double ?: return null
        val w = b["width"].double ?: return null; val h = b["height"].double ?: return null
        val l = video.left + (x * video.width).toFloat(); val t = video.top + (y * video.height).toFloat()
        return Rect(l, t, l + (w * video.width).toFloat(), t + (h * video.height).toFloat())
    }
}

/** The letterboxed picture's place in a view of the given size (as the video view draws it). */
fun videoRect(viewW: Float, viewH: Float, size: Pair<Int, Int>): Rect {
    val va = size.first.toFloat() / size.second; val sa = viewW / viewH
    val w = if (va > sa) viewW else viewH * va
    val h = if (va > sa) viewW / va else viewH
    return Rect((viewW - w) / 2, (viewH - h) / 2, (viewW + w) / 2, (viewH + h) / 2)
}

/**
 * What's drawn over the picture: the tapped focus box (white while focusing, green when
 * focused, red on an error), the camera's tracking area in AF-C/Object, faces in Face mode.
 */
@Composable
fun FocusOverlay(cam: Camera, video: Rect, tap: Offset?, result: String?, showAreas: Boolean) {
    val v = cam.watch()
    val mode = AF.mode(v)
    Canvas(Modifier.fillMaxSize()) {
        if (showAreas && (mode == AFMode.CONTINUOUS || mode == AFMode.OBJECT))
            AF.rect(v[AF.TARGET], video)?.let { corners(it, Color.White.copy(alpha = 0.85f), 1.5.dp.toPx()) }
        if (showAreas && mode == AFMode.FACE)
            for (f in v[AF.FACES]["detectedFaces"].arr) AF.rect(f["position"], video)?.let {
                drawRoundRect(Color.White.copy(alpha = 0.9f), it.topLeft, it.size,
                    androidx.compose.ui.geometry.CornerRadius(4.dp.toPx()), style = Stroke(1.5.dp.toPx()))
            }
        if (tap != null) {
            // the camera only says "Focused" briefly (AF-S returns to Idle), so the result is kept
            val state = result ?: AF.state(v)
            val color = when (state) { "Focused" -> Color.Green; "Error" -> Color.Red; else -> Color.White }
            val c = Offset(video.left + tap.x * video.width, video.top + tap.y * video.height)
            val half = 35.dp.toPx()
            corners(Rect(c.x - half, c.y - half, c.x + half, c.y + half), color, 2.dp.toPx())
        }
    }
}

/** A focus-box outline drawn as four corners. */
private fun DrawScope.corners(r: Rect, color: Color, width: Float) {
    val l = minOf(r.width, r.height) * 0.28f
    for ((corner, dx, dy) in listOf(Triple(r.topLeft, 1f, 1f), Triple(r.topRight, -1f, 1f),
        Triple(r.bottomLeft, 1f, -1f), Triple(r.bottomRight, -1f, -1f))) {
        drawLine(color, Offset(corner.x + dx * l, corner.y), corner, width)
        drawLine(color, corner, Offset(corner.x, corner.y + dy * l), width)
    }
}

/** The autofocus mode rail: a thin column of icons at the right edge. */
@Composable
fun AFModeRail(cam: Camera, picked: () -> Unit) {
    val v = cam.watch()
    val current = AF.mode(v)
    val haptic = LocalHapticFeedback.current
    Column(
        Modifier.shadow(3.dp, RoundedCornerShape(topStart = 12.dp, bottomStart = 12.dp))
            .background(HudStyle.picker, RoundedCornerShape(topStart = 12.dp, bottomStart = 12.dp)).padding(6.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        for (m in AF.modes(v)) {
            val on = m == current
            val fg = if (on) Color.Black else Color.White
            Box(
                Modifier.size(44.dp).background(if (on) Color.White else Color.Transparent, RoundedCornerShape(8.dp))
                    .clickable { haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove); AF.setMode(cam, m); picked() }
                    .semantics { contentDescription = m.title; selected = on },
                contentAlignment = Alignment.Center
            ) {
                when (m) {
                    AFMode.SINGLE, AFMode.CONTINUOUS -> Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("AF", color = fg, fontSize = 10.sp, fontWeight = FontWeight.Black, lineHeight = 11.sp)
                        Text(if (m == AFMode.SINGLE) "S" else "C", color = fg, fontSize = 13.sp, fontWeight = FontWeight.Black, lineHeight = 14.sp)
                    }
                    AFMode.FACE -> Icon(Icons.Outlined.Face, null, tint = fg, modifier = Modifier.size(22.dp))
                    AFMode.OBJECT -> Icon(Icons.Filled.GpsFixed, null, tint = fg, modifier = Modifier.size(22.dp))
                }
            }
        }
    }
}

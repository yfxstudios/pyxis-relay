package com.matthewyak.pyxisviewer

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.lifecycleScope
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlin.math.abs

class MainActivity : ComponentActivity() {
    private val player = StreamPlayer()
    private lateinit var cam: Camera
    private lateinit var luts: MonitorLuts
    private lateinit var capture: Capture
    private val prefs by lazy { getSharedPreferences("app", Context.MODE_PRIVATE) }

    private val relay = MutableStateFlow("")
    private val ssid = MutableStateFlow("")
    private val joining = MutableStateFlow<String?>(null)  // what we're doing while joining, shown on screen
    private val flash = MutableStateFlow<String?>(null)
    private var resumed = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        cam = Camera(applicationContext, lifecycleScope)
        luts = MonitorLuts(applicationContext, lifecycleScope)
        capture = Capture(applicationContext, lifecycleScope)
        capture.cameraName = { cam.v("/system/product")["productName"].str }
        relay.value = prefs.getString("relay", "") ?: ""
        ssid.value = prefs.getString("ssid", "") ?: ""
        lifecycleScope.launch { cam.message.collect { it?.let { m -> flash.value = m; cam.message.value = null } } }
        lifecycleScope.launch { luts.message.collect { it?.let { m -> flash.value = m; luts.message.value = null } } }
        lifecycleScope.launch { capture.message.collect { it?.let { m -> flash.value = m; capture.message.value = null } } }
        lifecycleScope.launch {
            player.state.collect {
                if (it is StreamPlayer.State.Playing) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
        }
        handle(intent)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = HudStyle.accent)) { Root() }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    override fun onResume() {
        super.onResume()
        resumed = true
        if (joining.value == null) lifecycleScope.launch { ensureNetwork(); connect() }
    }

    /** Android only keeps the relay's Wi-Fi while the app runs: join it again when it's needed
     *  (Android remembers the approval, so there's no prompt the second time). */
    private suspend fun ensureNetwork() {
        val s = ssid.value; val r = relay.value
        if (s.isEmpty() || r.isEmpty() || WiFi.relayReachable(r)) return
        joining.value = "Joining $s…"
        WiFi.join(this, s, SecretStore.read(this, "wifi"))?.let { flash.value = it }
        joining.value = null
    }

    override fun onPause() {
        super.onPause()
        resumed = false
        capture.stopRecording()
        player.stop()
        cam.stop()
    }

    private fun connect() {
        val r = relay.value
        if (r.isEmpty() || !resumed) return
        player.play(r)
        cam.start(r)
    }

    private fun setRelay(r: String) {
        relay.value = r
        prefs.edit().putString("relay", r).apply()
    }

    /** A pyxisviewer://join link, from the relay's QR code (camera app or the in-app scanner). */
    private fun handle(intent: Intent?) {
        val link = JoinLink.parse(intent?.data) ?: return
        intent?.data = null
        join(link)
    }

    private fun join(link: JoinLink) {
        setRelay(link.relay)
        if (link.ssid.isNotEmpty()) {
            ssid.value = link.ssid
            prefs.edit().putString("ssid", link.ssid).apply()
            SecretStore.save(this, "wifi", link.password)
        }
        player.stop(); cam.stop()
        lifecycleScope.launch {
            if (link.ssid.isNotEmpty() && !WiFi.relayReachable(link.relay)) {
                joining.value = "Joining ${link.ssid}…"
                WiFi.join(this@MainActivity, link.ssid, link.password)?.let { flash.value = it }
            }
            joining.value = null
            connect()
        }
    }

    private fun rejoin() {
        val s = ssid.value.ifEmpty { return }
        join(JoinLink(s, SecretStore.read(this, "wifi"), relay.value))
    }

    private fun scan() {
        GmsBarcodeScanning.getClient(this).startScan()
            .addOnSuccessListener { code ->
                val link = JoinLink.parse(code.rawValue?.let(Uri::parse))
                if (link != null) join(link) else flash.value = "That isn't a camera relay QR code."
            }
            .addOnFailureListener { flash.value = "Couldn't scan: ${it.message}" }
    }

    private fun systemBars(show: Boolean) {
        val c = WindowCompat.getInsetsController(window, window.decorView)
        c.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        if (show) c.show(WindowInsetsCompat.Type.systemBars()) else c.hide(WindowInsetsCompat.Type.systemBars())
    }

    @Composable
    private fun Root() {
        val relayHost by relay.collectAsState()
        val joinText by joining.collectAsState()
        var menu by remember { mutableStateOf(false) }
        Box(Modifier.fillMaxSize().background(Color.Black)) {
            when {
                joinText != null -> Centered { CircularProgressIndicator(color = Color.White); Text(joinText!!, color = Color.White, modifier = Modifier.padding(top = 16.dp)) }
                relayHost.isEmpty() -> Welcome()
                else -> Viewer { menu = true }
            }
            if (menu) CameraMenu(cam, luts, relayHost, { setRelay(it); player.stop(); connect() }, ssid.collectAsState().value,
                if (ssid.collectAsState().value.isNotEmpty()) ::rejoin else null) { menu = false }
            Flash()
        }
    }

    @Composable
    private fun Viewer(openMenu: () -> Unit) {
        val state by player.state.collectAsState()
        val link by cam.link.collectAsState()
        var clean by remember { mutableStateOf(false) }
        var panel by remember { mutableStateOf<QuickPanel?>(null) }
        // Full screen while viewing: the status and navigation bars stay hidden (swipe in from
        // an edge to bring them back for a moment).
        DisposableEffect(Unit) { systemBars(false); onDispose { systemBars(true) } }
        val swipe = with(LocalDensity.current) { 60.dp.toPx() }
        val v = cam.watch()
        val afOK = AF.supported(cam, v)
        val size by player.size.collectAsState()
        // tap-to-focus: the last tap (0...1 on the picture) while its box shows, and the camera's verdict
        var focusTap by remember { mutableStateOf<Offset?>(null) }
        var focusTapId by remember { mutableIntStateOf(0) }
        var focusResult by remember { mutableStateOf<String?>(null) }
        var rail by remember { mutableStateOf(false) }
        var railHideAt by remember { mutableLongStateOf(0L) }
        val afState = AF.state(v)
        LaunchedEffect(afState) { if (focusTap != null && (afState == "Focused" || afState == "Error")) focusResult = afState }
        LaunchedEffect(focusTapId) { if (focusTap != null) { delay(2500); focusTap = null } }
        LaunchedEffect(railHideAt) { if (rail) { delay(maxOf(0, railHideAt - System.currentTimeMillis())); rail = false } }
        fun openRail(seconds: Double) { rail = true; railHideAt = System.currentTimeMillis() + (seconds * 1000).toLong() }
        val haptic = LocalHapticFeedback.current
        BoxWithConstraints(Modifier.fillMaxSize()) {
            val compact = maxWidth < maxHeight
            val video = with(LocalDensity.current) { videoRect(maxWidth.toPx(), maxHeight.toPx(), size) }
            AndroidView({ VideoView(it, player, luts.box, capture) }, Modifier.fillMaxSize())
            FocusOverlay(cam, video, focusTap, focusResult, showAreas = !clean && afOK)
            // Swipe up or down anywhere on the picture: controls away (clean feed) and back.
            // Swipe right to left on the picture: the autofocus mode rail (left to right closes it).
            // (Not from the screen edge: in full screen Android keeps edge swipes for its nav buttons.)
            // A tap closes the AF rail or a picker, brings the controls back, or focuses there.
            Box(Modifier.fillMaxSize()
                .pointerInput(afOK) {
                    var dx = 0f
                    detectHorizontalDragGestures(onDragStart = { dx = 0f }, onDragEnd = {
                        if (afOK && dx < -swipe) openRail(5.0) else if (dx > swipe) rail = false
                    }) { _, d -> dx += d }
                }
                .pointerInput(Unit) {
                    var total = 0f
                    detectVerticalDragGestures(onDragStart = { total = 0f },
                        onDragEnd = { if (abs(total) > swipe) { clean = !clean; panel = null } }) { _, dy -> total += dy }
                }
                .pointerInput(video, afOK) {
                    detectTapGestures { p ->
                        when {
                            rail -> rail = false
                            panel != null -> panel = null
                            clean -> clean = false
                            afOK && video.contains(p) && video.width > 0 -> {
                                val n = Offset((p.x - video.left) / video.width, (p.y - video.top) / video.height)
                                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                                AF.focus(cam, lifecycleScope, n.x.toDouble(), n.y.toDouble())
                                focusResult = null; focusTap = n; focusTapId++
                            }
                        }
                    }
                })
            Status(state)
            AnimatedVisibility(!clean, enter = fadeIn(), exit = fadeOut()) {
                Column(Modifier.fillMaxSize().safeDrawingPadding()) {
                    TopBar(cam, compact, panel, { panel = it }, openMenu)
                    if (link !is Camera.Link.Connected) LinkChip(link)
                    capture.recordingSince.collectAsState().value?.let {
                        Box(Modifier.fillMaxWidth().padding(top = 6.dp), contentAlignment = Alignment.Center) { LocalRecordingPill(it) }
                    }
                    Spacer(Modifier.weight(1f))
                    val p = panel
                    if (p != null) QuickPanelView(cam, luts, p) { panel = null }
                    else {
                        if (compact) Box(Modifier.fillMaxWidth().padding(end = 8.dp, bottom = 4.dp), contentAlignment = Alignment.CenterEnd) {
                            CaptureButtons(capture)
                        }
                        BottomBar(cam, luts, capture, compact, panel) { panel = it }
                    }
                }
            }
            AnimatedVisibility(rail && afOK, Modifier.align(Alignment.CenterEnd).safeDrawingPadding(),
                enter = slideInHorizontally { it } + fadeIn(), exit = slideOutHorizontally { it } + fadeOut()) {
                Box(Modifier.pointerInput(Unit) {
                    var dx = 0f
                    detectHorizontalDragGestures(onDragStart = { dx = 0f }, onDragEnd = { if (dx > 24.dp.toPx()) rail = false }) { _, d -> dx += d }
                }) { AFModeRail(cam) { openRail(1.2) } }
            }
        }
    }

    @Composable
    private fun Status(state: StreamPlayer.State) {
        val text = when (state) {
            StreamPlayer.State.Playing -> null
            StreamPlayer.State.Idle, StreamPlayer.State.Connecting -> "Connecting to the relay at ${relay.value}…"
            StreamPlayer.State.Offline -> "Waiting for the camera's stream…"
            is StreamPlayer.State.Failed -> state.message
        } ?: return
        Centered {
            if (state !is StreamPlayer.State.Failed) CircularProgressIndicator(color = Color.White.copy(alpha = 0.8f))
            Text(text, style = HudStyle.text(15.sp), textAlign = TextAlign.Center, modifier = Modifier.padding(top = 14.dp, start = 24.dp, end = 24.dp))
        }
    }

    @Composable
    private fun LinkChip(link: Camera.Link) {
        val text = when (link) {
            Camera.Link.Off -> return
            Camera.Link.Searching -> "Looking for the camera…"
            is Camera.Link.Connecting -> "Connecting to the camera…"
            is Camera.Link.NeedsLogin -> "Camera needs its Secure Login (menu → Connection)"
            is Camera.Link.Failed -> "Camera control: ${link.message}"
            is Camera.Link.Connected -> return
        }
        Box(Modifier.fillMaxWidth().padding(top = 6.dp), contentAlignment = Alignment.Center) {
            Text(text, color = Color.White, fontSize = 12.sp,
                modifier = Modifier.background(Color.Black.copy(alpha = 0.55f), RoundedCornerShape(50)).padding(horizontal = 12.dp, vertical = 5.dp))
        }
    }

    @Composable
    private fun Welcome() {
        // connect as soon as the relay answers by name (no address to type)
        LaunchedEffect(Unit) {
            while (true) {
                if (WiFi.relayReachable(WiFi.RELAY_NAME)) { setRelay(WiFi.RELAY_NAME); connect(); break }
                delay(3000)
            }
        }
        Centered {
            Text("PYXIS Viewer", color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.SemiBold)
            Text("Scan the QR code on the relay's settings page. It joins the PYXIS-Stream Wi-Fi and opens the picture.",
                color = Color.White.copy(alpha = 0.7f), textAlign = TextAlign.Center, modifier = Modifier.widthIn(max = 360.dp).padding(16.dp))
            Button(::scan, colors = ButtonDefaults.buttonColors(containerColor = HudStyle.accent, contentColor = Color.White)) { Text("Scan QR code") }
            Spacer(Modifier.height(28.dp))
            Text("Already on the PYXIS-Stream Wi-Fi? The picture starts by itself.", color = Color.White.copy(alpha = 0.6f), fontSize = 13.sp)
        }
    }

    @Composable
    private fun Flash() {
        val text by flash.collectAsState()
        LaunchedEffect(text) { if (text != null) { delay(3500); flash.value = null } }
        AnimatedVisibility(text != null, Modifier.fillMaxSize(), enter = fadeIn(), exit = fadeOut()) {
            Box(Modifier.fillMaxSize().safeDrawingPadding().padding(bottom = 96.dp), contentAlignment = Alignment.BottomCenter) {
                Text(text ?: "", color = Color.White, fontSize = 14.sp, textAlign = TextAlign.Center,
                    modifier = Modifier.padding(horizontal = 24.dp).background(Color.Black.copy(alpha = 0.75f), RoundedCornerShape(10.dp)).padding(12.dp))
            }
        }
    }
}

@Composable
private fun Centered(content: @Composable () -> Unit) {
    Column(Modifier.fillMaxSize().safeDrawingPadding(), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) { content() }
}

# PYXIS Viewer for Android

The Android version of the iPhone app (`../PyxisViewer-iOS`), with the same features:

- **One QR code.** The relay's settings-page QR (`pyxisviewer://join?ssid=…&pass=…&relay=…`) opens the app. It joins **PYXIS-Stream** itself (Android shows its own "Connect?" prompt the first time) and plays. If the camera app on your phone doesn't open the link, use **Scan QR code** on the app's welcome screen.
- **No address to type.** Already on the PYXIS-Stream Wi-Fi, the app finds the relay at `pyxis-relay.local`
  by itself; the camera is found through the relay.
- **Live picture.** RTSP from the relay (`rtsp://<relay>:8554/live/pyxis`), hardware H.264/H.265 decode in low-latency mode, frames shown as soon as they're decoded.
- **Camera control** laid out like the camera's touchscreen:
  - Top bar: FPS, shutter, iris, ISO, WB, tint, timecode and battery.
  - Bottom bar: record, media slots and LUT.
  - Tap a setting for the docked picker. Presets are marked BASE, and the ISO slider snaps to the camera's ISOs.
  - The menu (top-left) has everything else: Record, Monitor (including the Stream output), Audio, Color, Lens, Slate, Presets & camera LUTs, Setup, Livestream and Connection.
- **Autofocus** (when the lens supports it), same as the iPhone app:
  - Tap the picture to focus there. The box turns green when the camera says it's focused, red on an error.
  - Swipe right to left on the picture for the mode rail (AF-S, AF-C, face tracking, object tracking); left to right closes it. It isn't an edge swipe, because in full screen Android keeps edge swipes for its nav buttons.
  - In AF-C and Object modes the tracking area is shown; in Face mode, the detected faces (tap one to track it).
- **Full screen.** The status and nav bars stay hidden while you watch; swipe in from a screen edge to show them for a moment.
- **Capture on the phone:** FRAME saves the current picture as a full-resolution PNG; LOCAL records it to an
  H.264 MP4 (about 20 Mb/s at 1080p). Both are what you see, monitor LUT included, saved to the gallery
  (Pictures/PYXIS Viewer, Movies/PYXIS Viewer). Not the camera's own recording. Video only.
- **Clean feed.** Swipe up or down on the picture to hide all controls. Swipe again, or tap, to bring them back.
- **Monitor LUTs** applied in the app on the GPU (Rec.709 → look):
  - Six film looks.
  - Import your own `.cube` files.
  - Tap LUT to toggle; hold to choose.
  - The camera isn't changed.
- **Wi-Fi.** Android only keeps the app's join while the app runs, so it rejoins PYXIS-Stream by itself when it opens and the relay isn't reachable. There's no prompt after the first time.
- **Secure Login.** Optional. The username and password are kept encrypted (Android Keystore) and sent only over HTTPS.

## Build and install

Needs JDK 17 and the Android SDK (platform 36). From this folder:

```bash
./gradlew :app:assembleRelease
```

The APK is `app/build/outputs/apk/release/app-release.apk`. It's signed with the debug key, which is fine for sideloading. To install it, plug in the phone with USB debugging on:

```bash
adb install -r app/build/outputs/apk/release/app-release.apk
```

Android 10 or newer.

## Files

| File | What it does |
|---|---|
| `Rtsp.kt` | RTSP client (RTP over TCP) and H.264/H.265 depacketizer |
| `Player.kt` | MediaCodec decoder and the OpenGL video view with the 3D LUT |
| `Camera.kt` | Blackmagic camera REST and WebSocket API, timecode clock, encrypted login store |
| `Hud.kt`, `Pickers.kt`, `Menu.kt` | Camera-style controls, docked pickers, full menu |
| `Capture.kt` | Frame grabs and local recordings (encoder, MP4, gallery) |
| `Focus.kt` | Tap-to-focus, focus/face boxes, AF mode rail |
| `MonitorLuts.kt` | Film looks, `.cube` import |
| `JoinLink.kt` | QR link and joining the Wi-Fi |
| `MainActivity.kt` | Screens, gestures, deep link, QR scanner |

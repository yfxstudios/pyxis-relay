# PYXIS Viewer for iPhone, iPad and Mac

Watch the PYXIS 12K live on an iPhone or iPad with one scan, or on a Mac (see [On the Mac](#on-the-mac)). The QR code on the relay's settings page
opens this app. The app joins the relay's Wi-Fi itself and starts the picture.

```
Camera app scans QR  ->  "Open in PYXIS Viewer"  ->  iOS asks "Join PYXIS-Stream?"  ->  live picture
```

## The QR code

The relay's settings page (`http://192.168.50.1/`, Watch card) shows it. **Print QR card** makes a card to
put next to the camera. It's built from the relay's current Wi-Fi name, password and address, so it stays
right if you change them. Re-print after changing the Wi-Fi password.

It holds a link:

```
pyxisviewer://join?ssid=PYXIS-Stream&pass=<Wi-Fi password>&relay=192.168.50.1
```

Like any Wi-Fi QR code, it contains the Wi-Fi password, so anyone who can see it can join.

The app has to be installed first. Without it, the Camera app shows nothing for this code. (A web link that
falls back to an install page would need a website and an App Store or TestFlight listing.)

## Playback

The app plays the relay's RTSP stream (`rtsp://<relay>:8554/live/pyxis`) itself:

- RTSP with RTP over the same TCP connection. No player buffer.
- An RTP depacketizer for H.264 and H.265 (the same logic as the R5C's HDMI player). After a lost packet it
  waits for the next keyframe, so a damaged picture is never shown.
- `AVSampleBufferDisplayLayer` for hardware decode, with every frame marked "display immediately". The
  picture is as current as the network allows, with no fixed delay.
- Video only. For sound, use the relay's HLS stream in Safari (about 4–8 s behind).
- It reconnects by itself when the camera stops and restarts, the relay restarts, or the Wi-Fi drops. It
  stops in the background and resumes when you return to it.

Tap the picture to show or hide the status (resolution, frame rate) and the settings button.

## Camera control

The picture carries a camera-style overlay, laid out like the PYXIS's own touchscreen:

- **Top:** menu · FPS · shutter angle (or speed) · iris · timecode (red while recording) · ISO · white balance
  · tint · battery (percent or voltage, as the camera is set).
- **Bottom:** record button · card slots (active card highlighted, remaining record time) · **LUT**, the
  monitor LUT (see below).

On a phone held upright the bars sit above and below the picture. In landscape they lie over it, as on the
camera.

**Clean feed:** swipe up or down on the picture to hide every control, the status bar included. Swipe
again or tap to bring them back.

Tap a setting in the top bar to open its picker, docked along the bottom in place of the bottom bar, as on
the camera. A row of presets runs across it, with the current one underlined. Below that, ‹ › step
through every value and a slider covers the whole range. Tap another setting to switch, or tap the
picture to close.

| Tap | Presets | ‹ › and slider |
|---|---|---|
| FPS | The format's project frame rates | Project rates, or the sensor rate with **Off speed** on |
| SA / SHUTTER | Familiar angles (or speeds) | Every supported angle (or speed) |
| IRIS | – | Half-stop steps and iris position, for lenses the camera can drive |
| ISO | Familiar ISOs, always including the current one and base ISO (marked BASE) | Every supported ISO |
| WB | Tungsten, fluorescent, mixed, daylight, cloudy, plus **AWB** | 50K steps across the camera's range |
| TINT | −20, −10, 0, 10, 20 | Steps of 1 across the camera's range |

Battery, the timecode (record controls) and the card slots open docked panels in the same place. Shutter
angle/speed display, auto exposure, gain and ND (when the camera has it) are under Menu → Record →
Exposure.

The bracket icon opens the full menu:

- **Record:** exposure (shutter display, auto exposure, gain, ND), resolution, codec, frame rate,
  off-speed, dynamic range, color science, sharpening, proxies, LUT in clips, pre-record, stills, media.
- **Monitor:** per output (LCD, front and rear USB-C, SDI, and Stream, the picture this app shows): clean feed, display LUT, zebra, focus assist,
  frame guide, grids, safe area, false color, brightness; zebra level and skin tone; focus-assist style,
  colour and level; frame-guide ratio; grid types; safe-area size.
- **Audio:** per channel: input, gain, phantom power, pad, low cut (as each input supports).
- **Lens:** iris, focus, zoom and autofocus, for lenses the camera can drive.
- **Color:** lift, gamma, gain and offset (R/G/B/luma), contrast, hue, saturation, luma mix, reset.
- **Slate:** next clip's reel, scene, take, auto-increment, shot, take type, location, time, good take;
  project and lens details.
- **Presets & LUTs:** load, save, update and delete presets; choose the LUT.
- **Setup:** color bars, program feed, tally, battery display, the camera's function buttons, info
  (firmware, reference lock, timecode source), Blackmagic Cloud status.
- **Livestream:** status, start/stop, platform and quality. Stopping it stops the picture here too.
- **Connection:** relay and camera addresses, the camera's Secure Login, rejoin Wi-Fi.

How it works:

- The app finds the camera through the relay (`http://<relay>/cgi-bin/pyxis-camera`), or uses an address
  typed in Connection.
- It reads and writes the camera's REST API, `https://<camera>/control/api/v1`. This needs **Web media
  manager** on, in Blackmagic Camera Setup → Network Access.
- It subscribes to the camera's WebSocket, so changes made on the camera itself show up at once. Updates are
  applied up to 10 times a second.
- Timecode isn't subscribed to (the camera would push it every frame). The app reads it, runs its own clock
  at the project frame rate (23.98 counts 24 frames per timecode second), and re-reads it every 10 s and
  whenever recording starts or stops or the frame rate changes. Each reading is checked against the last,
  so record-run timecode that stands still while not recording also stands still in the app. Tested against
  the camera: the app's timecode stayed within the time between two readings.
- If the camera is set to "Enabled with security only", enter its Secure Login under Connection. It's kept
  in the Keychain and only sent over HTTPS.
- Anything the camera reports as unsupported is left out. On this PYXIS that's ND, sharpening level and
  color science, plus lens control when the lens is manual.

## Autofocus

When the lens can autofocus (the camera reports it), two things appear. Neither appears with a manual
lens.

- **Tap to focus:** tap the picture to focus there. A focus box marks the spot: white while the camera is
  focusing, then green when it reports "Focused" (red on an error). Taps are mapped onto the picture's own
  area, so the letterbox bars do nothing. With the controls hidden, or a picker open, a tap still brings
  the controls back or closes the picker first.
  - **AF-S:** focuses once at that point.
  - **AF-C:** moves the continuous-AF area there. The camera's area is drawn on the picture.
  - **Object:** sets the area and starts tracking what's there.
  - **Face:** tracks the detected face nearest the tap. Detected faces are outlined.
- **AF mode rail:** swipe in from the right edge for a thin column of icons: AF-S, AF-C, Face, Object, with
  the current mode highlighted. It hides a moment after you pick, after 5 s, or with a swipe back.

The camera takes a target by its centre point and reports boxes by top-left corner and size; this was
measured on the PYXIS.

Tested on the PYXIS 12K with an 18 mm autofocus lens:
- AF-S tap: Idle → Focusing → Focused in about a second, at exactly the tapped point.
- Face mode: detected faces drawn where the camera reports them, following the person.
- The rail reads and sets the mode.
- Not yet tried live: AF-C and Object.

## Monitor LUTs

LUTs applied by the app to the picture you watch, like a LUT on a field monitor. The camera, its outputs
and its recordings aren't changed, and nothing is uploaded to the camera.

- **Using them:** tap **LUT** in the bottom bar to switch the monitor LUT on and off. Hold it to open the
  chooser, docked at the bottom. Menu → Monitor LUTs has the same choices, with descriptions, plus delete.
- **Built-in film looks:** Film Print, Warm Film, Teal & Orange, Bleach Bypass, Faded Film, Black & White.
  They're generated in the app, not shipped as files. They're Rec.709 → look: they go on top of the camera's
  own LUT on its Stream output (e.g. "Film to Extended Video"), like a look LUT after a technical conversion.
  Colour-balance moves work on light (gamma 2.4); contrast and split-toning work on the video signal.
  Checked numerically: black and white stay in place (except Faded Film's lifted blacks), mid-grey stays at
  about 0.45, and each look moves skin, sky, shadows and highlights the way its name says.
- **Your own LUTs:** **Import .cube** reads 3D .cube files (2 to 129 points, input range 0–1) from the Files
  app, checks them, and keeps a copy in the app. 1D and malformed LUTs are refused with a reason.
- **How it's applied:** on the GPU (Core Image colour cube) to each decoded frame, on Rec.709-encoded
  values, as a monitor applies a LUT to its video input. About a millisecond per frame.
- **Camera LUT:** the film looks expect Rec.709, so the camera's own LUT should be on for its Stream output.
  If it's off (the stream is log), the chooser warns and offers to turn it on. Menu → Monitor LUTs has that
  switch too. The relay turns it on each time it starts the stream (its settings page can turn that off).

Base ISO is marked in the ISO picker. The API doesn't report it, so it's worked out as follows:

1. Where the camera's ISO and gain lists step together, the ISO at 0 dB. On the PYXIS 12K that's 800;
   ISO 1250 reads +4 dB, which agrees.
2. Otherwise from the current gain, if the camera reports one.
3. Otherwise Blackmagic's published native ISOs for the model: 12K/17K → 800; 6K and 4K → 400 and 3200.

Not included: uploading LUT, preset or custom platform files, and timeline editing.

## Build and install

Needs Xcode 26 or later and iOS 17 or later.

1. Open `PyxisViewer.xcodeproj`.
2. Under **Signing & Capabilities**, pick your team. The project is set to team `A8DG268PP3` and bundle
   ID `com.matthewyak.pyxisviewer`; change the bundle ID if you like.
3. Check that the **Hotspot Configuration** capability is on. It's in `PyxisViewer.entitlements`. Apple
   requires it for an app to join a Wi-Fi network, and it needs a paid Apple Developer Program membership.
   Without it, everything else works, but you join the Wi-Fi in Settings yourself and type the relay
   address into the app.
4. Choose your iPhone and run.

`make-icon.swift` redraws the app icon (`swift make-icon.swift`).

## Files

| File | What it is |
|---|---|
| `PyxisViewer/App.swift` | Screens: welcome/manual address, full-screen player with status, settings. Handles the QR link. |
| `PyxisViewer/JoinLink.swift` | Parses the `pyxisviewer://join` link; joins the Wi-Fi with `NEHotspotConfiguration`. |
| `PyxisViewer/RTSPConnection.swift` | Minimal RTSP client (DESCRIBE, SETUP interleaved TCP, PLAY, keepalive). |
| `PyxisViewer/Depacketizer.swift` | RTP to whole frames, H.264 and H.265. |
| `PyxisViewer/StreamPlayer.swift` | Worker thread, reconnects, VideoToolbox decode, display layer. |
| `PyxisViewer/Camera.swift` | Camera control: discovery, REST calls, WebSocket subscription, Secure Login. |
| `PyxisViewer/JSON.swift` | Small JSON value type for the camera's data. |
| `PyxisViewer/Timecode.swift` | The locally run timecode clock. |
| `PyxisViewer/FilmLooks.swift` | The built-in film looks (Rec.709 → look), generated as 3D LUTs. |
| `PyxisViewer/MonitorLUT.swift` | .cube parsing, the LUT library and selection, GPU LUT processing. |
| `PyxisViewer/LUTViews.swift` | The LUT chooser and Menu → Monitor LUTs. |
| `PyxisViewer/Focus.swift` | Tap to focus, the focus/target/face overlays, the AF mode rail. |
| `PyxisViewer/CameraHUD.swift` | The top and bottom bars. |
| `PyxisViewer/CameraPickers.swift` | The docked camera-style setting picker (FPS, shutter, iris, ISO, WB, tint). |
| `PyxisViewer/CameraPanels.swift` | Docked power, media and record panels; shared controls; the audio and lens controls used by the menu. |
| `PyxisViewer/CameraMenu.swift` | The full menu. |
| `Info.plist`, `PyxisViewer.entitlements` | URL scheme `pyxisviewer`, local-network permission, Hotspot Configuration. |

## Tested

In the iOS Simulator (iPhone 17 Pro, Xcode 27.1) on the PYXIS-Stream network, with the real PYXIS
streaming through the R5C:

- Opening the join link showed iOS's "Open in PYXIS Viewer?" prompt. After **Open**, the live picture came
  up within about 2.5 s, at 1920×1080 and a steady 24 fps, the camera's full rate.
- The QR code the settings page makes, built from the relay's real settings, was decoded with Apple's QR
  detector. It matched the expected link exactly, Wi-Fi password included, and opening the decoded link
  played the stream.
- The app also compiles for a physical iPhone (Release, unsigned).
- Camera control, against the real PYXIS 12K (firmware 10.2.96):
  - The app found the camera through the relay.
  - The bars showed the camera's real values: 24 fps, 180°, ISO 800, 3400K, tint 10, live timecode,
    battery voltage, the three card slots with remaining time, both audio inputs.
  - Setting ISO 1000 from the app changed the camera (read back from its API).
  - Setting it back to 800 directly on the camera updated the app within a moment.
  - The Monitor and Record pages matched the camera's state.
  - The swipe to a clean feed and back works.
  - Portrait and landscape layouts checked. Landscape was forced with the `-landscape` debug launch flag,
    since the Simulator can't be rotated from the command line.
- Before writing the client, the camera's own API documentation was read from the camera (20 OpenAPI files,
  155 endpoints), along with its list of about 190 subscribable properties.

Not yet tested:

- Pressing record from the app. It wasn't pressed against your camera, whose active card had 33 s left.
- Formatting a card, presets, function buttons, livestream stop and color correction. These change the
  camera's state or erase data, so they're built to the API spec but weren't run against your camera.
- A camera with Secure Login on (HTTPS with a password).

- On a real iPhone: the Camera app scan, and the Wi-Fi join itself. The Simulator has no Wi-Fi to join, so
  there the join step is skipped. Joining needs a signed build with the Hotspot Configuration capability.
- The real delay on a phone, compared with the web viewer.
- H.265 streams. The code handles them, but the PYXIS sends H.264.

## Capturing on this device

Two buttons next to LUT (in portrait, just above the bottom bar) capture **on the device you're holding**,
not on the camera:

- **FRAME** saves the current picture as a lossless PNG at the stream's full resolution (1920×1080 now).
- **LOCAL** records the picture to an H.264 movie (about 20 Mb/s at 1080p, tagged Rec.709) until tapped
  again. A red "Recording on this device" bar shows while it runs, so it isn't mistaken for the camera
  recording. Video only. It stops by itself when the app goes to the background.

Both capture what you see, monitor LUT included. Quality is limited by the camera's stream (1080p at about
6 Mb/s on the profile's LAN Medium level); LAN High or a 2160p stream gives more. For the camera's
full-quality picture, record or take a still on the camera.

Where they go: Photos on iPhone/iPad (it asks once for permission to add); Movies › PYXIS Viewer and
Pictures › PYXIS Viewer on the Mac (⌘S frame, ⌘R record); Movies/PYXIS Viewer and Pictures/PYXIS Viewer in
the gallery on Android. The code is in `Capture.swift` / `Capture.kt`.

## On the Mac

The same app, from the same project and source files, builds as a native macOS app (macOS 14 or later):
the same picture, camera controls, pickers, menus, monitor LUTs and autofocus.

```bash
xcodebuild -project PyxisViewer.xcodeproj -scheme PyxisViewer -configuration Release -destination 'platform=macOS' build
```

Then copy `PYXIS Viewer.app` from the build folder to Applications.

Differences from the iPhone:
- **Wi-Fi:** join **PYXIS-Stream** from the Wi-Fi menu in the menu bar. The app finds the relay by itself at
  `pyxis-relay.local` and starts as soon as it answers. There's no address to type, in any version of the app.
- **Autofocus:** the AF mode rail stays on the right edge while the controls are showing. Click a picture
  point to focus there.
- **Clean feed:** drag up or down on the picture, or press ⌘K. Click to bring the controls back.
- **Menu bar:** Camera Settings… (⌘,), Monitor LUT on/off (⌘L), Focus menu with the four AF modes (⌘1–⌘4).
  Full screen is ⌃⌘F.
- Not sandboxed: a sandboxed build couldn't reach the relay and camera on the local network.
- Platform-specific code is in `PyxisViewer/Platform.swift` (haptics, keeping the screen awake, the video
  view, menu commands).

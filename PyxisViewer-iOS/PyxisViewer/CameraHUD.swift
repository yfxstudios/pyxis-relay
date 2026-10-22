import SwiftUI

// The camera-style overlay: a status strip along the top (FPS, shutter, iris, timecode,
// ISO, white balance, tint, power) and one along the bottom (record, media), laid out
// like the PYXIS's own touchscreen. Tapping a value opens its control.

enum HUDStyle {
    static let shadow = Color.black.opacity(0.7)  // keeps text legible on the bars, which have no background
    static let picker = Color(red: 0.16, green: 0.18, blue: 0.23).opacity(0.45)  // the camera's slate grey, see-through
    static let label = Font.system(size: 10, weight: .semibold)
    static let value = Font.system(size: 21, weight: .regular).monospacedDigit()
    static let timecode = Font.system(size: 32, weight: .light).monospacedDigit()
    static let accent = Color(red: 0.16, green: 0.53, blue: 0.95)
    static let record = Color(red: 0.92, green: 0.20, blue: 0.20)
}

/// Quick controls opened from the bars.
enum QuickPanel: String, Identifiable {
    case fps, shutter, iris, iso, whiteBalance, tint, power, media, record, lut
    var id: String { rawValue }
}

// MARK: - value formatting

@MainActor
enum Show {
    static func fps(_ cam: Camera) -> String {
        let f = cam.v("/system/format")
        if f["offSpeedEnabled"].bool == true, let os = f["offSpeedFrameRate"].double { return trim(os) }
        return f["frameRate"].string ?? "–"
    }
    static func shutterLabel(_ cam: Camera) -> String {
        cam.v("/video/shutter/measurement")["measurement"].string == "ShutterSpeed" ? "SHUTTER" : "SA"
    }
    static func shutter(_ cam: Camera) -> String {
        let s = cam.v("/video/shutter")
        if cam.v("/video/shutter/measurement")["measurement"].string == "ShutterSpeed" {
            return s["shutterSpeed"].int.map { "1/\($0)" } ?? "–"
        }
        return s["shutterAngle"].double.map { angle($0) } ?? "–"
    }
    static func angle(_ hundredths: Double) -> String { trim(hundredths / 100) + "°" }
    static func iris(_ cam: Camera) -> String {
        if let f = cam.v("/lens/iris")["apertureStop"].double { return "f" + trim((f * 10).rounded() / 10) }
        return "–"
    }
    static func iso(_ cam: Camera) -> String { cam.v("/video/iso")["iso"].int.map(String.init) ?? "–" }
    static func wb(_ cam: Camera) -> String { cam.v("/video/whiteBalance")["whiteBalance"].int.map { "\($0)K" } ?? "–" }
    static func tint(_ cam: Camera) -> String { cam.v("/video/whiteBalanceTint")["whiteBalanceTint"].int.map(String.init) ?? "–" }
    static func timecode(_ cam: Camera, at t: Date = Date()) -> String { cam.timecode?.string(at: t) ?? "--:--:--:--" }
    static func recording(_ cam: Camera) -> Bool { cam.v("/transports/0/record")["recording"].bool == true }

    /// Remaining record time, given in seconds by the camera.
    static func remaining(_ seconds: Int) -> String {
        if seconds < 60 { return "\(max(0, seconds))s" }
        return "\(seconds / 60)min"
    }
    static func trim(_ d: Double) -> String {
        d == d.rounded() ? String(Int(d)) : String(format: "%.2f", d).replacingOccurrences(of: #"0+$"#, with: "", options: .regularExpression)
    }
}

// MARK: - top bar

struct TopBar: View {
    @ObservedObject var cam: Camera
    let compact: Bool  // portrait: two rows
    @Binding var panel: QuickPanel?
    let openMenu: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            if compact {
                HStack(spacing: 0) {
                    menuButton
                    Spacer()
                    timecode
                    Spacer()
                    power
                }
                .padding(.horizontal, 14)
                // each setting fills its share of the row: the space around its text taps it too
                HStack(spacing: 0) {
                    item(.fps, "FPS", Show.fps(cam), align: .leading)
                    item(.shutter, Show.shutterLabel(cam), Show.shutter(cam))
                    item(.iris, "IRIS", Show.iris(cam))
                    item(.iso, "ISO", Show.iso(cam))
                    item(.whiteBalance, "WB", Show.wb(cam))
                    item(.tint, "TINT", Show.tint(cam), align: .trailing)
                }
                .padding(.horizontal, 14).padding(.vertical, 2)
            } else {
                HStack(spacing: 0) {
                    menuButton
                    item(.fps, "FPS", Show.fps(cam))
                    item(.shutter, Show.shutterLabel(cam), Show.shutter(cam))
                    item(.iris, "IRIS", Show.iris(cam))
                    timecode
                    item(.iso, "ISO", Show.iso(cam))
                    item(.whiteBalance, "WB", Show.wb(cam))
                    item(.tint, "TINT", Show.tint(cam))
                    power
                }
                .padding(.horizontal, 20).padding(.vertical, 4)
            }
        }
        .foregroundStyle(.white)
        .shadow(color: HUDStyle.shadow, radius: 2, x: 0, y: 1)
    }

    private var menuButton: some View {
        Button(action: openMenu) {
            ZStack {
                RoundedRectangle(cornerRadius: 6).stroke(.white, lineWidth: 1.6).frame(width: 40, height: 32)
                Image(systemName: "viewfinder").font(.system(size: 17, weight: .regular))
            }
            .frame(width: 44, height: 44)
            .contentShape(Rectangle())
        }
        .accessibilityLabel("Camera menu")
    }

    private var timecode: some View {
        Button { panel = panel == .record ? nil : .record } label: {
            // Advanced locally at the frame rate (the camera is only asked every few seconds).
            TimelineView(.periodic(from: .now, by: 1 / (cam.timecode?.rate ?? 24))) { ctx in
                Text(Show.timecode(cam, at: ctx.date))
                    .font(compact ? .system(size: 26, weight: .light).monospacedDigit() : HUDStyle.timecode)
                    .foregroundStyle(Show.recording(cam) ? HUDStyle.record : .white)
                    .lineLimit(1).minimumScaleFactor(0.6)
            }
            .hudHitArea(horizontal: 12, vertical: 6)
        }
        .accessibilityLabel("Timecode \(Show.timecode(cam))")
    }

    private var power: some View {
        Button { panel = panel == .power ? nil : .power } label: { BatteryView(cam: cam).hudHitArea(horizontal: 4, vertical: 6) }
    }

    private func item(_ p: QuickPanel, _ label: String, _ value: String, align: Alignment = .center) -> some View {
        Button { panel = panel == p ? nil : p } label: {
            VStack(alignment: .leading, spacing: 1) {
                Text(label).font(HUDStyle.label).foregroundStyle(.white.opacity(0.75))
                Text(value).font(compact ? .system(size: 18).monospacedDigit() : HUDStyle.value)
                    .lineLimit(1).minimumScaleFactor(0.7)
            }
            .padding(.vertical, 4).padding(.horizontal, 4)
            .background(panel == p ? Color.white.opacity(0.18) : .clear, in: RoundedRectangle(cornerRadius: 6))
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity, alignment: align)
            .contentShape(Rectangle())
        }
        .accessibilityLabel("\(label) \(value)")
    }
}

struct BatteryView: View {
    @ObservedObject var cam: Camera
    var body: some View {
        let p = cam.v("/camera/power")
        let source = p["source"].string ?? ""
        let battery = p["batteries"][0]
        let percent = battery["chargeRemainingPercent"].int
        let showVolts = cam.v("/camera/power/displayMode")["mode"].string == "Voltage"
        HStack(spacing: 6) {
            if source == "Battery" || source.isEmpty {
                if showVolts, let mv = battery["milliVolt"].int ?? p["milliVolt"].int {
                    Text(String(format: "%.1fV", Double(mv) / 1000)).font(.system(size: 15, weight: .medium).monospacedDigit())
                }
                BatteryIcon(fraction: Double(percent ?? 0) / 100, known: percent != nil)
            } else {
                Image(systemName: "powerplug.portrait.fill").font(.system(size: 18))
                Text(source).font(.system(size: 13, weight: .medium))
            }
        }
        .frame(minWidth: 44, minHeight: 44)
        .accessibilityLabel(percent.map { "Battery \($0) percent" } ?? "Power \(source)")
    }
}

struct BatteryIcon: View {
    let fraction: Double
    let known: Bool
    var body: some View {
        HStack(spacing: 1.5) {
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 4).stroke(.white, lineWidth: 2).frame(width: 46, height: 24)
                HStack(spacing: 2.5) {
                    ForEach(0..<4) { i in
                        RoundedRectangle(cornerRadius: 1.2)
                            .fill(.white.opacity(known && fraction > Double(i) * 0.25 + 0.05 ? 1 : 0.15))
                            .frame(width: 8, height: 15)
                    }
                }
                .padding(.leading, 4.5)
            }
            RoundedRectangle(cornerRadius: 1).fill(.white).frame(width: 3, height: 9)
        }
    }
}

// MARK: - bottom bar

struct BottomBar: View {
    @ObservedObject var cam: Camera
    @ObservedObject var luts: MonitorLUTs
    @ObservedObject var capture: Capture
    let compact: Bool
    @Binding var panel: QuickPanel?

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .center, spacing: compact ? 16 : 26) {
                RecordButton(cam: cam)
                MediaSlots(cam: cam, nameWidth: compact ? 50 : 78) {
                    panel = panel == .media ? nil : .media
                }
                MonitorLUTButton(luts: luts, showName: !compact) { panel = .lut }
                if !compact { CaptureButtons(capture: capture) }  // portrait: above the bar (no room in it)
            }
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 14).padding(.vertical, compact ? 10 : 8)
        }
        .foregroundStyle(.white)
        .shadow(color: HUDStyle.shadow, radius: 2, x: 0, y: 1)
    }
}

struct RecordButton: View {
    @ObservedObject var cam: Camera
    @State private var busy = false
    var body: some View {
        let recording = Show.recording(cam)
        Button {
            guard !busy else { return }
            busy = true
            Haptic.medium()
            Task {
                await cam.setRecording(!recording)
                busy = false
            }
        } label: {
            ZStack {
                Circle().stroke(.white, lineWidth: 2.5).frame(width: 48, height: 48)
                Circle().fill(recording ? HUDStyle.record : Color.white.opacity(0.55)).frame(width: 38, height: 38)
            }
            .frame(width: 56, height: 56)
            .contentShape(Circle())
            .opacity(cam.isConnected ? 1 : 0.4)
        }
        .disabled(!cam.isConnected)
        .accessibilityLabel(recording ? "Stop recording" : "Record")
    }
}

struct MediaSlots: View {
    @ObservedObject var cam: Camera
    var nameWidth: CGFloat = 78
    let tap: () -> Void
    var body: some View {
        let ws = cam.v("/media/workingset")["workingset"].array
        let slots = cam.v("/media/slots").array
        let count = max(ws.count, slots.count, 2)
        Button(action: tap) {
            HStack(spacing: 12) {
                ForEach(0..<count, id: \.self) { i in
                    let m = ws.indices.contains(i) ? ws[i] : .null
                    let active = m["activeDisk"].bool == true
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 2) {
                            Text("\(i + 1)").font(.system(size: 11, weight: .bold))
                                .frame(width: 16, height: 16)
                                .background(active ? HUDStyle.accent : Color.white.opacity(0.3))
                            Text(m.isNull ? (slots.indices.contains(i) ? slots[i]["type"].string ?? "" : "") : (m["volume"].string ?? m["deviceName"].string ?? ""))
                                .font(.system(size: 11, weight: .semibold)).lineLimit(1)
                                .padding(.horizontal, 4)
                                .frame(width: nameWidth, height: 16, alignment: .leading)
                                .background(active ? HUDStyle.accent : Color.white.opacity(0.3))
                        }
                        Text(m.isNull ? "No Card" : (m["remainingRecordTime"].int.map(Show.remaining) ?? "–"))
                            .font(.system(size: 19).monospacedDigit())
                            .lineLimit(1).fixedSize()
                            .foregroundStyle(m.isNull ? .white.opacity(0.8) : .white)
                    }
                }
            }
            .hudHitArea(horizontal: 4, vertical: 6)
        }
        .accessibilityLabel("Media")
    }
}


/// The monitor LUT (applied in this app): tap to turn it on and off, hold to choose one.
struct MonitorLUTButton: View {
    @ObservedObject var luts: MonitorLUTs
    var showName = true
    let choose: () -> Void

    var body: some View {
        let on = luts.enabled
        VStack(alignment: .leading, spacing: 3) {
            Text("LUT").font(.system(size: 13, weight: .bold)).tracking(0.5)
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(on ? Color.white : .clear, in: RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(.white, lineWidth: 1.4))
                .foregroundStyle(on ? Color.black : .white)
            if showName {
                Text(on ? luts.currentName : "Off").font(.system(size: 11)).foregroundStyle(.white.opacity(0.8))
                    .lineLimit(1).frame(maxWidth: 140, alignment: .leading)
            }
        }
        .frame(minWidth: 44, minHeight: 44)
        .contentShape(Rectangle())
        .onTapGesture {
            Haptic.light()
            luts.setEnabled(!on)
        }
        .onLongPressGesture(minimumDuration: 0.4) {
            Haptic.medium()
            choose()
        }
        .accessibilityElement()
        .accessibilityLabel(on ? "Monitor LUT \(luts.currentName), on" : "Monitor LUT, off")
        .accessibilityHint("Double-tap to turn on or off. Hold to choose a LUT.")
        .accessibilityAction(named: "Choose LUT", choose)
        .accessibilityAddTraits(.isButton)
    }
}

/// Capture on this device (not on the camera): grab the current frame, record the picture.
struct CaptureButtons: View {
    @ObservedObject var capture: Capture

    var body: some View {
        HStack(spacing: 10) {
            Button {
                Haptic.light()
                capture.grabFrame()
            } label: {
                item("camera", "FRAME", tint: .white)
            }
            .accessibilityLabel("Capture the frame")
            Button {
                Haptic.medium()
                capture.toggleRecording()
            } label: {
                item(capture.isRecording ? "stop.circle.fill" : "record.circle", "LOCAL",
                     tint: capture.isRecording ? HUDStyle.record : .white)
            }
            .accessibilityLabel(capture.isRecording ? "Stop recording on this device" : "Record on this device")
        }
    }

    private func item(_ icon: String, _ caption: String, tint: Color) -> some View {
        VStack(spacing: 3) {
            Image(systemName: icon).font(.system(size: 21, weight: .medium)).foregroundStyle(tint)
            Text(caption).font(.system(size: 9, weight: .bold)).tracking(0.5).foregroundStyle(.white.opacity(0.85))
        }
        .frame(minWidth: 44, minHeight: 44)
        .contentShape(Rectangle())
    }
}

/// Shown while recording on this device: so it isn't mistaken for the camera recording.
struct LocalRecordingPill: View {
    let since: Date

    var body: some View {
        TimelineView(.periodic(from: since, by: 1)) { ctx in
            let s = max(0, Int(ctx.date.timeIntervalSince(since)))
            HStack(spacing: 7) {
                Circle().fill(HUDStyle.record).frame(width: 8, height: 8)
                Text("Recording on this device  \(s / 60):\(String(format: "%02d", s % 60))")
                    .font(.caption.weight(.semibold)).monospacedDigit()
            }
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(.black.opacity(0.7), in: Capsule())
            .foregroundStyle(.white)
        }
        .allowsHitTesting(false)
    }
}

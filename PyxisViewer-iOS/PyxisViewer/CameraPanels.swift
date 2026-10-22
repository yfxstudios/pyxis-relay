import SwiftUI

// Quick controls that open from the top and bottom bars, styled like the camera's own
// touchscreen pickers: a translucent strip of choices plus a fine-adjust slider.

struct QuickPanelView: View {
    @ObservedObject var cam: Camera
    @ObservedObject var luts: MonitorLUTs
    let panel: QuickPanel
    let close: () -> Void

    var body: some View {
        DockedPanel {
            switch panel {
            case .fps, .shutter, .iris, .iso, .whiteBalance, .tint:
                SettingPickerView(cam: cam, panel: panel)
            case .lut:
                LUTChooser(cam: cam, luts: luts, close: close)
            case .power, .media, .record:
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Text(title).font(.system(size: 13, weight: .bold)).foregroundStyle(.white.opacity(0.75))
                        Spacer()
                        Button(action: close) {
                            Image(systemName: "xmark").font(.system(size: 13, weight: .bold)).frame(width: 30, height: 30)
                        }
                        .accessibilityLabel("Close")
                    }
                    switch panel {
                    case .power: PowerPanel(cam: cam)
                    case .media: MediaPanel(cam: cam)
                    default: RecordPanel(cam: cam)
                    }
                }
                .frame(maxWidth: 640)
            }
        }
    }

    private var title: String {
        switch panel {
        case .power: return "POWER"
        case .media: return "MEDIA"
        default: return "RECORD"
        }
    }
}

// MARK: - building blocks

struct SliderRow: View {
    let label: String
    let value: Double
    let range: ClosedRange<Double>
    var step: Double = 0
    let text: (Double) -> String
    let set: (Double) -> Void

    @State private var local: Double?

    var body: some View {
        HStack(spacing: 10) {
            Text(label).font(.system(size: 12, weight: .semibold)).foregroundStyle(.white.opacity(0.7)).frame(width: 64, alignment: .leading)
            Slider(value: Binding(get: { local ?? value }, set: { v in
                let s = step > 0 ? (v / step).rounded() * step : v
                local = s
                set(s)
            }), in: range, onEditingChanged: { editing in if !editing { local = nil } })
            .tint(.white)
            Text(text(local ?? value)).font(.system(size: 14).monospacedDigit()).frame(width: 64, alignment: .trailing)
        }
    }
}

struct ToggleRow: View {
    let label: String
    let isOn: Bool
    let set: (Bool) -> Void
    var body: some View {
        Toggle(label, isOn: Binding(get: { isOn }, set: set)).tint(HUDStyle.accent)
    }
}

struct Segmented: View {
    let options: [String]
    let selected: String?
    var label: (String) -> String = { $0 }
    let pick: (String) -> Void
    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.self) { o in
                Button { pick(o) } label: {
                    Text(label(o)).font(.system(size: 13, weight: .semibold))
                        .frame(maxWidth: .infinity).padding(.vertical, 7)
                        .background(o == selected ? Color.white : .clear, in: RoundedRectangle(cornerRadius: 7))
                        .foregroundStyle(o == selected ? Color.black : .white)
                }
            }
        }
        .padding(2)
        .background(Color.white.opacity(0.1), in: RoundedRectangle(cornerRadius: 9))
    }
}

/// Changes the recording format. The camera takes the whole format at once.
@MainActor
func setFormat(_ cam: Camera, _ change: (inout [String: JSON]) -> Void) {
    let f = cam.v("/system/format")
    var body: [String: JSON] = [
        "codec": f["codec"], "frameRate": f["frameRate"], "offSpeedEnabled": f["offSpeedEnabled"],
        "offSpeedFrameRate": f["offSpeedFrameRate"], "recordResolution": f["recordResolution"],
        "sensorResolution": f["sensorResolution"],
    ]
    change(&body)
    cam.put("/system/format", .object(body))
}

/// The supported-format entry for the current resolution.
@MainActor
func currentFormatEntry(_ cam: Camera) -> JSON {
    let f = cam.v("/system/format")
    return cam.v("/system/supportedFormats")["supportedFormats"].array.first {
        $0["recordResolution"] == f["recordResolution"] && $0["sensorResolution"] == f["sensorResolution"]
    } ?? .null
}

// MARK: - panels

func codecName(_ c: String) -> String {
    // "BRaw:12_1" -> "BRAW 12:1", "BRaw:Q0" -> "BRAW Q0"
    guard c.hasPrefix("BRaw:") else { return c }
    return "BRAW " + c.dropFirst(5).replacingOccurrences(of: "_", with: ":")
}

struct PowerPanel: View {
    @ObservedObject var cam: Camera
    var body: some View {
        let p = cam.v("/camera/power")
        VStack(alignment: .leading, spacing: 10) {
            Text("Source: \(p["source"].string ?? "–")").font(.system(size: 14))
            ForEach(Array(p["batteries"].array.enumerated()), id: \.offset) { i, b in
                Text("Battery \(i + 1): \(b["chargeRemainingPercent"].int.map { "\($0)%" } ?? "–") · \(b["milliVolt"].int.map { String(format: "%.2f V", Double($0) / 1000) } ?? "–")")
                    .font(.system(size: 14).monospacedDigit())
            }
            Text("SHOW BATTERY AS").font(HUDStyle.label).foregroundStyle(.white.opacity(0.6))
            Segmented(options: ["Percentage", "Voltage"], selected: cam.v("/camera/power/displayMode")["mode"].string) {
                cam.put("/camera/power/displayMode", ["mode": .string($0)])
            }
        }
    }
}

struct RecordPanel: View {
    @ObservedObject var cam: Camera
    var body: some View {
        let src = cam.v("/transports/0/timecode/source")
        let pre = cam.v("/transports/0/prerecord")
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                PanelButton(Show.recording(cam) ? "Stop" : "Record", icon: Show.recording(cam) ? "stop.fill" : "record.circle",
                            tint: HUDStyle.record) {
                    await cam.setRecording(!Show.recording(cam))
                }
                PanelButton("Still", icon: "camera") { await cam.post("/transports/0/doStillCapture") }
                if cam.has("/transports/0/prerecord") {
                    PanelButton("Pre-record", icon: "clock.arrow.circlepath") { await cam.post("/transports/0/prerecord") }
                }
            }
            Text("Timecode \(Show.timecode(cam)) · source \(src["timecodeInputSource"].string ?? "–") (\(src["source"].string ?? "–"))")
                .font(.system(size: 12).monospacedDigit()).foregroundStyle(.white.opacity(0.7))
            if pre["prerecording"].bool == true {
                Text("Pre-recording: \(pre["duration"].int ?? 0) s buffered").font(.system(size: 12)).foregroundStyle(.white.opacity(0.7))
            }
            let next = cam.v("/slates/nextClip")["clip"]
            Text("Next: reel \(next["reel"].int ?? 0) · scene \(next["scene"].string ?? "") · take \(next["take"].int ?? 0)")
                .font(.system(size: 12)).foregroundStyle(.white.opacity(0.7))
        }
    }
}

struct PanelButton: View {
    let title: String
    let icon: String
    var tint: Color = .white
    let action: () async -> Void
    @State private var busy = false
    init(_ title: String, icon: String, tint: Color = .white, action: @escaping () async -> Void) {
        self.title = title; self.icon = icon; self.tint = tint; self.action = action
    }
    var body: some View {
        Button {
            guard !busy else { return }
            busy = true
            Task { await action(); busy = false }
        } label: {
            Label(title, systemImage: icon).font(.system(size: 14, weight: .semibold))
                .foregroundStyle(tint)
                .padding(.horizontal, 14).padding(.vertical, 9)
                .background(Color.white.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
                .opacity(busy ? 0.5 : 1)
        }
    }
}

struct MediaPanel: View {
    @ObservedObject var cam: Camera
    @State private var formatTarget: JSON?
    @State private var filesystem = "ExFAT"
    @State private var volume = ""
    @State private var confirmText = ""
    @State private var switching: Int?  // card being switched to, until the camera confirms

    var body: some View {
        let ws = cam.v("/media/workingset")["workingset"].array
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(ws.enumerated()), id: \.offset) { i, m in
                if !m.isNull {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(i + 1) · \(m["volume"].string ?? m["deviceName"].string ?? "")").font(.system(size: 15, weight: .semibold))
                            Text("\(m["clipCount"].int ?? 0) clips · \(Show.remaining(m["remainingRecordTime"].int ?? 0)) left · \(bytes(m["remainingSpace"].double)) of \(bytes(m["totalSpace"].double)) free")
                                .font(.system(size: 12)).foregroundStyle(.white.opacity(0.65))
                        }
                        Spacer()
                        if m["activeDisk"].bool == true {
                            Text("RECORDING TO").font(HUDStyle.label).padding(5).background(HUDStyle.accent, in: RoundedRectangle(cornerRadius: 4))
                        } else if (m["remainingRecordTime"].int ?? 1) <= 0 {
                            Text("FULL").font(HUDStyle.label).padding(5)
                                .overlay(RoundedRectangle(cornerRadius: 4).stroke(.white.opacity(0.6)))
                                .accessibilityLabel("Full")
                        } else if switching == (m["index"].int ?? i) {
                            ProgressView().tint(.white)
                        } else {
                            Button("Use") { Task { await use(m, index: m["index"].int ?? i) } }
                                .font(.system(size: 13, weight: .semibold))
                                .disabled(Show.recording(cam))
                        }
                        Menu {
                            Button("Format…", role: .destructive) { formatTarget = m; volume = m["volume"].string ?? ""; confirmText = "" }
                        } label: { Image(systemName: "ellipsis.circle").frame(width: 32, height: 32) }
                    }
                }
            }
            if ws.allSatisfy(\.isNull) { Text("No media").foregroundStyle(.white.opacity(0.7)) }
        }
        .sheet(item: Binding(get: { formatTarget.map { FormatTarget(device: $0["deviceName"].string ?? "") } },
                             set: { if $0 == nil { formatTarget = nil } })) { target in
            FormatSheet(cam: cam, device: target.device, clipCount: formatTarget?["clipCount"].int ?? 0,
                        volume: $volume, filesystem: $filesystem, confirmText: $confirmText) { formatTarget = nil }
        }
    }

    private func bytes(_ b: Double?) -> String {
        guard let b else { return "–" }
        return ByteCountFormatter.string(fromByteCount: Int64(b), countStyle: .file)
    }

    /// Makes a card the one recorded to. The PYXIS answers "done" even when it doesn't
    /// switch (it ignores a full card), so the active card is read back before showing it.
    private func use(_ m: JSON, index: Int) async {
        let name = m["volume"].string ?? m["deviceName"].string ?? "that card"
        switching = index
        defer { switching = nil }
        guard await cam.action("PUT", "/media/active", ["workingsetIndex": .number(Double(index))]) else { return }
        for _ in 0..<6 {
            try? await Task.sleep(for: .milliseconds(500))
            await cam.refresh("/media/active")
            if cam.v("/media/active")["workingsetIndex"].int == index {
                await cam.refresh("/media/workingset")
                return
            }
        }
        await cam.refresh("/media/workingset")
        cam.message = "The camera didn't switch to \(name)."
    }
}

struct FormatTarget: Identifiable { let device: String; var id: String { device } }

/// Erasing a card: the camera's two-step format (one-time key, then the format itself),
/// behind a typed confirmation.
struct FormatSheet: View {
    @ObservedObject var cam: Camera
    let device: String
    let clipCount: Int
    @Binding var volume: String
    @Binding var filesystem: String
    @Binding var confirmText: String
    let done: () -> Void
    @State private var working = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Formatting erases all \(clipCount) clips on \(device). This can't be undone.")
                        .foregroundStyle(.red)
                }
                Section("Card") {
                    TextField("Volume name", text: $volume).autocorrectionDisabled()
                    Picker("File system", selection: $filesystem) {
                        ForEach(cam.v("/media/devices/doformatSupportedFilesystems").array.compactMap(\.string), id: \.self) { Text($0) }
                    }
                }
                Section {
                    TextField("Type ERASE to confirm", text: $confirmText)
                        .capitalsField()
                    Button("Format \(device)", role: .destructive) {
                        working = true
                        Task {
                            let path = "/media/devices/\(device.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? device)/doformat"
                            if let key = await cam.get(path)?["key"].string {
                                if await cam.action("PUT", path, ["key": .string(key), "filesystem": .string(filesystem), "volume": .string(volume)]) {
                                    done()
                                }
                            } else { cam.message = "The camera didn't give a format key" }
                            working = false
                        }
                    }
                    .disabled(confirmText != "ERASE" || volume.isEmpty || working)
                }
            }
            .navigationTitle("Format card")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: done) } }
        }
        .preferredColorScheme(.dark)
    }
}

struct AudioPanel: View {
    @ObservedObject var cam: Camera
    var body: some View {
        let count = cam.v("/audio/channels")["channels"].int ?? 2
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                ForEach(0..<count, id: \.self) { ch in
                    if cam.has("/audio/channel/\(ch)/input") { AudioChannelControls(cam: cam, ch: ch) }
                }
            }
        }
        .frame(maxHeight: 360)
    }
}

struct AudioChannelControls: View {
    @ObservedObject var cam: Camera
    let ch: Int
    var body: some View {
        let base = "/audio/channel/\(ch)"
        let inputs = cam.v("\(base)/supportedInputs").array.filter { $0["available"].bool != false }.compactMap { $0["input"].string }
        let desc = cam.v("\(base)/input/description")["description"]
        let caps = desc["capabilities"][0]
        let lo = desc["gainRange"]["Min"].double ?? -6, hi = desc["gainRange"]["Max"].double ?? 6
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("CH\(ch + 1)").font(.system(size: 13, weight: .bold))
                Spacer()
                Menu {
                    ForEach(inputs, id: \.self) { i in Button(i) { cam.put("\(base)/input", ["input": .string(i)]) } }
                } label: {
                    HStack(spacing: 4) {
                        Text(cam.v("\(base)/input")["input"].string ?? "–").font(.system(size: 14))
                        Image(systemName: "chevron.up.chevron.down").font(.system(size: 11))
                    }
                }
            }
            if hi > lo {
                SliderRow(label: "GAIN", value: cam.v("\(base)/level")["gain"].double ?? 0, range: lo...hi, step: 0.5,
                          text: { ($0 > 0 ? "+" : "") + Show.trim($0) + " dB" }) {
                    cam.putLive("\(base)/level", ["gain": .number($0)])
                }
            }
            if caps["PhantomPower"].bool == true {
                ToggleRow(label: "Phantom power (+48V)", isOn: cam.v("\(base)/phantomPower")["enabled"].bool == true) {
                    cam.put("\(base)/phantomPower", ["enabled": .bool($0)])
                }
            }
            if caps["Padding"]["available"].bool == true {
                ToggleRow(label: "Pad", isOn: cam.v("\(base)/padding")["enabled"].bool == true) {
                    cam.put("\(base)/padding", ["enabled": .bool($0)])
                }
            }
            if caps["LowCutFilter"].bool == true {
                ToggleRow(label: "Low cut filter", isOn: cam.v("\(base)/lowCutFilter")["enabled"].bool == true) {
                    cam.put("\(base)/lowCutFilter", ["enabled": .bool($0)])
                }
            }
        }
        .padding(10)
        .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
    }
}

/// Iris, focus and zoom, for lenses the camera can drive electronically.
struct LensPanel: View {
    @ObservedObject var cam: Camera
    var compact = false
    var body: some View {
        let irisOK = cam.v("/lens/iris/description")["controllable"].bool == true
        let focusOK = cam.v("/lens/focus/description")["controllable"].bool == true
        let zoomOK = cam.v("/lens/zoom/description")["controllable"].bool == true
        let af = cam.v("/lens/focus/autoFocus/description")
        VStack(alignment: .leading, spacing: 12) {
            if !irisOK && !focusOK && !zoomOK {
                Text("The lens on the camera has no electronic control (or isn't reporting it). Iris, focus and zoom are set on the lens.")
                    .font(.system(size: 13)).foregroundStyle(.white.opacity(0.75))
            }
            if irisOK {
                let iris = cam.v("/lens/iris")
                SliderRow(label: "IRIS", value: iris["normalised"].double ?? iris["normalized"].double ?? 0, range: 0...1,
                          text: { _ in Show.iris(cam) }) { cam.putLive("/lens/iris", ["normalised": .number($0)]) }
                HStack(spacing: 10) {
                    PanelButton("Close ½", icon: "minus") { await cam.action("PUT", "/lens/iris", ["adjustmentStep": -1]) }
                    PanelButton("Open ½", icon: "plus") { await cam.action("PUT", "/lens/iris", ["adjustmentStep": 1]) }
                }
            }
            if !compact || !irisOK {
                if focusOK {
                    let f = cam.v("/lens/focus")
                    SliderRow(label: "FOCUS", value: f["normalised"].double ?? f["normalized"].double ?? 0, range: 0...1,
                              text: { String(format: "%.0f%%", $0 * 100) }) { cam.putLive("/lens/focus", ["normalised": .number($0)]) }
                }
                if af["supported"].bool == true {
                    HStack(spacing: 10) {
                        PanelButton("Autofocus", icon: "scope") { await cam.action("PUT", "/lens/focus/doAutoFocus", ["position": ["x": 0.5, "y": 0.5]]) }
                    }
                    Segmented(options: af["supportedModes"].array.compactMap(\.string),
                              selected: cam.v("/lens/focus/autoFocus")["mode"].string) {
                        cam.put("/lens/focus/autoFocus", ["mode": .string($0)])
                    }
                }
                if zoomOK {
                    let z = cam.v("/lens/zoom")
                    SliderRow(label: "ZOOM", value: z["normalised"].double ?? z["normalized"].double ?? 0, range: 0...1,
                              text: { _ in z["focalLength"].double.map { "\(Int($0))mm" } ?? "" }) {
                        cam.putLive("/lens/zoom", ["normalised": .number($0)])
                    }
                }
                if cam.v("/lens/opticalImageStabilization")["controlAvailable"].bool == true {
                    ToggleRow(label: "Image stabilisation", isOn: cam.v("/lens/opticalImageStabilization")["enabled"].bool == true) {
                        cam.put("/lens/opticalImageStabilization", ["enabled": .bool($0)])
                    }
                }
            }
        }
    }
}

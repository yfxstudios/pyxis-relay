import SwiftUI

// The full camera menu: every control the camera's API offers that this camera supports
// (anything it answers "not supported" for is left out), grouped like the camera's own menus.

struct CameraMenu: View {
    @ObservedObject var cam: Camera
    @ObservedObject var luts: MonitorLUTs
    @Binding var relayHost: String
    let ssid: String
    let rejoin: (() -> Void)?
    let done: () -> Void

    var body: some View {
        NavigationStack {
            List {
                Section {
                    CameraLinkRow(cam: cam)
                }
                if cam.isConnected {
                    Section {
                        NavigationLink { RecordMenu(cam: cam) } label: { Label("Record", systemImage: "record.circle") }
                        NavigationLink { MonitorMenu(cam: cam) } label: { Label("Monitor", systemImage: "rectangle.on.rectangle") }
                        NavigationLink { Form { AudioPanel(cam: cam) }.navigationTitle("Audio") } label: { Label("Audio", systemImage: "waveform") }
                        NavigationLink { ColorMenu(cam: cam) } label: { Label("Color", systemImage: "paintpalette") }
                        NavigationLink { Form { LensPanel(cam: cam) }.navigationTitle("Lens") } label: { Label("Lens", systemImage: "camera.aperture") }
                        NavigationLink { SlateMenu(cam: cam) } label: { Label("Slate", systemImage: "film") }
                        NavigationLink { PresetsMenu(cam: cam) } label: { Label("Presets & LUTs", systemImage: "square.stack") }
                        NavigationLink { SetupMenu(cam: cam) } label: { Label("Setup", systemImage: "gearshape") }
                        NavigationLink { StreamMenu(cam: cam) } label: { Label("Livestream", systemImage: "dot.radiowaves.left.and.right") }
                    }
                }
                Section {
                    NavigationLink { MonitorLUTMenu(cam: cam, luts: luts) } label: { Label("Monitor LUTs", systemImage: "camera.filters") }
                } footer: { Text("LUTs applied in this app to the picture you watch. The camera isn't changed.") }
                Section {
                    NavigationLink {
                        ConnectionMenu(cam: cam, relayHost: $relayHost, ssid: ssid, rejoin: rejoin)
                    } label: { Label("Connection", systemImage: "network") }
                }
            }
            .navigationTitle(cam.v("/system/product")["productName"].string ?? "Camera")
            .inlineNavigationTitle()
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done", action: done) } }
        }
        .preferredColorScheme(.dark)
        .tint(HUDStyle.accent)
    }
}

struct CameraLinkRow: View {
    @ObservedObject var cam: Camera
    var body: some View {
        HStack {
            Circle().fill(color).frame(width: 9, height: 9)
            Text(text).font(.subheadline)
        }
    }
    private var text: String {
        switch cam.link {
        case .off: return "Camera control off"
        case .searching: return "Looking for the camera…"
        case .connecting(let h): return "Connecting to the camera at \(h)…"
        case .connected(let h):
            let p = cam.v("/system/product")
            return "\(p["productName"].string ?? "Camera") at \(h) · firmware \(p["softwareVersion"].string ?? "?")"
        case .needsLogin(let h): return "The camera at \(h) needs its Secure Login (Connection)"
        case .failed(let m): return m
        }
    }
    private var color: Color {
        switch cam.link {
        case .connected: return .green
        case .needsLogin, .failed: return .red
        default: return .orange
        }
    }
}

// MARK: - helpers

@MainActor
private func flag(_ cam: Camera, _ path: String, _ key: String = "enabled") -> Binding<Bool> {
    Binding(get: { cam.v(path)[key].bool == true }, set: { cam.put(path, [key: .bool($0)]) })
}

private struct PickerRow: View {
    let title: String
    let options: [String]
    let selected: String?
    var label: (String) -> String = { $0 }
    let pick: (String) -> Void
    var body: some View {
        Picker(title, selection: Binding(get: { selected ?? "" }, set: pick)) {
            if selected == nil || !(options.contains(selected!)) { Text(selected ?? "–").tag(selected ?? "") }
            ForEach(options, id: \.self) { Text(label($0)).tag($0) }
        }
    }
}

// MARK: - record

struct RecordMenu: View {
    @ObservedObject var cam: Camera
    var body: some View {
        let f = cam.v("/system/format")
        let formats = cam.v("/system/supportedFormats")["supportedFormats"].array
        let entry = currentFormatEntry(cam)
        Form {
            Section("Format") {
                Picker("Resolution", selection: Binding(
                    get: { formats.firstIndex { $0["recordResolution"] == f["recordResolution"] && $0["sensorResolution"] == f["sensorResolution"] } ?? -1 },
                    set: { i in
                        guard formats.indices.contains(i) else { return }
                        let e = formats[i]
                        setFormat(cam) { b in
                            b["recordResolution"] = e["recordResolution"]
                            b["sensorResolution"] = e["sensorResolution"]
                            let codecs = e["codecs"].array.compactMap(\.string)
                            if let c = b["codec"]?.string, !codecs.contains(c), let first = codecs.first { b["codec"] = .string(first) }
                            let rates = e["frameRates"].array.compactMap(\.string)
                            if let r = b["frameRate"]?.string, !rates.contains(r), let first = rates.first { b["frameRate"] = .string(first) }
                        }
                    })) {
                    ForEach(Array(formats.enumerated()), id: \.offset) { i, e in
                        let sensor = e["sensorResolution"] == e["recordResolution"] ? "" : " (scaled)"
                        Text("\(e["resolutionDescriptor"]["description"].string ?? "") · \(String(e["recordResolution"]["width"].int ?? 0))×\(String(e["recordResolution"]["height"].int ?? 0))\(sensor)").tag(i)
                    }
                }
                PickerRow(title: "Codec", options: entry["codecs"].array.compactMap(\.string), selected: f["codec"].string,
                          label: codecName) { c in setFormat(cam) { $0["codec"] = .string(c) } }
                PickerRow(title: "Project frame rate", options: entry["frameRates"].array.compactMap(\.string),
                          selected: f["frameRate"].string) { r in setFormat(cam) { $0["frameRate"] = .string(r) } }
                Toggle("Off-speed", isOn: Binding(get: { f["offSpeedEnabled"].bool == true },
                                                  set: { on in setFormat(cam) { $0["offSpeedEnabled"] = .bool(on) } }))
                if f["offSpeedEnabled"].bool == true {
                    Stepper("Sensor frame rate: \(f["offSpeedFrameRate"].int ?? 0) fps",
                            value: Binding(get: { f["offSpeedFrameRate"].int ?? 24 },
                                           set: { v in setFormat(cam) { $0["offSpeedFrameRate"] = .number(Double(v)) } }),
                            in: (f["minOffSpeedFrameRate"].int ?? 12)...(f["maxOffSpeedFrameRate"].int ?? 60))
                }
            }
            Section {
                PickerRow(title: "Shutter shown as", options: ["ShutterAngle", "ShutterSpeed"],
                          selected: cam.v("/video/shutter/measurement")["measurement"].string,
                          label: { $0 == "ShutterAngle" ? "Angle" : "Speed" }) {
                    cam.put("/video/shutter/measurement", ["measurement": .string($0)])
                }
                if cam.has("/video/autoExposure") {
                    PickerRow(title: "Auto exposure", options: ["Off", "OneShot", "Continuous"],
                              selected: cam.v("/video/autoExposure")["mode"].string,
                              label: { $0 == "OneShot" ? "One shot" : $0 }) {
                        cam.put("/video/autoExposure", ["mode": .string($0)])
                    }
                }
                let gains = cam.v("/video/supportedGains")["supportedGains"].array.compactMap(\.int)
                if !gains.isEmpty {
                    PickerRow(title: "Gain", options: gains.map(String.init), selected: cam.v("/video/gain")["gain"].int.map(String.init),
                              label: { "\(Int($0) ?? 0 > 0 ? "+" : "")\($0) dB" }) {
                        cam.put("/video/gain", ["gain": .number(Double($0) ?? 0)])
                    }
                }
                if cam.has("/video/ndFilter") {
                    PickerRow(title: "ND filter", options: cam.v("/video/supportedNDFilters")["supportedStops"].array.compactMap(\.double).map { Show.trim($0) },
                              selected: cam.v("/video/ndFilter")["stop"].double.map { Show.trim($0) }, label: { "\($0) stops" }) {
                        cam.put("/video/ndFilter", ["stop": .number(Double($0) ?? 0)])
                    }
                }
                let ff = cam.v("/video/flickerFreeShutters")["shutterAngles"].array.compactMap(\.double)
                if !ff.isEmpty {
                    LabeledContent("Flicker-free angles", value: ff.map { Show.angle($0) }.joined(separator: ", "))
                }
            } header: { Text("Exposure") } footer: { Text("ISO, shutter, white balance and tint are in the top bar.") }
            if cam.has("/system/dynamicRange") {
                Section("Image") {
                    PickerRow(title: "Dynamic range",
                              options: cam.v("/system/supportedDynamicRanges")["supportedDynamicRanges"].array.compactMap(\.string),
                              selected: cam.v("/system/dynamicRange")["dynamicRange"].string) {
                        cam.put("/system/dynamicRange", ["dynamicRange": .string($0)])
                    }
                    if cam.has("/system/colorScience") {
                        PickerRow(title: "Color science",
                                  options: cam.v("/system/supportedColorSciences")["supportedColorSciences"].array.compactMap(\.string),
                                  selected: cam.v("/system/colorScience")["colorScience"].string) {
                            cam.put("/system/colorScience", ["colorScience": .string($0)])
                        }
                    }
                    if cam.has("/video/detailSharpening") && !cam.unsupported.contains("/video/detailSharpeningLevel") {
                        Toggle("Detail sharpening", isOn: flag(cam, "/video/detailSharpening"))
                        if cam.has("/video/detailSharpeningLevel") {
                            PickerRow(title: "Sharpening level", options: ["Low", "Medium", "High"],
                                      selected: cam.v("/video/detailSharpeningLevel")["level"].string) {
                                cam.put("/video/detailSharpeningLevel", ["level": .string($0)])
                            }
                        }
                    }
                }
            }
            Section("Recording") {
                if cam.has("/transports/0/proxyRecording") { Toggle("Record proxies", isOn: flag(cam, "/transports/0/proxyRecording")) }
                if cam.has("/luts/recordWithLUT") { Toggle("Embed LUT in clips", isOn: flag(cam, "/luts/recordWithLUT")) }
                if cam.has("/transports/0/prerecord/auto") {
                    Toggle("Pre-record (always buffering)", isOn: flag(cam, "/transports/0/prerecord/auto", "autoEnabled"))
                    PickerRow(title: "Pre-record length",
                              options: cam.v("/transports/0/prerecord/supportedMaxDurations").array.compactMap(\.int).map(String.init),
                              selected: cam.v("/transports/0/prerecord/maxDuration")["maxDuration"].int.map(String.init),
                              label: { "\($0) s" }) {
                        cam.put("/transports/0/prerecord/maxDuration", ["maxDuration": .number(Double($0) ?? 10)])
                    }
                }
                Button("Capture a still") { Task { await cam.post("/transports/0/doStillCapture") } }
            }
            Section("Media") { MediaPanel(cam: cam) }
        }
        .navigationTitle("Record")
    }
}

// MARK: - monitor

struct MonitorMenu: View {
    @ObservedObject var cam: Camera
    @State private var display = "LCD"
    var body: some View {
        let displays = cam.v("/monitoring/display")["displays"].array.compactMap(\.string)
            .filter { cam.has("/monitoring/\($0)/cleanFeed") }
        let names = displays.isEmpty ? ["LCD"] : displays
        let d = "/monitoring/\(display)"
        Form {
            Section {
                Picker("Display", selection: $display) {
                    ForEach(names, id: \.self) { Text(displayName($0)).tag($0) }
                }
                .pickerStyle(.menu)
            } footer: { Text("Overlays and LUT per camera output. \"Stream\" is the picture this app shows: turn its display LUT on for a normal-looking picture from Film dynamic range.") }
            Section(displayName(display)) {
                Toggle("Clean feed (no overlays)", isOn: flag(cam, "\(d)/cleanFeed"))
                Toggle("Display LUT", isOn: flag(cam, "\(d)/displayLUT"))
                Toggle("Zebra", isOn: flag(cam, "\(d)/zebra"))
                Toggle("Focus assist", isOn: flag(cam, "\(d)/focusAssist"))
                Toggle("Frame guide", isOn: flag(cam, "\(d)/frameGuide"))
                Toggle("Grids", isOn: flag(cam, "\(d)/frameGrids"))
                Toggle("Safe area", isOn: flag(cam, "\(d)/safeArea"))
                Toggle("False color", isOn: flag(cam, "\(d)/falseColor"))
                if cam.v("\(d)/brightness")["adjustable"].bool == true {
                    SliderRow(label: "BRIGHT", value: cam.v("\(d)/brightness")["brightness"].double ?? 50, range: 0...100, step: 1,
                              text: { "\(Int($0))" }) { cam.putLive("\(d)/brightness", ["brightness": .number($0)]) }
                }
            }
            Section("Zebra") {
                let z = cam.v("/monitoring/zebra")
                PickerRow(title: "Highlight level", options: ["75", "80", "85", "90", "95", "100"],
                          selected: z["highlight"]["level"].int.map(String.init), label: { "\($0)%" }) {
                    cam.put("/monitoring/zebra", ["highlight": ["level": .number(Double($0) ?? 100), "enabled": z["highlight"]["enabled"].bool.map(JSON.bool) ?? true]])
                }
                Toggle("Highlight zebra", isOn: Binding(get: { z["highlight"]["enabled"].bool == true }, set: {
                    cam.put("/monitoring/zebra", ["highlight": ["enabled": .bool($0), "level": z["highlight"]["level"]]])
                }))
                PickerRow(title: "Skin tone", options: ["None", "Middle Grey", "Middle Grey +1", "Blowout Threshold"],
                          selected: z["skinTone"]["type"].string) {
                    cam.put("/monitoring/zebra", ["skinTone": ["type": .string($0), "enabled": .bool($0 != "None")]])
                }
            }
            Section("Focus assist") {
                let fa = cam.v("/monitoring/focusAssist")
                PickerRow(title: "Style", options: ["Peak", "ColoredLines"], selected: fa["mode"].string,
                          label: { $0 == "ColoredLines" ? "Colored lines" : $0 }) { cam.put("/monitoring/focusAssist", ["mode": .string($0)]) }
                PickerRow(title: "Line color", options: ["Red", "Green", "Blue", "White", "Black"], selected: fa["color"].string) {
                    cam.put("/monitoring/focusAssist", ["color": .string($0)])
                }
                SliderRow(label: "LEVEL", value: fa["intensity"].double ?? 50, range: 0...100, step: 1, text: { "\(Int($0))%" }) {
                    cam.putLive("/monitoring/focusAssist", ["intensity": .number($0)])
                }
            }
            Section("Guides") {
                PickerRow(title: "Frame guide", options: cam.v("/monitoring/frameGuideRatio/presets")["presets"].array.compactMap(\.string),
                          selected: cam.v("/monitoring/frameGuideRatio")["ratio"].string) {
                    cam.put("/monitoring/frameGuideRatio", ["ratio": .string($0)])
                }
                let grids = cam.v("/monitoring/frameGrids")["frameGrids"].array.compactMap(\.string)
                ForEach(["Thirds", "Crosshair", "Dot", "Horizon"], id: \.self) { g in
                    Toggle(g == "Thirds" ? "Grid: thirds" : "Grid: \(g.lowercased())", isOn: Binding(get: { grids.contains(g) }, set: { on in
                        let new = on ? grids + [g] : grids.filter { $0 != g }
                        cam.put("/monitoring/frameGrids", ["frameGrids": .array(new.map { .string($0) })])
                    }))
                }
                SliderRow(label: "SAFE", value: cam.v("/monitoring/safeAreaPercent")["percent"].double ?? 90, range: 50...100, step: 1,
                          text: { "\(Int($0))%" }) { cam.putLive("/monitoring/safeAreaPercent", ["percent": .number($0)]) }
            }
        }
        .navigationTitle("Monitor")
    }

    private func displayName(_ d: String) -> String {
        switch d {
        case "FrontUSBC": return "Front USB-C"
        case "RearUSBC": return "Rear USB-C"
        case "MainSDI": return "SDI"
        case "Stream": return "Stream"
        default: return d
        }
    }
}

// MARK: - color

struct ColorMenu: View {
    @ObservedObject var cam: Camera
    var body: some View {
        Form {
            wheel("Lift", "/colorCorrection/lift", -2...2, neutral: 0)
            wheel("Gamma", "/colorCorrection/gamma", -4...4, neutral: 0)
            wheel("Gain", "/colorCorrection/gain", 0...16, neutral: 1)
            wheel("Offset", "/colorCorrection/offset", -8...8, neutral: 0)
            Section("Contrast") {
                let c = cam.v("/colorCorrection/contrast")
                SliderRow(label: "PIVOT", value: c["pivot"].double ?? 0.5, range: 0...1, text: { String(format: "%.2f", $0) }) {
                    cam.putLive("/colorCorrection/contrast", ["pivot": .number($0)])
                }
                SliderRow(label: "ADJUST", value: c["adjust"].double ?? 1, range: 0...2, text: { String(format: "%.2f", $0) }) {
                    cam.putLive("/colorCorrection/contrast", ["adjust": .number($0)])
                }
            }
            Section("Color") {
                let c = cam.v("/colorCorrection/color")
                SliderRow(label: "HUE", value: c["hue"].double ?? 0, range: -1...1, text: { String(format: "%.0f°", $0 * 180) }) {
                    cam.putLive("/colorCorrection/color", ["hue": .number($0)])
                }
                SliderRow(label: "SAT", value: c["saturation"].double ?? 1, range: 0...2, text: { String(format: "%.0f%%", $0 * 100) }) {
                    cam.putLive("/colorCorrection/color", ["saturation": .number($0)])
                }
                SliderRow(label: "LUMA MIX", value: cam.v("/colorCorrection/lumaContribution")["lumaContribution"].double ?? 1, range: 0...1,
                          text: { String(format: "%.0f%%", $0 * 100) }) {
                    cam.putLive("/colorCorrection/lumaContribution", ["lumaContribution": .number($0)])
                }
            }
            Section {
                Button("Reset all color correction", role: .destructive) {
                    for (p, n) in [("/colorCorrection/lift", 0.0), ("/colorCorrection/gamma", 0), ("/colorCorrection/gain", 1), ("/colorCorrection/offset", 0)] {
                        cam.put(p, ["red": .number(n), "green": .number(n), "blue": .number(n), "luma": .number(n)])
                    }
                    cam.put("/colorCorrection/contrast", ["pivot": 0.5, "adjust": 1])
                    cam.put("/colorCorrection/color", ["hue": 0, "saturation": 1])
                    cam.put("/colorCorrection/lumaContribution", ["lumaContribution": 1])
                }
            } footer: { Text("Applies to the camera's monitoring and the stream. BRAW clips keep it as metadata.") }
        }
        .navigationTitle("Color")
    }

    private func wheel(_ title: String, _ path: String, _ range: ClosedRange<Double>, neutral: Double) -> some View {
        let v = cam.v(path)
        return Section(title) {
            ForEach(["red", "green", "blue", "luma"], id: \.self) { k in
                SliderRow(label: k.uppercased(), value: v[k].double ?? neutral, range: range, text: { String(format: "%.2f", $0) }) {
                    cam.putLive(path, [k: .number($0)])
                }
            }
        }
    }
}

// MARK: - slate

struct SlateMenu: View {
    @ObservedObject var cam: Camera
    var body: some View {
        let s = cam.v("/slates/nextClip")
        let clip = s["clip"], lens = s["lens"], project = s["project"]
        Form {
            Section("Next clip") {
                Stepper("Reel \(clip["reel"].int ?? 1)", value: Binding(get: { clip["reel"].int ?? 1 },
                        set: { cam.put("/slates/nextClip", ["clip": ["reel": .number(Double($0))]]) }), in: 1...999)
                TextRow(title: "Scene", value: clip["scene"].string ?? "") { cam.put("/slates/nextClip", ["clip": ["scene": .string($0)]]) }
                Stepper("Take \(clip["take"].int ?? 1)", value: Binding(get: { clip["take"].int ?? 1 },
                        set: { cam.put("/slates/nextClip", ["clip": ["take": .number(Double($0))]]) }), in: 1...99)
                Toggle("Auto-increment take", isOn: flag(cam, "/slates/takeAutoIncrement"))
                PickerRow(title: "Shot", options: ["None", "WS", "MS", "MCU", "CU", "BCU", "ECU"], selected: clip["shotType"].string) {
                    cam.put("/slates/nextClip", ["clip": ["shotType": .string($0)]])
                }
                PickerRow(title: "Take type", options: ["None", "PU", "VFX", "SER"], selected: clip["takeType"].string) {
                    cam.put("/slates/nextClip", ["clip": ["takeType": .string($0)]])
                }
                PickerRow(title: "Location", options: ["Interior", "Exterior"], selected: clip["sceneLocation"].string) {
                    cam.put("/slates/nextClip", ["clip": ["sceneLocation": .string($0)]])
                }
                PickerRow(title: "Time", options: ["Day", "Night"], selected: clip["sceneTime"].string) {
                    cam.put("/slates/nextClip", ["clip": ["sceneTime": .string($0)]])
                }
                Toggle("Good take", isOn: Binding(get: { clip["goodTake"].bool == true },
                                                  set: { cam.put("/slates/nextClip", ["clip": ["goodTake": .bool($0)]]) }))
            }
            Section("Project") {
                ForEach([("projectName", "Project"), ("director", "Director"), ("camera", "Camera"), ("cameraOperator", "Operator")], id: \.0) { k, t in
                    TextRow(title: t, value: project[k].string ?? "") { cam.put("/slates/nextClip", ["project": [k: .string($0)]]) }
                }
                Button("Clear project details") { Task { await cam.post("/slates/nextClip/resetProjectData"); await cam.refresh("/slates/nextClip") } }
            }
            Section("Lens") {
                ForEach([("lensType", "Lens"), ("iris", "Iris"), ("focalLength", "Focal length"), ("distance", "Distance"), ("filter", "Filter")], id: \.0) { k, t in
                    TextRow(title: t, value: lens[k].string ?? "") { cam.put("/slates/nextClip", ["lens": [k: .string($0)]]) }
                }
                Button("Clear lens details") { Task { await cam.post("/slates/nextClip/resetLensData"); await cam.refresh("/slates/nextClip") } }
            }
        }
        .navigationTitle("Slate")
    }
}

/// A text field that sends its value when editing ends.
struct TextRow: View {
    let title: String
    let value: String
    let commit: (String) -> Void
    @State private var text = ""
    @FocusState private var focused: Bool
    var body: some View {
        HStack {
            Text(title)
            TextField(title, text: $text).multilineTextAlignment(.trailing).focused($focused)
                .onSubmit { if text != value { commit(text) } }
                .onChange(of: focused) { _, f in if !f && text != value { commit(text) } }
        }
        .onAppear { text = value }
        .onChange(of: value) { _, v in if !focused { text = v } }
    }
}

// MARK: - presets & LUTs

struct PresetsMenu: View {
    @ObservedObject var cam: Camera
    @State private var newName = ""
    var body: some View {
        let presets = cam.v("/presets")["presets"].array.compactMap(\.string)
        let active = cam.v("/presets/active")["preset"].string
        let luts = cam.v("/luts")["luts"].array
        let slot0 = cam.v("/luts/slots/0")
        Form {
            Section {
                if presets.isEmpty { Text("No presets saved on the camera").foregroundStyle(.secondary) }
                ForEach(presets, id: \.self) { p in
                    HStack {
                        Button(p) { cam.put("/presets/active", ["preset": .string(p)]) }
                        Spacer()
                        if p == active { Image(systemName: "checkmark") }
                    }
                    .swipeActions {
                        Button("Delete", role: .destructive) {
                            Task { await cam.action("DELETE", "/presets/\(enc(p))"); await cam.refresh("/presets") }
                        }
                        Button("Update") { Task { await cam.action("PUT", "/presets/\(enc(p))") } }
                    }
                }
                HStack {
                    TextField("New preset name", text: $newName)
                    Button("Save current") {
                        let n = newName.trimmingCharacters(in: .whitespaces)
                        Task { if await cam.action("PUT", "/presets/\(enc(n))") { newName = ""; await cam.refresh("/presets") } }
                    }
                    .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            } header: { Text("Presets") } footer: { Text("Tap to load a preset. Swipe for update (save the current settings into it) or delete.") }
            Section {
                ForEach(Array(luts.enumerated()), id: \.offset) { _, l in
                    let file = l["fileName"].string ?? ""
                    Button {
                        cam.put("/luts/slots/0", ["fileName": .string(file)])
                    } label: {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(l["title"].string ?? file)
                                Text("\(l["inputColorScience"].string ?? "") → \(l["outputGamut"].string ?? "") \(l["outputGamma"].string ?? "")")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if slot0["fileName"].string == file { Image(systemName: "checkmark") }
                        }
                    }
                    .foregroundStyle(.primary)
                }
            } header: { Text("LUT in slot 1") } footer: { Text("Turn the LUT on per display in Monitor, or embed it in clips in Record.") }
        }
        .navigationTitle("Presets & LUTs")
        .task { await cam.refresh("/presets"); await cam.refresh("/luts/slots/0") }
    }

    private func enc(_ s: String) -> String { s.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? s }
}

// MARK: - setup

struct SetupMenu: View {
    @ObservedObject var cam: Camera
    var body: some View {
        let p = cam.v("/system/product")
        Form {
            Section("Camera") {
                Toggle("Color bars", isOn: flag(cam, "/camera/colorBars"))
                Toggle("Program feed on LCD", isOn: flag(cam, "/camera/programFeedDisplay"))
                PickerRow(title: "Tally", options: ["None", "Preview", "Program"], selected: cam.v("/camera/tallyStatus")["status"].string) {
                    cam.put("/camera/tallyStatus", ["status": .string($0)])
                }
                PickerRow(title: "Battery shown as", options: ["Percentage", "Voltage"], selected: cam.v("/camera/power/displayMode")["mode"].string) {
                    cam.put("/camera/power/displayMode", ["mode": .string($0)])
                }
            }
            let buttons = cam.v("/panel/devices").array.filter { $0["enabled"].bool != false }
            if !buttons.isEmpty {
                Section {
                    ForEach(Array(buttons.enumerated()), id: \.offset) { _, b in
                        Button("Press \(b["label"].string ?? "") (\(b["name"].string ?? ""))") {
                            Task { await cam.action("PUT", "/panel/devices/\(b["name"].string ?? "")/state", ["action": "press"]) }
                        }
                    }
                } header: { Text("Function buttons") } footer: { Text("Does whatever the button is assigned to on the camera.") }
            }
            Section("Info") {
                LabeledContent("Model", value: p["productName"].string ?? "–")
                LabeledContent("Name", value: p["deviceName"].string ?? "–")
                LabeledContent("Firmware", value: p["softwareVersion"].string ?? "–")
                LabeledContent("Camera ID", value: cam.v("/camera/id")["id"].int.map(String.init) ?? "–")
                LabeledContent("Reference lock", value: cam.v("/camera/timingReferenceLock")["locked"].bool == true ? "Locked" : "Not locked")
                LabeledContent("Timecode source", value: cam.v("/transports/0/timecode/source")["timecodeInputSource"].string ?? "–")
                LabeledContent("Network access", value: cam.v("/access/status")["availability"].string ?? "–")
            }
            let projects = cam.v("/cloud/projects").array
            if !projects.isEmpty {
                Section("Blackmagic Cloud") {
                    LabeledContent("Active project", value: cam.v("/cloud/projects/active")["name"].string ?? "None")
                    ForEach(Array(projects.enumerated()), id: \.offset) { _, pr in
                        let st = pr["status"]
                        LabeledContent(pr["name"].string ?? "", value: (st["uploadPercent"].int ?? -1) >= 0 ? "\(st["uploadPercent"].int!)% uploaded" : "Idle")
                    }
                    let up = cam.v("/cloud/clips/activeUploading").array
                    if !up.isEmpty { LabeledContent("Uploading", value: "\(up.count) clips") }
                }
            }
        }
        .navigationTitle("Setup")
    }
}

// MARK: - livestream

struct StreamMenu: View {
    @ObservedObject var cam: Camera
    @State private var profiles: [String] = []
    var body: some View {
        let s = cam.v("/livestreams/0")
        let a = cam.v("/livestreams/0/activePlatform")
        let streaming = s["status"].string == "Streaming" || s["status"].string == "Connecting"
        Form {
            Section {
                LabeledContent("State", value: s["status"].string ?? "–")
                if let b = s["bitrate"].double, b > 0 { LabeledContent("Bitrate", value: String(format: "%.1f Mb/s", b / 1e6)) }
                if let f = s["effectiveVideoFormat"].string { LabeledContent("Format", value: f) }
                if let c = s["cache"].double { LabeledContent("Cache", value: String(format: "%.0f%%", c)) }
                Button(streaming ? "Stop streaming" : "Start streaming", role: streaming ? .destructive : nil) {
                    Task { await cam.action("PUT", streaming ? "/livestreams/0/stop" : "/livestreams/0/start") }
                }
                .disabled(cam.v("/livestreams/0/available")["available"].bool == false)
            } header: { Text("Status") } footer: {
                Text("This app watches the camera through this stream: stopping it stops the picture here.")
            }
            Section("Destination") {
                PickerRow(title: "Platform", options: cam.v("/livestreams/platforms").array.compactMap(\.string), selected: a["platform"].string) { p in
                    cam.put("/livestreams/0/activePlatform", ["platform": .string(p)])
                    Task { await loadProfiles(p) }
                }
                if !profiles.isEmpty {
                    PickerRow(title: "Quality", options: profiles, selected: a["quality"].string) {
                        cam.put("/livestreams/0/activePlatform", ["quality": .string($0)])
                    }
                }
                if let server = a["server"].string { LabeledContent("Server", value: server) }
            }
        }
        .navigationTitle("Livestream")
        .task { if let p = a["platform"].string { await loadProfiles(p) } }
    }

    private func loadProfiles(_ platform: String) async {
        let enc = platform.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? platform
        profiles = (await cam.get("/livestreams/platforms/\(enc)"))?["profiles"].array.compactMap { $0["profile"].string } ?? []
    }
}

// MARK: - connection

struct ConnectionMenu: View {
    @ObservedObject var cam: Camera
    @Binding var relayHost: String
    let ssid: String
    let rejoin: (() -> Void)?
    @State private var user = ""
    @State private var pass = ""

    var body: some View {
        Form {
            Section {
                LabeledContent("Relay", value: relayHost.isEmpty ? WiFi.relayName : relayHost)
                LabeledContent("Camera", value: cam.host.isEmpty ? "Looking for it…" : cam.host)
            } footer: { Text("Found by themselves: the relay by name on the PYXIS-Stream Wi-Fi, the camera through the relay.") }
            Section {
                TextField("Secure Login username (if used)", text: $user).plainField()
                SecureField("Secure Login password", text: $pass)
            } header: { Text("Camera control") } footer: {
                Text("Needs Web media manager on (Blackmagic Camera Setup → Network Access). A login is only needed when it's set to \"Enabled with security only\"; it's kept in the iPhone's Keychain and only sent over HTTPS.")
            }
            if !ssid.isEmpty {
                Section("Wi-Fi") {
                    LabeledContent("Network", value: ssid)
                    if let rejoin { Button("Join \(ssid) again", action: rejoin) }
                }
            }
            Section {
                Button("Save and reconnect") {
                    cam.manualHost = ""
                    cam.username = user
                    cam.password = pass
                    cam.start(relay: relayHost)
                }
            }
        }
        .navigationTitle("Connection")
        .onAppear { user = cam.username; pass = cam.password }
    }
}

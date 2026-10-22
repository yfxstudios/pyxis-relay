import SwiftUI
import UniformTypeIdentifiers

private let cubeType = UTType(filenameExtension: "cube", conformingTo: .data) ?? .data
private let cameraLUT = "/monitoring/Stream/displayLUT"

/// The docked LUT chooser (hold the LUT button): monitor LUT on/off, the film looks and
/// imported LUTs, import, and a warning if the stream is still the camera's log picture.
struct LUTChooser: View {
    @ObservedObject var cam: Camera
    @ObservedObject var luts: MonitorLUTs
    let close: () -> Void
    @State private var importing = false
    /// The camera's Stream LUT state has been read since the chooser opened. Until then the
    /// warning stays hidden, so an old reading can't flash it up.
    @State private var fresh = false

    var body: some View {
        let options = FilmLook.allCases.map { MonitorLUTs.Choice.look($0) } + luts.imported.map { .file($0) }
        let cameraOn = cam.v(cameraLUT)["enabled"].bool == true
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Text("MONITOR LUT").font(.system(size: 13, weight: .bold)).foregroundStyle(.white.opacity(0.75))
                Spacer()
                Button(luts.enabled ? "On" : "Off") { luts.setEnabled(!luts.enabled) }
                    .font(.system(size: 14, weight: .semibold))
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .background(luts.enabled ? Color.white : .clear, in: RoundedRectangle(cornerRadius: 6))
                    .foregroundStyle(luts.enabled ? Color.black : .white)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(.white.opacity(0.7)))
                    .accessibilityLabel(luts.enabled ? "Monitor LUT on" : "Monitor LUT off")
                Button(action: close) { Image(systemName: "xmark").font(.system(size: 13, weight: .bold)).frame(width: 30, height: 30) }
                    .accessibilityLabel("Close")
            }
            ScrollViewReader { proxy in
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 22) {
                        ForEach(options, id: \.self) { c in
                            let selected = luts.enabled && luts.choice == c
                            Button { luts.select(c) } label: {
                                VStack(spacing: 5) {
                                    Text(luts.name(c)).font(.system(size: 17)).lineLimit(1)
                                    Rectangle().fill(selected ? Color.white : .clear).frame(height: 2.5)
                                }
                                .fixedSize()
                                .frame(minHeight: 44)
                            }
                            .id(c)
                            .accessibilityAddTraits(selected ? .isSelected : [])
                        }
                        Button { importing = true } label: {
                            Label("Import .cube", systemImage: "plus").font(.system(size: 15, weight: .semibold))
                                .padding(.horizontal, 10).padding(.vertical, 6)
                                .overlay(RoundedRectangle(cornerRadius: 6).stroke(.white.opacity(0.7)))
                        }
                    }
                    .padding(.horizontal, 2)
                }
                .onAppear { proxy.scrollTo(luts.choice, anchor: .center) }
            }
            if fresh && luts.enabled && cam.has(cameraLUT) && !cameraOn {
                VStack(alignment: .leading, spacing: 8) {
                    Label {
                        Text("The camera's LUT is off, so the stream is log. The film looks are made for Rec.709.")
                            .font(.system(size: 13)).fixedSize(horizontal: false, vertical: true)
                    } icon: {
                        Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.yellow)
                    }
                    Button("Turn camera LUT on") { cam.put(cameraLUT, ["enabled": true]) }
                        .font(.system(size: 14, weight: .semibold))
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(.white.opacity(0.7)))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else if luts.enabled && !cam.has(cameraLUT) && cam.v("/system/dynamicRange")["dynamicRange"].string == "Film" {
                // cameras without a separate Stream output: warn from the dynamic range instead
                Label {
                    Text("The camera is in Film dynamic range, so the stream may be log. The film looks are made for Rec.709: turn on a display LUT for the output the camera streams, or use Video dynamic range.")
                        .font(.system(size: 13)).fixedSize(horizontal: false, vertical: true)
                } icon: {
                    Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.yellow)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                Text("Applied in this app only, on top of the camera's Rec.709 picture.")
                    .font(.system(size: 12)).foregroundStyle(.white.opacity(0.6))
            }
        }
        .frame(maxWidth: 700)
        .task {  // the camera doesn't push this output's LUT state: ask before warning
            fresh = await cam.refreshUnpublished()
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [cubeType]) { result in
            if case .success(let url) = result { luts.importLUT(from: url) }
        }
    }
}

/// Menu → Monitor LUTs: choose, import and delete; the camera's Stream LUT for reference.
struct MonitorLUTMenu: View {
    @ObservedObject var cam: Camera
    @ObservedObject var luts: MonitorLUTs
    @State private var importing = false

    var body: some View {
        Form {
            Section {
                Toggle("Monitor LUT", isOn: Binding(get: { luts.enabled }, set: { luts.setEnabled($0) }))
            } footer: {
                Text("Applied by this app to the picture you watch, like a LUT on a field monitor. The camera, its outputs and recordings aren't changed. Tap the LUT button to switch it on and off; hold it to choose.")
            }
            Section {
                ForEach(FilmLook.allCases) { l in row(.look(l), subtitle: l.blurb) }
            } header: { Text("Film looks") } footer: {
                Text("Made for Rec.709: they go on top of the camera's own LUT on its Stream output (e.g. Film to Extended Video), like a look LUT after a technical conversion.")
            }
            Section {
                ForEach(luts.imported, id: \.self) { f in
                    row(.file(f), subtitle: nil)
                        .swipeActions { Button("Delete", role: .destructive) { luts.delete(f) } }
                }
                Button { importing = true } label: { Label("Import a .cube LUT…", systemImage: "plus") }
            } header: { Text("Your LUTs") } footer: {
                Text("3D .cube LUTs from the Files app, up to 129 points. Swipe to delete.")
            }
            if cam.has(cameraLUT) {
                Section {
                    Toggle("Camera LUT on the stream", isOn: Binding(get: { cam.v(cameraLUT)["enabled"].bool == true },
                                                                    set: { cam.put(cameraLUT, ["enabled": .bool($0)]) }))
                } footer: {
                    Text("The camera's own LUT on its Stream output: it turns the camera's log picture into Rec.709. Keep it on for the film looks here.")
                }
            }
        }
        .navigationTitle("Monitor LUTs")
        .fileImporter(isPresented: $importing, allowedContentTypes: [cubeType]) { result in
            if case .success(let url) = result { luts.importLUT(from: url) }
        }
    }

    private func row(_ c: MonitorLUTs.Choice, subtitle: String?) -> some View {
        Button { luts.select(c) } label: {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(luts.name(c)).foregroundStyle(.primary)
                    if let subtitle { Text(subtitle).font(.caption).foregroundStyle(.secondary) }
                }
                Spacer()
                if luts.enabled && luts.choice == c { Image(systemName: "checkmark").foregroundStyle(HUDStyle.accent) }
            }
        }
    }
}

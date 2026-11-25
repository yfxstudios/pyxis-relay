import SwiftUI

// Menu → HDMI output: the frame guide on the relay's own HDMI output (a screen plugged into
// the relay). Set through http://<relay>/cgi-bin/pyxis-hdmi; the relay shows a change within
// a second, without interrupting the stream.

struct RelayHDMIMenu: View {
    let relayHost: String

    enum Load: Equatable { case loading, ready, notInstalled, failed(String) }
    @State private var load = Load.loading
    @State private var guide = "off"
    @State private var shade = 60.0
    @State private var fill = false
    @State private var saving: Task<Void, Never>?
    @State private var sent = ""  // the settings the relay has (to send only changes)

    private static let guides = ["off"] + FrameGuide.allCases.dropFirst().map(\.rawValue)

    var body: some View {
        Form {
            switch load {
            case .loading:
                HStack { ProgressView(); Text("Asking the relay…").foregroundStyle(.secondary) }
            case .notInstalled:
                Text("This relay has no HDMI player installed.").foregroundStyle(.secondary)
            case .failed(let m):
                Text(m).foregroundStyle(.secondary)
                Button("Try again") { Task { await read() } }
            case .ready:
                Section {
                    Picker("Frame", selection: $guide) {
                        ForEach(Self.guides, id: \.self) { Text($0 == "off" ? "None" : $0).tag($0) }
                    }
                    VStack(alignment: .leading) {
                        HStack {
                            Text("Outside the frame")
                            Spacer()
                            Text("\(Int(shade))% dark").monospacedDigit().foregroundStyle(.secondary)
                        }
                        Slider(value: $shade, in: 0...100, step: 5)
                    }
                    .disabled(guide == "off")
                    Toggle("Fill the screen", isOn: $fill)
                } header: { Text("Frame guide") } footer: {
                    Text("On the screen plugged into the relay's HDMI port. The frame sits inside the area the camera records (in 6:5 or 3:2 the stream has black bars), and Fill zooms the frame to the screen. The change shows within a second.")
                }
            }
        }
        .navigationTitle("HDMI Output")
        .task { await read() }
        .onChange(of: guide) { _, _ in save() }
        .onChange(of: shade) { _, _ in save() }
        .onChange(of: fill) { _, _ in save() }
    }

    private var query: String { "?guide=\(guide.replacingOccurrences(of: ":", with: "%3A"))&shade=\(Int(shade))&fill=\(fill ? 1 : 0)" }

    private func url(_ query: String = "") -> URL? { URL(string: "http://\(relayHost)/cgi-bin/pyxis-hdmi\(query)") }

    private func apply(_ data: Data) {
        let j = JSON(data: data)
        guard j["ok"].bool == true else { load = .failed(j["error"].string ?? "The relay didn't accept that."); return }
        guard j["installed"].bool == true else { load = .notInstalled; return }
        guide = j["guide"].string ?? "off"
        shade = j["shade"].double ?? 60
        fill = j["fill"].bool == true
        sent = query
        load = .ready
    }

    private func read() async {
        load = .loading
        guard let u = url(), let (data, resp) = try? await URLSession.shared.data(from: u) else {
            load = .failed("Couldn't reach the relay at \(relayHost)."); return
        }
        if (resp as? HTTPURLResponse)?.statusCode == 404 {
            load = .failed("This relay's software is older: update it to set the HDMI frame guide from here."); return
        }
        apply(data)
    }

    /// Sends the settings a moment after the last change (the slider sends many).
    private func save() {
        let q = query
        guard load == .ready, q != sent else { return }
        sent = q
        saving?.cancel()
        saving = Task {
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled, let u = url(q) else { return }
            var r = URLRequest(url: u)
            r.httpMethod = "POST"
            if let (data, _) = try? await URLSession.shared.data(for: r), JSON(data: data)["ok"].bool != true {
                load = .failed(JSON(data: data)["error"].string ?? "The relay didn't accept that.")
            }
        }
    }
}

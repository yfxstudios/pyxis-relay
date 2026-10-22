import SwiftUI
import AVFoundation

@main
struct PyxisViewerApp: App {
    var body: some Scene {
        #if os(macOS)
        // one window: links (pyxisviewer://) go to it instead of opening another
        Window("PYXIS Viewer", id: "viewer") { RootView() }
            .defaultSize(width: 1280, height: 760)
            .windowStyle(.hiddenTitleBar)
            .commands { ViewerCommands() }
        #else
        WindowGroup { RootView() }
        #endif
    }
}

struct RootView: View {
    @StateObject private var player = StreamPlayer()
    @StateObject private var cam = Camera()
    @StateObject private var luts = MonitorLUTs()
    @StateObject private var capture = Capture()
    @AppStorage("relayHost") private var relayHost = ""
    @AppStorage("ssid") private var ssid = ""
    @AppStorage("swipeHintShown") private var swipeHintShown = false
    @Environment(\.scenePhase) private var phase

    @State private var joining: String?       // network being joined
    @State private var joinError: String?
    @State private var showMenu = false
    @State private var chrome = true           // false = clean feed
    @State private var panel: QuickPanel?
    @State private var hint: String?
    @State private var focusTap: CGPoint?       // last tap-to-focus point (0...1) while its box shows
    @State private var focusTapID = UUID()
    @State private var focusResult: String?
    @State private var showAFRail = false
    @State private var railHide: Task<Void, Never>?
    @State private var pendingLink: JoinLink?  // for "Join again"

    private var content: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if relayHost.isEmpty && joining == nil {
                WelcomeView { host in relayHost = host; start() }
            } else {
                viewer.hudButtons()
            }
        }
        .preferredColorScheme(.dark)
        .hideStatusBar(!chrome)
        .persistentSystemOverlays(chrome ? .automatic : .hidden)
    }

    /// Links, app state, camera and LUT messages.
    private func events(_ v: some View) -> some View {
        v
        .onOpenURL(perform: handle)
        .onChange(of: phase) { _, p in
            if p == .active { start() } else if p == .background { capture.stopRecording(); player.stop(); cam.stop() }
        }
        .onChange(of: player.state) { _, s in ScreenAwake.set(s == .playing) }
        .onChange(of: AF.state(cam)) { _, s in
            if focusTap != nil, s == "Focused" || s == "Error" { focusResult = s }  // keep it until the box fades
        }
        .onChange(of: luts.message) { _, m in
            guard let m else { return }
            flash(m)
            luts.message = nil
        }
        .onChange(of: capture.message) { _, m in
            guard let m else { return }
            flash(m)
            capture.message = nil
        }
        .onChange(of: cam.message) { _, m in
            guard let m else { return }
            flash(m)
            cam.message = nil
        }
    }

    var body: some View {
        menuCommands(events(content))
        .onAppear {
            start()
            #if DEBUG && os(iOS)
            // `-landscape` / `-portrait` launch arguments: rotate (for testing in the Simulator)
            let args = ProcessInfo.processInfo.arguments
            if let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene {
                if args.contains("-landscape") { scene.requestGeometryUpdate(.iOS(interfaceOrientations: .landscapeRight)) { _ in } }
                if args.contains("-portrait") { scene.requestGeometryUpdate(.iOS(interfaceOrientations: .portrait)) { _ in } }
            }
            #endif
        }
        .sheet(isPresented: $showMenu) {
            CameraMenu(cam: cam, luts: luts, relayHost: $relayHost, ssid: ssid,
                       rejoin: pendingLink.map { l in { showMenu = false; Task { await join(l) } } }) {
                showMenu = false
                if !relayHost.isEmpty && player.state == .idle { start() }
            }
            .macSheetSize()
        }
    }

    /// The picture with its controls, focus boxes, AF rail and status.
    private var viewer: some View {
        GeometryReader { geo in
            let portrait = geo.size.height > geo.size.width
            ZStack {
                // the picture fills the whole screen; taps are mapped onto it for focus
                GeometryReader { full in
                    let video = AVMakeRect(aspectRatio: player.videoSize == .zero ? CGSize(width: 16, height: 9) : player.videoSize,
                                           insideRect: CGRect(origin: .zero, size: full.size))
                    ZStack {
                        VideoLayerView(layer: player.layer)
                        FocusOverlay(cam: cam, video: video, tap: focusTap, result: focusResult, showAreas: chrome && AF.supported(cam))
                    }
                    .contentShape(Rectangle())
                    .onTapGesture(coordinateSpace: .local) { p in tapVideo(at: p, video: video) }
                    .gesture(swipe)
                }
                .ignoresSafeArea()
                // swipe in from the right edge: the autofocus mode rail
                if AF.supported(cam) && !showAFRail {
                    HStack {
                        Spacer()
                        Color.clear.frame(width: 28).contentShape(Rectangle())
                            .gesture(DragGesture(minimumDistance: 12).onEnded { g in
                                if g.translation.width < -24 { openAFRail() }
                            })
                    }
                    .ignoresSafeArea()
                }
                if chrome { controls(portrait: portrait).transition(.opacity) }
                if (showAFRail || (Platform.railAlwaysShown && chrome)) && AF.supported(cam) {
                    HStack {
                        Spacer()
                        AFModeRail(cam: cam) { scheduleRailHide(after: 1.2) }
                            .gesture(DragGesture(minimumDistance: 12).onEnded { g in
                                if g.translation.width > 24 { closeAFRail() }
                            })
                    }
                    .transition(.move(edge: .trailing).combined(with: .opacity))
                }
                centerStatus
                if let hint {
                    Text(hint).font(.footnote.weight(.semibold))
                        .padding(.horizontal, 14).padding(.vertical, 8)
                        .background(.ultraThinMaterial, in: Capsule())
                        .transition(.opacity)
                        .allowsHitTesting(false)
                }
            }
        }
    }

    // MARK: overlay

    private func controls(portrait: Bool) -> some View {
        VStack(spacing: 0) {
            TopBar(cam: cam, compact: portrait, panel: $panel) { panel = nil; showMenu = true }
            if !cam.isConnected { cameraLinkChip.padding(.top, 8) }
            if let since = capture.recordingSince { LocalRecordingPill(since: since).padding(.top, 8) }
            Spacer(minLength: 0)
            if let joinError {
                Text(joinError).font(.callout).multilineTextAlignment(.center)
                    .padding(12).background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12)).padding()
            }
            // A selected setting's picker takes the bottom bar's place, as on the camera.
            if let p = panel {
                QuickPanelView(cam: cam, luts: luts, panel: p) { withAnimation(.easeOut(duration: 0.15)) { panel = nil } }
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            } else {
                if portrait {
                    HStack { Spacer(); CaptureButtons(capture: capture) }
                        .padding(.trailing, 8).padding(.bottom, 2)
                        .shadow(color: HUDStyle.shadow, radius: 2, x: 0, y: 1)
                }
                BottomBar(cam: cam, luts: luts, capture: capture, compact: portrait, panel: $panel)
            }
        }
        .animation(.easeOut(duration: 0.15), value: panel)
    }

    private var cameraLinkChip: some View {
        Button { showMenu = true } label: {
            HStack(spacing: 8) {
                Circle().fill(chipColor).frame(width: 7, height: 7)
                Text(chipText).font(.caption.weight(.semibold)).lineLimit(1)
            }
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(.black.opacity(0.7), in: Capsule())
            .foregroundStyle(.white)
        }
    }

    private var chipText: String {
        switch cam.link {
        case .off, .searching: return "Camera control: looking for the camera…"
        case .connecting(let h): return "Camera control: connecting to \(h)…"
        case .needsLogin: return "Camera control: needs the camera's Secure Login"
        case .failed(let m): return "Camera control: \(m)"
        case .connected: return ""
        }
    }

    private var chipColor: Color {
        if case .needsLogin = cam.link { return .red }
        if case .failed = cam.link { return .red }
        return .orange
    }

    /// Stream state in the middle of the picture (shown even with the controls hidden).
    @ViewBuilder private var centerStatus: some View {
        if let joining {
            statusText("Joining \(joining)…")
        } else {
            switch player.state {
            case .playing: EmptyView()
            case .idle, .connecting: statusText("Connecting to \(relayHost)…")
            case .offline: statusText("Waiting for the camera to stream")
            case .failed(let m): statusText(m)
            }
        }
    }

    private func statusText(_ s: String) -> some View {
        HStack(spacing: 10) {
            ProgressView().tint(.white)
            Text(s).font(.subheadline.weight(.semibold))
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .background(.black.opacity(0.6), in: Capsule())
        .foregroundStyle(.white)
        .allowsHitTesting(false)
    }

    // MARK: gestures

    /// Swipe up or down on the picture: hide or bring back every control (clean feed).
    /// Up or down: controls away (clean feed) and back. Right to left: the autofocus mode rail
    /// (left to right closes it); handy with a mouse, where an edge swipe isn't.
    private var swipe: some Gesture {
        DragGesture(minimumDistance: 24).onEnded { g in
            let dx = g.translation.width, dy = g.translation.height
            if abs(dy) > 50, abs(dy) > abs(dx) * 1.3 { setChrome(!chrome); return }
            guard abs(dx) > 60, abs(dx) > abs(dy) * 1.3 else { return }
            if dx < 0 { if AF.supported(cam) { openAFRail() } } else if showAFRail { closeAFRail() }
        }
    }

    /// The Mac's menu-bar commands (see ViewerCommands).
    private func menuCommands(_ v: some View) -> some View {
        v.onReceive(NotificationCenter.default.publisher(for: .viewerCommand)) { n in
            switch n.object as? ViewerCommand {
            case .cameraMenu?: panel = nil; showMenu = true
            case .cleanFeed?: setChrome(!chrome)
            case .monitorLUT?: luts.setEnabled(!luts.enabled)
            case .grabFrame?: capture.grabFrame()
            case .localRecording?: capture.toggleRecording()
            case .focusMode(let m)?: if AF.supported(cam) { AF.setMode(cam, m) }
            case nil: break
            }
        }
    }

    /// A tap on the picture: closes the AF rail or an open picker, brings the controls back in
    /// clean feed, and otherwise focuses there (when the lens has autofocus).
    private func tapVideo(at p: CGPoint, video: CGRect) {
        if showAFRail { closeAFRail(); return }
        if panel != nil { withAnimation(.easeOut(duration: 0.15)) { panel = nil }; return }
        if !chrome { setChrome(true); return }
        guard AF.supported(cam), video.contains(p), video.width > 0, video.height > 0 else { return }
        let n = CGPoint(x: (p.x - video.minX) / video.width, y: (p.y - video.minY) / video.height)
        Haptic.light()
        AF.focus(cam, at: n)
        let id = UUID()
        focusTapID = id
        focusResult = nil
        withAnimation(.easeOut(duration: 0.15)) { focusTap = n }
        Task {
            try? await Task.sleep(for: .seconds(2.5))
            if focusTapID == id { withAnimation(.easeOut(duration: 0.3)) { focusTap = nil } }
        }
    }

    private func openAFRail() {
        withAnimation(.easeOut(duration: 0.2)) { showAFRail = true }
        scheduleRailHide(after: 5)
    }

    private func closeAFRail() {
        railHide?.cancel()
        withAnimation(.easeOut(duration: 0.2)) { showAFRail = false }
    }

    private func scheduleRailHide(after seconds: Double) {
        railHide?.cancel()
        railHide = Task {
            try? await Task.sleep(for: .seconds(seconds))
            if !Task.isCancelled { closeAFRail() }
        }
    }

    private func setChrome(_ on: Bool) {
        withAnimation(.easeOut(duration: 0.2)) {
            chrome = on
            panel = nil
        }
        if !on && !swipeHintShown {
            swipeHintShown = true
            flash("Swipe or tap to bring the controls back")
        }
    }

    private func flash(_ text: String) {
        withAnimation { hint = text }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.2) { withAnimation { if hint == text { hint = nil } } }
    }

    // MARK: connection

    private func start() {
        guard joining == nil, !relayHost.isEmpty, phase != .background else { return }
        player.lutBox = luts.box
        player.frameTap = capture.tap
        capture.cameraName = { [cam] in cam.v("/system/product")["productName"].string }
        player.play(relayHost: relayHost)
        cam.start(relay: relayHost)
    }

    private func handle(_ url: URL) {
        #if DEBUG
        // pyxisviewer://debug-capture?do=frame|record (testing without the UI)
        if url.host == "debug-capture" {
            switch URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first?.value {
            case "frame": capture.grabFrame()
            case "record": capture.toggleRecording()
            default: break
            }
            return
        }
        #endif
        guard let link = JoinLink(url: url) else {
            joinError = "That QR code isn't a camera relay code."
            return
        }
        pendingLink = link
        Task { await join(link) }
    }

    private func join(_ link: JoinLink) async {
        joinError = nil
        player.stop()
        cam.stop()
        relayHost = link.relay
        if !link.ssid.isEmpty {
            ssid = link.ssid
            joining = link.ssid
            joinError = await WiFi.join(ssid: link.ssid, password: link.password)
            joining = nil
        }
        chrome = true
        start()
    }
}

struct WelcomeView: View {
    let connect: (String) -> Void

    var body: some View {
        VStack(spacing: 22) {
            #if os(macOS)
            Image(systemName: "wifi").font(.system(size: 64, weight: .light))
            Text("PYXIS Viewer").font(.largeTitle.bold())
            Text("Join the PYXIS-Stream Wi-Fi from the Wi-Fi menu in the menu bar. The picture starts by itself once the relay answers.")
                .multilineTextAlignment(.center).foregroundStyle(.secondary)
            #else
            Image(systemName: "qrcode.viewfinder").font(.system(size: 64, weight: .light))
            Text("PYXIS Viewer").font(.largeTitle.bold())
            Text("Scan the QR code from your camera relay's settings page with the Camera app. It joins the relay's Wi-Fi and starts the live picture.")
                .multilineTextAlignment(.center).foregroundStyle(.secondary)
            Text("Already on the PYXIS-Stream Wi-Fi? The picture starts by itself.")
                .font(.footnote).foregroundStyle(.secondary)
            #endif
            ProgressView().tint(.white)
        }
        .padding(28)
        .frame(maxWidth: 480)
        .foregroundStyle(.white)
        .task {
            // connect as soon as the relay answers by name (no address to type)
            while !Task.isCancelled {
                if await WiFi.relayReachable(WiFi.relayName) { connect(WiFi.relayName); return }
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }
}

import Foundation
import Security

/// The PYXIS's control API (Blackmagic Camera Control REST API, https://<camera>/control/api/v1,
/// served by the camera's Web media manager) plus its WebSocket notifications.
///
/// - Finds the camera through the relay (http://<relay>/cgi-bin/pyxis-camera), unless an
///   address is set by hand.
/// - Subscribes to every property the camera publishes, so `values` mirrors the camera
///   (keyed by API path, e.g. "/video/iso" -> {"iso": 800}) and changes made on the camera
///   itself show up here.
/// - Writes go out as PUT/POST with an optimistic local update; on failure the value is
///   read back and the error is shown.
@MainActor
final class Camera: ObservableObject {
    enum Link: Equatable {
        case off, searching, connecting(String), connected(String), needsLogin(String), failed(String)
    }

    @Published private(set) var link: Link = .off
    @Published private(set) var values: [String: JSON] = [:]
    /// Paths the camera answered "not supported" (404/501) for: their controls are hidden.
    @Published private(set) var unsupported: Set<String> = []
    @Published var message: String?  // last error, shown briefly
    /// The camera's timecode, run locally between readings (see TimecodeClock).
    @Published private(set) var timecode: TimecodeClock?

    @Published var manualHost: String = UserDefaults.standard.string(forKey: "cameraHost") ?? "" {
        didSet { UserDefaults.standard.set(manualHost, forKey: "cameraHost") }
    }
    @Published var username: String = UserDefaults.standard.string(forKey: "cameraUser") ?? "" {
        didSet { UserDefaults.standard.set(username, forKey: "cameraUser"); auth.set(user: username, password: password) }
    }
    @Published var password: String = Keychain.read() ?? "" {
        didSet { Keychain.save(password); auth.set(user: username, password: password) }
    }

    private let auth = CameraAuth()
    private lazy var session = URLSession(configuration: .ephemeral, delegate: auth, delegateQueue: nil)
    private(set) var host = ""
    private var scheme = "https"
    private var runner: Task<Void, Never>?
    private var socket: URLSessionWebSocketTask?
    private var pending: [String: JSON] = [:]  // events waiting for the next UI refresh
    private var flushScheduled = false
    private var liveSends: [String: JSON] = [:]  // slider values waiting to go out
    private var liveInFlight: Set<String> = []
    private var timecodeSync: Task<Void, Never>?
    private var unpublishedPoll: Task<Void, Never>?
    /// Outputs the camera lists but doesn't publish over the WebSocket (the PYXIS's "Stream").
    private var unpublishedDisplays: [String] = []
    private var lastTimecodeRead: Int?  // frames, to tell running timecode from stopped

    /// Pushed several times a second; not needed live. (The timecode, pushed every frame,
    /// is read every few seconds instead and run locally in between.)
    private static let skipSubscriptions: Set<String> = [
        "/camera/motionSensor/euler", "/camera/motionSensor/horizon", "/transports/0/timecode",
    ]
    private static let timecodeResync: Duration = .seconds(10)
    /// Useful values that aren't published over the WebSocket: read once per connection.
    private static let extraReads = [
        "/system/supportedFormats", "/monitoring/display", "/monitoring/frameGuideRatio/presets",
        "/transports/0/prerecord/supportedMaxDurations", "/media/devices/doformatSupportedFilesystems",
        "/audio/channels", "/lens/opticalImageStabilization", "/lens/jumpPoints/focus", "/lens/jumpPoints/zoom",
        "/video/supportedNDFilters", "/video/ndFilter", "/video/ndFilter/displayMode", "/video/ndFilterSelectable",
        "/video/detailSharpeningLevel", "/system/colorScience", "/system/supportedColorSciences",
        "/livestreams/customPlatforms", "/luts/slots", "/system/dynamicRange",
    ]

    init() { auth.set(user: username, password: password) }

    func v(_ path: String) -> JSON { values[path] ?? .null }
    func has(_ path: String) -> Bool { values[path].map { !$0.isNull } ?? false }
    var isConnected: Bool { if case .connected = link { return true }; return false }

    // MARK: connection

    func start(relay: String) {
        stop()
        runner = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.runOnce(relay: relay)
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }

    func stop() {
        runner?.cancel()
        runner = nil
        timecodeSync?.cancel()
        timecodeSync = nil
        unpublishedPoll?.cancel()
        unpublishedPoll = nil
        socket?.cancel(with: .goingAway, reason: nil)
        socket = nil
        link = .off
    }

    private func runOnce(relay: String) async {
        // 1. where is the camera?
        var candidates: [String] = []
        let manual = manualHost.trimmingCharacters(in: .whitespaces)
        if !manual.isEmpty { candidates = [manual] } else {
            link = .searching
            if let url = URL(string: "http://\(relay)/cgi-bin/pyxis-camera"),
               let (data, _) = try? await session.data(from: url) {
                candidates = JSON(data: data)["cameras"].array.compactMap(\.string)
            }
        }
        guard !candidates.isEmpty else { link = .failed("No camera found on the relay's network"); return }

        // 2. which one answers the API? (HTTPS, or HTTP when there's no login to protect)
        var found = false
        for c in candidates {
            host = c
            link = .connecting(c)
            auth.cameraHost = c.lowercased()
            for s in hasLogin ? ["https"] : ["https", "http"] {
                scheme = s
                if let (code, _) = try? await raw("GET", "/system/product") {
                    if code == 401 || code == 403 { link = .needsLogin(c); return }
                    if code == 200 { found = true; break }
                }
            }
            if found { break }
        }
        guard found else {
            link = .failed("The camera at \(host) isn't answering. Turn on Web media manager in Blackmagic Camera Setup → Network Access.")
            return
        }

        // 3. live values over the WebSocket
        var req = URLRequest(url: URL(string: "\(scheme == "https" ? "wss" : "ws")://\(host)/control/api/v1/event/websocket")!)
        req.timeoutInterval = 10
        let ws = session.webSocketTask(with: req)
        socket = ws
        ws.resume()
        do {
            try await send(ws, ["type": "request", "id": 1, "data": ["action": "listProperties"]])
            link = .connected(host)
            Task { await self.readExtras() }
            unpublishedPoll?.cancel()
            unpublishedPoll = Task { [weak self] in
                // their LUT can be changed elsewhere (camera menu, relay, another app): re-read it
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(5))
                    await self?.refreshUnpublished()
                }
            }
            timecodeSync?.cancel()
            timecodeSync = Task { [weak self] in
                await self?.syncTimecode(probe: true)
                while !Task.isCancelled {
                    try? await Task.sleep(for: Self.timecodeResync)
                    await self?.syncTimecode(probe: false)
                }
            }
            while !Task.isCancelled {
                let msg = try await ws.receive()
                let data: Data
                switch msg {
                case .string(let s): data = Data(s.utf8)
                case .data(let d): data = d
                @unknown default: continue
                }
                let j = JSON(data: data)
                if j["type"].string == "event", j["data"]["action"].string == "propertyValueChanged",
                   let p = j["data"]["property"].string {
                    queue(p, j["data"]["value"])
                } else if j["id"].int == 1 {
                    let props = j["data"]["properties"].array.compactMap(\.string).filter { !Self.skipSubscriptions.contains($0) }
                    try await send(ws, ["type": "request", "id": 2,
                                        "data": ["action": "subscribe", "properties": .array(props.map { .string($0) })]])
                } else if j["id"].int == 2 {
                    for (k, v) in j["data"]["values"].object { values[k] = v }
                    Task { await self.syncTimecode(probe: true) }  // now the frame rate is known
                }
            }
        } catch {
            if !Task.isCancelled { link = .failed("Lost the camera connection") }
        }
        timecodeSync?.cancel()
        timecodeSync = nil
        unpublishedPoll?.cancel()
        unpublishedPoll = nil
        ws.cancel(with: .goingAway, reason: nil)
    }

    private func send(_ ws: URLSessionWebSocketTask, _ j: JSON) async throws {
        try await ws.send(.string(String(decoding: j.data, as: UTF8.self)))
    }

    /// Batches WebSocket events into ~10 UI updates a second (the timecode alone changes
    /// every frame).
    private func queue(_ path: String, _ value: JSON) {
        pending[path] = value
        // Record-run timecode starts and stops with recording; the frame rate sets its speed.
        if path == "/transports/0/record" || path == "/system/format" {
            Task { await self.syncTimecode(probe: true) }
        }
        guard !flushScheduled else { return }
        flushScheduled = true
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(100))
            for (k, v) in pending { values[k] = v }
            pending.removeAll()
            flushScheduled = false
        }
    }

    /// Reads the camera's timecode and restarts the local clock from it. Whether it's
    /// running comes from comparing with the previous reading; `probe` takes a second
    /// reading a moment later to find out straight away.
    func syncTimecode(probe: Bool) async {
        let (base, rate) = TimecodeClock.rates(v("/system/format")["frameRate"].string)
        func read() async -> (Int, String, Date)? {
            let sent = Date()
            guard let j = await get("/transports/0/timecode"), let d = j["display"].string,
                  let (f, sep) = TimecodeClock.parse(d, base: base) else { return nil }
            // the reading was taken somewhere in the round trip: assume its middle
            return (f, sep, sent.addingTimeInterval(Date().timeIntervalSince(sent) / 2))
        }
        guard var r = await read() else { return }
        var running = timecode?.running ?? true
        if probe {
            try? await Task.sleep(for: .milliseconds(250))
            if let r2 = await read() { running = r2.0 != r.0; r = r2 }
        } else if let last = lastTimecodeRead {
            running = r.0 != last
        }
        lastTimecodeRead = r.0
        timecode = TimecodeClock(frames: r.0, at: r.2, base: base, rate: rate, running: running, separator: r.1)
    }

    private func readExtras() async {
        for p in Self.extraReads { await refresh(p) }
        // Outputs the camera lists but doesn't publish over the WebSocket (the PYXIS's
        // "Stream" output): read their settings directly so the Monitor menu can show them.
        unpublishedDisplays = v("/monitoring/display")["displays"].array.compactMap(\.string)
            .filter { !has("/monitoring/\($0)/cleanFeed") }
        for d in unpublishedDisplays {
            for k in ["cleanFeed", "displayLUT", "displayLUTSlot", "zebra", "focusAssist", "frameGuide",
                      "frameGrids", "safeArea", "falseColor", "brightness"] {
                await refresh("/monitoring/\(d)/\(k)")
            }
        }
    }

    /// Re-reads the LUT settings of outputs the camera doesn't publish (cheap: two small GETs
    /// each). Returns whether every reading came back.
    @discardableResult
    func refreshUnpublished() async -> Bool {
        guard isConnected else { return false }
        var ok = true
        for d in unpublishedDisplays {
            if !(await refresh("/monitoring/\(d)/displayLUT")) { ok = false }
            if !(await refresh("/monitoring/\(d)/displayLUTSlot")) { ok = false }
        }
        return ok
    }

    // MARK: requests

    private var hasLogin: Bool { !username.isEmpty && !password.isEmpty }

    private func raw(_ method: String, _ path: String, body: JSON? = nil, contentType: String = "application/json") async throws -> (Int, Data) {
        guard let url = URL(string: "\(scheme)://\(host)/control/api/v1\(path)") else { throw URLError(.badURL) }
        var req = URLRequest(url: url, timeoutInterval: 6)
        req.httpMethod = method
        if let body {
            req.httpBody = body.data
            req.setValue(contentType, forHTTPHeaderField: "Content-Type")
        }
        let (data, resp) = try await session.data(for: req)
        return ((resp as? HTTPURLResponse)?.statusCode ?? 0, data)
    }

    /// Reads a path into `values` (or marks it unsupported). Returns whether the camera answered.
    @discardableResult
    func refresh(_ path: String) async -> Bool {
        guard let (code, data) = try? await raw("GET", path) else { return false }
        if code == 200 { values[path] = JSON(data: data); unsupported.remove(path); return true }
        if code == 404 || code == 501 { unsupported.insert(path); values[path] = nil; return true }
        return false
    }

    /// Sets a value: updates the screen at once, then tells the camera.
    func put(_ path: String, _ body: JSON) {
        values[path] = v(path).merged(with: body)
        Task { await self.write("PUT", path, body) }
    }

    /// For sliders: sends the latest value only, one request at a time per path.
    func putLive(_ path: String, _ body: JSON) {
        values[path] = v(path).merged(with: body)
        liveSends[path] = body
        guard !liveInFlight.contains(path) else { return }
        liveInFlight.insert(path)
        Task {
            while let next = liveSends.removeValue(forKey: path) {
                _ = await write("PUT", path, next, quiet: true)
            }
            liveInFlight.remove(path)
        }
    }

    @discardableResult
    func post(_ path: String, _ body: JSON? = nil) async -> Bool { await write("POST", path, body) }

    @discardableResult
    func action(_ method: String, _ path: String, _ body: JSON? = nil) async -> Bool { await write(method, path, body) }

    /// Starts or stops recording. Current firmware: POST /transports/0/record and
    /// PUT /transports/0/stop. Older firmware (and other cameras) only have
    /// PUT /transports/0/record {"recording": true/false}, so that's the fallback.
    @discardableResult
    func setRecording(_ on: Bool) async -> Bool {
        let current = on ? await write("POST", "/transports/0/record", [:], quiet: true)
                         : await write("PUT", "/transports/0/stop", nil, quiet: true)
        if current { return true }
        return await write("PUT", "/transports/0/record", ["recording": .bool(on)])
    }

    @discardableResult
    private func write(_ method: String, _ path: String, _ body: JSON?, quiet: Bool = false) async -> Bool {
        do {
            let (code, data) = try await raw(method, path, body: body)
            if (200...299).contains(code) { return true }
            let err = JSON(data: data)["error"].string ?? "HTTP \(code)"
            if !quiet { message = "Camera: \(err)" }
        } catch {
            if !quiet { message = "Camera didn't answer" }
        }
        if method == "PUT" { await refresh(path) }  // show the camera's real value again
        return false
    }

    /// GET returning the body (for one-off reads such as a format key).
    func get(_ path: String) async -> JSON? {
        guard let (code, data) = try? await raw("GET", path), code == 200 else { return nil }
        return JSON(data: data)
    }
}

/// Accepts the camera's self-signed certificate (only for the camera's own address) and
/// answers its Secure Login challenge (only over HTTPS, and once).
final class CameraAuth: NSObject, URLSessionTaskDelegate, URLSessionWebSocketDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private var user = ""
    private var password = ""
    private var _cameraHost = ""

    var cameraHost: String {
        get { lock.withLock { _cameraHost } }
        set { lock.withLock { _cameraHost = newValue } }
    }

    func set(user: String, password: String) {
        lock.withLock { self.user = user; self.password = password }
    }

    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        handle(challenge, completionHandler)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        handle(challenge, completionHandler)
    }

    private func handle(_ challenge: URLAuthenticationChallenge,
                        _ completion: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        let space = challenge.protectionSpace
        guard space.host.lowercased() == cameraHost else { return completion(.performDefaultHandling, nil) }
        switch space.authenticationMethod {
        case NSURLAuthenticationMethodServerTrust:
            if let trust = space.serverTrust { completion(.useCredential, URLCredential(trust: trust)) }
            else { completion(.performDefaultHandling, nil) }
        case NSURLAuthenticationMethodHTTPBasic, NSURLAuthenticationMethodHTTPDigest, NSURLAuthenticationMethodDefault:
            let (u, p) = lock.withLock { (user, password) }
            let secure = space.protocol == NSURLProtectionSpaceHTTPS || space.receivesCredentialSecurely
            if u.isEmpty || p.isEmpty || !secure || challenge.previousFailureCount > 0 {
                completion(.rejectProtectionSpace, nil)
            } else {
                completion(.useCredential, URLCredential(user: u, password: p, persistence: .forSession))
            }
        default:
            completion(.performDefaultHandling, nil)
        }
    }
}

/// The camera's Secure Login password, in the Keychain.
enum Keychain {
    private static let base: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "PYXIS Viewer camera login",
        kSecAttrAccount as String: "web-media-manager",
    ]

    static func read() -> String? {
        var q = base
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func save(_ value: String) {
        if value.isEmpty { SecItemDelete(base as CFDictionary); return }
        let data = Data(value.utf8)
        let status = SecItemUpdate(base as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var add = base
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            SecItemAdd(add as CFDictionary, nil)
        }
    }
}

import Foundation
import Darwin

enum VideoCodec { case h264, h265 }

struct StreamError: LocalizedError {
    let message: String
    /// The relay answered but has no stream at this path (camera not streaming).
    var offline = false
    var errorDescription: String? { message }
}

/// Minimal RTSP client for the relay: DESCRIBE, SETUP with RTP interleaved on the same TCP
/// connection, PLAY. Video only. Blocking sockets; run it on its own thread.
/// Same protocol handling as the R5C's HDMI player (nanopi-relay/hdmi/pyxis-hdmi.c).
final class RTSPConnection {
    private let url: String
    private let host: String
    private let port: String
    private var fd: Int32 = -1
    private var cseq = 0
    private var session = ""
    private var base = ""
    private var control = ""
    private var buf: [UInt8] = []
    private var pos = 0  // start of unread bytes in buf
    private var chunk = [UInt8](repeating: 0, count: 65536)
    private var lastKeepalive = Date()

    private(set) var codec: VideoCodec = .h264
    private(set) var payloadType = -1
    /// Parameter sets from the SDP (VPS/SPS/PPS), without start codes.
    private(set) var parameterSets: [Data] = []

    init(url: String) throws {
        guard url.hasPrefix("rtsp://") else { throw StreamError(message: "Not an rtsp:// address") }
        self.url = url
        let rest = url.dropFirst(7)
        let hostPort = rest.split(separator: "/", maxSplits: 1).first.map(String.init) ?? ""
        if let colon = hostPort.lastIndex(of: ":") {
            host = String(hostPort[..<colon])
            port = String(hostPort[hostPort.index(after: colon)...])
        } else {
            host = hostPort
            port = "554"
        }
    }

    deinit { close() }

    // MARK: socket

    private func connectSocket(timeout: TimeInterval) throws {
        var hints = addrinfo(ai_flags: 0, ai_family: AF_UNSPEC, ai_socktype: SOCK_STREAM, ai_protocol: 0,
                             ai_addrlen: 0, ai_canonname: nil, ai_addr: nil, ai_next: nil)
        var res: UnsafeMutablePointer<addrinfo>?
        guard getaddrinfo(host, port, &hints, &res) == 0, let first = res else {
            throw StreamError(message: "Can't find the relay at \(host)")
        }
        defer { freeaddrinfo(res) }
        var a: UnsafeMutablePointer<addrinfo>? = first
        while let ai = a {
            let s = socket(ai.pointee.ai_family, ai.pointee.ai_socktype, ai.pointee.ai_protocol)
            if s >= 0 {
                var one: Int32 = 1
                setsockopt(s, SOL_SOCKET, SO_NOSIGPIPE, &one, socklen_t(MemoryLayout<Int32>.size))
                setsockopt(s, IPPROTO_TCP, TCP_NODELAY, &one, socklen_t(MemoryLayout<Int32>.size))
                var rcv: Int32 = 4 << 20  // room for 4K keyframes
                setsockopt(s, SOL_SOCKET, SO_RCVBUF, &rcv, socklen_t(MemoryLayout<Int32>.size))
                // connect with a timeout: non-blocking connect, then poll
                let flags = fcntl(s, F_GETFL)
                _ = fcntl(s, F_SETFL, flags | O_NONBLOCK)
                var ok = Darwin.connect(s, ai.pointee.ai_addr, ai.pointee.ai_addrlen) == 0
                if !ok && errno == EINPROGRESS {
                    var p = pollfd(fd: s, events: Int16(POLLOUT), revents: 0)
                    if poll(&p, 1, Int32(timeout * 1000)) == 1 {
                        var err: Int32 = 0
                        var len = socklen_t(MemoryLayout<Int32>.size)
                        getsockopt(s, SOL_SOCKET, SO_ERROR, &err, &len)
                        ok = err == 0
                    }
                }
                _ = fcntl(s, F_SETFL, flags)
                if ok { fd = s; buf.removeAll(keepingCapacity: true); pos = 0; return }
                Darwin.close(s)
            }
            a = ai.pointee.ai_next
        }
        throw StreamError(message: "Can't reach the relay at \(host)")
    }

    /// Reads more bytes. Returns false on timeout; throws when the connection closed.
    private func fill(timeout: TimeInterval) throws -> Bool {
        var p = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
        let r = poll(&p, 1, Int32(timeout * 1000))
        if r == 0 { return false }
        if r < 0 { if errno == EINTR { return false }; throw StreamError(message: "Connection error") }
        if pos > 0 && pos == buf.count { buf.removeAll(keepingCapacity: true); pos = 0 }
        if pos > 1 << 20 { buf.removeFirst(pos); pos = 0 }
        let n = recv(fd, &chunk, chunk.count, 0)
        if n <= 0 { throw StreamError(message: "The relay closed the connection") }
        buf.append(contentsOf: chunk[0..<n])
        return true
    }

    private var available: Int { buf.count - pos }

    private func send(_ method: String, _ target: String, _ extra: String = "") throws {
        cseq += 1
        var req = "\(method) \(target) RTSP/1.0\r\nCSeq: \(cseq)\r\nUser-Agent: PYXIS Viewer iOS\r\n\(extra)"
        if !session.isEmpty { req += "Session: \(session)\r\n" }
        req += "\r\n"
        let bytes = Array(req.utf8)
        var off = 0
        while off < bytes.count {
            let w = bytes[off...].withUnsafeBufferPointer { Darwin.send(fd, $0.baseAddress, $0.count, 0) }
            if w <= 0 { if errno == EINTR { continue }; throw StreamError(message: "Connection error") }
            off += w
        }
    }

    /// One RTSP response, skipping interleaved RTP before it. Returns (status, headers, body).
    private func readResponse(timeout: TimeInterval) throws -> (Int, [String: String], String) {
        let deadline = Date().addingTimeInterval(timeout)
        while true {
            while available >= 4 && buf[pos] == 0x24 {  // '$' interleaved frame
                let len = Int(buf[pos + 2]) << 8 | Int(buf[pos + 3])
                if available < 4 + len { break }
                pos += 4 + len
            }
            if available >= 4 && buf[pos] != 0x24, let end = findHeaderEnd() {
                let head = String(decoding: buf[pos..<end], as: UTF8.self)
                var headers: [String: String] = [:]
                let lines = head.components(separatedBy: "\r\n")
                for line in lines.dropFirst() {
                    guard let c = line.firstIndex(of: ":") else { continue }
                    headers[line[..<c].lowercased()] = line[line.index(after: c)...].trimmingCharacters(in: .whitespaces)
                }
                let blen = Int(headers["content-length"] ?? "0") ?? 0
                if available >= end - pos + blen {
                    let body = String(decoding: buf[end..<end + blen], as: UTF8.self)
                    pos = end + blen
                    let status = lines.first.flatMap { l -> Int? in
                        let parts = l.split(separator: " ")
                        return parts.count > 1 ? Int(parts[1]) : nil
                    } ?? -1
                    return (status, headers, body)
                }
            }
            let left = deadline.timeIntervalSinceNow
            if left <= 0 { throw StreamError(message: "The relay didn't answer") }
            _ = try fill(timeout: left)
        }
    }

    private func findHeaderEnd() -> Int? {
        var i = pos
        while i + 3 < buf.count {
            if buf[i] == 13 && buf[i + 1] == 10 && buf[i + 2] == 13 && buf[i + 3] == 10 { return i + 4 }
            i += 1
        }
        return nil
    }

    // MARK: RTSP

    func open() throws {
        session = ""
        try connectSocket(timeout: 3)
        try send("DESCRIBE", url, "Accept: application/sdp\r\n")
        var (code, headers, body) = try readResponse(timeout: 3)
        if code == 404 { throw StreamError(message: "The camera isn't streaming", offline: true) }
        guard code == 200 else { throw StreamError(message: "The relay answered \(code)") }
        base = headers["content-base"] ?? url
        try parseSDP(body)

        try send("SETUP", control, "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n")
        (code, headers, _) = try readResponse(timeout: 3)
        guard code == 200 else { throw StreamError(message: "The relay refused the stream (\(code))") }
        if let s = headers["session"] { session = String(s.split(separator: ";").first ?? "") }

        try send("PLAY", base, "Range: npt=0.000-\r\n")
        (code, _, _) = try readResponse(timeout: 3)
        guard code == 200 else { throw StreamError(message: "The relay refused to play (\(code))") }
        lastKeepalive = Date()
    }

    private func parseSDP(_ sdp: String) throws {
        var inVideo = false, found = false
        var ctl = ""
        parameterSets = []
        payloadType = -1
        for raw in sdp.components(separatedBy: .newlines) {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("m=") {
                if found && inVideo { break }  // done with the first video section
                inVideo = line.hasPrefix("m=video")
                if inVideo {
                    let f = line.split(separator: " ")
                    payloadType = f.count > 3 ? Int(f[3]) ?? -1 : -1
                }
                continue
            }
            guard inVideo else { continue }
            if line.hasPrefix("a=rtpmap:") {
                let f = line.dropFirst(9).split(separator: " ")
                if f.count >= 2, Int(f[0]) == payloadType {
                    let name = f[1].split(separator: "/").first?.uppercased() ?? ""
                    if name == "H264" { codec = .h264; found = true }
                    if name == "H265" || name == "HEVC" { codec = .h265; found = true }
                }
            } else if line.hasPrefix("a=control:") {
                ctl = String(line.dropFirst(10))
            } else if line.hasPrefix("a=fmtp:") {
                for kv in line.split(separator: ";") {
                    let pair = kv.trimmingCharacters(in: .whitespaces)
                    for key in ["sprop-vps=", "sprop-sps=", "sprop-pps=", "sprop-parameter-sets="] {
                        guard let r = pair.range(of: key) else { continue }
                        for b64 in pair[r.upperBound...].split(separator: ",") {
                            if let d = Self.base64(String(b64)) { parameterSets.append(d) }
                        }
                    }
                }
            }
        }
        guard found else { throw StreamError(message: "The stream has no H.264 or H.265 video") }
        if ctl.hasPrefix("rtsp://") { control = ctl }
        else if !ctl.isEmpty && ctl != "*" { control = base + (base.hasSuffix("/") ? "" : "/") + ctl }
        else { control = base }
    }

    private static func base64(_ s: String) -> Data? {
        var t = s.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        t = t.trimmingCharacters(in: CharacterSet(charactersIn: "="))
        while t.count % 4 != 0 { t += "=" }
        return Data(base64Encoded: t)
    }

    /// Next RTP packet on the video channel, or nil after `timeout` without one.
    func readRTP(timeout: TimeInterval) throws -> ArraySlice<UInt8>? {
        if Date().timeIntervalSince(lastKeepalive) > 20 {  // the relay drops idle sessions
            try send("GET_PARAMETER", base)
            lastKeepalive = Date()
        }
        let deadline = Date().addingTimeInterval(timeout)
        while true {
            if available >= 4 {
                if buf[pos] == 0x24 {
                    let ch = buf[pos + 1]
                    let len = Int(buf[pos + 2]) << 8 | Int(buf[pos + 3])
                    if available >= 4 + len {
                        let pkt = buf[(pos + 4)..<(pos + 4 + len)]
                        pos += 4 + len
                        if ch == 0 { return pkt }
                        continue  // RTCP
                    }
                } else if buf[pos] == 0x52, let end = findHeaderEnd() {  // 'R': a reply (keepalive)
                    let head = String(decoding: buf[pos..<end], as: UTF8.self)
                    var blen = 0
                    for l in head.components(separatedBy: "\r\n") where l.lowercased().hasPrefix("content-length:") {
                        blen = Int(l.dropFirst(15).trimmingCharacters(in: .whitespaces)) ?? 0
                    }
                    if available >= end - pos + blen { pos = end + blen; continue }
                } else if buf[pos] != 0x52 {
                    pos += 1  // resync
                    continue
                }
            }
            let left = deadline.timeIntervalSinceNow
            if left <= 0 { return nil }
            _ = try fill(timeout: left)
        }
    }

    func close() {
        if fd >= 0 {
            if !session.isEmpty { try? send("TEARDOWN", base) }
            Darwin.close(fd)
            fd = -1
        }
    }
}

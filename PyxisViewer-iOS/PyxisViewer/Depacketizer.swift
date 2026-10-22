import Foundation

/// One picture: its NAL units (no start codes), whether it's a keyframe, its RTP time.
struct AccessUnit {
    var nals: [Data]
    var isKey: Bool
    var rtpTimestamp: UInt32
}

/// RTP (RFC 6184 H.264 / RFC 7798 H.265) -> whole access units.
/// After a lost packet it drops pictures until the next keyframe, so a damaged picture is
/// never shown. Port of the depacketizer in nanopi-relay/hdmi/pyxis-hdmi.c.
struct Depacketizer {
    let codec: VideoCodec
    private var nals: [Data] = []
    private var ts: UInt32 = 0
    private var haveTS = false
    private var corrupt = false
    private var key = false
    private var fuOpen = false
    private var lastSeq: UInt16 = 0
    private var haveSeq = false
    private var waitingForKey = true

    init(codec: VideoCodec) { self.codec = codec }

    private func isKey(_ h: UInt8) -> Bool {
        if codec == .h264 { return h & 0x1f == 5 }
        let t = (h >> 1) & 0x3f
        return t >= 16 && t <= 21
    }

    private mutating func note(_ h: UInt8) { if isKey(h) { key = true } }

    private mutating func reset() {
        nals.removeAll(keepingCapacity: true)
        corrupt = false; key = false; fuOpen = false; haveTS = false
    }

    private mutating func emit() -> AccessUnit? {
        defer { reset() }
        guard !nals.isEmpty else { return nil }
        if corrupt { waitingForKey = true; return nil }
        if waitingForKey && !key { return nil }
        if key { waitingForKey = false }
        return AccessUnit(nals: nals, isKey: key, rtpTimestamp: ts)
    }

    /// Feeds one RTP packet; returns any access units it completes (at most two).
    mutating func push(_ p: ArraySlice<UInt8>) -> [AccessUnit] {
        var out: [AccessUnit] = []
        let b = p.startIndex
        guard p.count >= 12, p[b] >> 6 == 2 else { return out }
        let marker = p[b + 1] & 0x80 != 0
        let seq = UInt16(p[b + 2]) << 8 | UInt16(p[b + 3])
        let t = UInt32(p[b + 4]) << 24 | UInt32(p[b + 5]) << 16 | UInt32(p[b + 6]) << 8 | UInt32(p[b + 7])
        var off = 12 + 4 * Int(p[b] & 0x0f)
        if p[b] & 0x10 != 0 {  // header extension
            guard p.count >= off + 4 else { return out }
            off += 4 + 4 * (Int(p[b + off + 2]) << 8 | Int(p[b + off + 3]))
        }
        var end = p.count
        if p[b] & 0x20 != 0 { end -= Int(p[b + p.count - 1]) }  // padding
        guard off < end else { return out }
        let pl = p[(b + off)..<(b + end)]
        let s = pl.startIndex

        if haveSeq && lastSeq &+ 1 != seq { corrupt = true }  // lost packet(s)
        lastSeq = seq; haveSeq = true

        if haveTS && t != ts, let au = emit() { out.append(au) }  // missed marker: new picture
        if !haveTS { ts = t; haveTS = true }

        if codec == .h264 {
            let type = pl[s] & 0x1f
            if type >= 1 && type <= 23 {
                nals.append(Data(pl)); note(pl[s])
            } else if type == 24 {  // STAP-A
                var i = s + 1
                while i + 2 <= pl.endIndex {
                    let sz = Int(pl[i]) << 8 | Int(pl[i + 1]); i += 2
                    if sz == 0 || i + sz > pl.endIndex { corrupt = true; break }
                    nals.append(Data(pl[i..<(i + sz)])); note(pl[i]); i += sz
                }
            } else if type == 28 {  // FU-A
                guard pl.count >= 2 else { return out }
                let fu = pl[s + 1]
                if fu & 0x80 != 0 {
                    let h = (pl[s] & 0xe0) | (fu & 0x1f)
                    var d = Data([h]); d.append(contentsOf: pl[(s + 2)...])
                    nals.append(d); note(h); fuOpen = true
                } else if fuOpen, !nals.isEmpty {
                    nals[nals.count - 1].append(contentsOf: pl[(s + 2)...])
                } else { corrupt = true }
                if fu & 0x40 != 0 { fuOpen = false }
            }
        } else {
            guard pl.count >= 2 else { return out }
            let type = (pl[s] >> 1) & 0x3f
            if type < 48 {
                nals.append(Data(pl)); note(pl[s])
            } else if type == 48 {  // aggregation packet
                var i = s + 2
                while i + 2 <= pl.endIndex {
                    let sz = Int(pl[i]) << 8 | Int(pl[i + 1]); i += 2
                    if sz < 2 || i + sz > pl.endIndex { corrupt = true; break }
                    nals.append(Data(pl[i..<(i + sz)])); note(pl[i]); i += sz
                }
            } else if type == 49 {  // fragmentation unit
                guard pl.count >= 3 else { return out }
                let fu = pl[s + 2]
                if fu & 0x80 != 0 {
                    let h0 = (pl[s] & 0x81) | ((fu & 0x3f) << 1)
                    var d = Data([h0, pl[s + 1]]); d.append(contentsOf: pl[(s + 3)...])
                    nals.append(d); note(h0); fuOpen = true
                } else if fuOpen, !nals.isEmpty {
                    nals[nals.count - 1].append(contentsOf: pl[(s + 3)...])
                } else { corrupt = true }
                if fu & 0x40 != 0 { fuOpen = false }
            }
        }
        if marker, let au = emit() { out.append(au) }
        return out
    }
}

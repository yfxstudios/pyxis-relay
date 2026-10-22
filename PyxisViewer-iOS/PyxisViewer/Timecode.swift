import Foundation

/// The camera's timecode, run locally: one reading from the camera plus the time it was
/// taken, advanced at the project frame rate. The camera is asked again every few seconds
/// (and whenever recording starts or stops), so drift never builds up.
struct TimecodeClock: Equatable {
    var frames: Int          // timecode at `at`, in frames since 00:00:00:00
    var at: Date
    var base: Int            // frames counted per timecode second (24 for 23.98)
    var rate: Double         // real frames per second (24000/1001 for 23.98)
    var running: Bool        // false when the timecode stands still (record run, not recording)
    var separator: String    // ":" or ";" (drop frame), as the camera writes it

    private var day: Int { base * 86400 }

    func frames(at t: Date) -> Int {
        guard running else { return frames }
        let f = frames + Int((t.timeIntervalSince(at) * rate).rounded(.down))
        return ((f % day) + day) % day
    }

    func string(at t: Date) -> String {
        let f = frames(at: t)
        let ff = f % base, s = f / base
        return String(format: "%02d:%02d:%02d%@%02d", s / 3600, (s / 60) % 60, s % 60, separator, ff)
    }

    /// "HH:MM:SS:FF" (or with ";" before the frames) -> frames, separator.
    static func parse(_ s: String, base: Int) -> (Int, String)? {
        let parts = s.split(whereSeparator: { $0 == ":" || $0 == ";" }).compactMap { Int($0) }
        guard parts.count == 4 else { return nil }
        let sep = s.contains(";") ? ";" : ":"
        return ((((parts[0] * 60) + parts[1]) * 60 + parts[2]) * base + parts[3], sep)
    }

    /// Timecode base and real rate for a project frame rate as the camera names it.
    static func rates(_ projectRate: String?) -> (Int, Double) {
        switch projectRate {
        case "23.98": return (24, 24000.0 / 1001)
        case "29.97": return (30, 30000.0 / 1001)
        case "47.95": return (48, 48000.0 / 1001)
        case "59.94": return (60, 60000.0 / 1001)
        case "119.88": return (120, 120000.0 / 1001)
        default:
            let r = Double(projectRate ?? "") ?? 24
            return (max(1, Int(r.rounded())), r)
        }
    }
}

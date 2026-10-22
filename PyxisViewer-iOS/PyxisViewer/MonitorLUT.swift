import Foundation
import CoreImage
import CoreVideo

// Monitor LUTs: applied by the app to the picture it shows, like LUTs on a field monitor.
// Nothing is sent to the camera; recordings and the camera's outputs are unaffected.

/// A 3D LUT (RGBA floats, red changing fastest, as Core Image's colour cube wants).
struct CubeLUT {
    let title: String
    let size: Int
    let rgba: [Float]

    struct ParseError: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    /// Reads a .cube file (Adobe/Resolve format, 3D LUTs).
    static func parse(_ data: Data, fallbackTitle: String) throws -> CubeLUT {
        guard let text = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) else {
            throw ParseError(message: "That file isn't text.")
        }
        var title = fallbackTitle, size = 0
        var rgba: [Float] = []
        for raw in text.split(whereSeparator: \.isNewline) {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.isEmpty || line.hasPrefix("#") { continue }
            if line.hasPrefix("TITLE") {
                let t = line.dropFirst(5).trimmingCharacters(in: CharacterSet(charactersIn: " \t\""))
                if !t.isEmpty { title = t }
            } else if line.hasPrefix("LUT_3D_SIZE") {
                size = Int(line.split(separator: " ").last ?? "") ?? 0
                guard (2...129).contains(size) else { throw ParseError(message: "LUT size \(size) isn't supported.") }
                rgba.reserveCapacity(size * size * size * 4)
            } else if line.hasPrefix("LUT_1D_SIZE") {
                throw ParseError(message: "1D LUTs aren't supported; use a 3D .cube LUT.")
            } else if line.hasPrefix("DOMAIN_MIN") || line.hasPrefix("DOMAIN_MAX") {
                let v = line.split(separator: " ").dropFirst().compactMap { Float($0) }
                let want: Float = line.hasPrefix("DOMAIN_MIN") ? 0 : 1
                guard v.allSatisfy({ abs($0 - want) < 1e-4 }) else {
                    throw ParseError(message: "LUTs with an input range other than 0–1 aren't supported.")
                }
            } else if let f = line.first, f.isNumber || f == "-" || f == "." {
                let v = line.split(whereSeparator: { $0 == " " || $0 == "\t" }).compactMap { Float($0) }
                guard v.count == 3 else { throw ParseError(message: "A line in the LUT isn't three numbers.") }
                rgba += [v[0], v[1], v[2], 1]
            }
        }
        guard size > 0 else { throw ParseError(message: "Not a 3D LUT (no LUT_3D_SIZE).") }
        guard rgba.count == size * size * size * 4 else {
            throw ParseError(message: "The LUT has \(rgba.count / 4) entries; a \(size)-point LUT needs \(size * size * size).")
        }
        return CubeLUT(title: title, size: size, rgba: rgba)
    }
}

/// The LUT the video thread should apply (or nil), handed over safely between threads.
final class LUTBox: @unchecked Sendable {
    private let lock = NSLock()
    private var lut: CubeLUT?
    private var version = 0

    func set(_ l: CubeLUT?) { lock.withLock { lut = l; version += 1 } }
    var current: (CubeLUT?, Int) { lock.withLock { (lut, version) } }
}

/// The app's monitor LUT: which one is chosen, whether it's on, and the imported ones.
@MainActor
final class MonitorLUTs: ObservableObject {
    enum Choice: Hashable {
        case look(FilmLook)
        case file(String)   // file name in the app's LUT folder
    }

    @Published private(set) var choice: Choice
    @Published private(set) var enabled: Bool
    @Published private(set) var imported: [String] = []
    @Published var message: String?

    let box = LUTBox()
    private var cache: [Choice: CubeLUT] = [:]

    nonisolated static let folder: URL = {
        let u = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("LUTs")
        try? FileManager.default.createDirectory(at: u, withIntermediateDirectories: true)
        return u
    }()

    init() {
        let d = UserDefaults.standard
        enabled = d.bool(forKey: "monitorLUTOn")
        let saved = d.string(forKey: "monitorLUT") ?? ""
        if saved.hasPrefix("file:") { choice = .file(String(saved.dropFirst(5))) }
        else { choice = .look(FilmLook(rawValue: saved) ?? .print) }
        reloadImported()
        if case .file(let f) = choice, !imported.contains(f) { choice = .look(.print) }
        update()
    }

    func name(_ c: Choice) -> String {
        switch c {
        case .look(let l): return l.rawValue
        case .file(let f): return (f as NSString).deletingPathExtension
        }
    }

    var currentName: String { name(choice) }

    func select(_ c: Choice) {
        choice = c
        enabled = true
        save()
        update()
    }

    func setEnabled(_ on: Bool) {
        enabled = on
        save()
        update()
    }

    private func save() {
        let d = UserDefaults.standard
        d.set(enabled, forKey: "monitorLUTOn")
        switch choice {
        case .look(let l): d.set(l.rawValue, forKey: "monitorLUT")
        case .file(let f): d.set("file:" + f, forKey: "monitorLUT")
        }
    }

    /// Hands the chosen LUT (built or read off the main thread) to the video thread.
    private func update() {
        guard enabled else { box.set(nil); return }
        let c = choice
        if let hit = cache[c] { box.set(hit); return }
        Task.detached(priority: .userInitiated) {
            let result: Result<CubeLUT, Error>
            switch c {
            case .look(let l): result = .success(l.lut())
            case .file(let f):
                result = Result {
                    try CubeLUT.parse(Data(contentsOf: Self.folder.appendingPathComponent(f)),
                                      fallbackTitle: (f as NSString).deletingPathExtension)
                }
            }
            await MainActor.run {
                switch result {
                case .success(let lut):
                    self.cache[c] = lut
                    if self.choice == c && self.enabled { self.box.set(lut) }
                case .failure(let e):
                    self.message = "LUT: \(e.localizedDescription)"
                    if self.choice == c { self.setEnabled(false) }
                }
            }
        }
    }

    // MARK: imported LUTs

    private func reloadImported() {
        imported = ((try? FileManager.default.contentsOfDirectory(atPath: Self.folder.path)) ?? [])
            .filter { $0.lowercased().hasSuffix(".cube") }
            .sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    }

    /// Copies a .cube file into the app (after checking it parses) and selects it.
    func importLUT(from url: URL) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            let data = try Data(contentsOf: url)
            let base = url.deletingPathExtension().lastPathComponent
            let lut = try CubeLUT.parse(data, fallbackTitle: base)
            var name = base + ".cube", n = 2
            while FileManager.default.fileExists(atPath: Self.folder.appendingPathComponent(name).path) {
                name = "\(base) \(n).cube"; n += 1
            }
            try data.write(to: Self.folder.appendingPathComponent(name))
            reloadImported()
            cache[.file(name)] = lut
            select(.file(name))
        } catch {
            message = "Couldn't import that LUT: \(error.localizedDescription)"
        }
    }

    func delete(_ file: String) {
        try? FileManager.default.removeItem(at: Self.folder.appendingPathComponent(file))
        cache[.file(file)] = nil
        reloadImported()
        if choice == .file(file) { choice = .look(.print); setEnabled(false) }
    }
}

/// Applies a LUT to decoded frames on the GPU (Core Image colour cube). Used by the video
/// thread only.
final class LUTProcessor {
    private let context = CIContext(options: [.cacheIntermediates: false, .name: "monitor-lut"])
    private let space = CGColorSpace(name: CGColorSpace.itur_709)!
    private var filter: CIFilter?
    private var version = -1
    private var pool: CVPixelBufferPool?
    private var poolSize = (0, 0)

    /// The frame with the LUT applied, as a new BGRA buffer, or nil to show the frame as is.
    func process(_ frame: CVPixelBuffer, box: LUTBox) -> CVPixelBuffer? {
        let (lut, v) = box.current
        guard let lut else { return nil }
        if v != version || filter == nil {
            version = v
            let f = CIFilter(name: "CIColorCubeWithColorSpace")
            f?.setValue(lut.size, forKey: "inputCubeDimension")
            f?.setValue(lut.rgba.withUnsafeBufferPointer { Data(buffer: $0) }, forKey: "inputCubeData")
            // The LUT works on Rec.709-encoded values, like a LUT on a monitor's video input.
            f?.setValue(space, forKey: "inputColorSpace")
            filter = f
        }
        guard let filter else { return nil }
        tag709(frame)
        filter.setValue(CIImage(cvPixelBuffer: frame), forKey: kCIInputImageKey)
        guard let out = filter.outputImage else { return nil }

        let w = CVPixelBufferGetWidth(frame), h = CVPixelBufferGetHeight(frame)
        if pool == nil || poolSize != (w, h) {
            let attrs: [String: Any] = [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
                kCVPixelBufferWidthKey as String: w, kCVPixelBufferHeightKey as String: h,
                kCVPixelBufferIOSurfacePropertiesKey as String: [String: Any](),
            ]
            pool = nil
            CVPixelBufferPoolCreate(kCFAllocatorDefault, nil, attrs as CFDictionary, &pool)
            poolSize = (w, h)
        }
        var dst: CVPixelBuffer?
        guard let pool, CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, pool, &dst) == kCVReturnSuccess,
              let dst else { return nil }
        context.render(out, to: dst, bounds: CGRect(x: 0, y: 0, width: w, height: h), colorSpace: space)
        tag709(dst)
        return dst
    }

    /// The stream is untagged HD video: say it's Rec.709, so colours convert both ways exactly.
    func tag709(_ b: CVPixelBuffer) {
        if CVBufferCopyAttachment(b, kCVImageBufferColorPrimariesKey, nil) == nil {
            CVBufferSetAttachment(b, kCVImageBufferColorPrimariesKey, kCVImageBufferColorPrimaries_ITU_R_709_2, .shouldPropagate)
        }
        if CVBufferCopyAttachment(b, kCVImageBufferTransferFunctionKey, nil) == nil {
            CVBufferSetAttachment(b, kCVImageBufferTransferFunctionKey, kCVImageBufferTransferFunction_ITU_R_709_2, .shouldPropagate)
        }
        if CVBufferCopyAttachment(b, kCVImageBufferYCbCrMatrixKey, nil) == nil {
            CVBufferSetAttachment(b, kCVImageBufferYCbCrMatrixKey, kCVImageBufferYCbCrMatrix_ITU_R_709_2, .shouldPropagate)
        }
    }
}

import Foundation
import AVFoundation
import CoreImage
import VideoToolbox
#if os(iOS)
import Photos
#endif

// Local recordings and frame grabs: the picture as it's shown in the app (with the monitor LUT
// when it's on), at the stream's full resolution. Video only (the app doesn't play the sound).
//
// Saved to Photos on iPhone/iPad, and to Movies/PYXIS Viewer and Pictures/PYXIS Viewer on the Mac.
// Recording here doesn't record on the camera, and the camera's record button doesn't record here.

/// The app side: start/stop a recording, grab a frame, report what happened.
@MainActor
final class Capture: ObservableObject {
    @Published private(set) var recordingSince: Date?
    @Published var message: String?
    /// Handed to the player; the decoding thread feeds it every frame it shows.
    let tap = FrameTap()
    /// The connected camera's model, for file names ("PYXIS 12K 2026-…"); set by the app.
    var cameraName: @MainActor () -> String? = { nil }

    private var prefix: String { cameraName().map { $0.replacingOccurrences(of: "/", with: "-") } ?? "Camera" }

    var isRecording: Bool { recordingSince != nil }

    func toggleRecording() { isRecording ? stopRecording() : startRecording() }

    func startRecording() {
        guard !isRecording else { return }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(Self.name(prefix) + ".mov")
        tap.startRecording(to: url)
        recordingSince = Date()
    }

    func stopRecording() {
        guard isRecording else { return }
        recordingSince = nil
        tap.stopRecording { [weak self] result in
            Task { @MainActor in
                guard let self else { return }
                switch result {
                case .success(let url): await self.keepVideo(url)
                case .failure(let e): self.message = e.localizedDescription
                }
            }
        }
    }

    func grabFrame() {
        tap.grabNextFrame { [weak self] png in
            Task { @MainActor in
                guard let self else { return }
                guard let png else { self.message = "No picture to capture yet."; return }
                await self.keepPhoto(png)
            }
        }
    }

    /// "PYXIS 12K 2026-10-21 at 21.30.15"
    static func name(_ prefix: String) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd 'at' HH.mm.ss"
        return "\(prefix) \(f.string(from: Date()))"
    }

    // MARK: saving

    #if os(iOS)
    private func photosAllowed() async -> Bool {
        let s = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        if s == .authorized || s == .limited { return true }
        message = "Allow PYXIS Viewer to add to Photos (Settings → PYXIS Viewer → Photos)."
        return false
    }

    private func keepVideo(_ url: URL) async {
        defer { try? FileManager.default.removeItem(at: url) }
        guard await photosAllowed() else { return }
        do {
            try await PHPhotoLibrary.shared().performChanges {
                PHAssetCreationRequest.forAsset().addResource(with: .video, fileURL: url, options: nil)
            }
            message = "Recording saved to Photos"
        } catch { message = "Couldn't save the recording: \(error.localizedDescription)" }
    }

    private func keepPhoto(_ png: Data) async {
        guard await photosAllowed() else { return }
        do {
            try await PHPhotoLibrary.shared().performChanges {
                let o = PHAssetResourceCreationOptions()
                o.uniformTypeIdentifier = "public.png"
                PHAssetCreationRequest.forAsset().addResource(with: .photo, data: png, options: o)
            }
            message = "Frame saved to Photos"
        } catch { message = "Couldn't save the frame: \(error.localizedDescription)" }
    }
    #else
    private func folder(_ base: FileManager.SearchPathDirectory) throws -> URL {
        let dir = try FileManager.default.url(for: base, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("PYXIS Viewer", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func keepVideo(_ url: URL) async {
        do {
            let dest = try folder(.moviesDirectory).appendingPathComponent(url.lastPathComponent)
            try FileManager.default.moveItem(at: url, to: dest)
            message = "Recording saved to Movies › PYXIS Viewer"
        } catch { message = "Couldn't save the recording: \(error.localizedDescription)" }
    }

    private func keepPhoto(_ png: Data) async {
        do {
            let dest = try folder(.picturesDirectory).appendingPathComponent(Self.name(prefix) + ".png")
            try png.write(to: dest)
            message = "Frame saved to Pictures › PYXIS Viewer"
        } catch { message = "Couldn't save the frame: \(error.localizedDescription)" }
    }
    #endif
}

/// The decoding thread's side. Thread-safe: `take` is called from the worker thread, the rest
/// from the app.
final class FrameTap: @unchecked Sendable {
    private let lock = NSLock()
    private var frameWanted: ((Data?) -> Void)?
    private var writer: ClipWriter?
    private static let ci = CIContext(options: [.cacheIntermediates: false])

    func startRecording(to url: URL) { lock.withLock { if writer == nil { writer = ClipWriter(url: url) } } }

    func stopRecording(_ done: @escaping @Sendable (Result<URL, Error>) -> Void) {
        let w = lock.withLock { () -> ClipWriter? in let w = writer; writer = nil; return w }
        guard let w else { return }
        w.finish(done)
    }

    /// The next frame shown, as a lossless PNG (nil if none comes within 2 s). The stream is
    /// already compressed once; a JPEG would compress it again.
    func grabNextFrame(_ done: @escaping @Sendable (Data?) -> Void) {
        lock.withLock { frameWanted = done }
        DispatchQueue.global().asyncAfter(deadline: .now() + 2) { [weak self] in
            guard let self else { return }
            let pending = self.lock.withLock { () -> ((Data?) -> Void)? in let f = self.frameWanted; self.frameWanted = nil; return f }
            pending?(nil)
        }
    }

    /// Every picture shown (worker thread).
    func take(_ image: CVPixelBuffer, pts: CMTime) {
        let (still, w) = lock.withLock { () -> (((Data?) -> Void)?, ClipWriter?) in
            let f = frameWanted; frameWanted = nil; return (f, writer)
        }
        w?.append(image, pts: pts)
        if let still {
            // encode off the decoding thread; the pixel buffer is retained by the closure
            let buffer = UncheckedSendable(image)
            DispatchQueue.global(qos: .userInitiated).async {
                let ci = CIImage(cvPixelBuffer: buffer.value)
                let png = Self.ci.pngRepresentation(of: ci, format: .RGBA8, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!)
                still(png)
            }
        }
    }
}

/// Writes shown pictures to a QuickTime movie, H.264 at a high bitrate, tagged Rec.709.
/// Keeps time continuous across reconnects (the stream's clock restarts when it does).
final class ClipWriter: @unchecked Sendable {
    private let url: URL
    private let queue = DispatchQueue(label: "clip-writer")
    private var writer: AVAssetWriter?
    private var input: AVAssetWriterInput?
    private var adaptor: AVAssetWriterInputPixelBufferAdaptor?
    private var failed: Error?
    private var lastSource: CMTime?
    private var lastOut = CMTime.zero
    private var offset = CMTime.zero

    init(url: URL) { self.url = url }

    func append(_ image: CVPixelBuffer, pts: CMTime) {
        let buffer = UncheckedSendable(image)
        queue.async { [self] in
            guard failed == nil else { return }
            if writer == nil { start(width: CVPixelBufferGetWidth(buffer.value), height: CVPixelBufferGetHeight(buffer.value)) }
            guard let writer, let input, let adaptor, writer.status == .writing else { return }
            // continuous time: a jump back, or forward by more than 2 s, is a reconnect
            let step = CMTime(value: 1, timescale: 30)
            if let last = lastSource, pts <= last || (pts - last).seconds > 2 {
                offset = lastOut + step - pts
            } else if lastSource == nil {
                offset = .zero - pts
            }
            let out = pts + offset
            guard lastSource == nil || out > lastOut else { return }
            if lastSource == nil { writer.startSession(atSourceTime: out) }
            lastSource = pts
            guard input.isReadyForMoreMediaData else { return }  // encoder busy: drop this one
            if adaptor.append(buffer.value, withPresentationTime: out) { lastOut = out }
        }
    }

    private func start(width: Int, height: Int) {
        do {
            try? FileManager.default.removeItem(at: url)
            let w = try AVAssetWriter(outputURL: url, fileType: .mov)
            let settings: [String: Any] = [
                AVVideoCodecKey: AVVideoCodecType.h264,
                AVVideoWidthKey: width, AVVideoHeightKey: height,
                AVVideoCompressionPropertiesKey: [
                    AVVideoAverageBitRateKey: width * height * 10,  // ~20 Mb/s at 1080p
                    AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
                    AVVideoExpectedSourceFrameRateKey: 30,
                ],
                AVVideoColorPropertiesKey: [
                    AVVideoColorPrimariesKey: AVVideoColorPrimaries_ITU_R_709_2,
                    AVVideoTransferFunctionKey: AVVideoTransferFunction_ITU_R_709_2,
                    AVVideoYCbCrMatrixKey: AVVideoYCbCrMatrix_ITU_R_709_2,
                ],
            ]
            let i = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
            i.expectsMediaDataInRealTime = true
            let a = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: i, sourcePixelBufferAttributes: nil)
            guard w.canAdd(i) else { throw StreamError(message: "Can't record this picture size") }
            w.add(i)
            guard w.startWriting() else { throw w.error ?? StreamError(message: "Can't start recording") }
            writer = w; input = i; adaptor = a
        } catch { failed = error }
    }

    func finish(_ done: @escaping @Sendable (Result<URL, Error>) -> Void) {
        queue.async { [self] in
            if let failed { done(.failure(failed)); return }
            guard let writer, let input, lastSource != nil else {
                done(.failure(StreamError(message: "Nothing was recorded (no picture).")))
                return
            }
            input.markAsFinished()
            let url = self.url
            let w = UncheckedSendable(writer)
            writer.finishWriting {
                if w.value.status == .completed { done(.success(url)) }
                else { done(.failure(w.value.error ?? StreamError(message: "The recording couldn't be finished."))) }
            }
        }
    }
}

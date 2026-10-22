import Foundation
import AVFoundation
import CoreMedia
import VideoToolbox

/// Plays the relay's stream with the lowest delay the phone allows:
///   RTSP over TCP from the relay (no player buffer)
///   -> RTP depacketizer -> compressed frames
///   -> VideoToolbox hardware decoder
///   -> AVSampleBufferDisplayLayer, each picture marked "display immediately".
/// Reconnects by itself when the stream stops, the Wi-Fi drops or the relay restarts.
@MainActor
final class StreamPlayer: ObservableObject {
    enum State: Equatable {
        case idle, connecting, playing, offline, failed(String)
    }

    @Published private(set) var state: State = .idle
    @Published private(set) var resolution = ""
    @Published private(set) var fps: Double = 0
    /// Size of the decoded picture (for mapping taps to the camera's frame).
    @Published private(set) var videoSize: CGSize = .zero

    let layer = AVSampleBufferDisplayLayer()
    /// The monitor LUT to apply (set by the app before playing).
    var lutBox: LUTBox?
    /// Local recording and frame grabs (set by the app before playing).
    var frameTap: FrameTap?
    private var worker: Thread?
    private var stopFlag: StopFlag?

    init() {
        layer.videoGravity = .resizeAspect
        layer.backgroundColor = CGColor(gray: 0, alpha: 1)
    }

    func play(relayHost: String) {
        stop()
        let host = relayHost.trimmingCharacters(in: .whitespaces)
        guard !host.isEmpty else { return }
        let url = "rtsp://\(host):8554/live/pyxis"
        let flag = StopFlag()
        stopFlag = flag
        state = .connecting
        // The renderer accepts frames from any thread; only this worker enqueues.
        let renderer = UncheckedSendable(layer.sampleBufferRenderer)
        let box = lutBox, tap = frameTap
        let t = Thread { [weak self] in
            Self.run(url: url, renderer: renderer.value, lut: box, tap: tap, stop: flag) { update in
                Task { @MainActor in
                    guard let self, self.stopFlag === flag else { return }
                    update(self)
                }
            }
        }
        t.name = "rtsp"
        t.qualityOfService = .userInteractive
        worker = t
        t.start()
    }

    func stop() {
        stopFlag?.stopped = true
        stopFlag = nil
        worker = nil
        layer.sampleBufferRenderer.flush(removingDisplayedImage: false, completionHandler: nil)
        state = .idle
        fps = 0
    }

    // MARK: worker thread

    final class StopFlag: @unchecked Sendable {
        private let lock = NSLock()
        private var value = false
        var stopped: Bool {
            get { lock.withLock { value } }
            set { lock.withLock { value = newValue } }
        }
    }

    private nonisolated static func run(url: String, renderer: AVSampleBufferVideoRenderer, lut: LUTBox?, tap: FrameTap?, stop: StopFlag,
                                        post: @escaping (@escaping @MainActor (StreamPlayer) -> Void) -> Void) {
        while !stop.stopped {
            post { if $0.state != .offline { $0.state = .connecting } }
            do {
                let rtsp = try RTSPConnection(url: url)
                defer { rtsp.close() }
                try rtsp.open()
                var depay = Depacketizer(codec: rtsp.codec)
                let sink = FrameSink(codec: rtsp.codec, renderer: renderer, lut: lut, tap: tap)
                defer { sink.close() }
                sink.setParameterSets(rtsp.parameterSets)
                var started = false
                var shown = 0  // frames in the current 1 s window
                var windowStart = Date()
                var lastFrame = Date()
                while !stop.stopped {
                    guard let pkt = try rtsp.readRTP(timeout: 0.5) else {
                        if Date().timeIntervalSince(lastFrame) > 5 {
                            throw StreamError(message: "The camera stopped sending", offline: true)
                        }
                        continue
                    }
                    for au in depay.push(pkt) where !stop.stopped && sink.show(au) {
                        lastFrame = Date()
                        shown += 1
                        if !started {
                            started = true
                            windowStart = Date()
                            shown = 0
                            let res = sink.resolution, size = sink.dimensions
                            post { $0.state = .playing; $0.resolution = res; $0.videoSize = size }
                        }
                        let dt = Date().timeIntervalSince(windowStart)
                        if dt >= 1 {
                            let rate = Double(shown) / dt, res = sink.resolution, size = sink.dimensions
                            post { $0.fps = rate; $0.resolution = res; $0.videoSize = size }
                            shown = 0
                            windowStart = Date()
                        }
                    }
                }
            } catch let e as StreamError {
                post { $0.state = e.offline ? .offline : .failed(e.message); $0.fps = 0 }
            } catch {
                post { $0.state = .failed(error.localizedDescription); $0.fps = 0 }
            }
            // try again shortly (stream offline, Wi-Fi switching, relay restarting)
            for _ in 0..<10 where !stop.stopped { Thread.sleep(forTimeInterval: 0.1) }
        }
    }
}

struct UncheckedSendable<T>: @unchecked Sendable {
    let value: T
    init(_ value: T) { self.value = value }
}

/// Access units -> VideoToolbox -> decoded pictures on the display layer. Used by one
/// worker thread only.
final class FrameSink {
    let codec: VideoCodec
    private let renderer: AVSampleBufferVideoRenderer
    private var vps: Data?, sps: Data?, pps: Data?
    private var format: CMVideoFormatDescription?
    private var formatDirty = true
    private var decoder: VTDecompressionSession?
    private var imageFormat: CMVideoFormatDescription?
    private(set) var resolution = ""
    private(set) var dimensions = CGSize.zero

    private let lut: LUTBox?
    private let lutProcessor = LUTProcessor()
    private let tap: FrameTap?

    init(codec: VideoCodec, renderer: AVSampleBufferVideoRenderer, lut: LUTBox?, tap: FrameTap?) {
        self.codec = codec
        self.renderer = renderer
        self.lut = lut
        self.tap = tap
    }

    func close() {
        if let decoder { VTDecompressionSessionInvalidate(decoder) }
        decoder = nil
    }

    private func nalType(_ n: Data) -> Int {
        guard let h = n.first else { return -1 }
        return codec == .h264 ? Int(h & 0x1f) : Int((h >> 1) & 0x3f)
    }

    /// Takes parameter sets out of the picture; returns whether `n` was one.
    private func absorb(_ n: Data) -> Bool {
        switch (codec, nalType(n)) {
        case (.h264, 7), (.h265, 33): if sps != n { sps = n; formatDirty = true }; return true
        case (.h264, 8), (.h265, 34): if pps != n { pps = n; formatDirty = true }; return true
        case (.h265, 32): if vps != n { vps = n; formatDirty = true }; return true
        case (.h264, 9), (.h265, 35): return true  // access unit delimiter: not needed
        default: return false
        }
    }

    func setParameterSets(_ sets: [Data]) { for s in sets { _ = absorb(s) } }

    private func rebuildFormat() {
        formatDirty = false
        var sets: [Data] = []
        if codec == .h265 { guard let v = vps else { return }; sets.append(v) }
        guard let s = sps, let p = pps else { return }
        sets += [s, p]
        var desc: CMVideoFormatDescription?
        let status: OSStatus = withPointers(sets) { ptrs, sizes in
            codec == .h264
                ? CMVideoFormatDescriptionCreateFromH264ParameterSets(
                    allocator: kCFAllocatorDefault, parameterSetCount: sets.count, parameterSetPointers: ptrs,
                    parameterSetSizes: sizes, nalUnitHeaderLength: 4, formatDescriptionOut: &desc)
                : CMVideoFormatDescriptionCreateFromHEVCParameterSets(
                    allocator: kCFAllocatorDefault, parameterSetCount: sets.count, parameterSetPointers: ptrs,
                    parameterSetSizes: sizes, nalUnitHeaderLength: 4, extensions: nil, formatDescriptionOut: &desc)
        }
        guard status == noErr, let desc else { return }
        format = desc
        let dim = CMVideoFormatDescriptionGetDimensions(desc)
        resolution = "\(dim.width)×\(dim.height)"
        dimensions = CGSize(width: Int(dim.width), height: Int(dim.height))
        if let d = decoder, !VTDecompressionSessionCanAcceptFormatDescription(d, formatDescription: desc) {
            VTDecompressionSessionInvalidate(d)
            decoder = nil
        }
    }

    private func makeDecoder(_ format: CMVideoFormatDescription) -> VTDecompressionSession? {
        let attrs: [String: Any] = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange,
            kCVPixelBufferIOSurfacePropertiesKey as String: [String: Any](),
        ]
        var s: VTDecompressionSession?
        let spec: [String: Any] = [kVTVideoDecoderSpecification_EnableHardwareAcceleratedVideoDecoder as String: true]
        guard VTDecompressionSessionCreate(allocator: kCFAllocatorDefault, formatDescription: format,
                                           decoderSpecification: spec as CFDictionary,
                                           imageBufferAttributes: attrs as CFDictionary,
                                           outputCallback: nil, decompressionSessionOut: &s) == noErr else { return nil }
        if let s { VTSessionSetProperty(s, key: kVTDecompressionPropertyKey_RealTime, value: kCFBooleanTrue) }
        return s
    }

    /// Decodes and shows one picture. Returns false if it couldn't be shown.
    func show(_ au: AccessUnit) -> Bool {
        var payload = Data()
        for n in au.nals where !absorb(n) {
            var len = UInt32(n.count).bigEndian
            payload.append(Data(bytes: &len, count: 4))
            payload.append(n)
        }
        if formatDirty { rebuildFormat() }
        guard let format, !payload.isEmpty else { return false }
        if decoder == nil { decoder = makeDecoder(format) }
        guard let decoder, let sample = compressedSample(payload, format: format, au: au) else { return false }
        if renderer.status == .failed { renderer.flush() }  // e.g. after the app was in the background

        var shown = false
        let status = VTDecompressionSessionDecodeFrame(decoder, sampleBuffer: sample, flags: [], infoFlagsOut: nil) {
            [self] status, _, image, pts, _ in
            guard status == noErr, let image else { return }
            shown = display(image, pts: pts)
        }
        if status == kVTInvalidSessionErr { VTDecompressionSessionInvalidate(decoder); self.decoder = nil }
        return status == noErr && shown
    }

    private func compressedSample(_ payload: Data, format: CMVideoFormatDescription, au: AccessUnit) -> CMSampleBuffer? {
        var block: CMBlockBuffer?
        guard CMBlockBufferCreateWithMemoryBlock(
            allocator: kCFAllocatorDefault, memoryBlock: nil, blockLength: payload.count,
            blockAllocator: kCFAllocatorDefault, customBlockSource: nil, offsetToData: 0,
            dataLength: payload.count, flags: kCMBlockBufferAssureMemoryNowFlag, blockBufferOut: &block) == noErr,
              let block else { return nil }
        _ = payload.withUnsafeBytes { CMBlockBufferReplaceDataBytes(with: $0.baseAddress!, blockBuffer: block,
                                                                   offsetIntoDestination: 0, dataLength: payload.count) }
        var timing = CMSampleTimingInfo(duration: .invalid,
                                        presentationTimeStamp: CMTime(value: CMTimeValue(au.rtpTimestamp), timescale: 90000),
                                        decodeTimeStamp: .invalid)
        var size = payload.count
        var sample: CMSampleBuffer?
        guard CMSampleBufferCreateReady(allocator: kCFAllocatorDefault, dataBuffer: block, formatDescription: format,
                                        sampleCount: 1, sampleTimingEntryCount: 1, sampleTimingArray: &timing,
                                        sampleSizeEntryCount: 1, sampleSizeArray: &size, sampleBufferOut: &sample) == noErr
        else { return nil }
        return sample
    }

    private func display(_ decoded: CVImageBuffer, pts: CMTime) -> Bool {
        lutProcessor.tag709(decoded)
        // the monitor LUT, if one is on (a new BGRA picture), else the decoded picture itself
        let image = lut.flatMap { lutProcessor.process(decoded, box: $0) } ?? decoded
        tap?.take(image, pts: pts)  // local recording / frame grab: what's shown
        if imageFormat == nil || !CMVideoFormatDescriptionMatchesImageBuffer(imageFormat!, imageBuffer: image) {
            imageFormat = nil
            CMVideoFormatDescriptionCreateForImageBuffer(allocator: kCFAllocatorDefault, imageBuffer: image,
                                                         formatDescriptionOut: &imageFormat)
        }
        guard let imageFormat else { return false }
        var timing = CMSampleTimingInfo(duration: .invalid, presentationTimeStamp: pts, decodeTimeStamp: .invalid)
        var sample: CMSampleBuffer?
        guard CMSampleBufferCreateReadyWithImageBuffer(allocator: kCFAllocatorDefault, imageBuffer: image,
                                                       formatDescription: imageFormat, sampleTiming: &timing,
                                                       sampleBufferOut: &sample) == noErr, let sample else { return false }
        if let atts = CMSampleBufferGetSampleAttachmentsArray(sample, createIfNecessary: true), CFArrayGetCount(atts) > 0 {
            let d = unsafeBitCast(CFArrayGetValueAtIndex(atts, 0), to: CFMutableDictionary.self)
            // Show as soon as decoded: no clock, no buffering.
            CFDictionarySetValue(d, Unmanaged.passUnretained(kCMSampleAttachmentKey_DisplayImmediately).toOpaque(),
                                 Unmanaged.passUnretained(kCFBooleanTrue).toOpaque())
        }
        renderer.enqueue(sample)
        return true
    }
}

/// Calls body with C pointer/size arrays for a list of Data blobs.
private func withPointers<R>(_ blobs: [Data], _ body: (UnsafePointer<UnsafePointer<UInt8>>, UnsafePointer<Int>) -> R) -> R {
    let bufs = blobs.map { d -> UnsafeMutablePointer<UInt8> in
        let p = UnsafeMutablePointer<UInt8>.allocate(capacity: d.count)
        d.copyBytes(to: p, count: d.count)
        return p
    }
    defer { bufs.forEach { $0.deallocate() } }
    let ptrs = bufs.map { UnsafePointer($0) }
    let sizes = blobs.map(\.count)
    return ptrs.withUnsafeBufferPointer { p in sizes.withUnsafeBufferPointer { s in body(p.baseAddress!, s.baseAddress!) } }
}

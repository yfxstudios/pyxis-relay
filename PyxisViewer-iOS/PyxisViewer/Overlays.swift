import SwiftUI
import CoreImage
import CoreVideo

// Frame guides and exposure/focus overlays, like a field monitor's: drawn by this app over the
// picture it shows. Frame grabs and local recordings don't include them.
//
//   lines (drawn over the picture):   frame guide (2.39, 1.85, 16:9...), shade outside it,
//                                     rule of thirds, 90% safe area, centre cross
//   image (made from the picture):    false colour, zebras, focus peaking
//
// Guides sit inside the area the camera records, not the whole stream: in 6:5 or 3:2 the camera
// streams its 16:9 picture with black bars, and a 2.39 guide belongs inside the 6:5 part.

enum FrameGuide: String, CaseIterable, Identifiable {
    case off = "Off", r239 = "2.39", r200 = "2.00", r185 = "1.85", r169 = "16:9", r43 = "4:3", r11 = "1:1",
         r45 = "4:5", r916 = "9:16"
    var id: String { rawValue }

    var ratio: CGFloat? {
        switch self {
        case .off: return nil
        case .r239: return 2.39
        case .r200: return 2
        case .r185: return 1.85
        case .r169: return 16 / 9
        case .r43: return 4 / 3
        case .r11: return 1
        case .r45: return 4 / 5
        case .r916: return 9 / 16
        }
    }

    /// The guide's frame: the largest rectangle of its ratio centred in the recorded area.
    func rect(in area: CGRect) -> CGRect { ratio.map { fit($0, in: area) } ?? area }
}

/// The largest rectangle of `ratio` (width / height) centred in `r`.
func fit(_ ratio: CGFloat, in r: CGRect) -> CGRect {
    guard ratio > 0, r.width > 0, r.height > 0 else { return r }
    if r.width / r.height > ratio {
        let w = r.height * ratio
        return CGRect(x: r.midX - w / 2, y: r.minY, width: w, height: r.height)
    }
    let h = r.width / ratio
    return CGRect(x: r.minX, y: r.midY - h / 2, width: r.width, height: h)
}

/// Where the picture is on screen: the stream's frame, the part of it the camera records, and the
/// zoom that maps them to the screen.
struct PictureLayout {
    var video: CGRect          // the stream's picture, unzoomed
    var recorded: CGRect       // the part the camera records (the whole picture if it doesn't say)
    var scale: CGFloat = 1     // zoom, about the centre of `bounds`
    var pan: CGSize = .zero
    var bounds: CGRect

    init(video: CGRect, recordedRatio: CGFloat?, bounds: CGRect) {
        self.video = video
        self.recorded = recordedRatio.map { fit($0, in: video) } ?? video
        self.bounds = bounds
    }

    /// A rectangle of the unzoomed picture, where it is on screen now.
    func shown(_ r: CGRect) -> CGRect {
        let c = CGPoint(x: bounds.midX, y: bounds.midY)
        return CGRect(x: c.x + (r.minX - c.x) * scale + pan.width, y: c.y + (r.minY - c.y) * scale + pan.height,
                      width: r.width * scale, height: r.height * scale)
    }

    /// The zoom that makes `r` (of the unzoomed picture) fill the screen, centred.
    func filling(_ r: CGRect) -> (CGFloat, CGSize) {
        guard r.width > 0, r.height > 0 else { return (1, .zero) }
        let s = min(bounds.width / r.width, bounds.height / r.height)
        return (s, CGSize(width: (bounds.midX - r.midX) * s, height: (bounds.midY - r.midY) * s))
    }

    /// Keeps a pan from sliding the picture off the screen.
    func clamped(_ p: CGSize, scale s: CGFloat) -> CGSize {
        let mx = max(0, (video.width * s - bounds.width) / 2), my = max(0, (video.height * s - bounds.height) / 2)
        return CGSize(width: min(mx, max(-mx, p.width)), height: min(my, max(-my, p.height)))
    }
}

/// The image overlays the video thread should make (handed over safely between threads).
struct ImageOverlays: Equatable {
    var falseColor = false
    var zebras = false
    var zebraLevel = 95  // percent of the video range
    var peaking = false
    var any: Bool { falseColor || zebras || peaking }
}

final class OverlayBox: @unchecked Sendable {
    private let lock = NSLock()
    private var value = ImageOverlays()
    func set(_ v: ImageOverlays) { lock.withLock { value = v } }
    var current: ImageOverlays { lock.withLock { value } }
}

/// What's chosen, remembered between launches. `enabled` turns them all off and on again.
@MainActor
final class Overlays: ObservableObject {
    @Published var enabled: Bool { didSet { save() } }
    @Published var guide: FrameGuide { didSet { save() } }
    @Published var shadeOpacity: Double { didSet { save() } }  // outside the frame guide, 0...1
    @Published var fill: Bool { didSet { save() } }             // zoom so the guide fills the screen
    @Published var thirds: Bool { didSet { save() } }
    @Published var safeArea: Bool { didSet { save() } }
    @Published var center: Bool { didSet { save() } }
    @Published var falseColor: Bool { didSet { save() } }
    @Published var zebras: Bool { didSet { save() } }
    @Published var zebraLevel: Int { didSet { save() } }
    @Published var peaking: Bool { didSet { save() } }

    static let zebraLevels = [70, 80, 90, 95, 100]

    let box = OverlayBox()
    private let d = UserDefaults.standard

    init() {
        enabled = d.object(forKey: "overlaysOn") as? Bool ?? true
        guide = FrameGuide(rawValue: d.string(forKey: "frameGuide") ?? "") ?? .off
        shadeOpacity = d.object(forKey: "guideShadeOpacity") as? Double ?? 0.6
        fill = d.bool(forKey: "guideFill")
        thirds = d.bool(forKey: "guideThirds")
        safeArea = d.bool(forKey: "guideSafe")
        center = d.bool(forKey: "guideCenter")
        falseColor = d.bool(forKey: "falseColor")
        zebras = d.bool(forKey: "zebras")
        zebraLevel = d.object(forKey: "zebraLevel") as? Int ?? 95
        peaking = d.bool(forKey: "peaking")
        update()
    }

    /// Something is chosen and showing (the button lights up).
    var active: Bool {
        enabled && (guide != .off || thirds || safeArea || center || falseColor || zebras || peaking)
    }

    /// Turns one on or off; turning one on also turns the overlays back on.
    func toggle(_ key: ReferenceWritableKeyPath<Overlays, Bool>) {
        let on = !(enabled && self[keyPath: key])
        self[keyPath: key] = on
        if on { enabled = true }
    }

    func select(_ g: FrameGuide) {
        guide = enabled && guide == g ? .off : g
        if g != .off { enabled = true }
    }

    func nextZebraLevel() {
        let l = Self.zebraLevels
        zebraLevel = l[((l.firstIndex(of: zebraLevel) ?? 0) + 1) % l.count]
        zebras = true
        enabled = true
    }

    private func save() {
        d.set(enabled, forKey: "overlaysOn")
        d.set(guide.rawValue, forKey: "frameGuide")
        d.set(shadeOpacity, forKey: "guideShadeOpacity")
        d.set(fill, forKey: "guideFill")
        d.set(thirds, forKey: "guideThirds")
        d.set(safeArea, forKey: "guideSafe")
        d.set(center, forKey: "guideCenter")
        d.set(falseColor, forKey: "falseColor")
        d.set(zebras, forKey: "zebras")
        d.set(zebraLevel, forKey: "zebraLevel")
        d.set(peaking, forKey: "peaking")
        update()
    }

    private func update() {
        box.set(enabled ? ImageOverlays(falseColor: falseColor, zebras: zebras, zebraLevel: zebraLevel, peaking: peaking)
                        : ImageOverlays())
    }
}

// MARK: - false colour scale

/// Video levels (Rec.709 luma, 0–1) and their colours; the rest of the picture goes grey.
enum FalseColor {
    struct Band { let from: Float, to: Float, rgb: (Float, Float, Float), label: String, range: String }
    static let bands = [
        Band(from: 0, to: 0.025, rgb: (0.55, 0.15, 0.85), label: "Black clip", range: "0–2.5%"),
        Band(from: 0.025, to: 0.05, rgb: (0.10, 0.35, 1.00), label: "Near black", range: "2.5–5%"),
        Band(from: 0.38, to: 0.45, rgb: (0.15, 0.80, 0.25), label: "18% grey", range: "38–45%"),
        Band(from: 0.52, to: 0.58, rgb: (1.00, 0.45, 0.70), label: "Skin, +1 stop", range: "52–58%"),
        Band(from: 0.95, to: 0.99, rgb: (1.00, 0.85, 0.10), label: "Near white", range: "95–99%"),
        Band(from: 0.99, to: 1.01, rgb: (1.00, 0.15, 0.15), label: "Clipped", range: "99%+"),
    ]

    static func color(_ y: Float) -> (Float, Float, Float) {
        bands.first { y >= $0.from && y < $0.to }?.rgb ?? (y, y, y)
    }
}

// MARK: - image overlays (video thread)

/// Makes false colour, zebras and focus peaking on the GPU (Core Image). They're read from the
/// camera's picture (before the monitor LUT, as on a monitor) and drawn over what's shown.
/// Used by the video thread only.
final class OverlayProcessor {
    private let context = CIContext(options: [.cacheIntermediates: false, .name: "overlays"])
    private let space = CGColorSpace(name: CGColorSpace.itur_709)!
    private var pool: CVPixelBufferPool?
    private var poolSize = (0, 0)
    private lazy var falseColorCube = cube { FalseColor.color($0) }
    private var zebraCubes: [Int: CIFilter] = [:]

    private static let size = 64

    /// A colour cube that maps Rec.709 luma to a colour.
    private func cube(_ f: (Float) -> (Float, Float, Float)) -> CIFilter {
        let n = Self.size
        var rgba = [Float](repeating: 1, count: n * n * n * 4)
        for b in 0..<n { for g in 0..<n { for r in 0..<n {
            let y = 0.2126 * Float(r) / Float(n - 1) + 0.7152 * Float(g) / Float(n - 1) + 0.0722 * Float(b) / Float(n - 1)
            let c = f(y), i = ((b * n + g) * n + r) * 4
            rgba[i] = c.0; rgba[i + 1] = c.1; rgba[i + 2] = c.2
        } } }
        let filter = CIFilter(name: "CIColorCubeWithColorSpace")!
        filter.setValue(n, forKey: "inputCubeDimension")
        filter.setValue(rgba.withUnsafeBufferPointer { Data(buffer: $0) }, forKey: "inputCubeData")
        filter.setValue(space, forKey: "inputColorSpace")  // works on Rec.709-encoded values, i.e. video levels
        return filter
    }

    private func zebraCube(_ level: Int) -> CIFilter {
        if let c = zebraCubes[level] { return c }
        let t = Float(level) / 100 - 0.005
        let c = cube { $0 >= t ? (1, 1, 1) : (0, 0, 0) }
        zebraCubes[level] = c
        return c
    }

    /// `shown` with the overlays on it, as a new BGRA buffer; nil when none are on.
    func process(source: CVPixelBuffer, shown: CVPixelBuffer, box: OverlayBox) -> CVPixelBuffer? {
        let o = box.current
        guard o.any else { return nil }
        let src = CIImage(cvPixelBuffer: source)
        let extent = src.extent
        var out = CIImage(cvPixelBuffer: shown)

        if o.falseColor {
            falseColorCube.setValue(src, forKey: kCIInputImageKey)
            if let fc = falseColorCube.outputImage { out = fc }
        }
        if o.zebras {
            let cube = zebraCube(o.zebraLevel)
            cube.setValue(src, forKey: kCIInputImageKey)
            if let mask = cube.outputImage {
                // diagonal black and white stripes where the picture is at or above the level
                let stripes = CIFilter(name: "CIStripesGenerator", parameters: [
                    "inputColor0": CIColor(red: 1, green: 1, blue: 1), "inputColor1": CIColor(red: 0, green: 0, blue: 0),
                    "inputWidth": max(3, extent.width / 320), "inputSharpness": 1,
                ])?.outputImage?.transformed(by: CGAffineTransform(rotationAngle: .pi / 4)).cropped(to: extent)
                if let stripes {
                    out = stripes.applyingFilter("CIBlendWithMask", parameters: [kCIInputBackgroundImageKey: out, kCIInputMaskImageKey: mask])
                }
            }
        }
        if o.peaking {
            // sharp edges in the camera's picture, in red
            // (sensitivity tuned on a real frame: the in-focus detail lights up, soft areas don't)
            let edges = src.applyingFilter("CIEdges", parameters: [kCIInputIntensityKey: 8])
                .applyingFilter("CIMaximumComponent")
                .applyingFilter("CIColorThreshold", parameters: ["inputThreshold": 0.15])
                .applyingFilter("CIMorphologyMaximum", parameters: [kCIInputRadiusKey: max(1, extent.width / 1920)])  // visible when scaled down
                .cropped(to: extent)
            let red = CIImage(color: CIColor(red: 1, green: 0.1, blue: 0.1)).cropped(to: extent)
            out = red.applyingFilter("CIBlendWithMask", parameters: [kCIInputBackgroundImageKey: out, kCIInputMaskImageKey: edges])
        }

        let w = CVPixelBufferGetWidth(shown), h = CVPixelBufferGetHeight(shown)
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
        for (k, v) in [(kCVImageBufferColorPrimariesKey, kCVImageBufferColorPrimaries_ITU_R_709_2),
                       (kCVImageBufferTransferFunctionKey, kCVImageBufferTransferFunction_ITU_R_709_2),
                       (kCVImageBufferYCbCrMatrixKey, kCVImageBufferYCbCrMatrix_ITU_R_709_2)] {
            CVBufferSetAttachment(dst, k, v, .shouldPropagate)
        }
        return dst
    }
}

extension Show {
    /// The recorded picture's shape (width / height), if the camera says.
    static func recordedRatio(_ cam: Camera) -> CGFloat? {
        #if DEBUG
        // `-debugRecordedRatio 1.2` launch argument: pretend the camera records 6:5 (testing without one)
        let debug = UserDefaults.standard.double(forKey: "debugRecordedRatio")
        if debug > 0 { return debug }
        #endif
        let r = cam.v("/system/format")["recordResolution"]
        guard let w = r["width"].double, let h = r["height"].double, w > 0, h > 0 else { return nil }
        return w / h
    }
    /// The same as the camera names it, e.g. "6:5".
    static func recordedAspect(_ cam: Camera) -> String? {
        cam.v("/system/format")["resolutionDescriptor"]["aspectRatio"].string
    }
}

// MARK: - lines over the picture

struct GuidesOverlay: View {
    @ObservedObject var overlays: Overlays
    let layout: PictureLayout  // where the picture is, in this view's coordinates

    var body: some View {
        Canvas { ctx, _ in
            guard overlays.enabled, layout.video.width > 0 else { return }
            let video = layout.shown(layout.video)
            let frame = overlays.guide.rect(in: layout.shown(layout.recorded))
            if overlays.guide != .off {
                if overlays.shadeOpacity > 0 {
                    var outside = Path(video)
                    outside.addRect(frame)
                    ctx.fill(outside, with: .color(.black.opacity(overlays.shadeOpacity)), style: FillStyle(eoFill: true))
                }
                line(ctx, Path(frame), width: 1.2, opacity: 0.9)
            }
            if overlays.thirds {
                var p = Path()
                for i in 1...2 {
                    let x = frame.minX + frame.width * CGFloat(i) / 3, y = frame.minY + frame.height * CGFloat(i) / 3
                    p.move(to: CGPoint(x: x, y: frame.minY)); p.addLine(to: CGPoint(x: x, y: frame.maxY))
                    p.move(to: CGPoint(x: frame.minX, y: y)); p.addLine(to: CGPoint(x: frame.maxX, y: y))
                }
                line(ctx, p, width: 1, opacity: 0.55)
            }
            if overlays.safeArea {
                let safe = frame.insetBy(dx: frame.width * 0.05, dy: frame.height * 0.05)
                line(ctx, Path(safe), width: 1, opacity: 0.75, dash: [6, 5])
            }
            if overlays.center {
                let c = CGPoint(x: frame.midX, y: frame.midY), r: CGFloat = 12
                var p = Path()
                p.move(to: CGPoint(x: c.x - r, y: c.y)); p.addLine(to: CGPoint(x: c.x + r, y: c.y))
                p.move(to: CGPoint(x: c.x, y: c.y - r)); p.addLine(to: CGPoint(x: c.x, y: c.y + r))
                line(ctx, p, width: 1.5, opacity: 0.9)
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    /// A white line with a soft dark edge, so it shows on bright and dark pictures.
    private func line(_ ctx: GraphicsContext, _ p: Path, width: CGFloat, opacity: Double, dash: [CGFloat] = []) {
        ctx.stroke(p, with: .color(.black.opacity(0.35 * opacity)), style: StrokeStyle(lineWidth: width + 1.5, dash: dash))
        ctx.stroke(p, with: .color(.white.opacity(opacity)), style: StrokeStyle(lineWidth: width, dash: dash))
    }
}

// MARK: - controls

/// In the bottom bar: opens the guides panel. Blue while any are showing.
struct GuidesButton: View {
    @ObservedObject var overlays: Overlays
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            VStack(spacing: 3) {
                Image(systemName: "squareshape.dashed.squareshape").font(.system(size: 21, weight: .medium))
                    .foregroundStyle(overlays.active ? HUDStyle.accent : .white)
                Text("GUIDES").font(.system(size: 9, weight: .bold)).tracking(0.5).foregroundStyle(.white.opacity(0.85))
            }
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
        }
        .accessibilityLabel(overlays.active ? "Guides and overlays, on" : "Guides and overlays")
    }
}

/// The docked guides panel: frame guide, lines, and exposure and focus overlays.
struct OverlayChooser: View {
    @ObservedObject var overlays: Overlays
    let recorded: String?  // the camera's recorded area, e.g. "6:5"
    let close: () -> Void

    var body: some View {
        let on = overlays.enabled
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Text("GUIDES").font(.system(size: 13, weight: .bold)).foregroundStyle(.white.opacity(0.75))
                Spacer()
                if on && overlays.guide != .off {
                    // how dark it is outside the frame guide
                    HStack(spacing: 8) {
                        Text("Outside").font(.system(size: 13, weight: .semibold))
                        Slider(value: $overlays.shadeOpacity, in: 0...1).tint(.white).frame(maxWidth: 200)
                            .accessibilityLabel("Darken outside the frame")
                        Text("\(Int((overlays.shadeOpacity * 100).rounded()))%").font(.system(size: 13).monospacedDigit())
                            .frame(width: 38, alignment: .trailing)
                    }
                }
                chip(on ? "On" : "Off", on) { overlays.enabled.toggle() }
                    .accessibilityLabel(on ? "Guides on" : "Guides off")
                Button(action: close) { Image(systemName: "xmark").font(.system(size: 13, weight: .bold)).frame(width: 30, height: 30) }
                    .accessibilityLabel("Close")
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 22) {
                    ForEach(FrameGuide.allCases) { g in
                        let selected = (on || g == .off) && overlays.guide == g
                        Button { overlays.select(g) } label: {
                            VStack(spacing: 5) {
                                Text(g.rawValue).font(.system(size: 17).monospacedDigit()).lineLimit(1)
                                Rectangle().fill(selected ? Color.white : .clear).frame(height: 2.5)
                            }
                            .fixedSize()
                            .frame(minHeight: 44)
                            .contentShape(Rectangle())
                        }
                        .accessibilityLabel(g == .off ? "No frame guide" : "Frame guide \(g.rawValue)")
                        .accessibilityAddTraits(selected ? .isSelected : [])
                    }
                }
                .padding(.horizontal, 2)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    chip("Fill", overlays.fill) { overlays.fill.toggle() }
                        .accessibilityLabel("Fill the screen with the frame")
                    chip("Thirds", on && overlays.thirds) { overlays.toggle(\.thirds) }
                    chip("Safe 90%", on && overlays.safeArea) { overlays.toggle(\.safeArea) }
                    chip("Center", on && overlays.center) { overlays.toggle(\.center) }
                    Spacer().frame(width: 10)
                    chip("False color", on && overlays.falseColor) { overlays.toggle(\.falseColor) }
                    chip("Zebras", on && overlays.zebras) { overlays.toggle(\.zebras) }
                    if on && overlays.zebras {
                        chip("\(overlays.zebraLevel)%", false) { overlays.nextZebraLevel() }
                            .accessibilityLabel("Zebra level \(overlays.zebraLevel) percent")
                            .accessibilityHint("Changes the level")
                    }
                    chip("Peaking", on && overlays.peaking) { overlays.toggle(\.peaking) }
                }
                .padding(.horizontal, 2).padding(.vertical, 2)
            }
            if on && overlays.falseColor {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 14) {
                        ForEach(FalseColor.bands, id: \.label) { b in
                            HStack(spacing: 5) {
                                RoundedRectangle(cornerRadius: 2)
                                    .fill(Color(red: Double(b.rgb.0), green: Double(b.rgb.1), blue: Double(b.rgb.2)))
                                    .frame(width: 12, height: 12)
                                Text("\(b.label) \(b.range)")
                                    .font(.system(size: 12)).lineLimit(1)
                            }
                        }
                    }
                }
            } else {
                Text((recorded.map { "Frame guides sit inside the recorded \($0) area. " } ?? "")
                     + "Shown on this device only. Frame grabs and recordings don't include them.")
                    .font(.system(size: 12)).foregroundStyle(.white.opacity(0.6))
            }
        }
        .frame(maxWidth: 700)
    }

    private func chip(_ title: String, _ selected: Bool, action: @escaping () -> Void) -> some View {
        Button {
            Haptic.selection()
            action()
        } label: {
            Text(title).font(.system(size: 14, weight: .semibold)).lineLimit(1).fixedSize()
                .padding(.horizontal, 12).padding(.vertical, 7)
                .background(selected ? Color.white : .clear, in: RoundedRectangle(cornerRadius: 6))
                .foregroundStyle(selected ? Color.black : .white)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(.white.opacity(0.7)))
                .frame(minHeight: 44)
                .contentShape(Rectangle())
        }
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

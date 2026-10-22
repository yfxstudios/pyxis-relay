import Foundation

/// Built-in film looks: monitor LUTs the app applies to the picture it shows (nothing is
/// sent to the camera).
///
/// Input and output are Rec.709 video: the looks go on top of the camera's own LUT on its
/// Stream output (e.g. Blackmagic's "Film to Extended Video"), the way a look LUT goes on
/// after a technical conversion. Grading moves that change colour balance work on light
/// (Rec.709 decoded with gamma 2.4); contrast and split-toning work on the video signal.
enum FilmLook: String, CaseIterable, Identifiable {
    case print = "Film Print"
    case warm = "Warm Film"
    case tealOrange = "Teal & Orange"
    case bleach = "Bleach Bypass"
    case faded = "Faded Film"
    case mono = "Black & White"

    var id: String { rawValue }

    var blurb: String {
        switch self {
        case .print: return "Print-film contrast, slightly warm highlights"
        case .warm: return "Golden highlights, gentle contrast"
        case .tealOrange: return "Cool shadows, warm skin and highlights"
        case .bleach: return "Desaturated, high contrast, silver-retention look"
        case .faded: return "Lifted blacks, soft highlights, muted colour"
        case .mono: return "Black and white with film-like contrast"
        }
    }

    /// The look as a 3D LUT (red changes fastest, as in .cube files).
    func lut(size n: Int = 33) -> CubeLUT {
        var rgba = [Float]()
        rgba.reserveCapacity(n * n * n * 4)
        let d = Double(n - 1)
        for b in 0..<n {
            for g in 0..<n {
                for r in 0..<n {
                    let c = apply(Double(r) / d, Double(g) / d, Double(b) / d)
                    rgba += [Float(c.0), Float(c.1), Float(c.2), 1]
                }
            }
        }
        return CubeLUT(title: rawValue, size: n, rgba: rgba)
    }

    /// One Rec.709 colour (0...1) through the look.
    func apply(_ r: Double, _ g: Double, _ b: Double) -> (Double, Double, Double) {
        var v = Color3(r, g, b)
        switch self {
        case .print:
            v = v.contrast(0.2)
            v = v + Color3(0.018, 0.004, -0.02) * pow(v.luma, 2)    // warm highlights, neutral blacks
            v = v.saturation(1.06)
        case .warm:
            v = v.balance(red: 1.06, blue: 0.88).contrast(0.12).saturation(0.95)
        case .tealOrange:
            v = v.saturation(1.08)
            let l = v.luma
            // teal shadows, fading out towards true black so black stays black
            v = v + Color3(-0.035, 0.005, 0.045) * (pow(1 - l, 2) * min(1, l / 0.08))
            v = v + Color3(0.045, 0.012, -0.045) * pow(l, 1.5)    // orange highlights
            v = v.contrast(0.12)
        case .bleach:
            let l = v.luma
            v = v.mix(Color3(l, l, l), 0.55).contrast(0.45)
        case .faded:
            v = v.balance(red: 1.02, blue: 0.97).contrast(-0.1).saturation(0.8)
            v = Color3(0.06 + 0.88 * v.x, 0.065 + 0.875 * v.y, 0.07 + 0.86 * v.z)   // lifted, slightly cool blacks
        case .mono:
            let l = v.luma
            v = Color3(l, l, l).contrast(0.25)
        }
        return (v.x.clamped, v.y.clamped, v.z.clamped)
    }
}

/// A small RGB type for the look maths (Rec.709 signal values).
struct Color3 {
    var x, y, z: Double
    init(_ x: Double, _ y: Double, _ z: Double) { self.x = x; self.y = y; self.z = z }

    var luma: Double { 0.2126 * x + 0.7152 * y + 0.0722 * z }  // Rec.709 weights

    static func + (a: Color3, b: Color3) -> Color3 { Color3(a.x + b.x, a.y + b.y, a.z + b.z) }
    static func * (a: Color3, k: Double) -> Color3 { Color3(a.x * k, a.y * k, a.z * k) }

    func mix(_ o: Color3, _ t: Double) -> Color3 { self * (1 - t) + o * t }
    func saturation(_ s: Double) -> Color3 { let l = luma; return Color3(l + s * (x - l), l + s * (y - l), l + s * (z - l)) }

    /// S-curve contrast around mid grey (negative = flatter); keeps 0 and 1 in place.
    func contrast(_ k: Double) -> Color3 {
        func c(_ v: Double) -> Double {
            let v = max(0, min(1, v))
            let s = v * v * (3 - 2 * v)  // smoothstep
            return v + k * (s - v)
        }
        return Color3(c(x), c(y), c(z))
    }

    /// White balance shift, done on light (gamma 2.4), like a filter over the lens.
    func balance(red: Double, blue: Double) -> Color3 {
        func f(_ v: Double, _ k: Double) -> Double { pow(min(1, pow(max(0, v), 2.4) * k), 1 / 2.4) }
        return Color3(f(x, red), y, f(z, blue))
    }
}

private extension Double {
    var clamped: Double { Swift.max(0, Swift.min(1, self)) }
}

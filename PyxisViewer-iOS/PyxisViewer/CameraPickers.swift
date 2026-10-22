import SwiftUI

// The camera's own setting picker, docked along the bottom while a setting is selected:
//
//     200      400      1250     [3200]     8000        <- presets, the current one underlined
//   ‹ 3200 ›  ─────────────────────────●──────          <- step through every value, or slide
//
// Used for FPS, shutter, iris, ISO, white balance and tint.

struct PickerOption: Hashable {
    let id: String
    let label: String
    var icon: String? = nil
    var badge: String? = nil  // small caption above the value, e.g. "BASE"
}

/// The docked strip the pickers (and the other quick panels) sit in.
struct DockedPanel<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View {
        VStack(spacing: 0) {
            content
                .padding(.horizontal, 18).padding(.top, 12).padding(.bottom, 10)
                .frame(maxWidth: .infinity)
        }
        .background(HUDStyle.picker.ignoresSafeArea())
        .foregroundStyle(.white)
        .shadow(color: .black.opacity(0.6), radius: 2, x: 0, y: 1)  // legible over bright pictures
    }
}

struct SettingPicker: View {
    let presets: [PickerOption]
    let selected: String?
    let pick: (PickerOption) -> Void
    let value: String
    var prev: (() -> Void)? = nil
    var next: (() -> Void)? = nil
    /// Slider position and range; `set` is called while dragging.
    var slider: (value: Double, range: ClosedRange<Double>, set: (Double) -> Void)? = nil
    var trailing: AnyView? = nil
    var note: String? = nil
    var valueBadge: String? = nil
    /// Snap the slider to steps of this size (list pickers: 1 = every value), with a tick.
    var sliderStep: Double? = nil

    @State private var dragging: Double?

    var body: some View {
        let badges = presets.contains { $0.badge != nil }
        VStack(spacing: 14) {
            if !presets.isEmpty {
                HStack(spacing: 0) {
                    ForEach(presets, id: \.self) { o in
                        Button { pick(o) } label: {
                            VStack(spacing: 5) {
                                if badges {  // same height for every preset
                                    Text(o.badge ?? " ").font(.system(size: 9, weight: .bold)).tracking(0.8)
                                        .foregroundStyle(.white.opacity(0.75)).opacity(o.badge == nil ? 0 : 1)
                                }
                                // presets share the width and shrink to fit rather than widening the
                                // whole screen; an icon (WB) goes above its label to leave room
                                if let icon = o.icon { Image(systemName: icon).font(.system(size: 17)).frame(height: 20) }
                                Text(o.label).font(.system(size: 21).monospacedDigit()).lineLimit(1).minimumScaleFactor(0.55)
                                    .padding(.bottom, 7)
                                    .overlay(alignment: .bottom) {  // underline as wide as the label
                                        Rectangle().fill(o.id == selected ? Color.white : .clear).frame(height: 2.5)
                                            .padding(.horizontal, 6)
                                    }
                            }
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .contentShape(Rectangle())
                        }
                        .accessibilityAddTraits(o.id == selected ? .isSelected : [])
                    }
                }
            }
            HStack(spacing: 14) {
                if prev != nil || next != nil {
                    Button { prev?() } label: { Image(systemName: "chevron.left").font(.system(size: 20, weight: .medium)).frame(width: 34, height: 40) }
                        .disabled(prev == nil).opacity(prev == nil ? 0.3 : 1)
                        .accessibilityLabel("Lower")
                }
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text(value).font(.system(size: 21).monospacedDigit()).lineLimit(1)
                    if let valueBadge {
                        Text(valueBadge).font(.system(size: 9, weight: .bold)).tracking(0.8).foregroundStyle(.white.opacity(0.75))
                    }
                }
                .frame(minWidth: 64)
                if prev != nil || next != nil {
                    Button { next?() } label: { Image(systemName: "chevron.right").font(.system(size: 20, weight: .medium)).frame(width: 34, height: 40) }
                        .disabled(next == nil).opacity(next == nil ? 0.3 : 1)
                        .accessibilityLabel("Higher")
                }
                if let s = slider, s.range.upperBound > s.range.lowerBound {
                    let binding = Binding(get: { dragging ?? s.value }, set: { (v: Double) in
                        if sliderStep != nil, v != (dragging ?? s.value) { Haptic.selection() }
                        dragging = v
                        s.set(v)
                    })
                    Group {
                        if let step = sliderStep {
                            Slider(value: binding, in: s.range, step: step, onEditingChanged: { if !$0 { dragging = nil } })
                        } else {
                            Slider(value: binding, in: s.range, onEditingChanged: { if !$0 { dragging = nil } })
                        }
                    }
                    .tint(.white)
                } else {
                    Spacer(minLength: 0)
                }
                if let trailing { trailing }
            }
            if let note {
                Text(note).font(.system(size: 12)).foregroundStyle(.white.opacity(0.6)).frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}

/// Up to `n` values spread across a list, preferring familiar ones.
func presetValues<T: Comparable>(_ all: [T], preferred: [T] = [], count n: Int = 5) -> [T] {
    let fav = preferred.filter(all.contains)
    let pool = fav.count >= n ? fav : all
    guard pool.count > n else { return pool }
    return (0..<n).map { pool[Int((Double($0) * Double(pool.count - 1) / Double(n - 1)).rounded())] }
}

/// Index of the value nearest `v` in a sorted list.
private func nearest(_ list: [Double], _ v: Double) -> Int {
    list.indices.min { abs(list[$0] - v) < abs(list[$1] - v) } ?? 0
}

/// A picker over a fixed list of values (ISO, shutter, frame rates): presets, ‹ › steps
/// through the whole list, and the slider moves along it.
@MainActor
func listPicker(values: [Double], current: Double?, preferred: [Double] = [], label: @escaping (Double) -> String,
                set: @escaping (Double) -> Void, setLive: ((Double) -> Void)? = nil,
                marked: [Double] = [], markLabel: String = "BASE",
                trailing: AnyView? = nil, note: String? = nil) -> SettingPicker {
    let i = current.map { nearest(values, $0) }
    var picks = presetValues(values, preferred: preferred)
    // Marked values (base ISO), and a familiar current value, always get a preset,
    // each replacing its nearest neighbour that isn't itself one of these.
    var keep = marked.filter(values.contains)
    if let c = current, preferred.contains(c), values.contains(c) { keep.append(c) }
    for c in keep where !picks.contains(c) && !picks.isEmpty {
        let free = picks.indices.filter { !keep.contains(picks[$0]) }
        guard let k = free.min(by: { abs(picks[$0] - c) < abs(picks[$1] - c) }) else { break }
        picks[k] = c
        picks.sort()
    }
    let presets = picks.map { PickerOption(id: label($0), label: label($0), badge: marked.contains($0) ? markLabel : nil) }
    return SettingPicker(
        presets: presets,
        selected: current.map(label),
        pick: { o in if let v = values.first(where: { label($0) == o.id }) { set(v) } },
        value: current.map(label) ?? "–",
        prev: i.flatMap { k in k > 0 ? { set(values[k - 1]) } : nil },
        next: i.flatMap { k in k < values.count - 1 ? { set(values[k + 1]) } : nil },
        slider: values.count > 1 ? (Double(i ?? 0), 0...Double(values.count - 1), { idx in
            let k = Int(idx.rounded())
            if k != i { (setLive ?? set)(values[k]) }  // only when the value changes
        }) : nil,
        trailing: trailing, note: note,
        valueBadge: current.flatMap { marked.contains($0) ? markLabel : nil },
        sliderStep: 1)  // the slider moves along the list: it stops on each value
}

/// The camera's base (native) ISO: where its gain is 0 dB.
///   1. ISO and gain lists that step together (as on the PYXIS): the ISO in 0 dB's place.
///   2. Otherwise the current gain, if the camera reports it: current ISO ÷ gain (6 dB per stop).
///   3. Otherwise Blackmagic's published native ISOs for the model (dual-native models have two).
@MainActor
func baseISOs(_ cam: Camera) -> [Double] {
    let isos = cam.v("/video/supportedISOs")["supportedISOs"].array.compactMap(\.double).sorted()
    let gains = cam.v("/video/supportedGains")["supportedGains"].array.compactMap(\.double).sorted()
    if !isos.isEmpty, isos.count == gains.count, let k = gains.firstIndex(of: 0) { return [isos[k]] }
    if !isos.isEmpty, let iso = cam.v("/video/iso")["iso"].double, let g = cam.v("/video/gain")["gain"].double {
        return [isos[nearest(isos, iso / pow(10, g / 20))]]
    }
    // whole words of the model name ("URSA Mini Pro 4.6K G2" is a 4.6K, not a 6K)
    let words = Set((cam.v("/system/product")["productName"].string ?? "").lowercased()
        .split(whereSeparator: { " -()/".contains($0) }).map(String.init))
    let published: [(String, [Double])] = [("17k", [800]), ("12k", [800]), ("4.6k", [800]), ("6k", [400, 3200]), ("4k", [400, 3200])]
    for (key, base) in published where words.contains(key) {
        return isos.isEmpty ? base : base.filter(isos.contains)
    }
    return []
}

// MARK: - the settings

struct SettingPickerView: View {
    @ObservedObject var cam: Camera
    let panel: QuickPanel

    var body: some View {
        switch panel {
        case .iso: iso
        case .shutter: shutter
        case .whiteBalance: whiteBalance
        case .tint: tint
        case .fps: fps
        case .iris: iris
        default: EmptyView()
        }
    }

    private var iso: some View {
        let all = cam.v("/video/supportedISOs")["supportedISOs"].array.compactMap(\.double)
        return listPicker(values: all, current: cam.v("/video/iso")["iso"].double,
                          preferred: [100, 200, 400, 800, 1250, 1600, 3200, 6400, 8000, 12800],
                          label: { String(Int($0)) }, set: { cam.put("/video/iso", ["iso": .number($0)]) },
                          marked: baseISOs(cam))
    }

    private var shutter: some View {
        let speedMode = cam.v("/video/shutter/measurement")["measurement"].string == "ShutterSpeed"
        let supported = cam.v("/video/supportedShutters")
        let current = cam.v("/video/shutter")
        if speedMode {
            return listPicker(values: supported["shutterSpeeds"].array.compactMap(\.double),
                              current: current["shutterSpeed"].double, preferred: [24, 48, 50, 60, 100, 125, 250, 500],
                              label: { "1/\(Int($0))" }) { cam.put("/video/shutter", ["shutterSpeed": .number($0)]) }
        }
        return listPicker(values: supported["shutterAngles"].array.compactMap(\.double),
                          current: current["shutterAngle"].double, preferred: [4500, 9000, 17280, 18000, 27000, 36000],
                          label: { Show.angle($0) }) { cam.put("/video/shutter", ["shutterAngle": .number($0)]) }
    }

    private var whiteBalance: some View {
        let wb = cam.v("/video/whiteBalance")["whiteBalance"].double
        let d = cam.v("/video/whiteBalance/description")["whiteBalance"]
        let lo = d["min"].double ?? 2500, hi = d["max"].double ?? 10000
        let presets: [(Double, String)] = [(3200, "lightbulb"), (4000, "light.cylindrical.ceiling"), (4500, "sun.haze"),
                                           (5600, "sun.max"), (6500, "cloud")]
        let set = { (k: Double) in cam.put("/video/whiteBalance", ["whiteBalance": .number(min(hi, max(lo, k)))]) }
        return SettingPicker(
            presets: presets.map { PickerOption(id: "\(Int($0.0))", label: "\(Int($0.0))K", icon: $0.1) },
            selected: wb.map { "\(Int($0))" },
            pick: { o in set(Double(o.id) ?? 5600) },
            value: wb.map { "\(Int($0))K" } ?? "–",
            prev: wb.flatMap { w in w > lo ? { set(w - 50) } : nil },
            next: wb.flatMap { w in w < hi ? { set(w + 50) } : nil },
            slider: (wb ?? 5600, lo...hi, { v in
                cam.putLive("/video/whiteBalance", ["whiteBalance": .number((v / 50).rounded() * 50)])
            }),
            trailing: AnyView(Button {
                Task {
                    await cam.action("PUT", "/video/whiteBalance/doAuto")
                    await cam.refresh("/video/whiteBalance"); await cam.refresh("/video/whiteBalanceTint")
                }
            } label: {
                Text("AWB").font(.system(size: 15, weight: .semibold))
                    .padding(.horizontal, 12).padding(.vertical, 7)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(.white.opacity(0.7)))
            }.accessibilityLabel("Auto white balance")))
    }

    private var tint: some View {
        let t = cam.v("/video/whiteBalanceTint")["whiteBalanceTint"].double
        let d = cam.v("/video/whiteBalanceTint/description")["whiteBalanceTint"]
        let lo = d["min"].double ?? -50, hi = d["max"].double ?? 50
        let set = { (v: Double) in cam.put("/video/whiteBalanceTint", ["whiteBalanceTint": .number(min(hi, max(lo, v)))]) }
        return SettingPicker(
            presets: [-20, -10, 0, 10, 20].map { PickerOption(id: String($0), label: String($0)) },
            selected: t.map { String(Int($0)) },
            pick: { o in set(Double(o.id) ?? 0) },
            value: t.map { String(Int($0)) } ?? "–",
            prev: t.flatMap { v in v > lo ? { set(v - 1) } : nil },
            next: t.flatMap { v in v < hi ? { set(v + 1) } : nil },
            slider: (t ?? 0, lo...hi, { v in cam.putLive("/video/whiteBalanceTint", ["whiteBalanceTint": .number(v.rounded())]) }))
    }

    private var fps: some View {
        let f = cam.v("/system/format")
        let entry = currentFormatEntry(cam)
        let offSpeed = f["offSpeedEnabled"].bool == true
        let rates = entry["frameRates"].array.compactMap(\.string)
        let toggle = AnyView(Button {
            setFormat(cam) { $0["offSpeedEnabled"] = .bool(!offSpeed) }
        } label: {
            Text("Off speed").font(.system(size: 15, weight: .semibold))
                .padding(.horizontal, 12).padding(.vertical, 7)
                .background(offSpeed ? Color.white : .clear, in: RoundedRectangle(cornerRadius: 6))
                .foregroundStyle(offSpeed ? Color.black : .white)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(.white.opacity(0.7)))
        })
        let presets = rates.map { PickerOption(id: $0, label: $0) }
        let pickRate = { (o: PickerOption) in setFormat(cam) { $0["frameRate"] = .string(o.id) } }
        if offSpeed {
            let lo = f["minOffSpeedFrameRate"].double ?? 12, hi = f["maxOffSpeedFrameRate"].double ?? 60
            let os = f["offSpeedFrameRate"].double ?? lo
            let setOS = { (v: Double) in setFormat(cam) { $0["offSpeedFrameRate"] = .number(min(hi, max(lo, v))) } }
            return SettingPicker(
                presets: presets, selected: f["frameRate"].string, pick: pickRate,
                value: "\(Int(os)) fps",
                prev: os > lo ? { setOS(os - 1) } : nil, next: os < hi ? { setOS(os + 1) } : nil,
                slider: (os, lo...hi, { v in if v.rounded() != os { setOS(v.rounded()) } }),
                trailing: toggle, note: "Project \(f["frameRate"].string ?? "") · sensor \(Int(os)) fps")
        }
        let i = rates.firstIndex(of: f["frameRate"].string ?? "")
        return SettingPicker(
            presets: presets, selected: f["frameRate"].string, pick: pickRate,
            value: f["frameRate"].string ?? "–",
            prev: i.flatMap { k in k > 0 ? { pickRate(presets[k - 1]) } : nil },
            next: i.flatMap { k in k < presets.count - 1 ? { pickRate(presets[k + 1]) } : nil },
            trailing: toggle)
    }

    @ViewBuilder private var iris: some View {
        if cam.v("/lens/iris/description")["controllable"].bool == true {
            // the options follow the fitted lens's range; its widest aperture is always a preset, marked OPEN
            let d = cam.v("/lens/iris/description")["apertureStop"]
            let stops = irisStops(min: d["min"].double ?? 1.4, max: d["max"].double ?? 22)
            listPicker(values: stops, current: cam.v("/lens/iris")["apertureStop"].double,
                       preferred: irisPresets(stops),
                       label: { "f" + Show.trim(($0 * 10).rounded() / 10) },
                       set: { cam.put("/lens/iris", ["apertureStop": .number($0)]) },
                       marked: [stops[0]], markLabel: "OPEN")
        } else {
            Text("The lens has no electronic iris control. Set the iris on the lens.")
                .font(.system(size: 15)).foregroundStyle(.white.opacity(0.8))
                .frame(maxWidth: .infinity, minHeight: 60)
        }
    }
}

/// Third-stop f-numbers the lens can reach (as marked on lenses and shown by the camera). The
/// lens's widest aperture takes the place of the nearest marked stop when it isn't one (f/1.75 for f/1.8).
func irisStops(min lo: Double, max hi: Double) -> [Double] {
    let marked: [Double] = [1, 1.1, 1.2, 1.4, 1.6, 1.8, 2, 2.2, 2.5, 2.8, 3.2, 3.5, 4, 4.5, 5, 5.6, 6.3, 7.1, 8, 9, 10, 11,
                            13, 14, 16, 18, 20, 22, 25, 29, 32]
    var stops = marked.filter { $0 > lo + 0.01 && $0 <= hi + 0.01 }
    if let first = stops.first, first - lo < 0.1 { stops.removeFirst() }
    return [lo] + stops
}

/// Iris presets: wide open, then the next four full stops at least 2/3 stop smaller
/// (f/1.75 lens: OPEN, 2.8, 4, 5.6, 8; f/2.8 lens: OPEN, 4, 5.6, 8, 11).
func irisPresets(_ stops: [Double]) -> [Double] {
    guard let open = stops.first else { return [] }
    let full: [Double] = [1, 1.4, 2, 2.8, 4, 5.6, 8, 11, 16, 22, 32]
    return [open] + full.filter { $0 >= open * 1.25 && stops.contains($0) }.prefix(4)
}

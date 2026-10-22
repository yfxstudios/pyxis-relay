import SwiftUI

// Autofocus: tap the picture to focus there, and a thin rail (swipe in from the right edge)
// to pick the mode. Only shown when the camera reports autofocus for the fitted lens.
//
// Camera coordinates are 0...1 across the picture. A target is set by its centre point; the
// camera reports its target box (and detected faces) by top-left corner and size, as
// measured on the PYXIS (point 0.5,0.5 -> box x 0.441, y 0.411, w 0.118, h 0.178).

enum AFMode: String, CaseIterable, Identifiable {
    case single = "OneShot", continuous = "Continuous", face = "TrackFace", object = "TrackObject"
    var id: String { rawValue }
    var name: String {
        switch self {
        case .single: return "Single autofocus (AF-S)"
        case .continuous: return "Continuous autofocus (AF-C)"
        case .face: return "Face tracking"
        case .object: return "Object tracking"
        }
    }
}

@MainActor
enum AF {
    static let statusPath = "/lens/focus/autoFocus"
    static let targetPath = "/lens/focus/autoFocus/target"
    static let facesPath = "/lens/focus/autoFocus/detectedFaces"

    static func supported(_ cam: Camera) -> Bool {
        cam.isConnected && cam.v("/lens/focus/autoFocus/description")["supported"].bool == true
    }
    static func modes(_ cam: Camera) -> [AFMode] {
        let listed = cam.v("/lens/focus/autoFocus/description")["supportedModes"].array.compactMap(\.string)
        return AFMode.allCases.filter { listed.isEmpty || listed.contains($0.rawValue) }
    }
    static func mode(_ cam: Camera) -> AFMode? { cam.v(statusPath)["mode"].string.flatMap(AFMode.init) }
    static func state(_ cam: Camera) -> String { cam.v(statusPath)["state"].string ?? "Idle" }

    static func setMode(_ cam: Camera, _ m: AFMode) {
        cam.put(statusPath, ["mode": .string(m.rawValue), "enabled": true])
    }

    /// Focus on a point of the picture (0...1), the way the current mode does it.
    static func focus(_ cam: Camera, at p: CGPoint) {
        let x = Double(min(1, max(0, p.x))), y = Double(min(1, max(0, p.y)))
        let point: JSON = ["x": .number(x), "y": .number(y)]
        switch mode(cam) ?? .single {
        case .single:
            Task { await cam.action("PUT", "/lens/focus/doAutoFocus", ["position": point]) }
        case .continuous:
            cam.put(targetPath, point)  // continuous AF follows the target area
        case .object:
            Task {
                await cam.action("PUT", targetPath, point)
                await cam.action("PUT", "/lens/focus/autoFocus/retrigger")  // start tracking what's there
            }
        case .face:
            // the detected face under (or nearest) the tap; no faces: focus on the point instead
            let faces = cam.v(facesPath)["detectedFaces"].array
            let nearest = faces.min { distance($0, x, y) < distance($1, x, y) }
            if let f = nearest, let i = f["index"].int {
                Task { await cam.action("PUT", "/lens/focus/autoFocus/trackFace", ["faceIndex": .number(Double(i))]) }
            } else {
                cam.put(targetPath, point)
            }
        }
    }

    private static func distance(_ face: JSON, _ x: Double, _ y: Double) -> Double {
        let b = face["position"]
        let cx = (b["x"].double ?? 0) + (b["width"].double ?? 0) / 2, cy = (b["y"].double ?? 0) + (b["height"].double ?? 0) / 2
        return hypot(cx - x, cy - y)
    }

    /// A camera box (top-left + size, 0...1) in view coordinates.
    static func rect(_ b: JSON, in video: CGRect) -> CGRect? {
        guard let x = b["x"].double, let y = b["y"].double, let w = b["width"].double, let h = b["height"].double else { return nil }
        return CGRect(x: video.minX + x * video.width, y: video.minY + y * video.height,
                      width: w * video.width, height: h * video.height)
    }
}

/// What's drawn over the picture: the tapped focus box (white while focusing, green when
/// focused, red on an error), the camera's tracking area in AF-C/Object, faces in Face mode.
struct FocusOverlay: View {
    @ObservedObject var cam: Camera
    let video: CGRect           // where the picture is, in this view's coordinates
    let tap: CGPoint?           // last tap, 0...1, while its box is shown
    let result: String?         // "Focused" or "Error" once the camera has said so for this tap
    let showAreas: Bool         // controls visible: show tracking area / faces too

    var body: some View {
        ZStack(alignment: .topLeading) {
            let mode = AF.mode(cam)
            if showAreas, mode == .continuous || mode == .object, let r = AF.rect(cam.v(AF.targetPath), in: video) {
                Corners().stroke(.white.opacity(0.85), lineWidth: 1.5)
                    .frame(width: r.width, height: r.height).position(x: r.midX, y: r.midY)
            }
            if showAreas, mode == .face {
                ForEach(Array(cam.v(AF.facesPath)["detectedFaces"].array.enumerated()), id: \.offset) { _, f in
                    if let r = AF.rect(f["position"], in: video) {
                        RoundedRectangle(cornerRadius: 4).stroke(.white.opacity(0.9), lineWidth: 1.5)
                            .frame(width: r.width, height: r.height).position(x: r.midX, y: r.midY)
                    }
                }
            }
            if let t = tap {
                // the camera only says "Focused" briefly (AF-S returns to Idle), so the result is kept
                let state = result ?? AF.state(cam)
                let color: Color = state == "Focused" ? .green : state == "Error" ? .red : .white
                Corners().stroke(color, lineWidth: 2)
                    .frame(width: 70, height: 70)
                    .position(x: video.minX + t.x * video.width, y: video.minY + t.y * video.height)
                    .animation(.easeOut(duration: 0.15), value: state)
                    .transition(.scale(scale: 1.3).combined(with: .opacity))
            }
        }
        .allowsHitTesting(false)
    }
}

/// A focus-box outline drawn as four corners.
struct Corners: Shape {
    func path(in r: CGRect) -> Path {
        let l = min(r.width, r.height) * 0.28
        var p = Path()
        for (corner, dx, dy) in [(CGPoint(x: r.minX, y: r.minY), 1.0, 1.0), (CGPoint(x: r.maxX, y: r.minY), -1.0, 1.0),
                                 (CGPoint(x: r.minX, y: r.maxY), 1.0, -1.0), (CGPoint(x: r.maxX, y: r.maxY), -1.0, -1.0)] {
            p.move(to: CGPoint(x: corner.x + dx * l, y: corner.y))
            p.addLine(to: corner)
            p.addLine(to: CGPoint(x: corner.x, y: corner.y + dy * l))
        }
        return p
    }
}

/// The autofocus mode rail: a thin column of icons at the right edge.
struct AFModeRail: View {
    @ObservedObject var cam: Camera
    let picked: () -> Void

    var body: some View {
        let current = AF.mode(cam)
        VStack(spacing: 6) {
            ForEach(AF.modes(cam)) { m in
                Button {
                    Haptic.selection()
                    AF.setMode(cam, m)
                    picked()
                } label: {
                    icon(m)
                        .frame(width: 40, height: 40)
                        .background(m == current ? Color.white : .clear, in: RoundedRectangle(cornerRadius: 8))
                        .foregroundStyle(m == current ? Color.black : .white)
                }
                .accessibilityLabel(m.name)
                .accessibilityAddTraits(m == current ? .isSelected : [])
            }
        }
        .padding(6)
        .background(HUDStyle.picker, in: UnevenRoundedRectangle(topLeadingRadius: 12, bottomLeadingRadius: 12))
        .shadow(color: .black.opacity(0.5), radius: 3)
    }

    @ViewBuilder private func icon(_ m: AFMode) -> some View {
        switch m {
        case .single, .continuous:
            // AF-S / AF-C drawn as a small badge
            VStack(spacing: 0) {
                Text("AF").font(.system(size: 10, weight: .heavy))
                Text(m == .single ? "S" : "C").font(.system(size: 13, weight: .heavy))
            }
        case .face: Image(systemName: "face.dashed").font(.system(size: 19, weight: .medium))
        case .object: Image(systemName: "scope").font(.system(size: 19, weight: .medium))
        }
    }
}

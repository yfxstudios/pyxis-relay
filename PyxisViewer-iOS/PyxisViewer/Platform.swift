import SwiftUI
import AVFoundation
#if os(iOS)
import UIKit
#else
import AppKit
#endif

// The few things that differ between the iPhone/iPad app and the Mac app.

/// Taps you can feel: the iPhone's haptics; on a Mac, the Force Touch trackpad's (if any).
enum Haptic {
    static func light() {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #else
        NSHapticFeedbackManager.defaultPerformer.perform(.generic, performanceTime: .now)
        #endif
    }
    static func medium() {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #else
        NSHapticFeedbackManager.defaultPerformer.perform(.levelChange, performanceTime: .now)
        #endif
    }
    static func selection() {
        #if os(iOS)
        UISelectionFeedbackGenerator().selectionChanged()
        #else
        NSHapticFeedbackManager.defaultPerformer.perform(.alignment, performanceTime: .now)
        #endif
    }
}

/// Keeps the screen on while the picture plays.
enum ScreenAwake {
    #if os(macOS)
    private static var activity: NSObjectProtocol?
    #endif

    @MainActor static func set(_ on: Bool) {
        #if os(iOS)
        UIApplication.shared.isIdleTimerDisabled = on
        #else
        if on, activity == nil {
            activity = ProcessInfo.processInfo.beginActivity(options: [.idleDisplaySleepDisabled, .userInitiated],
                                                             reason: "Playing the live picture")
        } else if !on, let a = activity {
            ProcessInfo.processInfo.endActivity(a)
            activity = nil
        }
        #endif
    }
}

/// Hosts the display layer, sized to the view.
#if os(iOS)
struct VideoLayerView: UIViewRepresentable {
    let layer: AVSampleBufferDisplayLayer

    final class LayerView: UIView {
        var video: AVSampleBufferDisplayLayer? {
            didSet {
                oldValue?.removeFromSuperlayer()
                if let video { layer.addSublayer(video) }
                setNeedsLayout()
            }
        }
        override func layoutSubviews() {
            super.layoutSubviews()
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            video?.frame = bounds
            CATransaction.commit()
        }
    }

    func makeUIView(context: Context) -> LayerView {
        let v = LayerView()
        v.backgroundColor = .black
        v.video = layer
        return v
    }
    func updateUIView(_ v: LayerView, context: Context) {
        if v.video !== layer { v.video = layer }
    }
}
#else
struct VideoLayerView: NSViewRepresentable {
    let layer: AVSampleBufferDisplayLayer

    final class LayerView: NSView {
        var video: AVSampleBufferDisplayLayer? {
            didSet {
                oldValue?.removeFromSuperlayer()
                if let video { layer?.addSublayer(video) }
                needsLayout = true
            }
        }
        override init(frame: NSRect) {
            super.init(frame: frame)
            wantsLayer = true
            layer?.backgroundColor = NSColor.black.cgColor
        }
        required init?(coder: NSCoder) { fatalError() }
        override func layout() {
            super.layout()
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            video?.frame = bounds
            CATransaction.commit()
        }
    }

    func makeNSView(context: Context) -> LayerView {
        let v = LayerView()
        v.video = layer
        return v
    }
    func updateNSView(_ v: LayerView, context: Context) {
        if v.video !== layer { v.video = layer }
    }
}
#endif

// iPhone-only view settings, ignored on the Mac.
extension View {
    /// An address field: URL keyboard, no capitals or autocorrect.
    func addressField() -> some View {
        #if os(iOS)
        keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
        #else
        autocorrectionDisabled()
        #endif
    }
    /// A name or login field: no capitals or autocorrect.
    func plainField() -> some View {
        #if os(iOS)
        textInputAutocapitalization(.never).autocorrectionDisabled()
        #else
        autocorrectionDisabled()
        #endif
    }
    /// A field typed in capitals (the ERASE confirmation).
    func capitalsField() -> some View {
        #if os(iOS)
        textInputAutocapitalization(.characters).autocorrectionDisabled()
        #else
        autocorrectionDisabled()
        #endif
    }
    func inlineNavigationTitle() -> some View {
        #if os(iOS)
        navigationBarTitleDisplayMode(.inline)
        #else
        self
        #endif
    }
    func hideStatusBar(_ hidden: Bool) -> some View {
        #if os(iOS)
        statusBarHidden(hidden)
        #else
        self
        #endif
    }
}

extension View {
    /// Sheets on the Mac get a window-sized frame (on iPhone/iPad they size themselves).
    func macSheetSize() -> some View {
        #if os(macOS)
        frame(minWidth: 620, idealWidth: 680, minHeight: 640, idealHeight: 760)
        #else
        self
        #endif
    }
}

/// Menu-bar commands (Mac), delivered to the viewer.
enum ViewerCommand {
    case cameraMenu, cleanFeed, monitorLUT, grabFrame, localRecording
    case focusMode(AFMode)
}

extension Notification.Name {
    static let viewerCommand = Notification.Name("PyxisViewerCommand")
}

#if os(macOS)
struct ViewerCommands: Commands {
    private func send(_ c: ViewerCommand) { NotificationCenter.default.post(name: .viewerCommand, object: c) }

    var body: some Commands {
        CommandGroup(replacing: .appSettings) {
            Button("Camera Settings…") { send(.cameraMenu) }.keyboardShortcut(",")
        }
        CommandGroup(before: .toolbar) {
            Button("Show or Hide Controls (Clean Feed)") { send(.cleanFeed) }.keyboardShortcut("k")
            Button("Monitor LUT On or Off") { send(.monitorLUT) }.keyboardShortcut("l")
            Divider()
            Button("Capture Frame") { send(.grabFrame) }.keyboardShortcut("s")
            Button("Start or Stop Recording on This Mac") { send(.localRecording) }.keyboardShortcut("r")
            Divider()
        }
        CommandMenu("Focus") {
            ForEach(Array(AFMode.allCases.enumerated()), id: \.offset) { i, m in
                Button(m.name) { send(.focusMode(m)) }.keyboardShortcut(KeyEquivalent(Character("\(i + 1)")))
            }
        }
    }
}
#endif

extension View {
    /// The camera controls drawn over the picture are plain text and icons; on the Mac,
    /// buttons would otherwise get grey bezels.
    func hudButtons() -> some View {
        #if os(macOS)
        buttonStyle(HUDButtonStyle())
        #else
        self
        #endif
    }

    /// A control's tap/click area: a rectangle reaching past what's drawn, so the space around
    /// a setting's text works too.
    func hudHitArea(horizontal: CGFloat, vertical: CGFloat) -> some View {
        padding(.horizontal, horizontal).padding(.vertical, vertical).contentShape(Rectangle())
    }
}

#if os(macOS)
/// Plain buttons on the Mac only respond where something is drawn (between letters is a miss):
/// this one responds anywhere in the button, and dims while pressed.
struct HUDButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .contentShape(Rectangle())
            .opacity(configuration.isPressed ? 0.6 : 1)
    }
}
#endif

enum Platform {
    /// The autofocus mode rail stays on screen with the other controls on the Mac (there's
    /// room, and no edge swipe with a mouse); on iPhone/iPad it's swiped in when needed.
    #if os(macOS)
    static let railAlwaysShown = true
    #else
    static let railAlwaysShown = false
    #endif
}

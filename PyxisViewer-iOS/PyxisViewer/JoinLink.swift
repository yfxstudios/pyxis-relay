import Foundation
#if os(iOS)
import NetworkExtension
#endif

/// The link in the relay's QR code:
///   pyxisviewer://join?ssid=PYXIS-Stream&pass=<Wi-Fi password>&relay=192.168.50.1
/// Scanning it with the Camera app opens this app, which joins the Wi-Fi and plays.
/// (The relay's settings page makes the QR code; see nanopi-relay/router/web/index.html.)
struct JoinLink: Equatable {
    var ssid: String
    var password: String  // empty for an open network
    var relay: String

    init?(url: URL) {
        guard url.scheme?.lowercased() == "pyxisviewer", url.host?.lowercased() == "join",
              let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else { return nil }
        func value(_ k: String) -> String { items.first { $0.name == k }?.value ?? "" }
        ssid = value("ssid")
        password = value("pass")
        relay = value("relay")
        guard !relay.isEmpty, relay.range(of: #"^[A-Za-z0-9.\-:\[\]]+$"#, options: .regularExpression) != nil else { return nil }
    }
}

enum WiFi {
    /// Asks iOS to join the network (the system shows its own "Join?" prompt). The phone
    /// remembers it like any network joined in Settings. Returns nil, or what went wrong.
    static func join(ssid: String, password: String) async -> String? {
        #if targetEnvironment(simulator)
        return nil  // the Simulator uses the Mac's network; there is no Wi-Fi to join
        #elseif os(macOS)
        return "Join the \(ssid) Wi-Fi from the Wi-Fi menu in the menu bar, then try again."
        #else
        let cfg = password.isEmpty
            ? NEHotspotConfiguration(ssid: ssid)
            : NEHotspotConfiguration(ssid: ssid, passphrase: password, isWEP: false)
        cfg.joinOnce = false
        do {
            try await NEHotspotConfigurationManager.shared.apply(cfg)
            return nil
        } catch let e as NSError where e.domain == NEHotspotConfigurationErrorDomain {
            switch NEHotspotConfigurationError(rawValue: e.code) {
            case .alreadyAssociated: return nil
            case .userDenied: return "Joining \(ssid) was cancelled."
            case .invalidWPAPassphrase, .invalidSSID: return "The QR code's Wi-Fi details aren't valid."
            case .pending: return nil
            default: return "Couldn't join \(ssid): \(e.localizedDescription)"
            }
        } catch {
            return "Couldn't join \(ssid): \(error.localizedDescription)"
        }
        #endif
    }
}

extension WiFi {
    /// The relay's name on its Wi-Fi (it announces it over Bonjour/mDNS).
    static let relayName = "pyxis-relay.local"

    /// Whether the relay answers on the network we're on now.
    static func relayReachable(_ relay: String) async -> Bool {
        guard let url = URL(string: "http://\(relay)/cgi-bin/pyxis-camera") else { return false }
        var r = URLRequest(url: url)
        r.timeoutInterval = 1.5
        guard let (_, resp) = try? await URLSession.shared.data(for: r) else { return false }
        return ((resp as? HTTPURLResponse)?.statusCode ?? 0) < 500
    }
}

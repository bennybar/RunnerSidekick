import Aptabase
import Foundation

/// Anonymous app usage (Aptabase): which screens and features are used. Never health data, runs, the server, emails or
/// tokens; event properties are names only. Off in Me: nothing is tracked.
enum Analytics {
    static let key = "share_usage"
    private static let appKey = "A-US-6676968280"
    nonisolated(unsafe) private static var started = false

    private static var enabled: Bool { UserDefaults.standard.object(forKey: key) as? Bool ?? true }

    static func track(_ event: String, _ props: [String: String] = [:]) {
        guard enabled else { return }
        if !started { Aptabase.shared.initialize(appKey: appKey); started = true }
        Aptabase.shared.trackEvent(event, with: props)
    }
}

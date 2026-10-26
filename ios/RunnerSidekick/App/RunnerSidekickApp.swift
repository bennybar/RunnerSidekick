import SwiftUI
import UserNotifications

@main
struct RunnerSidekickApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @State private var store = Store.shared

    #if DEBUG
    // Simulator testing: `SIMCTL_CHILD_RSK_TOKEN=… xcrun simctl launch` signs in with that device token
    init() {
        let env = ProcessInfo.processInfo.environment
        if let t = env["RSK_TOKEN"], !t.isEmpty { Store.shared.setToken(t) }
        // …and RSK_TAB=0-3 / RSK_TRENDS=0-2 / RSK_RUN=<id> open a screen, for screenshots
        if let t = env["RSK_TAB"].flatMap(Int.init).flatMap(AppTab.init(rawValue:)) { Nav.shared.tab = t }
        Nav.shared.trendsTab = env["RSK_TRENDS"].flatMap(Int.init)
        if let r = env["RSK_RUN"] { Nav.shared.open(.run(r), tab: .runs) }
        // RSK_NOTIFY=1: notifications on, with quiet (provisional) permission, so background runs can be tested unattended
        if env["RSK_NOTIFY"] == "1" {
            Store.shared.local.notificationsEnabled = true
            Store.shared.local.save()
            UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .provisional]) { _, _ in }
        }
    }
    #endif

    var body: some Scene {
        WindowGroup {
            AppRoot()
                .environment(store)
                .tint(Palette.primary)
                .preferredColorScheme(store.local.appearance == .light ? .light : store.local.appearance == .dark ? .dark : nil)
                .tint(Palette.primary)
        }
    }
}

/// Background refresh and notification taps.
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        Background.register()
        Background.schedule()  // also when the app is never sent to the background (closed from the switcher, say)
        return true
    }

    /// A tapped notification opens its run or report.
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        let info = response.notification.request.content.userInfo
        await MainActor.run {
            if let run = info["run"] as? String { Nav.shared.open(.run(run), tab: .runs) }
            else if let rep = info["report"] as? Int { Nav.shared.open(.report(rep), tab: .me) }
            else { Nav.shared.tab = .today }
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .list]
    }
}

/// Every page that can be pushed onto a tab.
enum Route: Hashable {
    case run(String)
    case trophies
    case route(String, current: String?)
    case trophy(String)
    case journal
    case report(Int)
    case day(String)
    case readiness, briefing, vo2, race, focus
    case score(String)
    case cardio
    case number(String)
    case insight(String)
}

enum AppTab: Int, CaseIterable {
    case today, runs, trends, me
    var label: String { switch self { case .today: "Today"; case .runs: "Runs"; case .trends: "Trends"; case .me: "Me" } }
    var icon: String { switch self { case .today: "house"; case .runs: "figure.run"; case .trends: "chart.line.uptrend.xyaxis"; case .me: "person" } }
}

/// The tab and each tab's stack of pages, so anything (a notification, a link on Today) can open a page anywhere.
@MainActor
@Observable
final class Nav {
    static let shared = Nav()
    var tab: AppTab = .today
    var paths: [AppTab: [Route]] = [.today: [], .runs: [], .trends: [], .me: []]
    /// Which Trends sub-tab to show when Trends opens (0 Summary, 1 Compare, 2 Charts)
    var trendsTab: Int?

    func open(_ r: Route, tab: AppTab? = nil) {
        if let tab { self.tab = tab }
        paths[self.tab, default: []].append(r)
    }
    func binding(_ t: AppTab) -> Binding<[Route]> {
        Binding(get: { self.paths[t] ?? [] }, set: { self.paths[t] = $0 })
    }
}

struct AppRoot: View {
    @Environment(Store.self) private var store

    var body: some View {
        Group {
            if store.local.hasToken { MainTabs() } else { SignInView() }
        }
        .onOpenURL { url in handle(url) }
    }

    /// The server's Garmin callback page hands Garmin's answer over: finish linking, signed in as this app's user.
    private func handle(_ url: URL) {
        guard url.scheme == "runnersidekick", url.host == "garmin-callback",
              let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems,
              let state = q.first(where: { $0.name == "state" })?.value, let code = q.first(where: { $0.name == "code" })?.value else { return }
        Task {
            let m = await store.attempt { try await store.completeGarmin(state: state, code: code) }
            store.toast = m ?? "Garmin connected"
        }
    }
}

struct MainTabs: View {
    @Environment(Store.self) private var store
    @Environment(\.scenePhase) private var phase
    @State private var nav = Nav.shared
    @State private var garminPrompt = false
    @State private var prompted = false

    var body: some View {
        // The system tab bar: Liquid Glass on iOS 26. Status messages float just above it, on every page.
        TabView(selection: $nav.tab) {
            ForEach(AppTab.allCases, id: \.self) { t in
                Tab(t.label, systemImage: t.icon, value: t) {
                    NavigationStack(path: nav.binding(t)) {
                        root(t).navigationDestination(for: Route.self) { RouteView(route: $0) }
                    }
                    .overlay(alignment: .bottom) { StatusPills().padding(.bottom, 8) }
                }
            }
        }
        .tabBarMinimizeBehavior(.onScrollDown)
        .screenBackground()
        .environment(nav)
        // Signed in without Garmin connected: Connect Garmin opens by itself, once, until it's connected or skipped
        .onChange(of: store.status?.value.garminLinked) { _, _ in promptGarmin() }
        .onAppear { promptGarmin() }
        .fullScreenCover(isPresented: $garminPrompt) {
            GarminConnectView(onSkip: store.status?.value.garminLinked == false ? {
                store.local.garminPromptSkipped = true; store.local.save(); garminPrompt = false
            } : nil, onDone: { garminPrompt = false; nav.tab = .today })
        }
        .onChange(of: phase) { _, p in if p == .background { Background.schedule() } }
    }

    private func promptGarmin() {
        guard let s = store.status?.value, !prompted, !s.garminLinked, !s.synthetic, !store.local.garminPromptSkipped else { return }
        prompted = true
        garminPrompt = true
    }

    @ViewBuilder private func root(_ t: AppTab) -> some View {
        switch t {
        case .today: TodayView()
        case .runs: RunsView()
        case .trends: TrendsView()
        case .me: MeView()
        }
    }
}

/// Pages pushed onto a tab.
struct RouteView: View {
    var route: Route
    var body: some View {
        switch route {
        case .run(let id): RunDetailView(id: id)
        case .trophies: TrophiesView()
        case .route(let id, let current): RoutePageView(routeId: id, current: current)
        case .trophy(let id): TrophyPageView(trophyId: id)
        case .journal: JournalView()
        case .report(let id): ReportView(id: id)
        case .day(let d): DayView(date: d)
        case .readiness: ReadinessPage()
        case .briefing: BriefingPage()
        case .vo2: Vo2Page()
        case .race: RacePage()
        case .focus: FocusPage()
        case .score(let which): ScorePage(which: which)
        case .cardio: CardioPage()
        case .number(let id): NumberPage(id: id)
        case .insight(let id): InsightPage(id: id)
        }
    }
}

/// What a refresh or sync is doing, and one-off messages, just above the tab bar.
struct StatusPills: View {
    @Environment(Store.self) private var store
    var body: some View {
        VStack(spacing: 4) {
            if let p = store.progress {
                HStack(spacing: 8) {
                    ProgressView(value: p.fraction).frame(width: 60)
                    Text("\(p.label) · \(Int(p.fraction * 100))%").font(Typo.labelMedium)
                }
                .padding(.horizontal, 14).padding(.vertical, 8)
                .glassEffect(.regular, in: .capsule)
                if let h = p.hint {
                    Text(h).font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).multilineTextAlignment(.center)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .glassEffect(.regular, in: .rect(cornerRadius: 14))
                        .padding(.horizontal, 48)
                }
            }
            if let t = store.toast {
                Text(t).font(Typo.bodyMedium).foregroundStyle(Palette.onSurface).multilineTextAlignment(.leading)
                    .padding(.horizontal, 18).padding(.vertical, 14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .glassEffect(.regular, in: .rect(cornerRadius: 22))
                    .padding(.horizontal, 16)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .onTapGesture { store.toast = nil }
                    .task(id: t) {
                        try? await Task.sleep(for: .seconds(4))
                        if store.toast == t { withAnimation { store.toast = nil } }
                    }
            }
        }
        .animation(.easeInOut(duration: 0.2), value: store.toast)
        .animation(.easeInOut(duration: 0.2), value: store.progress)
    }
}

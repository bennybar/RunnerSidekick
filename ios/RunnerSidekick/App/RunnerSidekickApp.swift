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
    }
    #endif

    var body: some Scene {
        WindowGroup {
            AppRoot()
                .environment(store)
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
    var iconOn: String { switch self { case .today: "house.fill"; case .runs: "figure.run"; case .trends: "chart.line.uptrend.xyaxis"; case .me: "person.fill" } }
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
        let onRoot = (nav.paths[nav.tab] ?? []).isEmpty
        ZStack(alignment: .bottom) {
            TabView(selection: $nav.tab) {
                ForEach(AppTab.allCases, id: \.self) { t in
                    NavigationStack(path: nav.binding(t)) {
                        root(t).navigationDestination(for: Route.self) { RouteView(route: $0) }
                    }
                    .tag(t)
                    .toolbar(.hidden, for: .tabBar)
                }
            }
            VStack(spacing: 8) {
                StatusPills()
                if onRoot { FloatingNav(selected: $nav.tab) }
            }
            .padding(.bottom, onRoot ? 0 : 12)
            .animation(.easeInOut(duration: 0.2), value: onRoot)
        }
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

/// The tab bar: a centred pill of tabs; the current one fills in with its label (with a little bounce). Lifted and
/// outlined so it reads apart from the tiles behind it. Sliding a finger along it moves from tab to tab.
struct FloatingNav: View {
    @Binding var selected: AppTab
    @Environment(\.colorScheme) private var scheme
    @State private var frames: [AppTab: CGRect] = [:]

    var body: some View {
        HStack(spacing: 6) {
            ForEach(AppTab.allCases, id: \.self) { t in
                let on = selected == t
                Button { select(t) } label: {
                    HStack(spacing: 8) {
                        Image(systemName: on ? t.iconOn : t.icon).font(.system(size: 19, weight: .semibold))
                        if on { Text(t.label).font(Typo.labelLarge).lineLimit(1).fixedSize() }
                    }
                    .foregroundStyle(on ? Palette.onPrimary : Palette.onSurfaceVariant)
                    .padding(.horizontal, on ? 18 : 12)
                    .frame(height: 48)
                    .background(Capsule().fill(on ? Palette.primary : .clear))
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(t.label)
                .accessibilityAddTraits(on ? [.isSelected, .isButton] : .isButton)
                .background(GeometryReader { g in Color.clear.onAppear { frames[t] = g.frame(in: .named("nav")) }
                    .onChange(of: g.frame(in: .named("nav"))) { _, f in frames[t] = f } })
            }
        }
        .padding(.horizontal, 8)
        .frame(height: 64)
        .background(Capsule().fill(scheme == .dark ? Palette.cardHigh : Palette.card))
        .overlay(Capsule().strokeBorder(Palette.outlineVariant, lineWidth: 1))
        .shadow(color: .black.opacity(0.22), radius: 14, y: 4)
        .coordinateSpace(name: "nav")
        .gesture(DragGesture(minimumDistance: 4, coordinateSpace: .named("nav")).onChanged { v in
            // Only switch once the finger is inside another tab, so a tab growing under it can't bounce back
            if let t = frames.first(where: { $0.value.minX <= v.location.x && v.location.x <= $0.value.maxX })?.key, t != selected { select(t) }
        })
        .animation(.spring(response: 0.35, dampingFraction: 0.72), value: selected)
        .padding(.bottom, 8)
    }

    private func select(_ t: AppTab) {
        guard t != selected else {
            Nav.shared.paths[t] = []  // tapping the current tab goes back to its first page
            return
        }
        UISelectionFeedbackGenerator().selectionChanged()
        selected = t
    }
}

/// What a refresh or sync is doing, and one-off messages, just above the tab bar.
struct StatusPills: View {
    @Environment(Store.self) private var store
    var body: some View {
        VStack(spacing: 4) {
            if let p = store.progress {
                Text("\(p.label) · \(Int(p.fraction * 100))%").font(Typo.labelSmall)
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(Capsule().fill(Palette.cardHighest))
                if let h = p.hint {
                    Text(h).font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).multilineTextAlignment(.center)
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .background(RoundedRectangle(cornerRadius: 10).fill(Palette.cardHigh))
                        .padding(.horizontal, 48)
                }
            }
            if let t = store.toast {
                Text(t).font(Typo.bodyMedium).foregroundStyle(Palette.onPrimary).multilineTextAlignment(.leading)
                    .padding(.horizontal, 16).padding(.vertical, 12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Palette.primary))
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

/// Room for the floating tab bar at the bottom of a tab's list: pages scroll underneath it.
extension View {
    func navBarRoom() -> some View { safeAreaPadding(.bottom, 88) }
}

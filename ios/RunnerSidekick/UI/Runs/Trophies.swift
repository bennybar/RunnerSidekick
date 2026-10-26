import SwiftUI

func routeTitle(_ name: String, _ km: Double, _ loop: Bool, _ runs: Int) -> String {
    "\(name) · \(String(format: "%.1f", km)) km\(loop ? " loop" : "") · \(runs) runs"
}

/// Your records: fastest times, longest runs and biggest weeks, heart and fitness bests, steps and streaks. Garmin's
/// all-time records next to the app's own bests, each with where it comes from and how it compares with people of your
/// age and sex where there's a published reference.
struct TrophiesView: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @State private var error: String?

    var body: some View {
        DetailPage(title: "Your records") {
            if let t = store.trophies?.value {
                if t.groups.isEmpty { Footnote(text: "No records yet. They appear once your runs have synced.").padding(.top, 16) }
                ForEach(t.groups) { g in
                    CardGroup(title: g.title, tint: g.id == "fastest" ? .amber : g.id == "longest" ? .orange : .green) {
                        ForEach(g.items) { r in
                            let when = r.date.map { Fmt.shortDate($0) }
                            let meta = [when, r.source.nilIfEmpty].compactMap { $0 }.joined(separator: " · ")
                            GroupRow(headline: r.title, supporting: [meta.nilIfEmpty, r.comparison?.headline].compactMap { $0 }.joined(separator: "\n"),
                                     action: { nav.open(.trophy(r.id)) }) {
                                Text(r.value).font(Typo.titleLarge)
                            }
                        }
                    }
                }
                if let rs = store.routes?.value.routes, !rs.isEmpty {
                    CardGroup(title: "Your routes") {
                        ForEach(rs) { rt in
                            GroupRow(routeTitle(rt.name, rt.distanceKm, rt.loop, rt.runs),
                                     supporting: rt.progress ?? "Run \(rt.runs) times since \(rt.first.map { Fmt.shortDate($0) } ?? "—")") {
                                nav.open(.route(rt.id, current: nil))
                            }
                        }
                    }
                }
                if !t.basis.isEmpty { Footnote(text: t.basis) }
            } else {
                Footnote(text: error ?? "Loading your records…").padding(.top, 16)
            }
        }
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        error = await store.attempt { try await store.refreshTrophies() }
        _ = await store.attempt { try await store.refreshRoutes() }
    }
}

/// One record, as a full page: its value and comparison, and how it got there (each improvement, oldest first; a run opens).
struct TrophyPageView: View {
    var trophyId: String
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav

    var body: some View {
        let r = store.trophies?.value.groups.flatMap(\.items).first { $0.id == trophyId }
        DetailPage(title: r?.title ?? "Record") {
            if let r {
                VStack(alignment: .leading, spacing: 6) {
                    Text(r.value).font(Typo.displayMedium)
                    Text([r.date.map { Fmt.longDate($0) }, r.source.nilIfEmpty].compactMap { $0 }.joined(separator: " · "))
                        .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                    if let c = r.comparison { Text([c.headline, c.detail].compactMap { $0 }.joined(separator: "\n")).font(Typo.bodyMedium) }
                }
                .padding(.horizontal, 12).padding(.top, 8).padding(.bottom, 4)
                if r.history.count >= 2 {
                    Tile(tint: .amber) {
                        Text("How it got here").font(Typo.titleSmall)
                        // Drawn so better is always up (a faster time is a lower number)
                        Sparkline(values: r.history.map { r.lowerIsBetter ? -$0.v : $0.v }, color: Tint.amber.ink,
                                  description: "\(r.title): " + r.history.map { "\($0.value) on \($0.date)" }.joined(separator: ", "))
                            .frame(height: 72)
                    }
                }
                if !r.history.isEmpty {
                    CardGroup {
                        let hist = Array(r.history.reversed())
                        ForEach(Array(hist.enumerated()), id: \.offset) { i, pt in
                            let note: String? = pt.garmin ? "Garmin's record, before the app's history" : i == hist.count - 1 ? "where the history starts" : i == 0 ? "the record now" : nil
                            GroupRow(pt.value, supporting: [Fmt.longDate(pt.date), note].compactMap { $0 }.joined(separator: " · "),
                                     action: pt.sourceId.map { id in { nav.open(.run(id)) } })
                        }
                    }
                }
                if r.history.count < 2 { Footnote(text: "No earlier best in the app's history yet: the next run that beats it shows up here.") }
            }
        }
    }
}

/// The route's shape, drawn from its outline (a unit box, no map): enough to recognise it, or to spot a wrong match.
private struct RouteOutline: View {
    var outline: [[Double]]
    var body: some View {
        Canvas { ctx, size in
            let pad: CGFloat = 12
            let side = min(size.width, size.height) - 2 * pad
            let ox = (size.width - side) / 2, oy = (size.height - side) / 2
            func at(_ p: [Double]) -> CGPoint { CGPoint(x: ox + p[0] * side, y: oy + p[1] * side) }
            var path = Path()
            path.move(to: at(outline[0]))
            outline.dropFirst().forEach { path.addLine(to: at($0)) }
            ctx.stroke(path, with: .color(Tint.blue.ink), style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
            let s = at(outline[0])
            ctx.fill(Path(ellipseIn: CGRect(x: s.x - 6, y: s.y - 6, width: 12, height: 12)), with: .color(Tint.orange.hue))  // where it starts
        }
        .accessibilityLabel("The route's shape")
    }
}

/// A repeat route, as a full page: how it has gone, its runs with their conditions, and how it's recognised.
/// current: the run it was opened from, which can be split off ("this run is a different route").
struct RoutePageView: View {
    var routeId: String
    var current: String?
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let rt = store.routes?.value.routes.first { $0.id == routeId }
        DetailPage(title: rt?.name ?? "Route") {
            if let route = rt {
                Tile(tint: .blue, spacing: 10) {
                    if route.outline.count >= 2 { RouteOutline(outline: route.outline).frame(height: 160) }
                    Text(routeTitle(route.name, route.distanceKm, route.loop, route.runs).components(separatedBy: " · ").dropFirst().joined(separator: " · "))
                        .font(Typo.titleSmall)
                    Text(route.progress ?? "Not enough comparable runs yet: progress needs runs of the same kind, in the same conditions, at a similar heart rate.")
                        .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                }
                CardGroup(title: "Its runs") {
                    ForEach(route.rows.reversed()) { r in
                        let weather = r.temperatureC.map { "\(Int($0.rounded()))°C" + (r.hot == true ? ", hot and humid" : "") } ?? "weather not known"
                        GroupRow(headline: "\(Fmt.pace(r.paceSPerKm, store.units)) · \(r.avgHr.map { "\(Int($0.rounded())) bpm" } ?? "no HR")",
                                 supporting: Fmt.shortDate(r.date) + (r.sourceId == current ? " · this run" : "") + " · " + weather,
                                 action: r.sourceId == current ? nil : { nav.open(.run(r.sourceId)) }) {
                            Text(r.kind == "easy" ? "easy or steady" : r.kind == "hard" ? "harder" : "kind not known").font(Typo.labelMedium)
                                .padding(.horizontal, 10).padding(.vertical, 5)
                                .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Palette.cardHighest))
                        }
                    }
                }
                if let c = current {
                    OutlineButton(title: "This run is a different route") {
                        Task { if let m = await store.attempt({ try await store.differentRoute(c) }) { store.toast = m } else { dismiss() } }
                    }
                }
                if let b = store.routes?.value.basis.nilIfEmpty { Footnote(text: b) }
            }
        }
        .task { if rt == nil { _ = await store.attempt { try await store.refreshRoutes() } } }
    }
}

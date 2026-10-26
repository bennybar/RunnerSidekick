import SwiftUI

/// What a report of type is called.
private func kindOf(_ type: String?) -> String {
    switch type { case "morning": "Morning briefing"; case "post_run": "Run report"; case "weekly": "Weekly review"; default: "Insights update" }
}

/// Reports by month (and check-ins, for people who logged some earlier).
struct JournalView: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @State private var tab = 0
    @State private var busy = false

    var body: some View {
        let checkins = store.myCheckins
        DetailPage(title: "Reports") {
            // The app no longer asks for check-ins; the tab only stays for people who logged some earlier
            if !checkins.isEmpty { ChoiceGroup(labels: ["Reports", "Check-ins"], selected: tab) { tab = $0 } }
            if tab == 0 || checkins.isEmpty {
                if store.journal.isEmpty {
                    EmptyState(icon: "book", title: busy ? "Loading reports" : "No reports yet", message: "Reports appear here after your first sync.")
                }
                let months = Dictionary(grouping: store.journal) { String($0.localDate.prefix(7)) }.sorted { $0.key > $1.key }
                ForEach(months, id: \.key) { month, rs in
                    CardGroup(title: monthTitle(month)) {
                        ForEach(rs) { r in
                            let (icon, shape): (String, BadgeShape) = switch r.type {
                            case "morning": ("sun.max", .sunny)
                            case "post_run": ("figure.run", .cookie9)
                            case "weekly": ("calendar", .cookie12)
                            default: ("lightbulb", .flower)
                            }
                            let kind = kindOf(r.type)
                            GroupRow(r.title ?? kind, overline: "\(kind) · \(Fmt.shortDate(r.localDate))" + (r.revision > 1 ? " · revised" : ""),
                                     icon: icon, shape: shape) { nav.open(.report(r.id)) }
                        }
                    }
                }
            } else {
                CardGroup {
                    ForEach(checkins) { c in
                        let flags = [c.pain ? "Pain" : nil, c.illness ? "Unwell" : nil, c.pendingSync ? "Not uploaded yet" : nil].compactMap { $0 }.joined(separator: " · ")
                        GroupRow("Energy \(c.energy.map(String.init) ?? "–") · Soreness \(c.soreness.map(String.init) ?? "–") · Recovery \(c.recovery.map(String.init) ?? "–")",
                                 supporting: [flags.nilIfEmpty, c.notes].compactMap { $0 }.joined(separator: "\n").nilIfEmpty,
                                 overline: Fmt.shortDate(c.localDate), icon: "square.and.pencil", shape: .cookie4)
                    }
                }
            }
        }
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        busy = true
        defer { busy = false }
        if let m = await store.attempt({ try await store.refreshJournal() }) { store.toast = m }
    }

    private func monthTitle(_ ym: String) -> String {
        guard let d = Fmt.day(ym + "-01") else { return ym }
        let f = DateFormatter(); f.dateFormat = "MMMM yyyy"
        return f.string(from: d)
    }
}

/// Shows a report exactly as generated at the time (its own revision), not recomputed with today's baselines.
struct ReportView: View {
    var id: Int
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @State private var revisions: [RevisionInfo] = []
    @State private var evidence: Finding?
    @State private var loaded = false

    var body: some View {
        let body = store.reportBody(id)
        let keys = body.flatMap { (try? JSONSerialization.jsonObject(with: $0)) as? [String: Any] } ?? [:]
        let type = keys["activity"] != nil ? "post_run" : keys["week_start"] != nil ? "weekly" : keys["recommendation"] != nil ? "morning" : keys["insights"] != nil ? "insights" : nil
        let morning = type == "morning" ? body.flatMap { try? JSON.decode(MorningReport.self, $0) } : nil
        let run = type == "post_run" ? body.flatMap { try? JSON.decode(PostRunReport.self, $0) } : nil
        let ins = type == "insights" ? body.flatMap { try? JSON.decode(InsightsReport.self, $0) } : nil
        let wk = type == "weekly" ? body.flatMap { try? JSON.decode(WeeklyReport.self, $0) } : nil
        let date = morning?.localDate ?? run?.activity.localDate ?? ins?.localDate ?? wk?.weekEnd
        DetailPage(title: type.map { "\(kindOf($0)) · \(date.map { Fmt.shortDate($0) } ?? "")" } ?? "Report") {
            if morning?.synthetic == true || run?.synthetic == true { DemoBadge() }
            if let r = ins {
                Text("Insights as they stood on \(Fmt.shortDate(r.localDate))").font(Typo.titleMedium).padding(.horizontal, 8)
                ForEach(r.insights) { InsightCard(i: $0, emphasised: $0.verdict == "pattern") {} }
            }
            if let w = wk {
                Headline(headline: w.headline, label: "Week of \(Fmt.shortDate(w.weekStart)) – \(Fmt.shortDate(w.weekEnd))", lines: ["Next week: \(w.nextWeekFocus.text)"])
                findings(w.findings)
                Meta(text: "Revision \(w.revision) · generated \(w.generatedAt) · focus rule \(w.nextWeekFocus.rule)")
            }
            if let m = morning {
                Headline(headline: m.headline, lines: [m.recommendation.suggestion, m.recommendation.reason])
                findings(m.findings)
                Meta(text: "Revision \(m.revision) · generated \(m.generatedAt) · data through \(m.dataCutoff ?? "unknown") · \(m.algorithmVersion.values.sorted().joined(separator: ", "))")
            }
            if let r = run {
                Headline(headline: r.activity.name ?? "Run", lines: [r.nextFocus])
                findings(r.findings)
                OutlineButton(title: "Open run details") { nav.open(.run(r.activity.sourceId)) }
                Meta(text: "Revision \(r.revision) · generated \(r.generatedAt)")
            }
            if type == nil || (morning == nil && run == nil && ins == nil && wk == nil) {
                if loaded { EmptyState(icon: "book", title: "Report not cached", message: "Connect to the backend once to save this report for offline reading.") }
                else { ProgressView().frame(maxWidth: .infinity).padding(.top, 32) }
            }
            if revisions.count > 1 {
                CardGroup(title: "Versions") {
                    ForEach(revisions) { v in
                        GroupRow("Revision \(v.revision)" + (v.id == id ? " · showing" : ""),
                                 supporting: "Generated \(v.generatedAt.replacingOccurrences(of: "T", with: " ").replacingOccurrences(of: "Z", with: "")) UTC",
                                 action: v.id == id ? nil : { nav.open(.report(v.id)) })
                    }
                }
            }
        }
        .sheet(item: $evidence) { EvidenceSheet(finding: $0) }
        .task {
            _ = await store.attempt { try await store.loadReport(id) }
            loaded = true
            // Its versions: the journal knows its type and subject; else the body does
            let item = store.journal.first { $0.id == id }
            let subject = item.map { ($0.type, $0.subjectKey) } ?? morning.map { ("morning", $0.localDate) } ?? run.map { ("post_run", $0.activity.sourceId) }
                ?? wk.map { ("weekly", $0.weekStart) } ?? ins.map { ("insights", $0.localDate) }
            if let (t, k) = subject, let v = try? await store.revisions(type: t, key: k) { revisions = v }
        }
    }

    @ViewBuilder private func findings(_ fs: [Finding]) -> some View {
        if !fs.isEmpty { SectionLabel(text: "Findings") }
        ForEach(fs) { f in FindingTile(f: f) { evidence = f } }
    }
}

/// One day's morning briefing, opened from a trend chart. Rendered from the report for that date.
struct DayView: View {
    var date: String
    @Environment(Store.self) private var store
    @State private var busy = true
    @State private var evidence: Finding?

    var body: some View {
        let m = store.day(date)?.value
        DetailPage(title: Fmt.longDate(date)) {
            if let m {
                if m.synthetic { DemoBadge() }
                Headline(headline: m.headline, lines: [m.recommendation.suggestion])
                if !m.findings.isEmpty { SectionLabel(text: "Findings") }
                ForEach(m.findings) { f in FindingTile(f: f) { evidence = f } }
                if let c = m.checkin { Meta(text: "Check-in: energy \(c.energy.map(String.init) ?? "–"), soreness \(c.soreness.map(String.init) ?? "–"), recovery \(c.recovery.map(String.init) ?? "–")") }
                Meta(text: "Report revision \(m.revision) · generated \(m.generatedAt)")
            } else {
                EmptyState(icon: "book", title: busy ? "Loading day" : "Day not cached", message: busy ? "Fetching…" : "Connect to the backend to load this day.")
            }
        }
        .sheet(item: $evidence) { EvidenceSheet(finding: $0, note: m?.note(for: $0.metric)) }
        .task {
            if let msg = await store.attempt({ try await store.refreshDay(date) }) { store.toast = msg }
            busy = false
        }
    }
}

/// The report's headline tile: an optional small label, the headline, then its sentences.
private struct Headline: View {
    var headline: String
    var label: String? = nil
    var lines: [String]
    var body: some View {
        Tile(tint: .purple) {
            if let label { Text(label).font(Typo.labelLarge).foregroundStyle(Tint.purple.ink) }
            Text(headline).font(Typo.headlineSmall)
            ForEach(lines, id: \.self) { Text($0).font(Typo.bodyLarge).foregroundStyle(Palette.onSurfaceVariant) }
        }
    }
}

private struct FindingTile: View {
    var f: Finding
    var onWhy: () -> Void
    var body: some View {
        Tile(spacing: 4) {
            Text(f.title).font(Typo.titleMedium)
            Text(f.statement).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
            LinkButton(title: "Show why", action: onWhy)
        }
    }
}

private struct Meta: View {
    var text: String
    var body: some View { Text(text).font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant).padding(.horizontal, 8) }
}

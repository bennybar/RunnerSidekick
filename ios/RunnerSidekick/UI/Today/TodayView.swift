import SwiftUI

let tileMetrics = ["sleep_duration", "resting_hr", "hrv_overnight_avg", "running_moving_time_7d"]
let tileBadges: [String: (String, BadgeShape)] = [
    "sleep_duration": ("bed.double", .clover4), "resting_hr": ("heart", .heart),
    "hrv_overnight_avg": ("waveform.path.ecg", .softBurst), "running_moving_time_7d": ("figure.run", .cookie6)]
let tileTints: [String: Tint] = ["sleep_duration": .indigo, "resting_hr": .pink, "hrv_overnight_avg": .pink, "running_moving_time_7d": .orange]

/// The time a manual Garmin sync is next allowed, while it's still ahead ("14:30"); nil once it's allowed.
func syncWait(_ nextAllowedAt: String?, now: Date) -> String? {
    guard let at = Fmt.instant(nextAllowedAt), at > now else { return nil }
    return Fmt.clock(iso: nextAllowedAt!)
}

struct TodayView: View {
    @Environment(Store.self) private var store
    @Environment(Nav.self) private var nav
    @State private var busy = false
    @State private var offline = false
    @State private var evidence: Finding?
    @State private var refreshedAt: Date?

    var body: some View {
        let report = store.today?.value
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                Header(busy: busy, offline: offline, onSync: { Task { await sync() } })
                if let r = report { content(r) } else { noReport }
            }
            .padding(.horizontal, 12)
        }
        .refreshable { await refresh() }
        .screenBackground()
        .toolbar(.hidden, for: .navigationBar)
        .sheet(item: $evidence) { f in EvidenceSheet(finding: f, note: store.today?.value.note(for: f.metric)) }
        .task { if refreshedAt == nil { await refresh() } }
    }

    @ViewBuilder private var noReport: some View {
        if busy {
            VStack(spacing: 16) { ProgressView().controlSize(.large); Text("Preparing your briefing…").font(Typo.titleMedium) }
                .frame(maxWidth: .infinity).padding(.top, 96)
        } else {
            EmptyState(icon: "hourglass", title: "No briefing yet", message: "Pull down to refresh, or check the connection in Me.")
        }
    }

    @ViewBuilder private func content(_ r: MorningReport) -> some View {
        if let c = store.status?.value.connection, c.state != "connected" {
            ConnectionNotice(state: c.state, detail: c.detail) { nav.tab = .me }
        }
        // "How am I and what do I do today" first (readiness, then the next run), then the slower health and fitness scores.
        // "Not feeling well" is for the phone's today; until the server has it, the phone applies it itself: rest.
        let todayDate = Fmt.todayISO()
        let unwell = store.myCheckins.first { $0.localDate == todayDate }?.illness == true
        let pending = store.unwellPending
        if let rd = r.readiness {
            ReadinessCard(s: shownReadiness(rd), unwell: unwell, pending: pending,
                          onUnwell: { Task { await store.setUnwell(date: todayDate, on: !unwell) } }) { nav.open(.readiness) }
        }
        if let n = r.nextRun {
            NextRunCard(n: pending ? restRun(n, todayDate) : n, units: store.units)
        }
        if let race = r.race, let w = race.week { RaceWeekStrip(race: race, w: w) { nav.open(.race) } }
        if let f = store.focus?.value { FocusLine(state: f) { nav.open(.focus) } }
        if let sc = r.scores, sc.status == "ok" { ScoresCard(s: sc) { nav.open(.score($0)) } }
        coachTeaser(pending: pending)
        if !r.highlights.isEmpty { StandsOut(items: Array(r.highlights.prefix(3)), onOpen: openHighlight) }
        Readings(r: r, fitness: store.fitness?.value, onOpenVo2: { nav.open(.vo2) }) { evidence = $0 }
        if let n = r.overnight { LastNight(n: n) }
        if let run = r.recentRun { LastRunCard(run: run, units: store.units) { nav.open(.run(run.sourceId)) } }
    }

    /// One readiness as shown, for the card and its page alike: rest while "not feeling well" isn't in the briefing yet
    private func shownReadiness(_ r: Score) -> Score { store.unwellPending ? r.unwellShown : r }

    private func restRun(_ n: NextRun, _ d: String) -> NextRun {
        var x = n
        x.date = d; x.dayLabel = "Today"; x.kind = "rest"; x.title = "Rest or a short walk"; x.distanceKm = nil; x.minutes = nil; x.hr = nil
        x.pace = nil; x.paceSPerKm = nil; x.optional = false; x.caution = nil; x.why = ["you're not feeling well"]
        return x
    }

    @ViewBuilder private func coachTeaser(pending: Bool) -> some View {
        // Coach advice written before "not feeling well" reached the server would contradict the rest above: held back
        if !pending, store.aiEnabled, let c = store.coach?.value {
            let shown: CoachView? = c.status == "ok" ? c : (c.previous?.status == "ok" ? c.previous : nil)
            if let s = shown, let text = s.tldr ?? s.summary {
                // Older advice is labelled as such, so it never reads as current next to a changed briefing
                let note = s !== c ? (c.status == "pending" ? "Updating for today's changes…" : "From an earlier analysis")
                    : "Updated \(Fmt.ago(Fmt.instant(s.generatedAt)))"
                Tile(onTap: { nav.tab = .trends }) {
                    HStack(alignment: .firstTextBaseline) {
                        Text("From your AI coach").font(Typo.titleSmall).frame(maxWidth: .infinity, alignment: .leading)
                        Text(note).font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant).multilineTextAlignment(.trailing)
                    }
                    Text(text).font(Typo.bodyMedium)
                }
            }
        }
    }

    private func openHighlight(_ t: HighlightTarget) {
        switch t.type {
        case "run": if let id = t.id { nav.open(.run(id)) }
        case "compare": nav.trendsTab = 1; nav.tab = .trends
        default: nav.tab = .trends
        }
    }

    private func refresh() async {
        busy = true
        defer { busy = false; refreshedAt = Date() }
        let m = await store.attempt { try await store.refreshAll() }
        offline = m?.hasPrefix("Can't reach") == true
        if let m { store.toast = m }
        store.pollCoach()  // new data changes the evidence, so the coach is asked again
        await Notifier.check(store)
    }

    private func sync() async {
        busy = true
        defer { busy = false }
        if let m = await store.attempt({ try await store.syncNow() }) { store.toast = m }
    }
}

extension Score {
    /// Readiness while "not feeling well" is saved on the phone but not on the server yet: rest.
    var unwellShown: Score {
        var s = self
        s.score = nil; s.label = "Low"; s.headline = "Take it easy or rest"; s.holdReason = "you're not feeling well"; s.allows = "rest"
        return s
    }
}

/// "Today", the briefing's date and when the watch last synced, with the sync button top right.
private struct Header: View {
    var busy: Bool
    var offline: Bool
    var onSync: () -> Void
    @Environment(Store.self) private var store

    var body: some View {
        let status = store.status?.value
        let report = store.today?.value
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Spacer()
                if status?.synthetic == true { DemoBadge() }
                // Garmin syncs at most every 15 minutes (the server's cooldown); the button says when the next one can run
                TimelineView(.periodic(from: .now, by: 30)) { ctx in
                    let wait = syncWait(status?.syncNextAllowedAt, now: ctx.date)
                    PillButton(title: busy ? "Syncing…" : wait.map { "Next sync \($0)" } ?? "Sync Garmin", icon: "arrow.triangle.2.circlepath",
                               filled: false, busy: busy, action: onSync)
                        .disabled(busy || wait != nil)
                }
            }
            .padding(.top, 8)
            VStack(alignment: .leading, spacing: 6) {
                Text("Today").font(Typo.headlineLarge)
                if let d = report?.localDate { Text(Fmt.longDate(d)).font(Typo.bodyLarge).foregroundStyle(Palette.onSurfaceVariant) }
                if let r = report { Freshness(status: status, report: r) }
            }
            .padding(.horizontal, 12).padding(.top, 22).padding(.bottom, 8)
            if offline {
                Label("Offline: showing the briefing saved \(Fmt.ago(store.today?.fetchedAt)).", systemImage: "icloud.slash")
                    .font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant).padding(.horizontal, 16).padding(.vertical, 4)
            }
        }
    }
}

/// The sync line under the date: "Garmin synced 2 h ago", flagged in words and with a warning icon after 12 h.
private struct Freshness: View {
    var status: Status?
    var report: MorningReport
    var body: some View {
        let last = Fmt.instant(status?.connection.lastSuccessAt)
        let stale = last.map { Date().timeIntervalSince($0) >= 12 * 3600 } ?? true
        HStack(spacing: 6) {
            Image(systemName: stale ? "exclamationmark.triangle" : "checkmark.circle").font(.footnote)
                .foregroundStyle(stale ? Tint.orange.ink : Tint.green.ink)
            Text((status?.synthetic == true ? "Demo source synced " : status?.watch == "samsung" ? "Samsung synced " : "Garmin synced ") + Fmt.ago(last)
                 + (report.provisional ? " · last night not in yet" : ""))
                .font(Typo.bodyMedium).foregroundStyle(stale ? Tint.orange.ink : Palette.onSurfaceVariant)
        }
    }
}

private struct ConnectionNotice: View {
    var state: String
    var detail: String?
    var onOpen: () -> Void
    var body: some View {
        let (title, body): (String, String) = switch state {
        case "reauth_required": ("Garmin needs connecting again", "Garmin ended the connection, so syncing is paused. Tap to connect it again in Me.")
        case "rate_limited": ("Garmin asked us to slow down", "Syncing will retry automatically later.")
        case "not_configured": ("Garmin isn't connected", "Tap to connect Garmin in Me and download your runs, sleep and health data.")
        default: ("Last sync failed", detail ?? "Will retry later.")
        }
        Tile(tint: .orange, onTap: onOpen) {
            HStack(spacing: 12) {
                Image(systemName: "link.badge.plus").foregroundStyle(Tint.orange.ink)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Typo.titleSmall)
                    Text(body).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }
}

/// Our own training readiness out of 100, in the green tile: the number, what it means and what holds it back.
struct ReadinessCard: View {
    var s: Score
    var unwell: Bool
    var pending: Bool
    var onUnwell: () -> Void
    var onOpen: () -> Void

    var body: some View {
        Tile(tint: .green, spacing: 10, onTap: onOpen) {
            HStack {
                Text("Readiness").font(Typo.titleSmall).frame(maxWidth: .infinity, alignment: .leading)
                Text("Tap for details").font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
            }
            HStack(alignment: .lastTextBaseline) {
                BigValue(value: s.score.map(String.init) ?? "—", unit: "/100")
                Spacer()
                Text(s.label ?? "Not known yet").font(Typo.titleMedium).multilineTextAlignment(.trailing)
            }
            if let v = s.score { ProgressBar(fraction: Double(v) / 100, fill: Tint.green.hue) }
            if let h = s.headline { Text(h).font(Typo.bodyLarge) }
            // What decided it: the reason for "easy only" when there is one, else the weakest part
            if let why = s.holdReason.map({ (s.allows == "rest" ? "Rest: " : "Easy only: ") + $0 }) ?? s.heldBackBy.map({ "Held back by \($0.lowercased())" }) {
                Text(why).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
            }
            // Context the watch can't see; one tap for the day, tap again to undo. Never asked for.
            Button(action: onUnwell) {
                Text(unwell ? "Not feeling well today · undo" : "Not feeling well?").font(Typo.labelLarge)
                    .foregroundStyle(unwell ? Palette.onPrimary : Palette.onSurface)
                    .padding(.horizontal, 16).frame(minHeight: 40)
                    .background(Capsule().fill(unwell ? Palette.primary : Palette.card.opacity(0.8)))
            }
            .buttonStyle(PressStyle())
            if pending { Text("Saved on your phone; the score updates once it syncs.").font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant) }
        }
        .accessibilityElement(children: .contain)
    }
}

/// The next run in numbers: kind, distance, heart-rate cap, pace and time as chips, with the reason in one line.
private struct NextRunCard: View {
    var n: NextRun
    var units: Units
    var body: some View {
        let dist = n.distanceKm.map { units == .imperial ? String(format: "%.1f mi", $0 / 1.609344) : String(format: "%.1f km", $0) }
        // The pace in the runner's units (the backend's text is per km)
        let pace = n.paceSPerKm.map { p in n.paceWay == "around" ? "around \(Fmt.pace(p, units))" : "about \(Fmt.pace(p, units)) or slower" } ?? n.pace
        let chips = [dist, n.hr?.text, pace, n.minutes.map { "about \($0) min" }].compactMap { $0 }
        Tile(tint: .orange, spacing: 10) {
            HStack(spacing: 6) {
                Text("Next run").font(Typo.titleSmall).frame(maxWidth: .infinity, alignment: .leading)
                if n.optional { TagChip(text: "Optional") }
                TagChip(text: n.dayLabel, container: Tint.orange.hue.opacity(0.30), content: Tint.orange.ink)
            }
            Text(n.title).font(Typo.headlineSmall)
            if !chips.isEmpty { FlowLayout(spacing: 6, lineSpacing: 6) { ForEach(chips, id: \.self) { TagChip(text: $0) } } }
            if let c = n.caution {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle").foregroundStyle(Tint.orange.ink)
                    Text(c).font(Typo.bodyMedium)
                }
                .padding(.horizontal, 12).padding(.vertical, 10)
                .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.card.opacity(0.75)))
            }
            if !n.why.isEmpty { Text(n.why.joined(separator: " · ")).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
        }
    }
}

func daysToGo(_ d: Int) -> String { d > 0 ? "\(d) days" : d == 0 ? "Today" : "Done" }

/// The race week at a glance: one dot per day (done, missed, today, planned, rest) and the week's minutes.
private struct RaceWeekStrip: View {
    var race: RaceStatus
    var w: RaceWeek
    var onOpen: () -> Void
    var body: some View {
        Tile(tint: .amber, spacing: 10, onTap: onOpen) {
            HStack {
                VStack(alignment: .leading) {
                    Text("This week · \(w.phase.replacingOccurrences(of: "_", with: " "))").font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
                    Text(race.title ?? race.headline).font(Typo.titleMedium)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                TagChip(text: daysToGo(race.daysToGo))
            }
            HStack {
                ForEach(w.sessions, id: \.self) { s in
                    let done = ["done", "moved", "extra"].contains(s.status)
                    VStack(spacing: 4) {
                        ZStack {
                            if done { Circle().fill(Palette.primary); Image(systemName: "checkmark").font(.caption.bold()).foregroundStyle(Palette.onPrimary) }
                            else if s.status == "today" { Circle().strokeBorder(Palette.primary, lineWidth: 2) }
                            else if s.status == "missed" { Circle().fill(Tint.pink.hue.opacity(0.18)); Image(systemName: "xmark").font(.caption2.bold()).foregroundStyle(Tint.pink.ink) }
                            else if s.kind == "rest" { Circle().fill(Palette.outlineVariant).frame(width: 6, height: 6) }
                            else { Circle().fill(Palette.card.opacity(0.75)) }
                            if !done && s.kind == "race" { Image(systemName: "trophy").font(.caption).foregroundStyle(Tint.amber.ink) }
                        }
                        .frame(width: 32, height: 32)
                        Text(String(Fmt.weekdayShort(s.date).prefix(1))).font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            if let t = w.targetMinutes, t > 0 {
                ProgressBar(fraction: Double(w.doneMinutes) / Double(t), fill: Tint.amber.hue)
                Text("\(w.doneMinutes) of \(t) min this week").font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }
}

func focusStatusLabel(_ s: String?) -> String {
    switch s {
    case "achieved": "Done"
    case "partly": "Partly"
    case "missed": "Not this time"
    case "over": "Above target"
    case "off_track": "Off track"
    case "unavailable": "Can't measure"
    default: "In progress"
    }
}

/// The focus's status as a chip; "Done" is filled.
struct FocusStatusChip: View {
    var status: String?
    var body: some View {
        if status == "achieved" { TagChip(text: focusStatusLabel(status), container: Palette.primary, content: Palette.onPrimary) }
        else { TagChip(text: focusStatusLabel(status)) }
    }
}

/// This week's focus as one tile with its progress. Tap for the details, or to choose one.
private struct FocusLine: View {
    var state: FocusState
    var onOpen: () -> Void
    var body: some View {
        let cur = state.current
        Tile(tint: .amber, onTap: onOpen) {
            HStack {
                Text("This week's focus").font(Typo.titleSmall).frame(maxWidth: .infinity, alignment: .leading)
                if let c = cur { FocusStatusChip(status: c.status) }
            }
            Text(cur?.title ?? "Choose one").font(Typo.titleMedium)
            if let s = cur?.summary { Text(s).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant).lineLimit(2) }
        }
    }
}

/// Fitness and healthy habits out of 100, as two tinted tiles side by side, each with how it moved in 4 weeks.
private struct ScoresCard: View {
    var s: Scores
    var onOpen: (String) -> Void
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            ScoreTile(title: "Fitness", scope: s.scope["fitness"], horizon: s.horizon["fitness"], sc: s.fitness, tint: .blue) { onOpen("fitness") }
            ScoreTile(title: "Healthy habits", scope: s.scope["health"], horizon: s.horizon["health"], sc: s.health, tint: .purple) { onOpen("health") }
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

private struct ScoreTile: View {
    var title: String
    var scope: String?
    var horizon: String?
    var sc: Score?
    var tint: Tint
    var onOpen: () -> Void

    var body: some View {
        let v = sc?.score
        Tile(tint: tint, spacing: 6, onTap: onOpen) {
            Text(title).font(Typo.titleSmall)
            // The time it looks at, so it's clear why Health, Fitness and readiness move differently
            if let h = horizon { Text(h).font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant) }
            // What the number covers, so Health isn't read as a medical verdict
            Text(scope?.components(separatedBy: ",").first ?? "").font(Typo.labelSmall).foregroundStyle(Palette.onSurfaceVariant)
                .lineLimit(2, reservesSpace: true)
            HStack(spacing: 10) {
                ZStack {
                    Circle().stroke(tint.hue.opacity(0.18), lineWidth: 6)
                    Circle().trim(from: 0, to: CGFloat(min(1, max(0, Double(v ?? 0) / 100))))
                        .stroke(tint.hue, style: StrokeStyle(lineWidth: 6, lineCap: .round)).rotationEffect(.degrees(-90))
                }
                .frame(width: 44, height: 44)
                VStack(alignment: .leading) {
                    Text(v.map(String.init) ?? "—").font(Typo.headlineMedium)
                    Text(sc?.label ?? "Not enough data").font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
                }
            }
            Spacer(minLength: 0)
            // Completeness is shown on its own, never hidden behind the trend
            let t = sc?.trend
            let parts: [String?] = [
                t.map { t in t.delta > 0 ? "↑ \(t.delta) in 4 weeks" : t.delta < 0 ? "↓ \(-t.delta) in 4 weeks" + (t.note != nil ? " · estimate" : "") : "Same as 4 weeks ago" },
                sc?.status == "partial" ? "partial" : nil, sc?.stale == true ? "stale" : nil]
            let line = parts.compactMap { $0 }.joined(separator: " · ")
            Text(line.isEmpty ? (sc?.status == "unavailable" ? "Tap for what's needed" : "Tap for details") : line).font(Typo.labelMedium)
            if let p = sc?.progress, p.verdict != "insufficient" {
                Text("Progress: \(p.verdict)").font(Typo.labelMedium).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
        .frame(maxHeight: .infinity)
    }
}

/// What stands out today: Garmin's verdict, load, new bests, VO2 max movement, focus, comparisons. Attention first.
private struct StandsOut: View {
    var items: [Highlight]
    var onOpen: (HighlightTarget) -> Void
    var body: some View {
        CardGroup(title: "Stands out today") {
            ForEach(items) { h in
                let icon = h.tone == "attention" ? "exclamationmark.triangle" : h.tone == "positive" ? "trophy" : "info.circle"
                let shape: BadgeShape = h.tone == "attention" ? .softBurst : h.tone == "positive" ? .sunny : .cookie4
                let accent = ["attention": "training", "positive": "fitness", "info": "sleep"][h.tone]
                let target = h.target.flatMap { ["run", "compare", "insights", "race"].contains($0.type) ? $0 : nil }
                GroupRow(h.title, supporting: h.text.nilIfEmpty, icon: icon, shape: shape, accent: accent,
                         action: target.map { t in { onOpen(t) } })
            }
        }
    }
}

private func tileValue(_ f: Finding) -> (String, String?) {
    guard let v = f.observed?.value ?? f.last?.value else { return ("—", nil) }
    switch f.metric {
    case "sleep_duration", "running_moving_time_7d": let m = Int((v / 60).rounded()); return (String(format: "%dh %02dm", m / 60, m % 60), nil)
    case "resting_hr": return ("\(Int(v.rounded()))", "bpm")
    default: return ("\(Int(v.rounded()))", "ms")
    }
}

private func tileStatus(_ f: Finding) -> String {
    if f.metric == "running_moving_time_7d" { return f.status == "outside" ? "Well above recent weeks" : "Similar to recent weeks" }
    switch f.status {
    case "learning": return "Learning · \(f.sampleSize ?? 0)/14 days"
    case "not_compared": return "Daytime only · not compared"
    case "missing":
        guard let l = f.last else { return "Not in yet" }
        return l.date == Fmt.addDays(Fmt.todayISO(), -1) ? "Yesterday's" : "From \(Fmt.shortDate(l.date))"
    case "sustained": return "Unusual 3 days running"
    case "outside": return (f.delta?.abs ?? 0) > 0 ? "Above your usual" : "Below your usual"
    default: return f.comparison?.median != nil ? "Usual · \(Fmt.signedDelta(f.metric, f.delta?.abs))" : "Usual"
    }
}

private func dailySeries(_ f: Finding, _ end: String) -> [Double?] {
    let by = Dictionary((f.sparkline ?? []).map { ($0.date, $0.value) }, uniquingKeysWith: { a, _ in a })
    return (0...13).reversed().map { by[Fmt.addDays(end, -$0)] }
}

/// The VO2 max chosen in Settings: Runner Sidekick's (its series), else Garmin's current one, or the watch's latest
func chosenVo2(_ f: Fitness?) -> Double? {
    ((f?.maker == "Runner Sidekick") ? nil : f?.garmin?.vo2max?.value) ?? f?.vo2maxSeries.last?.value
}

private struct Readings: View {
    var r: MorningReport
    var fitness: Fitness?
    var onOpenVo2: () -> Void
    var onTap: (Finding) -> Void

    var body: some View {
        let found = tileMetrics.compactMap { m in r.findings.first { $0.metric == m } }
        let vo2 = chosenVo2(fitness)
        // nil marks the VO2 max tile's slot, right after the overnight readings
        let tiles: [Finding?] = found + (vo2 != nil ? [nil] : [])
        VStack(alignment: .leading, spacing: 10) {
            SectionLabel(text: "Readings")
            ForEach(Array(stride(from: 0, to: tiles.count, by: 2)), id: \.self) { i in
                // An odd last tile (usually VO2 max) takes the whole row
                HStack(alignment: .top, spacing: 10) {
                    ForEach(i..<min(i + 2, tiles.count), id: \.self) { k in
                        if let f = tiles[k] { readingTile(f) } else if let v = vo2 { vo2Tile(v) }
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func readingTile(_ f: Finding) -> some View {
        let (value, unit) = tileValue(f)
        let flagged = f.status == "outside" || f.status == "sustained"
        let d = f.delta?.abs
        let icon: String? = d.map { $0 > 0 ? "arrow.up.right" : $0 < 0 ? "arrow.down.right" : "arrow.right" }
        let tint = tileTints[f.metric] ?? .neutral
        let band = f.comparison.flatMap { c in c.q1.flatMap { a in c.q3.map { (a, $0) } } }
        return MetricTile(label: f.metric == "running_moving_time_7d" ? "Running, 7 days" : f.title, value: value, unit: unit,
                          status: tileStatus(f), statusIcon: icon, flagged: flagged, tint: tint, badge: tileBadges[f.metric], onTap: { onTap(f) }) {
            if !(f.sparkline ?? []).isEmpty {
                Sparkline(values: dailySeries(f, r.localDate), band: band, color: flagged ? Tint.orange.ink : tint.ink, description: "\(f.title), last 14 days")
                    .frame(height: 32)
            }
        }
        .frame(maxHeight: .infinity)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(f.title). \(f.statement)")
    }

    private func vo2Tile(_ v: Double) -> some View {
        let series = fitness?.vo2maxSeries ?? []
        let maker = fitness?.maker ?? "Garmin"
        let old = series.last { $0.date <= Fmt.addDays(r.localDate, -28) }
        let ch = old.map { v - $0.value }
        let status = ch.map { abs($0) < 0.05 ? "Same as 4 weeks ago" : String(format: "%+.1f in 4 weeks", $0) } ?? maker
        let icon: String? = ch.map { $0 > 0.05 ? "arrow.up.right" : $0 < -0.05 ? "arrow.down.right" : "arrow.right" }
        return MetricTile(label: "VO₂ max", value: Fmt.f1(v), unit: nil, status: status, statusIcon: icon, flagged: false, tint: .teal,
                          badge: ("speedometer", .sunny), onTap: onOpenVo2) {
            if series.count >= 2 {
                Sparkline(values: series.suffix(14).map { $0.value }, color: Tint.teal.ink, description: "VO2 max, recent \(maker) readings").frame(height: 32)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("VO2 max \(Fmt.f1(v)), \(maker)")
    }
}

/// The latest run as one tile: when, how long, and distance at pace.
private struct LastRunCard: View {
    var run: RecentRun
    var units: Units
    var onOpen: () -> Void
    var body: some View {
        let pace = Fmt.pace(run.distanceM.flatMap { d in run.movingS.flatMap { d > 0 ? $0 / (d / 1000) : nil } }, units)
        VStack(alignment: .leading, spacing: 10) {
            SectionLabel(text: "Latest run")
            Tile(onTap: onOpen) {
                HStack(spacing: 14) {
                    ShapeBadge(symbol: "figure.run", shape: .cookie9, size: 40, container: Tint.orange.hue.opacity(0.22), content: Tint.orange.ink, iconSize: 20)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("\(Fmt.shortDate(run.localDate)) · \(Fmt.duration(run.movingS))").font(Typo.labelLarge).foregroundStyle(Palette.onSurfaceVariant)
                        Text("\(Fmt.distance(run.distanceM, units)) at \(pace)").font(Typo.titleMedium)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    if let hr = run.avgHr { TagChip(text: "\(Int(hr.rounded())) bpm", container: Tint.pink.hue.opacity(0.16)) }
                }
            }
        }
    }
}

/// Last night with the Samsung watch: context next to the briefing; none of it feeds the suggestion.
private struct LastNight: View {
    var n: Overnight
    var body: some View {
        let learning = "your usual comes after 5 nights"
        let lines: [(String, String)] = [
            n.sleepHr.map { h in ("Sleeping heart rate", "\(Int((h.low ?? h.avg).rounded())) bpm" + (h.delta.map { d in
                abs(d) < 1 ? ", as usual" : ", \(Int(abs(d).rounded())) \(d > 0 ? "above" : "below") your usual" } ?? " · \(learning)")) },
            n.skinTemp.map { s in ("Skin temperature", s.delta.map { d in abs(d) < 0.1 ? "as usual" : String(format: "%+.1f °C vs your usual", d) }
                ?? String(format: "%.1f °C · %@", s.value, learning)) },
            n.spo2.map { o in ("Blood oxygen", "\(Int(o.avg.rounded()))%" + (o.min.map { " (lowest \(Int($0.rounded()))%)" } ?? "")
                + (o.usual.map { u in " · usual \(Int(u[0].rounded()))–\(Int(u[1].rounded()))%" } ?? "")) },
        ].compactMap { $0 }
        let covered = n.asleepS.flatMap { $0 > 0 ? min(1, n.measuredS / $0) : nil }
        VStack(alignment: .leading, spacing: 10) {
            SectionLabel(text: "Last night · Samsung")
            Tile(tint: .indigo, spacing: 10) {
                ForEach(lines, id: \.0) { l in
                    HStack(alignment: .top) {
                        Text(l.0).font(Typo.bodyMedium).frame(maxWidth: .infinity, alignment: .leading)
                        Text(l.1).font(Typo.bodyMedium.weight(.semibold)).multilineTextAlignment(.trailing).frame(maxWidth: .infinity, alignment: .trailing)
                    }
                }
                Text((covered.map { $0 >= 0.9 ? "Measured through the night" : "Measured \(Fmt.duration(n.measuredS)) of \(Fmt.duration(n.asleepS)) asleep, so read it loosely" }
                      ?? "Measured \(Fmt.duration(n.measuredS))") + ". From your Samsung watch; context only, not part of the suggestion. Skin temperature isn't body temperature.")
                    .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }
}

/// "Show why": the evidence behind a finding: value, personal range, sample size, dates, limitations, version.
struct EvidenceSheet: View {
    var finding: Finding
    var note: ReadingNote?
    var body: some View {
        let f = finding
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text(f.title).font(Typo.headlineSmall)
                if let note { NoteBlock(note: note) }
                Text(f.statement).font(Typo.bodyLarge)
                if let i = f.interpretation { Text(i).font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
                Tile(spacing: 6) {
                    if let v = f.observed?.value { row("Observed", Fmt.metricValue(f.metric, v) + (f.observed?.date.map { " on \(Fmt.shortDate($0))" } ?? "")) }
                    if let l = f.observed?.label { row("Garmin status", "\(l) (Garmin)") }
                    if let c = f.comparison {
                        if let m = c.median {
                            row("Your usual (median)", Fmt.metricValue(f.metric, m))
                            if let a = c.q1, let b = c.q3 { row("Typical range (middle 50%)", "\(Fmt.metricValue(f.metric, a)) – \(Fmt.metricValue(f.metric, b))") }
                        }
                        if c.kind == "prior_4_week_weekly_mean", let v = c.value { row("Prior 4-week weekly average", Fmt.metricValue(f.metric, v)) }
                        if let w = c.window, w.count == 2 { row("Compared with", "\(Fmt.shortDate(w[0])) – \(Fmt.shortDate(w[1]))") }
                    }
                    if let d = f.delta?.abs, f.comparison?.median != nil {
                        row("Difference", Fmt.signedDelta(f.metric, d) + (f.delta?.pct.map { String(format: " (%+.0f%%)", $0) } ?? ""))
                    }
                    if let n = f.sampleSize { row("Sample size", "\(n) \(f.category == "running" ? "records" : "days")") }
                    row("Derived", f.derived ? "Yes — calculated by Runner Sidekick" : "No — as reported by the source")
                    row("Algorithm", f.algorithmVersion)
                }
                if !f.limitations.isEmpty {
                    Text("Limitations").font(Typo.titleSmall)
                    ForEach(f.limitations, id: \.self) { Text("• \($0)").font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant) }
                }
            }
            .padding(24)
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .screenBackground()
    }

    private func row(_ l: String, _ v: String) -> some View {
        HStack(alignment: .top) {
            Text(l).foregroundStyle(Palette.onSurfaceVariant).frame(maxWidth: .infinity, alignment: .leading)
            Text(v).frame(maxWidth: .infinity, alignment: .leading)
        }
        .font(Typo.bodyMedium).padding(.vertical, 2)
    }
}

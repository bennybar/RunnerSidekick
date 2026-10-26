import Foundation

/// Display-boundary conversions (the Android app's Format). Storage and API stay in canonical metric units.
enum Fmt {
    private static let mPerMile = 1609.344

    static func distance(_ m: Double?, _ units: Units) -> String {
        guard let m else { return "—" }
        return units == .imperial ? String(format: "%.2f mi", m / mPerMile) : String(format: "%.2f km", m / 1000)
    }

    /// Pace from seconds per km.
    static func pace(_ sPerKm: Double?, _ units: Units) -> String {
        guard let p = sPerKm, p > 0, !p.isNaN, p.isFinite else { return "—" }
        let s = units == .imperial ? p * mPerMile / 1000 : p
        let total = Int(s.rounded())
        return String(format: "%d:%02d %@", total / 60, total % 60, units == .imperial ? "/mi" : "/km")
    }

    static func paceFromSpeed(_ mps: Double?, _ units: Units) -> String { pace(mps.flatMap { $0 > 0 ? 1000 / $0 : nil }, units) }

    static func duration(_ s: Double?) -> String {
        guard let s, s.isFinite else { return "—" }
        let t = Int(s.rounded())
        let h = t / 3600, m = (t % 3600) / 60, sec = t % 60
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, sec) : String(format: "%d:%02d", m, sec)
    }

    static func hoursMinutes(_ s: Double?) -> String {
        guard let s else { return "—" }
        let m = Int((s / 60).rounded())
        return m >= 60 ? String(format: "%d h %02d min", m / 60, m % 60) : "\(m) min"
    }

    static func elevation(_ m: Double?, _ units: Units) -> String {
        guard let m else { return "—" }
        return units == .imperial ? "\(Int((m * 3.28084).rounded())) ft" : "\(Int(m.rounded())) m"
    }

    static func metricValue(_ metric: String, _ v: Double?) -> String {
        guard let v else { return "—" }
        switch metric {
        case "sleep_duration", "running_moving_time_7d": return hoursMinutes(v)
        case "resting_hr": return "\(Int(v.rounded())) bpm"
        case _ where metric.hasPrefix("hrv"): return "\(Int(v.rounded())) ms"
        default: return String(format: "%.0f", v)
        }
    }

    static func signedDelta(_ metric: String, _ d: Double?) -> String {
        guard let d else { return "" }
        return (d > 0 ? "+" : d < 0 ? "−" : "±") + metricValue(metric, abs(d))
    }

    /// Whole-hour, minute and second clock for a duration in seconds ("26:18", "1:52:04").
    static func clock(_ s: Double?) -> String {
        guard let s else { return "—" }
        let t = Int(s)
        return t >= 3600 ? String(format: "%d:%02d:%02d", t / 3600, (t % 3600) / 60, t % 60) : String(format: "%d:%02d", t / 60, t % 60)
    }

    // MARK: Dates

    private static let isoDay: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    static func day(_ iso: String) -> Date? { isoDay.date(from: String(iso.prefix(10))) }
    static func iso(_ d: Date) -> String { isoDay.string(from: d) }
    static func todayISO() -> String { iso(Date()) }

    private static func pattern(_ p: String, _ d: Date, tz: TimeZone = .current) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_GB")
        f.timeZone = tz
        f.dateFormat = p
        return f.string(from: d)
    }

    /// "Monday, 26 October"
    static func longDate(_ iso: String) -> String { day(iso).map { pattern("EEEE, d MMMM", $0) } ?? iso }
    /// "Mon 26 Oct"
    static func shortDate(_ iso: String) -> String { day(iso).map { pattern("EEE d MMM", $0) } ?? iso }
    /// "26 October"
    static func dayMonth(_ iso: String) -> String { day(iso).map { pattern("d MMMM", $0) } ?? iso }
    /// "Monday"
    static func weekdayName(_ iso: String) -> String { day(iso).map { pattern("EEEE", $0) } ?? "" }
    /// "Mon"
    static func weekdayShort(_ iso: String) -> String { day(iso).map { pattern("EEE", $0) } ?? "" }
    static func dayOfMonth(_ iso: String) -> Int { day(iso).map { Calendar.current.component(.day, from: $0) } ?? 0 }

    static func instant(_ iso: String?) -> Date? {
        guard let iso else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: iso) { return d }
        f.formatOptions = [.withInternetDateTime]
        if let d = f.date(from: iso) { return d }
        // Server times without a zone are UTC
        let g = DateFormatter()
        g.locale = Locale(identifier: "en_US_POSIX")
        g.timeZone = TimeZone(identifier: "UTC")
        for p in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss"] {
            g.dateFormat = p
            if let d = g.date(from: iso) { return d }
        }
        return nil
    }

    static func nowISO() -> String { ISO8601DateFormatter().string(from: Date()) }

    /// Activity start in the activity's own offset (not the phone's current zone), so travel history stays true.
    static func activityTime(_ startUtc: String, _ offsetS: Int?) -> String {
        guard let d = instant(startUtc) else { return startUtc }
        let tz = offsetS.flatMap { TimeZone(secondsFromGMT: $0) } ?? .current
        return pattern("EEE d MMM · HH:mm", d, tz: tz)
    }

    /// "14:32" in the phone's time zone, from an ISO instant.
    static func clock(iso: String) -> String { instant(iso).map { pattern("HH:mm", $0) } ?? "" }

    static func ago(_ d: Date?, now: Date = Date()) -> String {
        guard let d else { return "never" }
        let s = now.timeIntervalSince(d)
        if s < 60 { return "just now" }
        if s < 3600 { return "\(Int(s / 60)) min ago" }
        if s < 86400 { return "\(Int(s / 3600)) h ago" }
        return "\(Int(s / 86400)) d ago"
    }

    /// The first day of the week from the backend's setting ("monday" … "sunday"), as Calendar's weekday (1 = Sunday).
    static func weekday(_ name: String?) -> Int {
        ["sunday": 1, "monday": 2, "tuesday": 3, "wednesday": 4, "thursday": 5, "friday": 6, "saturday": 7][(name ?? "monday").lowercased()] ?? 2
    }

    /// The start of the week holding iso, for a week starting on firstWeekday.
    static func weekStart(_ iso: String, _ firstWeekday: Int) -> String {
        guard let d = day(iso) else { return iso }
        let wd = Calendar.current.component(.weekday, from: d)
        let back = (wd - firstWeekday + 7) % 7
        return Fmt.iso(Calendar.current.date(byAdding: .day, value: -back, to: d)!)
    }

    static func addDays(_ iso: String, _ n: Int) -> String {
        guard let d = day(iso) else { return iso }
        return Fmt.iso(Calendar.current.date(byAdding: .day, value: n, to: d)!)
    }
    static func addMonths(_ iso: String, _ n: Int) -> String {
        guard let d = day(iso) else { return iso }
        return Fmt.iso(Calendar.current.date(byAdding: .month, value: n, to: d)!)
    }
    static func daysBetween(_ a: String, _ b: String) -> Int {
        guard let x = day(a), let y = day(b) else { return 0 }
        return Calendar.current.dateComponents([.day], from: x, to: y).day ?? 0
    }

    static func capitalized(_ s: String) -> String { s.prefix(1).uppercased() + s.dropFirst() }
    static func f1(_ v: Double) -> String { String(format: "%.1f", v) }
    static func f0(_ v: Double) -> String { String(format: "%.0f", v) }
}

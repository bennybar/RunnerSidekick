import Foundation
import Security

enum APIError: LocalizedError {
    case notConfigured
    case unauthorized
    /// detail: the server's own explanation ({"detail": "..."}), when it gave one
    case http(Int, String?)
    case network(String)
    /// The backend answered, but the Garmin sync itself didn't finish well (or is still running)
    case sync(String)

    var errorDescription: String? {
        switch self {
        case .notConfigured: return "Backend URL or device token not set"
        case .unauthorized: return "Device token rejected by the backend"
        case .http(let code, let detail): return detail ?? "Backend returned HTTP \(code)"
        case .network(let m): return "Backend unreachable: \(m)"
        case .sync(let d): return d
        }
    }

    /// What a screen says when an action fails (the Android app's wording).
    var userMessage: String {
        switch self {
        case .notConfigured: return "Backend not set up. Open Settings to connect."
        case .unauthorized: return "Your session has ended. Please sign in again."
        case .network: return "Can't reach the backend. Showing saved data."
        case .http(let code, let detail):
            if code == 429 { return "Too many requests. Try again in a minute." }
            if (400..<500).contains(code), let d = detail { return d }
            return "Backend error (\(code)). Showing saved data."
        case .sync(let d): return d
        }
    }
}

/// The server, built in (not a setting), as in the Android release build.
enum Backend {
    static let url = "https://runnersidekick.ibarak.org"
    /// Google sign-in: the iOS OAuth client ID (Google Cloud console → Credentials → iOS client for this bundle id).
    /// Empty until it's created; the sign-in screen then offers the device token only.
    static let googleIOSClientID = "162421419636-rj38evk6329k0es0r4oni08qa7ak0sm3.apps.googleusercontent.com"
}

/// Secrets on this device (the app token, the runner's own OpenAI key), in the Keychain.
enum Keychain {
    private static let service = "com.bennybarak.runnersidekick"

    static func get(_ account: String) -> String? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account, kSecReturnData as String: true]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data else { return nil }
        return String(data: d, encoding: .utf8)
    }

    static func set(_ account: String, _ value: String?) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account]
        SecItemDelete(q as CFDictionary)
        guard let v = value, !v.isEmpty else { return }
        var add = q
        add[kSecValueData as String] = Data(v.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly  // background refresh reads it
        SecItemAdd(add as CFDictionary, nil)
    }
}

/// HTTP to the backend. Returns raw bodies so the caller caches exactly what the server said.
actor API {
    static let shared = API()

    private let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 30
        c.timeoutIntervalForResource = 45  // the whole request, so a slow backend can't hold the radio open
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: c)
    }()

    /// Last body and ETag per GET URL: an unchanged answer comes back as an empty 304 instead of the full JSON
    private var etags: [String: (tag: String, body: Data)] = [:]

    /// Drops the remembered bodies (sign-out, a cleared cache): nothing of one session is answered to the next.
    func forget() { etags.removeAll() }

    func get(_ path: String, query: [String: String] = [:], headers: [String: String] = [:]) async throws -> Data {
        try await call("GET", path, query: query, body: nil, headers: headers)
    }
    func put(_ path: String, _ body: Data) async throws -> Data { try await call("PUT", path, query: [:], body: body) }
    func post(_ path: String, _ body: Data = Data(), headers: [String: String] = [:]) async throws -> Data {
        try await call("POST", path, query: [:], body: body, headers: headers)
    }
    func delete(_ path: String, query: [String: String] = [:]) async throws -> Data { try await call("DELETE", path, query: query, body: nil) }

    /// Unauthenticated POST (sign-in). Returns the HTTP code and body.
    func postPublic(_ path: String, _ body: Data) async throws -> (Int, Data) {
        var req = URLRequest(url: URL(string: Backend.url + path)!)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        return try await send(req)
    }

    /// A GET with an explicit token, before it's saved (to check a device token). (HTTP code, body)
    func getWithToken(_ path: String, token: String) async throws -> (Int, Data) {
        var req = URLRequest(url: URL(string: Backend.url + path)!)
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        return try await send(req)
    }

    private func send(_ req: URLRequest) async throws -> (Int, Data) {
        do {
            let (data, resp) = try await session.data(for: req)
            return ((resp as? HTTPURLResponse)?.statusCode ?? 0, data)
        } catch let e as URLError where e.code == .cancelled {
            throw CancellationError()
        } catch {
            throw APIError.network(error.localizedDescription)
        }
    }

    private func call(_ method: String, _ path: String, query: [String: String], body: Data?, headers: [String: String] = [:]) async throws -> Data {
        guard let token = Keychain.get("device_token") else { throw APIError.notConfigured }
        var comps = URLComponents(string: Backend.url + path)!
        if !query.isEmpty { comps.queryItems = (comps.queryItems ?? []) + query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) } }
        let url = comps.url!
        let key = "\(token.hashValue)|\(url.absoluteString)"
        let known = method == "GET" ? etags[key] : nil
        var req = URLRequest(url: url)
        req.httpMethod = method
        headers.forEach { req.setValue($0.value, forHTTPHeaderField: $0.key) }
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let k = known { req.setValue(k.tag, forHTTPHeaderField: "If-None-Match") }
        if let b = body { req.httpBody = b; req.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let (data, resp): (Data, URLResponse)
        do { (data, resp) = try await session.data(for: req) }
        catch let e as URLError where e.code == .cancelled { throw CancellationError() }
        catch { throw APIError.network(error.localizedDescription) }
        let http = resp as? HTTPURLResponse
        let code = http?.statusCode ?? 0
        if code == 304, let k = known { return k.body }
        if code == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(code) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw APIError.http(code, detail)
        }
        if method == "GET" {
            if let tag = http?.value(forHTTPHeaderField: "ETag") {
                if etags.count >= 200 && etags[key] == nil { etags.removeAll() }  // bounded: many per-run pages add up
                etags[key] = (tag, data)
            } else { etags[key] = nil }
        }
        return data
    }
}

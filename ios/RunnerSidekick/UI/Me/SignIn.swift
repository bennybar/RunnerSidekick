import AuthenticationServices
import CryptoKit
import SwiftUI
import WebKit

/// Google sign-in in a secure browser sheet (OAuth code flow with PKCE, the iOS client ID). Returns Google's ID token,
/// or nil when the runner cancelled.
@MainActor
final class GoogleSignIn: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes.compactMap { ($0 as? UIWindowScene)?.keyWindow }.first ?? ASPresentationAnchor()
    }

    func idToken() async throws -> String? {
        let client = Backend.googleIOSClientID
        let scheme = client.components(separatedBy: ".").reversed().joined(separator: ".")  // the reversed client ID
        let redirect = "\(scheme):/oauth2redirect"
        let verifier = Data((0..<32).map { _ in UInt8.random(in: 0...255) }).base64URL
        let challenge = Data(SHA256.hash(data: Data(verifier.utf8))).base64URL
        let state = UUID().uuidString
        var c = URLComponents(string: "https://accounts.google.com/o/oauth2/v2/auth")!
        c.queryItems = [.init(name: "client_id", value: client), .init(name: "redirect_uri", value: redirect),
                        .init(name: "response_type", value: "code"), .init(name: "scope", value: "openid email profile"),
                        .init(name: "code_challenge", value: challenge), .init(name: "code_challenge_method", value: "S256"),
                        .init(name: "state", value: state), .init(name: "prompt", value: "select_account")]
        let callback: URL? = try await withCheckedThrowingContinuation { cont in
            let s = ASWebAuthenticationSession(url: c.url!, callback: .customScheme(scheme)) { url, error in
                if let e = error as? ASWebAuthenticationSessionError, e.code == .canceledLogin { cont.resume(returning: nil) }
                else if let error { cont.resume(throwing: error) }
                else { cont.resume(returning: url) }
            }
            s.presentationContextProvider = self
            session = s
            s.start()
        }
        guard let url = callback, let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else { return nil }
        guard q.first(where: { $0.name == "state" })?.value == state, let code = q.first(where: { $0.name == "code" })?.value else {
            throw APIError.sync("Google sign-in didn't complete.")
        }
        var req = URLRequest(url: URL(string: "https://oauth2.googleapis.com/token")!)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        let form = ["code": code, "client_id": client, "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier]
        req.httpBody = form.map { "\($0.key)=\($0.value.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? "")" }.joined(separator: "&").data(using: .utf8)
        let (data, _) = try await URLSession.shared.data(for: req)
        guard let token = (try JSONSerialization.jsonObject(with: data) as? [String: Any])?["id_token"] as? String else {
            throw APIError.sync("Google sign-in didn't complete.")
        }
        return token
    }
}

extension Data {
    var base64URL: String {
        base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
}

struct SignInView: View {
    @Environment(Store.self) private var store
    @State private var busy = false
    @State private var error: String?
    @State private var manual = false
    @State private var token = ""
    @State private var google = GoogleSignIn()
    private var googleReady: Bool { !Backend.googleIOSClientID.isEmpty }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                Spacer().frame(height: 72)
                ShapeBadge(symbol: "figure.run", shape: .cookie9, size: 96, container: Tint.orange.hue.opacity(0.22), content: Tint.orange.ink, iconSize: 46)
                Text("Runner Sidekick").font(Typo.headlineLarge).multilineTextAlignment(.center)
                Text("Your Garmin's data, turned into a daily briefing, run analysis and insights you can check.")
                    .font(Typo.bodyLarge).foregroundStyle(Palette.onSurfaceVariant).multilineTextAlignment(.center).padding(.horizontal, 12)
                Spacer().frame(height: 16)
                Tile(padding: EdgeInsets(top: 20, leading: 20, bottom: 20, trailing: 20)) {
                    VStack(spacing: 14) {
                        if busy { ProgressView().controlSize(.large) }
                        Button { Task { await signInGoogle() } } label: {
                            Text("Sign in with Google").font(Typo.titleMedium).foregroundStyle(Palette.onPrimary)
                                .frame(maxWidth: .infinity, minHeight: 56).background(Capsule().fill(Palette.primary))
                        }
                        .buttonStyle(PressStyle()).disabled(!googleReady || busy).opacity(googleReady ? 1 : 0.4)
                        if !googleReady {
                            Text("Google sign-in isn't set up in this build yet. Use a device token below.")
                                .font(Typo.bodySmall).foregroundStyle(Palette.onSurfaceVariant).multilineTextAlignment(.center)
                        }
                        Text("Invite-only for now. Ask the owner to add your Google email.").font(Typo.labelMedium)
                            .foregroundStyle(Palette.onSurfaceVariant).multilineTextAlignment(.center)
                        if let error { Text(error).font(Typo.bodyMedium).foregroundStyle(Palette.error).multilineTextAlignment(.center) }
                        LinkButton(title: manual ? "Hide device token" : "Use a device token instead") { manual.toggle() }
                        if manual {
                            SecureField("Device token (rsk_…)", text: $token)
                                .textInputAutocapitalization(.never).autocorrectionDisabled()
                                .padding(14).background(RoundedRectangle(cornerRadius: 12).strokeBorder(Palette.outline))
                            Button { Task { await connect() } } label: {
                                Text("Connect").font(Typo.labelLarge).foregroundStyle(Palette.onPrimary)
                                    .frame(maxWidth: .infinity, minHeight: 48).background(Capsule().fill(Palette.primary))
                            }
                            .buttonStyle(PressStyle()).disabled(busy || !token.hasPrefix("rsk_")).opacity(token.hasPrefix("rsk_") ? 1 : 0.4)
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .padding(.horizontal, 16).padding(.bottom, 32)
            .frame(maxWidth: 520)
            .frame(maxWidth: .infinity)
        }
        .screenBackground()
        .onAppear { if let n = store.signInNote { error = n; store.signInNote = nil } }
    }

    private func signInGoogle() async {
        busy = true; error = nil
        defer { busy = false }
        do {
            if let id = try await google.idToken() { error = try await store.signInWithGoogle(idToken: id) }
        } catch let e as APIError { error = e.userMessage }
        catch { self.error = "Sign-in didn't complete. Please try again." }
    }

    private func connect() async {
        busy = true; error = nil
        defer { busy = false }
        let t = token.trimmingCharacters(in: .whitespaces)
        do {
            // Checked before it's saved: a token the server rejects is never stored
            error = try await store.checkToken(t)
            if error == nil { store.setToken(t) }
        } catch let e as APIError { error = e.userMessage }
        catch { self.error = "Couldn't connect. Check the token." }
    }
}

// MARK: Garmin

/// Connects Garmin: you sign in on Garmin's own page, here on the phone (your password and any two-factor code go only
/// to Garmin). Garmin answers with a one-time ticket, which is all the app sends to the server; the server turns it into
/// a lasting connection and starts downloading your history. onSkip is nil when there's nothing to skip to.
struct GarminConnectView: View {
    var onSkip: (() -> Void)?
    var onDone: () -> Void
    @Environment(Store.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var linking = false
    @State private var error: String?
    @State private var attempt = 0
    @State private var sent = false

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 8) {
                Text("Sign in on Garmin's page below. Your password goes only to Garmin; Runner Sidekick gets read access to your Garmin data and downloads your history.")
                    .font(Typo.bodyMedium).foregroundStyle(Palette.onSurfaceVariant).padding(.horizontal, 20).padding(.vertical, 8)
                if linking {
                    Tile(spacing: 12) {
                        Text("Connecting to Garmin…").font(Typo.titleMedium).frame(maxWidth: .infinity)
                        ProgressView().frame(maxWidth: .infinity)
                    }.padding(12)
                    Spacer()
                } else if let error {
                    Tile(tint: .orange, spacing: 16) {
                        Text(error).font(Typo.bodyLarge).foregroundStyle(Palette.error)
                        PillButton(title: "Try again") { self.error = nil; sent = false; attempt += 1 }
                    }.padding(12)
                    Spacer()
                } else {
                    GarminWebView(onTicket: submit).id(attempt)
                }
            }
            .screenBackground()
            .navigationTitle("Connect Garmin")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button { dismiss() } label: { Image(systemName: "xmark") } }
                if let onSkip { ToolbarItem(placement: .confirmationAction) { Button("Skip for now", action: onSkip) } }
            }
        }
    }

    private func submit(_ ticket: String) {
        guard !sent else { return }
        sent = true; linking = true; error = nil
        Task {
            if let m = await store.attempt({ try await store.linkGarmin(ticket: ticket) }) { error = m } else { onDone(); dismiss() }
            linking = false
        }
    }
}

/// Garmin's own sign-in page, asked for a ticket for this service (as Garmin's sign-in widget does). A private store: a
/// fresh sign-in each time, and nothing of the Garmin web session stays on the phone.
struct GarminWebView: UIViewRepresentable {
    var onTicket: (String) -> Void

    private static let embed = "https://sso.garmin.com/sso/embed"
    private static var signInURL: URL {
        var c = URLComponents(string: "https://sso.garmin.com/sso/signin")!
        c.queryItems = [("id", "gauth-widget"), ("embedWidget", "true"), ("gauthHost", embed), ("service", embed), ("source", embed),
                        ("redirectAfterAccountLoginUrl", embed), ("redirectAfterAccountCreationUrl", embed)].map { URLQueryItem(name: $0.0, value: $0.1) }
        return c.url!
    }
    /// Garmin's widget is made for a frame on a desktop page: phone-sized fields and buttons (looks only; the form is Garmin's).
    private static let phoneStyle = """
    (function(){ if (document.getElementById('rsk-style')) return;
      var m = document.createElement('meta'); m.name = 'viewport'; m.content = 'width=device-width, initial-scale=1'; document.head.appendChild(m);
      var s = document.createElement('style'); s.id = 'rsk-style';
      s.textContent = 'body{font-family:-apple-system,sans-serif;font-size:17px;padding:8px 16px;margin:0;color:#1b1b1b}' +
        'input[type=email],input[type=text],input[type=password],input[type=tel],input[type=number]{width:100%!important;max-width:none!important;box-sizing:border-box;font-size:18px;padding:14px 12px;margin:6px 0 14px;border:1px solid #8a8a8a;border-radius:10px}' +
        'button,input[type=submit],.btn{width:100%!important;font-size:18px;padding:14px;border-radius:24px;margin-top:8px}' +
        'h1,h2,h3{font-size:22px} label{font-weight:600} form,fieldset,#login-form,.form-group{width:auto!important;max-width:none!important}';
      document.head.appendChild(s); })()
    """

    func makeCoordinator() -> Coordinator { Coordinator(onTicket: onTicket) }

    func makeUIView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .nonPersistent()
        let v = WKWebView(frame: .zero, configuration: cfg)
        v.navigationDelegate = context.coordinator
        v.load(URLRequest(url: Self.signInURL))
        return v
    }
    func updateUIView(_ v: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate {
        let onTicket: (String) -> Void
        private let ticket = try! NSRegularExpression(pattern: "ticket=(ST-[A-Za-z0-9._\\-]{8,300})")
        init(onTicket: @escaping (String) -> Void) { self.onTicket = onTicket }

        private func caught(_ s: String?) -> Bool {
            guard let s, let m = ticket.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)), let r = Range(m.range(at: 1), in: s) else { return false }
            let t = String(s[r])
            DispatchQueue.main.async { self.onTicket(t) }
            return true
        }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction) async -> WKNavigationActionPolicy {
            guard let url = action.request.url else { return .cancel }
            if caught(url.absoluteString) { return .cancel }
            // Only Garmin's own pages load here
            guard let host = url.host, host == "garmin.com" || host.hasSuffix(".garmin.com") else { return .cancel }
            return .allow
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            // The sign-in widget's success page carries the ticket in its own script
            webView.evaluateJavaScript("document.documentElement.outerHTML") { html, _ in _ = self.caught(html as? String) }
            webView.evaluateJavaScript(GarminWebView.phoneStyle)
        }
    }
}

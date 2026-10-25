import SwiftUI

struct CredentialProfile: Decodable, Identifiable, Equatable {
    let id: String
    let service: String
    let label: String
    let kind: String
    var serviceTitle: String { service == "youtube" ? "YouTube" : "CDA" }
}

struct CredentialBrowser: Decodable, Identifiable {
    let id: String
    let status: String
    static let bundleIDs = ["chrome":"com.google.Chrome", "firefox":"org.mozilla.firefox",
                            "edge":"com.microsoft.edgemac", "brave":"com.brave.Browser", "safari":"com.apple.Safari"]
    var title: String { ["chrome":"Google Chrome", "firefox":"Firefox", "edge":"Microsoft Edge", "brave":"Brave", "safari":"Safari"][id] ?? id }
    var supported: Bool { status == "requires_consent" && Self.bundleIDs[id] != nil }
}

@MainActor final class CredentialModel: ObservableObject {
    typealias Request = @MainActor (String, JSONValue) async throws -> JSONValue
    private let request: Request
    @Published private(set) var profiles: [CredentialProfile] = []
    @Published private(set) var browsers: [CredentialBrowser] = []
    @Published private(set) var busy = false
    @Published var message: String?
    @Published private(set) var service = "cda"
    @Published var mode = "password"
    @Published var label = ""
    @Published var username = ""
    @Published var password = ""
    @Published var browser = "firefox"
    @Published var browserProfile = ""
    @Published var consent = false
    private(set) var profileID = UUID().uuidString.lowercased()
    var serviceTitle: String { service == "youtube" ? "YouTube" : "CDA" }
    var hasSavedProfile: Bool { profiles.contains { $0.service == service } }
    var selectedBrowserSupported: Bool { browsers.contains { $0.id == browser && $0.supported } }

    init(request: @escaping Request) { self.request = request }

    func selectService(_ value: String) {
        guard ["cda", "youtube"].contains(value), value != service else { return }
        service = value; mode = value == "cda" ? "password" : "browser"
        profileID = UUID().uuidString.lowercased()
        label = ""; username = ""; password = ""; consent = false; message = nil
    }

    func replace(_ profile: CredentialProfile) {
        selectService(profile.service)
        profileID = profile.id; label = profile.label
        mode = profile.kind == "password" ? "password" : "browser"
        username = ""; password = ""; consent = false; message = nil
    }

    func load() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            try await refreshProfiles()
            let result = try await request("auth.browsers",.object([:]))
            browsers = try result["browsers"].decoded([CredentialBrowser].self)
            if !browsers.contains(where: { $0.id == browser }), let first = browsers.first(where: \.supported) {
                browser = first.id
            }
        } catch { show(error) }
    }

    private func refreshProfiles() async throws {
        let result = try await request("auth.list",.object([:]))
        profiles = try result["profiles"].decoded([CredentialProfile].self)
        if result["reset"].bool == true {
            message = "Nie można odczytać poprzednich danych logowania. Dodaj je ponownie."
        }
    }

    private var baseParams: [String: JSONValue] {
        let title = label.trimmingCharacters(in:.whitespacesAndNewlines)
        return ["id":.string(profileID),"service":.string(service),"label":.string(title.isEmpty ? serviceTitle : title)]
    }

    func savePassword() async {
        guard !busy else { return }
        defer { password = "" }
        guard service == "cda", !username.isEmpty, !password.isEmpty else {
            message = "Podaj login i hasło do CDA."; return
        }
        var params = baseParams
        params["kind"] = .string("password")
        params["secret"] = .object(["username":.string(username),"password":.string(password)])
        await perform("auth.save",params:params)
    }

    func importBrowser() async {
        guard !busy else { return }
        guard consent else { message = "Zaznacz zgodę na odczyt cookies z wybranej przeglądarki.";return }
        var params = baseParams
        params["browser"] = .string(browser);params["consent"] = .bool(true)
        let profile = browserProfile.trimmingCharacters(in:.whitespacesAndNewlines)
        if !profile.isEmpty { params["profile"] = .string(profile) }
        await perform("auth.import_browser",params:params)
    }

    func importText(_ text: String) async {
        guard !busy else { return }
        guard !text.isEmpty, text.utf8.count <= 524_288 else {
            message = "Wybierz niepusty plik cookies w formacie Netscape, nie większy niż 512 KiB.";return
        }
        var params = baseParams;params["text"] = .string(text)
        await perform("auth.import_text",params:params)
    }

    func delete(_ profile: CredentialProfile) async {
        await perform("auth.delete",params:["id":.string(profile.id)],success:"Usunięto zapisane dane logowania.")
    }

    private func perform(_ method: String, params: [String: JSONValue], success: String = "Zapisano dane. Tożsamość i dostęp zostaną sprawdzone podczas pobierania.") async {
        guard !busy else { return }
        busy = true; message = nil
        defer { busy = false }
        do {
            _ = try await request(method,.object(params))
            message = success
            try await refreshProfiles()
        } catch { show(error) }
    }

    func show(_ error: Error) {
        // Never expose arbitrary errors originating in file paths or secret data.
        message = (error as? ClientError)?.errorDescription ?? "Nie udało się wykonać operacji. Spróbuj ponownie."
    }
    func clearSecrets() { password = ""; username = "";consent = false }
}

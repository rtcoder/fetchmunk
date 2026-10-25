import SwiftUI
import AppKit

struct CredentialSettingsView: View {
    @StateObject private var model: CredentialModel
    @Environment(\.dismiss) private var dismiss
    init(request: @escaping CredentialModel.Request) {
        _model = StateObject(wrappedValue:CredentialModel(request:request))
    }
    var body: some View {
        VStack(alignment:.leading,spacing:0) {
            HStack {
                Label("Logowanie do serwisów",systemImage:"lock.shield").font(.title2.bold())
                Spacer()
                Button("Gotowe") { model.clearSecrets(); dismiss() }.keyboardShortcut(.cancelAction).disabled(model.busy)
            }.padding(20)
            Divider()
            ScrollView {
                VStack(alignment:.leading,spacing:20) {
                    Text("Dane są szyfrowane lokalnie. Zapisane hasło lub sesję możesz zastąpić albo usunąć.")
                        .font(.callout).foregroundStyle(.secondary)
                    savedProfiles
                    Divider()
                    editor
                    if let message = model.message {
                        Text(message).font(.callout).foregroundStyle(.secondary)
                            .padding(12).frame(maxWidth:.infinity,alignment:.leading)
                            .background(fetchmunkAccent.opacity(0.08),in:RoundedRectangle(cornerRadius:8))
                            .accessibilityLabel(message)
                    }
                    if model.busy { HStack { ProgressView().controlSize(.small);Text("Oczekiwanie na operację lub zgodę systemu…").font(.caption) } }
                }.padding(20)
            }
        }.frame(width:620).frame(minHeight:480,idealHeight:650,maxHeight:700)
            .task { await model.load() }
            .onDisappear { model.clearSecrets() }
    }
    private var savedProfiles: some View {
        VStack(alignment:.leading,spacing:12) {
            Text("Zapisane dane").font(.headline)
            if model.profiles.isEmpty { Text("Brak zapisanych danych logowania.").foregroundStyle(.secondary).font(.callout) }
            ForEach(model.profiles) { profile in
                HStack(alignment:.top) {
                    Image(systemName:"lock.fill").foregroundStyle(fetchmunkAccent).padding(.top,2)
                    VStack(alignment:.leading,spacing:3) {
                        Text("\(profile.serviceTitle) · \(profile.label)").font(.callout.bold())
                        Text("Zapisano · tożsamość niezweryfikowana · \(profile.kind == "password" ? "hasło" : "cookies")")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Zastąp") { model.replace(profile) }
                    Button("Usuń",role:.destructive) { Task { await model.delete(profile) } }
                }.disabled(model.busy)
            }
        }
    }
    private var editor: some View {
        VStack(alignment:.leading,spacing:14) {
            Text(model.hasSavedProfile ? "Zastąp dane logowania" : "Dodaj dane logowania").font(.headline)
            Picker("Serwis",selection:Binding(get:{model.service},set:{model.selectService($0)})) {
                Text("CDA").tag("cda");Text("YouTube").tag("youtube")
            }.pickerStyle(.segmented)
            TextField("Twoja etykieta (opcjonalnie)",text:$model.label).textFieldStyle(.roundedBorder)
                .help("Możesz wpisać własną nazwę lub e-mail. Fetchmunk nie odczytuje tożsamości konta z cookies.")
            Picker("Sposób",selection:$model.mode) {
                if model.service == "cda" { Text("Login i hasło").tag("password") }
                Text("Z przeglądarki").tag("browser")
                Text("Plik cookies").tag("file")
            }.pickerStyle(.segmented)
                .onChange(of:model.mode) { _ in model.password = ""; model.consent = false }
            if model.mode == "password" {
                TextField("Login lub e-mail CDA",text:$model.username).textFieldStyle(.roundedBorder)
                SecureField("Hasło",text:$model.password).textFieldStyle(.roundedBorder)
                Button(model.hasSavedProfile ? "Zastąp login i hasło" : "Zapisz login i hasło") {
                    Task { await model.savePassword() }
                }.buttonStyle(.borderedProminent).disabled(model.username.isEmpty || model.password.isEmpty)
                Text("Hasło znika z formularza po każdej próbie zapisu.").font(.caption).foregroundStyle(.secondary)
            } else if model.mode == "browser" {
                browserImport
            } else {
                Text("Wybierz plik cookies w formacie Netscape (do 512 KiB). Zapisane zostaną wyłącznie cookies wybranego serwisu.")
                    .font(.callout).foregroundStyle(.secondary)
                Button("Wybierz plik cookies…") { chooseCookieFile() }.buttonStyle(.borderedProminent)
            }
            if model.hasSavedProfile {
                Text("Zapis zastąpi poprzednie dane tego serwisu. Nie zmienia konta w przeglądarce.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.disabled(model.busy)
    }
    private var browserImport: some View {
        VStack(alignment:.leading,spacing:12) {
            if model.browsers.isEmpty {
                Text("Lista przeglądarek jest niedostępna. Możesz użyć pliku cookies.").font(.callout).foregroundStyle(.secondary)
            } else {
                Picker("Przeglądarka",selection:$model.browser) {
                    ForEach(model.browsers) { browser in
                        Text(browser.title + (browser.supported ? "" : " · import niedostępny")).tag(browser.id)
                    }
                }.onChange(of:model.browser) { _ in model.consent = false }
                Button("Otwórz \(model.serviceTitle) w wybranej przeglądarce") { openBrowser() }
                    .disabled(CredentialBrowser.bundleIDs[model.browser] == nil)
                Text("Zaloguj się w tej przeglądarce, a potem wróć i zaimportuj sesję. Otwarcie strony nie importuje danych.")
                    .font(.caption).foregroundStyle(.secondary)
                TextField("Profil przeglądarki (opcjonalnie)",text:$model.browserProfile).textFieldStyle(.roundedBorder)
                    .onChange(of:model.browserProfile) { _ in model.consent = false }
                Toggle(isOn:$model.consent) {
                    Text("Zgadzam się na odczyt cookies z tej przeglądarki. Czytnik może odczytać bazę również dla innych domen, ale Fetchmunk zapisze wyłącznie cookies wybranego serwisu.")
                        .font(.callout).fixedSize(horizontal:false,vertical:true)
                }
                Button("Importuj sesję \(model.serviceTitle)") { Task { await model.importBrowser() } }
                    .buttonStyle(.borderedProminent).disabled(!model.consent || !model.selectedBrowserSupported)
                if !model.selectedBrowserSupported {
                    Text("Szyfrowanie tej przeglądarki nie jest obsługiwane. Wybierz inną przeglądarkę lub plik cookies.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
    }
    private func chooseCookieFile() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false;panel.allowsMultipleSelection = false
        panel.title = "Wybierz plik cookies Netscape"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            // Bound the actual read as well as the size check (file may change).
            let handle = try FileHandle(forReadingFrom:url)
            defer { try? handle.close() }
            let data = try handle.read(upToCount:524_289) ?? Data()
            guard data.count <= 524_288, let text = String(data:data,encoding:.utf8) else {
                model.message = "Plik musi być tekstem UTF-8 i mieć najwyżej 512 KiB.";return
            }
            Task { await model.importText(text) }
        } catch { model.message = "Nie można odczytać wybranego pliku. Sprawdź dostęp i spróbuj ponownie." }
    }
    private func openBrowser() {
        guard let bundleID = CredentialBrowser.bundleIDs[model.browser],
              let app = NSWorkspace.shared.urlForApplication(withBundleIdentifier:bundleID),
              let url = URL(string:model.service == "youtube" ? "https://www.youtube.com/" : "https://www.cda.pl/") else {
            model.message = "Nie znaleziono wybranej przeglądarki. Zainstaluj ją lub wybierz inną.";return
        }
        NSWorkspace.shared.open([url],withApplicationAt:app,configuration:NSWorkspace.OpenConfiguration()) { _, error in
            if error != nil { Task { @MainActor in model.message = "Nie udało się otworzyć wybranej przeglądarki." } }
        }
    }
}

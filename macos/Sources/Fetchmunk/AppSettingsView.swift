import SwiftUI
import AppKit

enum AppAppearance: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }
    var title: String {
        switch self { case .system: return "Jak w systemie";case .light: return "Jasny";case .dark: return "Ciemny" }
    }
    var colorScheme: ColorScheme? {
        switch self { case .system: return nil;case .light: return .light;case .dark: return .dark }
    }
}

enum AppInfo {
    static var version: String { Bundle.main.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String ?? "dev" }
}

struct AppSettingsView: View {
    @ObservedObject var model: AppModel
    @AppStorage("appearance") private var appearance = AppAppearance.system.rawValue
    var body: some View {
        Form {
            Section("Wygląd") {
                Picker("Motyw",selection:$appearance) {
                    ForEach(AppAppearance.allCases) { option in Text(option.title).tag(option.rawValue) }
                }.pickerStyle(.segmented)
            }
            Section("Pobrane pliki") {
                Text(model.destination.path).font(.callout).textSelection(.enabled)
                Button("Zmień katalog…") { model.chooseDestination() }
                Text("Zmiana dotyczy nowych zadań. Pliki z wcześniejszych pobrań pozostają na swoim miejscu.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("O aplikacji") {
                Text("Fetchmunk \(AppInfo.version)")
                Text("Ten build obsługuje publiczne źródła. Logowanie i automatyczne aktualizacje nie są jeszcze dostępne.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Wstrzymanie kolejki zatrzymuje uruchamianie następnych zadań. Aktywny transfer możesz anulować.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.formStyle(.grouped).padding(16).frame(width:510,height:390)
            .preferredColorScheme((AppAppearance(rawValue:appearance) ?? .system).colorScheme)
    }
}

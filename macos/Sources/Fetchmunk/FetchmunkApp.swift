import SwiftUI
@main struct FetchmunkApp: App {
    @NSApplicationDelegateAdaptor(AppLifecycle.self) private var lifecycle
    @StateObject private var model=AppModel()
    @AppStorage("appearance") private var appearance=AppAppearance.system.rawValue
    var body: some Scene {
        WindowGroup {
            MainView(model:model).tint(fetchmunkAccent)
                .preferredColorScheme((AppAppearance(rawValue:appearance) ?? .system).colorScheme)
                .task { lifecycle.model=model;await model.start() }
        }.defaultSize(width:1100,height:820)
            .commands {
                CommandGroup(replacing:.newItem) {
                    Button("Nowe pobranie") { model.addressFocusToken += 1 }.keyboardShortcut("l",modifiers:.command)
                }
                CommandMenu("Pobieranie") {
                    Button("Dodaj wiele linków…") { model.showingBatch = true }
                        .keyboardShortcut("l",modifiers:[.command,.shift]).disabled(!model.batchSupported)
                    Button("Odśwież listę") { Task { await model.refreshHistory() } }
                        .keyboardShortcut("r",modifiers:.command).disabled(!model.ready)
                    Button("Logowanie do serwisów…") { model.showingCredentials = true }.disabled(!model.ready)
                    Button("Katalog pobierania…") { model.chooseDestination() }
                    Divider()
                    Button("Wszystkie") { Task { await model.select("all") } }.keyboardShortcut("1",modifiers:.command)
                    Button("W kolejce") { Task { await model.select("active") } }.keyboardShortcut("2",modifiers:.command)
                    Button("Historia") { Task { await model.select("history") } }.keyboardShortcut("3",modifiers:.command)
                    Button("Ukończone") { Task { await model.select("completed") } }.keyboardShortcut("4",modifiers:.command)
                    Button("Do sprawdzenia") { Task { await model.select("failed") } }.keyboardShortcut("5",modifiers:.command)
                    Button("Anulowane") { Task { await model.select("cancelled") } }.keyboardShortcut("6",modifiers:.command)
                }
            }
        Settings { AppSettingsView(model:model).tint(fetchmunkAccent) }
    }
}

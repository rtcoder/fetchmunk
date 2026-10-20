import SwiftUI
@main struct FetchmunkApp: App {
    @NSApplicationDelegateAdaptor(AppLifecycle.self) private var lifecycle
    @StateObject private var model=AppModel()
    var body: some Scene {
        WindowGroup {
            MainView(model:model).tint(fetchmunkAccent)
                .task { lifecycle.model=model;await model.start() }
        }.defaultSize(width:1000,height:680)
            .commands {
                CommandGroup(replacing:.newItem) {}
                CommandGroup(after:.appInfo) {
                    Button("Katalog pobierania…") { model.chooseDestination() }
                }
            }
    }
}

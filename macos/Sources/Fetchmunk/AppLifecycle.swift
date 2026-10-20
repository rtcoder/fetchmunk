import AppKit
@MainActor final class AppLifecycle: NSObject, NSApplicationDelegate {
    weak var model: AppModel?
    private var quitting=false
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateLater }
        guard let model else { return .terminateNow }
        if model.jobs.contains(where: \.isActive) {
            let alert=NSAlert();alert.messageText="Zatrzymać pobieranie i zakończyć?"
            alert.informativeText="Ukończone pliki zostaną zachowane. Kolejkę możesz kontynuować po ponownym uruchomieniu."
            alert.addButton(withTitle:"Wróć");alert.addButton(withTitle:"Zatrzymaj i zakończ")
            if alert.runModal() != .alertSecondButtonReturn { return .terminateCancel }
        }
        quitting=true
        Task { await model.shutdown();sender.reply(toApplicationShouldTerminate:true) }
        return .terminateLater
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool { false }
    func applicationShouldHandleReopen(_ sender:NSApplication,hasVisibleWindows:Bool)->Bool {
        if !hasVisibleWindows { sender.windows.first?.makeKeyAndOrderFront(nil) };return true
    }
}

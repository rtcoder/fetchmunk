import AppKit
import SwiftUI

struct BatchAddView: View {
    @ObservedObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var pasteMessage: String?
    private var locked: Bool { model.addingBatch || model.hasPendingBatch }
    private var parsed: BatchInput { BatchInput.parse(model.batchDraft) }

    var body: some View {
        VStack(alignment:.leading, spacing:16) {
            Text("Dodaj wiele linków").font(.title2.bold())
            Text("Jeden adres w wierszu · maksymalnie 100 wierszy\nTen build obsługuje publiczne źródła. Logowanie pojawi się później.")
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Text("Adresy HTTP/HTTPS").font(.headline)
                Spacer()
                Button("Wklej") { paste() }.disabled(locked)
                    .accessibilityLabel("Wklej listę adresów ze schowka")
            }
            TextEditor(text:$model.batchDraft)
                .font(.system(.body, design:.monospaced))
                .frame(minHeight:180).disabled(locked)
                .accessibilityLabel("Lista adresów, jeden adres w wierszu")
                .onChange(of:model.batchDraft) { _ in pasteMessage = nil }
                .overlay(RoundedRectangle(cornerRadius:6).stroke(Color.secondary.opacity(0.3)))
            HStack {
                Label("Unikalne adresy: \(parsed.urls.count)", systemImage:"link")
                Spacer()
                Text("Duplikaty: \(parsed.duplicateCount)")
            }.font(.callout).accessibilityElement(children:.combine)
            Label(model.batchDestination.path, systemImage:"folder")
                .font(.caption).lineLimit(2).textSelection(.enabled)
                .accessibilityLabel("Katalog docelowy: \(model.batchDestination.path)")
            if let message = pasteMessage ?? model.batchMessage ?? parsed.errorMessage {
                Text(message).font(.callout).foregroundStyle(fetchmunkAccent)
                    .accessibilityLabel("Komunikat paczki: \(message)")
            }
            if model.hasPendingBatch {
                Text("Wynik poprzedniej próby jest niepewny. Ponów tę samą paczkę, aby ustalić wynik bez dodawania jej drugi raz.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Button("Zamknij") { dismiss() }.keyboardShortcut(.cancelAction).disabled(model.addingBatch)
                Spacer()
                if model.addingBatch { ProgressView().controlSize(.small).accessibilityLabel("Dodawanie paczki") }
                Button(model.hasPendingBatch ? "Ponów paczkę" : "Dodaj do kolejki") {
                    Task { if await model.addBatch(urls:parsed.urls) { dismiss() } }
                }.buttonStyle(.borderedProminent).tint(fetchmunkAccent).keyboardShortcut(.defaultAction)
                    .disabled(!model.ready || !model.batchSupported || model.addingBatch || (!model.hasPendingBatch && !parsed.canSubmit))
            }
        }.padding(24).frame(width:600, height:550)
    }

    private func paste() {
        guard !locked else { return }
        guard let text = NSPasteboard.general.string(forType:.string) else {
            pasteMessage = "Schowek nie zawiera tekstu."; return
        }
        // Bound pasted data before putting it into the editor; permit row separators and surrounding spaces.
        guard text.utf8.count <= BatchInput.maximumURLBytes + 16_384 else {
            pasteMessage = "Tekst w schowku jest zbyt duży. Wklej mniejszą paczkę (do 512 KiB adresów)."; return
        }
        pasteMessage = nil
        model.batchDraft = text
    }
}

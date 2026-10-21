import SwiftUI
import AppKit

struct JobDetailsView: View {
    let job: Job
    @Environment(\.dismiss) private var dismiss
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Szczegóły zadania").font(.title2.bold())
                Spacer()
                Button("Zamknij") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    field("Stan", job.status)
                    field("Identyfikator", job.id)
                    field("Próba", String(job.attempt))
                    field("Utworzono", JobPresentation.date(job.created_at))
                    field("Zaktualizowano", JobPresentation.date(job.updated_at))
                    field("Adres źródłowy", job.url)
                    field("Katalog wynikowy", job.output_dir)
                    if let file = job.current_file { FileProgressView(file: file) }
                    if let error = job.error {
                        Divider()
                        Text(errorMessage(error.code)).foregroundStyle(fetchmunkAccent)
                        Text(JobPresentation.errorHelp(error.code))
                    }
                    Divider()
                    Text("Raport zawiera wyłącznie stan, liczniki i kod błędu. Bez adresów, ścieżek i nazw plików.")
                        .font(.caption).foregroundStyle(.secondary)
                    Text(JobPresentation.diagnosticReport(job)).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                    Button(copied ? "Skopiowano raport" : "Kopiuj raport diagnostyczny") {
                        NSPasteboard.general.clearContents()
                        copied = NSPasteboard.general.setString(JobPresentation.diagnosticReport(job), forType: .string)
                    }.accessibilityLabel("Kopiuj bezpieczny raport diagnostyczny zadania")
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }.padding(24).frame(width: 600, height: 650)
    }
    private func field(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value.isEmpty ? "Brak danych" : value).textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

struct FileProgressView: View {
    let file: FileProgress
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(file.name).font(.caption).textSelection(.enabled)
            if let fraction = JobPresentation.fraction(done: file.bytes_done, total: file.bytes_total) {
                ProgressView(value: fraction).tint(fetchmunkAccent)
                    .accessibilityLabel("Postęp bieżącego pliku")
                    .accessibilityValue("\(Int(fraction * 100)) procent")
            } else {
                ProgressView().controlSize(.small)
                    .accessibilityLabel("Pobieranie bieżącego pliku; rozmiar nieznany")
            }
            HStack {
                Text(JobPresentation.bytes(file.bytes_done) + totalText)
                if let speed = JobPresentation.speed(file.bytes_per_second) { Text("· " + speed) }
            }.font(.caption).foregroundStyle(.secondary).monospacedDigit()
        }
    }
    private var totalText: String {
        guard let total = file.bytes_total, total > 0 else { return " · rozmiar nieznany" }
        return " z " + JobPresentation.bytes(total)
    }
}

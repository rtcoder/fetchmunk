import Foundation

enum JobPresentation {
    static func fraction(done: Int64, total: Int64?) -> Double? {
        guard let total, total > 0 else { return nil }
        return min(1, max(0, Double(done) / Double(total)))
    }
    static func bytes(_ value: Int64) -> String {
        ByteCountFormatter.string(fromByteCount: max(0, value), countStyle: .file)
    }
    static func speed(_ value: Double?) -> String? {
        guard let value, value.isFinite, value >= 0, value < Double(Int64.max) else { return nil }
        return bytes(Int64(value)) + "/s"
    }
    static func parseDate(_ value: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: value) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: value)
    }
    static func date(_ value: String) -> String {
        guard let date = parseDate(value) else { return "Brak danych" }
        return date.formatted(date: .abbreviated, time: .standard)
    }
    static func errorHelp(_ code: String) -> String {
        switch code {
        case "unsupported_url": return "Sprawdź adres materiału. To źródło może nie być obsługiwane przez dołączoną wersję gallery-dl."
        case "auth_required", "auth_expired": return "Źródło wymaga logowania. Ten build nie obsługuje sesji; wybierz publicznie dostępny materiał."
        case "permission_denied": return "Wybierz dostępny katalog w ustawieniach i dodaj zadanie ponownie z nową lokalizacją."
        case "disk_full": return "Zwolnij miejsce na dysku docelowym i użyj przycisku Ponów."
        case "network_error": return "Sprawdź połączenie z internetem i użyj przycisku Ponów."
        case "access_denied": return "Sprawdź, czy materiał jest publiczny i nadal dostępny w serwisie."
        case "dependency_unsupported": return "Ten build nie obsługuje wymaganej funkcji. Sprawdź dostępność nowszego wydania aplikacji."
        default: return "Spróbuj ponownie. Jeśli problem wraca, skopiuj raport diagnostyczny i dołącz go do zgłoszenia błędu."
        }
    }
    // Never serialize Job: every field below is numeric, boolean or a fixed allowlisted enum.
    static func diagnosticReport(_ job: Job) -> String {
        let states: Set<String> = ["queued", "extracting", "downloading", "waiting", "cancelling", "completed", "partial", "empty", "failed", "cancelled", "interrupted", "needs_auth"]
        let codes: Set<String> = ["unsupported_url", "invalid_url", "permission_denied", "disk_full", "auth_required", "auth_expired", "access_denied", "dependency_unsupported", "network_error", "engine_error", "worker_crashed", "download_error", "internal_error"]
        let state = states.contains(job.state) ? job.state : "unknown"
        let code = job.error.map { codes.contains($0.code) ? $0.code : "unknown" } ?? "none"
        return """
        Fetchmunk diagnostics v1
        protocol: 1
        state: \(state)
        attempt: \(job.attempt)
        revision: \(job.revision)
        downloaded: \(job.downloaded)
        skipped: \(job.skipped)
        failed_files: \(job.failed_files)
        error_code: \(code)
        retryable: \(job.error?.retryable ?? false)
        """
    }
}

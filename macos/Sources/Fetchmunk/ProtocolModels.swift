import Foundation

enum JSONValue: Codable, Sendable, Equatable {
    case object([String: JSONValue]), array([JSONValue]), string(String), number(Double), bool(Bool), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let x = try? c.decode(Bool.self) { self = .bool(x) }
        else if let x = try? c.decode(Double.self) { self = .number(x) }
        else if let x = try? c.decode(String.self) { self = .string(x) }
        else if let x = try? c.decode([String: JSONValue].self) { self = .object(x) }
        else { self = .array(try c.decode([JSONValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .object(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
    subscript(_ key: String) -> JSONValue { if case .object(let o) = self { return o[key] ?? .null }; return .null }
    var string: String? { if case .string(let v) = self { return v }; return nil }
    var int: Int? { if case .number(let v) = self, v.isFinite, v >= Double(Int.min), v < Double(Int.max) { return Int(v) }; return nil }
    var bool: Bool? { if case .bool(let v) = self { return v }; return nil }
    var array: [JSONValue] { if case .array(let v) = self { return v }; return [] }
    func decoded<T: Decodable>(_ type: T.Type) throws -> T { try JSONDecoder().decode(type, from: JSONEncoder().encode(self)) }
}

enum ClientError: Error, LocalizedError {
    case protocolError, disconnected, timeout, backend(String), missingBackend
    var errorDescription: String? {
        switch self {
        case .protocolError: return "Nieprawidłowa odpowiedź silnika. Uruchom aplikację ponownie."
        case .disconnected: return "Połączenie z silnikiem zostało przerwane."
        case .timeout: return "Silnik nie odpowiedział na czas. Spróbuj ponownie."
        case .missingBackend: return "Brak dołączonego silnika. Zainstaluj kompletną aplikację."
        case .backend(let code): return errorMessage(code)
        }
    }
}
func errorMessage(_ code: String) -> String {
    switch code {
    case "unsupported_url": return "Ten adres nie jest obsługiwany przez silnik."
    case "invalid_url": return "Wklej poprawny adres HTTP lub HTTPS, bez danych logowania."
    case "permission_denied": return "Brak dostępu do katalogu. Wybierz inną lokalizację."
    case "disk_full": return "Brak miejsca na dysku. Zwolnij miejsce i ponów pobieranie."
    case "auth_required": return "Źródło wymaga logowania. Dodaj dane w oknie Logowanie do serwisów i ponów pobieranie."
    case "auth_expired": return "Sesja wygasła. Zaloguj się ponownie w przeglądarce i zastąp zapisane cookies."
    case "credential_locked": return "Magazyn kluczy jest zablokowany lub odmówiono dostępu. Odblokuj go i ponów operację. Dane pozostały zapisane."
    case "credential_unavailable": return "Nie można uzyskać dostępu do magazynu kluczy lub zapisanych danych. Sprawdź uprawnienia i spróbuj ponownie."
    case "credential_lost": return "Nie można odszyfrować tych danych logowania. Dodaj je ponownie."
    case "invalid_credentials": return "Dane logowania mają nieprawidłowy format. Sprawdź formularz lub wybierz poprawny plik cookies."
    case "browser_consent_required", "consent_required": return "Potwierdź zgodę na odczyt cookies z wybranej przeglądarki."
    case "browser_import_failed", "browser_unavailable": return "Nie udało się zaimportować sesji. Sprawdź przeglądarkę i profil lub użyj pliku cookies."
    case "unsupported_encryption", "browser_unsupported_encryption", "browser_encryption_unsupported": return "Szyfrowanie tej przeglądarki nie jest obsługiwane. Użyj innej przeglądarki lub pliku cookies."
    case "auth_busy": return "Trwa inna operacja poświadczeń. Poczekaj na jej zakończenie i ponów."
    case "credentials_too_large": return "Wybrana sesja jest zbyt duża. Użyj pliku zawierającego tylko cookies tego serwisu."
    case "browser_permission_denied": return "System odmówił dostępu do profilu przeglądarki. Sprawdź uprawnienia lub użyj pliku cookies."
    case "invalid_cookies", "cookies_missing": return "Brak poprawnych cookies wybranego serwisu. Zaloguj się w nim i ponów import."
    case "drm_protected": return "Materiał jest chroniony DRM. Fetchmunk nie obsługuje jego pobierania."
    case "quality_unavailable": return "Wybrana jakość jest niedostępna dla tego materiału. Wybierz inną jakość."
    case "ffmpeg_missing": return "Brakuje składnika do połączenia obrazu i dźwięku. Zainstaluj kompletną aplikację."
    case "access_denied": return "Serwis odmówił dostępu do materiału."
    case "dependency_unsupported": return "Ta funkcja nie jest dostępna w tym buildzie."
    case "already_running": return "Inna instancja Fetchmunk korzysta już z tych danych."
    case "database_error": return "Nie udało się odczytać lub zapisać bazy zadań. Zachowaj dane i uruchom aplikację ponownie."
    case "schema_too_new": return "Dane pochodzą z nowszej wersji Fetchmunk. Zainstaluj nowszą aplikację."
    case "network_error": return "Nie udało się połączyć ze źródłem. Sprawdź sieć i ponów."
    default: return "Nie udało się ukończyć operacji. Możesz spróbować ponownie."
    }
}
struct FrameDecoder {
    private var buffer = Data()
    mutating func feed(_ chunk: Data) throws -> [JSONValue] {
        var messages: [JSONValue] = []
        for byte in chunk {
            buffer.append(byte)
            guard buffer.count <= 1_048_576 else { throw ClientError.protocolError }
            if byte == 10 {
                let value = try JSONDecoder().decode(JSONValue.self, from: buffer)
                guard value["protocol"] == .number(1), value["type"].string != nil else { throw ClientError.protocolError }
                messages.append(value); buffer.removeAll(keepingCapacity: true)
            }
        }
        return messages
    }
    func finish() throws { if !buffer.isEmpty { throw ClientError.protocolError } }
}
struct FileProgress: Codable, Sendable {
    var name: String
    var bytes_done: Int64
    var bytes_total: Int64?
    var bytes_per_second: Double?
}
struct JobError: Codable, Sendable { var code: String; var retryable: Bool; var action: String }
struct Job: Codable, Identifiable, Sendable {
    var job_id: String; var revision: Int; var attempt: Int; var state: String
    var url: String; var display_url: String; var destination: String; var output_dir: String
    var created_at: String; var updated_at: String
    var downloaded: Int; var skipped: Int; var failed_files: Int
    var current_file: FileProgress?; var error: JobError?
    var id: String { job_id }
    var isActive: Bool { ["extracting","downloading","waiting","cancelling"].contains(state) }
    var canRetry: Bool { ["failed","partial","cancelled","interrupted"].contains(state) }
    var canCancel: Bool { isActive || state == "queued" || state == "needs_auth" }
    var host: String { URL(string: display_url)?.host ?? display_url }
    var title: String { URL(string: display_url)?.lastPathComponent.removingPercentEncoding ?? host }
    var status: String {
        ["queued":"W kolejce", "extracting":"Odczytywanie źródła", "downloading":"Pobieranie", "waiting":"Oczekiwanie na serwis", "cancelling":"Zatrzymywanie", "completed":"Ukończono", "partial":"Pobrano częściowo", "empty":"Brak plików", "failed":"Nie udało się pobrać", "cancelled":"Anulowano", "interrupted":"Przerwano", "needs_auth":"Wymagane logowanie"][state] ?? state
    }
}
typealias BackendEvent = JSONValue

struct ChangeBuffer {
    private var ids: Set<String> = []
    private(set) var needsSnapshot = false
    var isEmpty: Bool { ids.isEmpty }
    mutating func insert(_ id:String) {
        guard !needsSnapshot else { return }
        ids.insert(id)
        if ids.count > 1000 { ids.removeAll();needsSnapshot=true }
    }
    mutating func drain() -> Set<String> { let result=ids;ids.removeAll();return result }
    mutating func reset() { ids.removeAll();needsSnapshot=false }
}

import Foundation

/// Validates the original rows before removing exact duplicates.
struct BatchInput {
    static let maximumURLs = 100
    static let maximumURLScalars = 16_384
    static let maximumURLBytes = 512 * 1024
    let urls: [String]
    let duplicateCount: Int
    let invalidLines: [Int]
    let errorMessage: String?
    var canSubmit: Bool { !urls.isEmpty && errorMessage == nil }

    static func parse(_ text: String) -> BatchInput {
        let lines = text.replacingOccurrences(of:"\r\n", with:"\n").components(separatedBy:"\n")
        var urls: [String] = []
        var seen = Set<Data>()
        var invalid: [Int] = []
        var duplicates = 0
        var count = 0
        var bytes = 0
        for (index, line) in lines.enumerated() {
            let url = line.trimmingCharacters(in:.whitespacesAndNewlines)
            guard !url.isEmpty else { continue }
            count += 1
            bytes += url.utf8.count
            guard valid(url) else { invalid.append(index + 1); continue }
            if seen.insert(Data(url.utf8)).inserted { urls.append(url) } else { duplicates += 1 }
        }
        let error: String?
        if count > maximumURLs { error = "Jedna paczka może zawierać najwyżej 100 niepustych wierszy (przed usunięciem duplikatów)." }
        else if bytes > maximumURLBytes { error = "Adresy przekraczają limit 512 KiB UTF-8. Podziel listę na mniejsze paczki." }
        else if !invalid.isEmpty { error = "Popraw adresy w wierszach: \(invalid.map(String.init).joined(separator:", ")). Użyj HTTP/HTTPS, bez danych logowania; limit adresu to 16384 znaki." }
        else { error = nil }
        return BatchInput(urls:urls, duplicateCount:duplicates, invalidLines:invalid, errorMessage:error)
    }

    private static func valid(_ value: String) -> Bool {
        guard value.unicodeScalars.count <= maximumURLScalars,
              !value.unicodeScalars.contains(where: { CharacterSet.whitespacesAndNewlines.contains($0) || CharacterSet.controlCharacters.contains($0) }),
              let components = URLComponents(string:value),
              let scheme = components.scheme?.lowercased(), ["http", "https"].contains(scheme),
              let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil,
              components.url != nil else { return false }
        if let port = components.port, !(0...65535).contains(port) { return false }
        return true
    }
}

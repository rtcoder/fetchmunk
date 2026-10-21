import XCTest
@testable import Fetchmunk

final class BatchInputTests: XCTestCase {
    func testTrimsLFAndCRLFSkipsEmptyAndDeduplicatesExactly() {
        let parsed = BatchInput.parse(" \n https://example.org/a \r\n\r\nhttps://example.org/b\nhttps://example.org/a\nhttps://example.org/A")
        XCTAssertEqual(parsed.urls, ["https://example.org/a", "https://example.org/b", "https://example.org/A"])
        XCTAssertEqual(parsed.duplicateCount, 1)
        XCTAssertTrue(parsed.canSubmit)
    }
    func testReportsOriginalLineNumbersWithoutLeakingInvalidURLs() {
        let parsed = BatchInput.parse("\nhttps://example.org/good\nftp://secret.example/a\nhttps://name:password@example.org/")
        XCTAssertEqual(parsed.invalidLines, [3, 4])
        XCTAssertFalse(parsed.canSubmit)
        XCTAssertFalse(parsed.errorMessage?.contains("secret") ?? true)
        XCTAssertFalse(parsed.errorMessage?.contains("password") ?? true)
    }
    func testLimitsNonemptyRowsBeforeDeduplication() {
        XCTAssertTrue(BatchInput.parse(Array(repeating:"https://example.org/", count:100).joined(separator:"\n")).canSubmit)
        XCTAssertFalse(BatchInput.parse(Array(repeating:"https://example.org/", count:101).joined(separator:"\n")).canSubmit)
    }
    func testScalarLimitIncludesCombiningCharacters() {
        let prefix = "https://example.org/"
        let allowed = prefix + String(repeating:"a", count:16384-prefix.unicodeScalars.count)
        XCTAssertTrue(BatchInput.parse(allowed).canSubmit)
        XCTAssertFalse(BatchInput.parse(allowed + "\u{301}").canSubmit)
    }
    func testUTF8BudgetBeforeDeduplication() {
        let url = "https://example.org/" + String(repeating:"ą", count:9000)
        XCTAssertTrue(BatchInput.parse(Array(repeating:url, count:29).joined(separator:"\n")).canSubmit)
        XCTAssertFalse(BatchInput.parse(Array(repeating:url, count:30).joined(separator:"\n")).canSubmit)
    }
    func testRejectsUnsafeAndMalformedURLs() {
        for url in ["https:///path", "file:///tmp/file", "https://example.org:65536/a", "https://example.org:bad/a", "https://example.org/a b", "https://example.org/a\tb", "https://example.org/a\0b", "https://@example.org/", "https://example.org/a\rb"] {
            XCTAssertFalse(BatchInput.parse(url).canSubmit, "Unexpected acceptance of malformed address")
        }
        XCTAssertTrue(BatchInput.parse("https://example.org:443/a%20b").canSubmit)
        XCTAssertTrue(BatchInput.parse("http://[::1]:8080/a").canSubmit)
    }
    func testCanonicallyEquivalentButByteDistinctURLsRemainSeparate() {
        let composed = "https://example.org/caf\u{e9}.jpg"
        let decomposed = "https://example.org/cafe\u{301}.jpg"
        let result = BatchInput.parse(composed + "\n" + decomposed)
        XCTAssertEqual(result.urls.count, 2)
        XCTAssertEqual(result.duplicateCount, 0)
    }
    func testEmptyInputCannotSubmit() {
        XCTAssertFalse(BatchInput.parse(" \n\r\n\t ").canSubmit)
    }
}

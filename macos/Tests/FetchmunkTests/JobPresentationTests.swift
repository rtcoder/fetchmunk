import XCTest
@testable import Fetchmunk

final class JobPresentationTests: XCTestCase {
    func testProgressClampsAndUnknownTotalsStayUnknown() {
        XCTAssertEqual(JobPresentation.fraction(done: -1, total: 100), 0)
        XCTAssertEqual(JobPresentation.fraction(done: 120, total: 100), 1)
        XCTAssertEqual(JobPresentation.fraction(done: 25, total: 100), 0.25)
        XCTAssertNil(JobPresentation.fraction(done: 10, total: nil))
        XCTAssertNil(JobPresentation.fraction(done: 10, total: 0))
        XCTAssertNil(JobPresentation.fraction(done: 10, total: -1))
        XCTAssertEqual(JobPresentation.fraction(done: Int64.max, total: 1), 1)
    }
    func testSizeAndSpeedRejectInvalidValues() {
        XCTAssertEqual(JobPresentation.bytes(-10), JobPresentation.bytes(0))
        XCTAssertFalse(JobPresentation.bytes(1_000_000).isEmpty)
        for invalid in [-1.0, Double.nan, Double.infinity, -Double.infinity, Double.greatestFiniteMagnitude] {
            XCTAssertNil(JobPresentation.speed(invalid))
        }
        XCTAssertNil(JobPresentation.speed(nil))
        XCTAssertNotNil(JobPresentation.speed(0))
        XCTAssertNotNil(JobPresentation.speed(1024))
    }
    func testDatesAndMissingOptionalData() {
        XCTAssertNotNil(JobPresentation.parseDate("2026-10-21T12:34:56Z"))
        XCTAssertNotNil(JobPresentation.parseDate("2026-10-21T12:34:56.123456+00:00"))
        XCTAssertNil(JobPresentation.parseDate("not-a-date"))
        XCTAssertEqual(JobPresentation.date(""), "Brak danych")
        XCTAssertEqual(JobPresentation.date("not-a-date"), "Brak danych")
        let report = JobPresentation.diagnosticReport(Job.example(id: "j", revision: 1, state: "completed"))
        XCTAssertTrue(report.contains("error_code: none"))
    }
    func testDiagnosticAllowlistExcludesUntrustedText() {
        let secret = "https://secret.example/private?token=SECRET /Users/private/file.jpg"
        var job = Job.example(id: secret, revision: 7, state: "failed")
        job.url=secret; job.display_url=secret; job.destination=secret; job.output_dir=secret
        job.created_at=secret; job.updated_at=secret
        job.current_file=FileProgress(name:secret, bytes_done:15, bytes_total:100, bytes_per_second:12)
        job.error=JobError(code:secret, retryable:true, action:secret)
        let report=JobPresentation.diagnosticReport(job)
        for forbidden in ["SECRET", "https:", "/Users", "file.jpg", "private", "token"] {
            XCTAssertFalse(report.contains(forbidden), report)
        }
        XCTAssertTrue(report.contains("state: failed"))
        XCTAssertTrue(report.contains("revision: 7"))
        XCTAssertTrue(report.contains("error_code: unknown"))
        job.state=secret
        XCTAssertTrue(JobPresentation.diagnosticReport(job).contains("state: unknown"))
    }
    func testActualEngineErrorCodesRemainUsefulInReport() {
        for code in ["engine_error", "disk_full", "permission_denied", "unsupported_url"] {
            var job = Job.example(id: "j", revision: 1, state: "failed")
            job.error = JobError(code: code, retryable: true, action: "retry")
            XCTAssertTrue(JobPresentation.diagnosticReport(job).contains("error_code: " + code))
        }
    }
    func testErrorHelpUsesKnownCodesRatherThanBackendActionText() {
        XCTAssertTrue(JobPresentation.errorHelp("auth_required").contains("logowania"))
        XCTAssertTrue(JobPresentation.errorHelp("disk_full").contains("miejsce"))
        XCTAssertFalse(JobPresentation.errorHelp("SECRET").contains("SECRET"))
    }
}

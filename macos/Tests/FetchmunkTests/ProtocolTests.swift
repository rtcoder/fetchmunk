import XCTest
@testable import Fetchmunk
final class ProtocolTests: XCTestCase {
    func testChunkedUnicodeAndMultipleFrames() throws {
        var decoder = FrameDecoder()
        let input = Data("{\"protocol\":1,\"type\":\"event\",\"name\":\"żółć\\n\"}\n".utf8)
        var messages: [JSONValue] = []
        for byte in input + input { messages += try decoder.feed(Data([byte])) }
        XCTAssertEqual(messages.count, 2)
        XCTAssertEqual(messages[0]["name"].string, "żółć\n")
    }
    func testRejectsInvalidVersionAndOversizedFrames() {
        var decoder = FrameDecoder()
        XCTAssertThrowsError(try decoder.feed(Data("{\"protocol\":true,\"type\":\"event\"}\n".utf8)))
        decoder = FrameDecoder()
        XCTAssertThrowsError(try decoder.feed(Data(repeating: 32, count: 1_048_577)))
    }
    func testTruncatedEOF() throws {
        var decoder = FrameDecoder(); _ = try decoder.feed(Data("{".utf8))
        XCTAssertThrowsError(try decoder.finish())
    }
    @MainActor func testOldRevisionCannotReplaceNewJob() throws {
        let model = AppModel()
        let first = Job.example(id: "j", revision: 3, state: "completed")
        model.apply(first)
        model.apply(Job.example(id: "j", revision: 2, state: "downloading"))
        XCTAssertEqual(model.jobs.first?.state, "completed")
    }
}
extension Job {
    static func example(id: String, revision: Int, state: String) -> Job {
        Job(job_id:id, revision:revision, attempt:1, state:state, url:"https://example.org/a.png", display_url:"https://example.org/a.png", destination:"/tmp", output_dir:"/tmp/out", created_at:"", updated_at:"", downloaded:0, skipped:0, failed_files:0, current_file:nil, error:nil)
    }
}

final class ChangeBufferTests: XCTestCase {
    func testRepeatedChangesCoalesceAndOverflowRequestsSnapshot() {
        var buffer=ChangeBuffer()
        for _ in 0..<1001 { buffer.insert("same") }
        XCTAssertEqual(buffer.drain(),Set(["same"]))
        XCTAssertFalse(buffer.needsSnapshot)
        for i in 0..<1001 { buffer.insert(String(i)) }
        XCTAssertTrue(buffer.needsSnapshot)
        XCTAssertTrue(buffer.drain().isEmpty)
    }
}

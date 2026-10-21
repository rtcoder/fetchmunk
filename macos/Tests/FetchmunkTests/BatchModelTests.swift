import XCTest
@testable import Fetchmunk

actor BatchBackend: BackendConnection {
    nonisolated let events = AsyncStream<BackendEvent> { _ in }
    var batches: [JSONValue] = []
    var inspection: CheckedContinuation<JSONValue, Error>?
    var waiting: CheckedContinuation<Void, Never>?
    func start(executableURL: URL) async throws {}
    func shutdown() async throws {}
    func waitForInspection() async {
        if inspection != nil { return }
        await withCheckedContinuation { waiting = $0 }
    }
    func releaseInspection() {
        inspection?.resume(returning:.object(["supported":.bool(true),"category":.string("old")]))
        inspection = nil
    }
    func request(method: String, params: JSONValue) async throws -> JSONValue {
        if method == "jobs.create_many" {
            batches.append(params)
            if batches.count == 1 { throw ClientError.disconnected }
            return .object(["created_count":.number(1),"jobs":.array([.object(["job_id":.string("one"),"revision":.number(1)])])])
        }
        if method == "sources.inspect" {
            return try await withCheckedThrowingContinuation { inspection = $0; waiting?.resume(); waiting = nil }
        }
        if method == "jobs.summary" { return .object(["at_seq":.number(0),"current_job":.null]) }
        return try json(historyPage([]))
    }
}
final class BatchModelTests: XCTestCase {
    @MainActor func testRetryPreservesOperationURLsAndDestination() async {
        let backend = BatchBackend(); let model = AppModel(client:backend)
        model.ready = true; model.batchSupported = true
        model.destination = URL(fileURLWithPath:"/tmp/original")
        model.batchDraft = "https://example.org/a.jpg"
        let first = await model.addBatch(urls:[model.batchDraft])
        XCTAssertFalse(first); XCTAssertTrue(model.hasPendingBatch)
        model.destination = URL(fileURLWithPath:"/tmp/changed")
        XCTAssertEqual(model.batchDestination.path,"/tmp/original")
        let second = await model.addBatch(urls:["https://example.org/different.jpg"])
        XCTAssertTrue(second); XCTAssertFalse(model.hasPendingBatch); XCTAssertEqual(model.batchDraft,"")
        let batches = await backend.batches
        XCTAssertEqual(batches.count,2); XCTAssertEqual(batches[0],batches[1])
    }
    @MainActor func testEditingAddressInvalidatesLateInspection() async {
        let backend = BatchBackend(); let model = AppModel(client:backend)
        model.ready = true; model.sourceInspectionSupported = true
        model.inputURL = "https://example.org/a.jpg"
        let task = Task { await model.inspectSource() }
        await backend.waitForInspection()
        model.inputURL = "https://example.org/b.jpg"
        await backend.releaseInspection(); await task.value
        XCTAssertNil(model.inspectionMessage); XCTAssertFalse(model.inspecting)
    }
    @MainActor func testUnavailableBatchDoesNotSendRequest() async {
        let backend = BatchBackend(); let model = AppModel(client:backend)
        model.ready = true
        let result = await model.addBatch(urls:["https://example.org/a.jpg"])
        XCTAssertFalse(result)
        let batches = await backend.batches; XCTAssertTrue(batches.isEmpty)
    }
}

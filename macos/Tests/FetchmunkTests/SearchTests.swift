import XCTest
@testable import Fetchmunk

actor SearchBackend: BackendConnection {
    nonisolated let events = AsyncStream<BackendEvent> { _ in }
    var seen: [JSONValue] = []
    var slow: CheckedContinuation<JSONValue, Error>?
    var waiting: CheckedContinuation<Void, Never>?
    func start(executableURL: URL) async throws {}
    func shutdown() async throws {}
    func waitForSlowRequest() async {
        if slow != nil { return }
        await withCheckedContinuation { waiting = $0 }
    }
    func release() throws {
        slow?.resume(returning: try json(historyPage([.example(id:"old",revision:1,state:"completed")])));slow=nil
    }
    func request(method: String, params: JSONValue) async throws -> JSONValue {
        seen.append(params)
        if params["cursor"].string == "expired" { throw ClientError.backend("snapshot_expired") }
        if params["query"].string == "slow" {
            return try await withCheckedThrowingContinuation { slow=$0;waiting?.resume();waiting=nil }
        }
        return try json(historyPage([.example(id:params["query"].string ?? "missing",revision:1,state:"completed")],next:"expired"))
    }
}

final class SearchTests: XCTestCase {
    func testQueryChangeDropsOldPageAndCursors() throws {
        var h=HistoryState()
        let first=h.begin(filter:"history",query:"old")
        _ = try h.accept(historyPage([.example(id:"old",revision:1,state:"completed")],next:"oldcursor"),token:first)
        let second=h.begin(filter:"history",query:"new")
        XCTAssertTrue(h.jobs.isEmpty);XCTAssertNil(h.nextCursor)
        XCTAssertFalse(try h.accept(historyPage([.example(id:"late",revision:1,state:"completed")]),token:first))
        XCTAssertTrue(try h.accept(historyPage([]),token:second))
        XCTAssertEqual(h.query,"new")
    }
    @MainActor func testOldSearchReplyCannotReplaceNewSearch() async throws {
        let backend=SearchBackend();let model=AppModel(client:backend)
        model.searchInput="slow"
        let old=Task { await model.search() }
        await backend.waitForSlowRequest()
        model.searchInput="new";await model.search()
        try await backend.release();await old.value
        XCTAssertEqual(model.history.query,"new")
        XCTAssertEqual(model.jobs.map(\.id),["new"])
    }
    @MainActor func testQueryPersistsAcrossFiltersExpiryAndClear() async {
        let backend=SearchBackend();let model=AppModel(client:backend)
        model.searchInput="50%_ zdjęcia";await model.search()
        await model.select("failed")
        await model.loadPage(cursor:"expired")
        let seen=await backend.seen
        XCTAssertEqual(seen.last?["query"].string,"50%_ zdjęcia")
        XCTAssertEqual(seen.last?["filter"].string,"failed")
        XCTAssertNotNil(seen.last?["anchor"].array.first)
        await model.clearSearch()
        XCTAssertEqual(model.history.query,"")
        XCTAssertEqual(model.searchInput,"")
    }
    @MainActor func testAddingJobClearsSearchSoNewJobIsVisible() async {
        let backend=SearchBackend();let model=AppModel(client:backend);model.ready=true
        model.searchInput="existing";await model.search()
        model.inputURL="https://example.org/image.png"
        await model.add()
        XCTAssertEqual(model.history.query,"")
        XCTAssertEqual(model.searchInput,"")
        XCTAssertEqual(model.selection,"all")
    }
    @MainActor func testInvalidSearchDoesNotSendRequest() async {
        let backend=SearchBackend();let model=AppModel(client:backend)
        model.searchInput=String(repeating:"a",count:201);await model.search()
        model.searchInput="bad\0query";await model.search()
        let seen=await backend.seen
        XCTAssertTrue(seen.isEmpty);XCTAssertNotNil(model.message)
    }
}

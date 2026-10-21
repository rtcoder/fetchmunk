import XCTest
@testable import Fetchmunk

func historyPage(_ jobs: [Job], next: String? = nil, previous: String? = nil) -> HistoryPage {
    HistoryPage(snapshot_id:"s",at_seq:1,jobs:jobs,next_cursor:next,previous_cursor:previous)
}
func json<T: Encodable>(_ value:T) throws -> JSONValue {
    try JSONDecoder().decode(JSONValue.self,from:JSONEncoder().encode(value))
}
actor HistoryBackend: BackendConnection {
    nonisolated let events=AsyncStream<BackendEvent> { _ in }
    var seen: [(String,JSONValue)]=[]
    var expired=false
    func start(executableURL:URL) async throws {}
    func shutdown() async throws {}
    func request(method:String,params:JSONValue) async throws -> JSONValue {
        seen.append((method,params))
        if method=="jobs.summary" {
            return .object(["total":.number(100000),"active":.number(1),"history":.number(99999),"completed":.number(99999),"at_seq":.number(2),"queue_enabled":.bool(true),"current_job":try json(Job.example(id:"current",revision:2,state:"downloading"))])
        }
        if method=="jobs.snapshot" {
            if params["cursor"].string=="expired" { throw ClientError.backend("snapshot_expired") }
            return try json(historyPage([Job.example(id:params["filter"].string ?? "all",revision:1,state:"completed")],next:"expired"))
        }
        throw ClientError.protocolError
    }
}
final class HistoryTests:XCTestCase {
    func testPageReplacementIsBoundedAndOldFilterReplyIsIgnored() throws {
        var h=HistoryState()
        let old=h.begin(filter:"all")
        let fresh=h.begin(filter:"history")
        XCTAssertFalse(try h.accept(historyPage([.example(id:"wrong",revision:1,state:"queued")]),token:old))
        XCTAssertTrue(try h.accept(historyPage((0..<100).map { .example(id:String($0),revision:1,state:"completed") }),token:fresh))
        let next=h.begin(filter:"history")
        XCTAssertTrue(try h.accept(historyPage([.example(id:"next",revision:1,state:"completed")]),token:next))
        XCTAssertEqual(h.jobs.map(\.id),["next"])
        h.apply(.example(id:"invisible",revision:99,state:"completed"))
        XCTAssertEqual(h.jobs.count,1)
    }
    func testNewerLiveRevisionSurvivesSnapshotAndOversizedPageRejected() throws {
        var h=HistoryState();let token=h.begin(filter:"all")
        _ = try h.accept(historyPage([.example(id:"j",revision:3,state:"completed")]),token:token)
        let refresh=h.begin(filter:"all")
        _ = try h.accept(historyPage([.example(id:"j",revision:1,state:"downloading")]),token:refresh)
        XCTAssertEqual(h.jobs.first?.revision,3)
        XCTAssertThrowsError(try h.accept(historyPage((0..<101).map { .example(id:String($0),revision:1,state:"completed") }),token:refresh))
    }
    @MainActor func testSummaryIsGlobalAndExpiredPageRefreshesNearAnchor() async throws {
        let backend=HistoryBackend();let model=AppModel(client:backend);model.ready=true
        await model.refreshSummary()
        await model.select("history")
        XCTAssertEqual(model.totalCount,100000)
        XCTAssertEqual(model.historyCount,99999)
        XCTAssertEqual(model.currentJob?.id,"current")
        XCTAssertEqual(model.jobs.count,1)
        await model.loadPage(cursor:"expired")
        let requests=await backend.seen
        XCTAssertEqual(requests.last?.1["anchor"].array.last?.string,"history")
        XCTAssertEqual(model.jobs.count,1)
        XCTAssertNotNil(model.message)
    }
    @MainActor func testEventGapRefreshesOnlyOnePageAndDoesNotAccumulateRows() async throws {
        let backend=HistoryBackend();let model=AppModel(client:backend);model.ready=true
        await model.select("history")
        await model.consume(.object(["event":.string("queue.changed"),"seq":.number(1),"session_id":.string("s"),"data":.object(["queue_enabled":.bool(true)])]))
        await model.consume(.object(["event":.string("queue.changed"),"seq":.number(3),"session_id":.string("s"),"data":.object(["queue_enabled":.bool(true)])]))
        XCTAssertEqual(model.jobs.count,1)
        let requests=await backend.seen
        XCTAssertEqual(requests.filter{$0.0=="jobs.snapshot"}.count,2)
    }
}

actor DelayedHistoryBackend: BackendConnection {
    nonisolated let events=AsyncStream<BackendEvent> { _ in }
    var reply: CheckedContinuation<JSONValue, Error>?
    var observer: CheckedContinuation<Void,Never>?
    func start(executableURL:URL) async throws {}
    func shutdown() async throws {}
    func waitForSlowPage() async {
        if reply != nil { return }
        await withCheckedContinuation { observer=$0 }
    }
    func release() throws {
        reply?.resume(returning:try json(historyPage([.example(id:"stale",revision:1,state:"completed")])));reply=nil
    }
    func request(method:String,params:JSONValue) async throws -> JSONValue {
        if params["filter"].string=="history" {
            return try await withCheckedThrowingContinuation { reply=$0;observer?.resume();observer=nil }
        }
        return try json(historyPage([.example(id:"queue",revision:1,state:"queued")]))
    }
}
extension HistoryTests {
    @MainActor func testSlowOldFilterCannotReplaceCurrentPage() async throws {
        let backend=DelayedHistoryBackend();let model=AppModel(client:backend)
        let slow=Task { await model.select("history") }
        await backend.waitForSlowPage()
        await model.select("active")
        try await backend.release();await slow.value
        XCTAssertEqual(model.selection,"active")
        XCTAssertEqual(model.jobs.map(\.id),["queue"])
        XCTAssertFalse(model.history.loading)
    }
}

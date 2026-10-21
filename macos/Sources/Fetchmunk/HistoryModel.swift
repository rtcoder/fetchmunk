import Foundation

struct HistoryPage: Codable, Sendable {
    var snapshot_id: String
    var at_seq: Int
    var jobs: [Job]
    var next_cursor: String?
    var previous_cursor: String?
}

/// Exactly one page. A generation identifies the filter/navigation request that owns it.
struct HistoryState {
    private(set) var jobs: [Job] = []
    private(set) var filter = "all"
    private(set) var generation = 0
    private(set) var nextCursor: String?
    private(set) var previousCursor: String?
    var loading = false
    var stale = false

    mutating func begin(filter: String) -> Int {
        generation += 1
        if self.filter != filter {
            jobs = [];nextCursor = nil;previousCursor = nil;stale = false
        }
        self.filter = filter;loading = true
        return generation
    }
    mutating func accept(_ page: HistoryPage, token: Int) throws -> Bool {
        guard token == generation else { return false }
        guard page.jobs.count <= 100, Set(page.jobs.map(\.id)).count == page.jobs.count else { throw ClientError.protocolError }
        let current = Dictionary(uniqueKeysWithValues: jobs.map { ($0.id,$0) })
        jobs = page.jobs.map { incoming in
            if let newer = current[incoming.id], newer.revision > incoming.revision { return newer }
            return incoming
        }
        nextCursor = page.next_cursor;previousCursor = page.previous_cursor
        loading = false;stale = false
        return true
    }
    mutating func apply(_ job: Job) {
        guard let index = jobs.firstIndex(where: { $0.id == job.id }), jobs[index].revision < job.revision else { return }
        jobs[index] = job
    }
    var anchor: JSONValue? {
        jobs.first.map { .array([.string($0.created_at),.string($0.id)]) }
    }
}

protocol BackendConnection: Sendable {
    var events: AsyncStream<BackendEvent> { get }
    func start(executableURL: URL) async throws
    func request(method: String, params: JSONValue) async throws -> JSONValue
    func shutdown() async throws
}

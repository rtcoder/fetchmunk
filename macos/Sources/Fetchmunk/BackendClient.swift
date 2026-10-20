import Foundation
import Darwin

actor BackendClient {
    nonisolated let events: AsyncStream<BackendEvent>
    private let continuation: AsyncStream<BackendEvent>.Continuation
    private let writeQueue = DispatchQueue(label:"Fetchmunk.backend.write")
    private var process: Process?
    private var input: FileHandle?
    private var decoder = FrameDecoder()
    private var hello: CheckedContinuation<Void, Error>?
    private var pending: [String: CheckedContinuation<JSONValue, Error>] = [:]
    private var timers: [String: Task<Void, Never>] = [:]
    private let handshakeSeconds: Double
    private let requestSeconds: Double
    private var connected = false
    init(handshakeSeconds: Double = 10, requestSeconds: Double = 5) {
        self.handshakeSeconds = handshakeSeconds; self.requestSeconds = requestSeconds
        var c: AsyncStream<BackendEvent>.Continuation!
        events = AsyncStream(bufferingPolicy: .bufferingNewest(1024)) { c = $0 }; continuation = c
    }
    func start(executableURL: URL) async throws {
        guard process == nil else { throw ClientError.protocolError }
        guard FileManager.default.isExecutableFile(atPath: executableURL.path) else { throw ClientError.missingBackend }
        let p = Process(); let stdin = Pipe(); let stdout = Pipe()
        p.executableURL = executableURL; p.standardInput = stdin; p.standardOutput = stdout; p.standardError = FileHandle.nullDevice
        p.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
        process = p; input = stdin.fileHandleForWriting
        try await withCheckedThrowingContinuation { (waiter: CheckedContinuation<Void, Error>) in
            hello = waiter
            do { try p.run() } catch { hello = nil; process = nil; waiter.resume(throwing: error); return }
            let seconds = handshakeSeconds
            timers["hello"] = Task { try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000)); if !Task.isCancelled { self.failHandshake() } }
            Task.detached { [weak self] in
                while true {
                    let data = stdout.fileHandleForReading.availableData
                    if data.isEmpty { await self?.ended(); break }
                    await self?.receive(data)
                }
                try? stdout.fileHandleForReading.close()
            }
        }
    }
    private func failHandshake() { if hello != nil { abort(ClientError.timeout) } }
    private func receive(_ data: Data) {
        do {
            for message in try decoder.feed(data) {
                switch message["type"].string {
                case "hello":
                    guard hello != nil else { throw ClientError.protocolError }
                    connected = true; timers.removeValue(forKey: "hello")?.cancel()
                    hello?.resume(); hello = nil
                case "response":
                    guard let id = message["id"].string else { throw ClientError.protocolError }
                    timers.removeValue(forKey:id)?.cancel()
                    if let waiter = pending.removeValue(forKey: id) {
                        if let code = message["error"]["code"].string { waiter.resume(throwing: ClientError.backend(code)) }
                        else { waiter.resume(returning: message["result"]) }
                    }
                case "event": continuation.yield(message)
                default: break
                }
            }
        } catch { abort(ClientError.protocolError) }
    }
    func request(method: String, params: JSONValue) async throws -> JSONValue {
        // A lost reply may follow a committed mutation. Preserve operation_id.
        do { return try await sendOnce(method:method, params:params) }
        catch ClientError.timeout { return try await sendOnce(method:method, params:params) }
    }
    private func sendOnce(method: String, params: JSONValue) async throws -> JSONValue {
        guard connected, let input else { throw ClientError.disconnected }
        let id = UUID().uuidString
        let message: JSONValue = .object(["protocol":.number(1),"type":.string("request"),"id":.string(id),"method":.string(method),"params":params])
        var data = try JSONEncoder().encode(message); data.append(10)
        guard data.count <= 1_048_576 else { throw ClientError.protocolError }
        return try await withCheckedThrowingContinuation { waiter in
            pending[id] = waiter
            let seconds = requestSeconds
            timers[id] = Task { try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000)); if !Task.isCancelled { self.expire(id) } }
            // FileHandle write may block if the backend is stuck; keep actor responsive.
            writeQueue.async { [weak self] in
                do { try input.write(contentsOf: data) }
                catch { Task { await self?.writeFailed(id) } }
            }
        }
    }
    private func expire(_ id: String) { timers.removeValue(forKey:id); pending.removeValue(forKey:id)?.resume(throwing:ClientError.timeout) }
    private func writeFailed(_ id: String) { timers.removeValue(forKey:id)?.cancel();pending.removeValue(forKey:id)?.resume(throwing:ClientError.disconnected) }
    private func ended() {
        do { try decoder.finish(); abort(ClientError.disconnected) }
        catch { abort(ClientError.protocolError) }
    }
    private func abort(_ error: Error) {
        connected = false
        hello?.resume(throwing:error); hello = nil
        for waiter in pending.values { waiter.resume(throwing:error) }; pending.removeAll()
        for timer in timers.values { timer.cancel() }; timers.removeAll()
        try? input?.close(); input = nil
        if let process, process.isRunning { process.terminate() }
        continuation.yield(.object(["event":.string("connection.closed")]))
    }
    func shutdown() async throws {
        if connected { _ = try? await request(method:"app.shutdown",params:.object(["operation_id":.string(UUID().uuidString),"reason":.string("quit")])) }
        guard let p = process else { return }
        let killer = Task.detached { try? await Task.sleep(nanoseconds:10_000_000_000); if !Task.isCancelled && p.isRunning { kill(p.processIdentifier,SIGKILL) } }
        await Task.detached { p.waitUntilExit() }.value
        killer.cancel(); process = nil; continuation.finish()
    }
}

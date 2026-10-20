import SwiftUI
import AppKit

@MainActor final class AppModel: ObservableObject {
    @Published var jobs: [Job] = []
    @Published var inputURL = ""
    @Published var destination: URL
    @Published var ready = false
    @Published var connecting = false
    @Published var queueEnabled = true
    @Published var adding = false
    @Published var message: String?
    @Published var selection = "all"
    @Published var pendingJobs: Set<String> = []
    private var client: BackendClient?
    private var eventTask: Task<Void, Never>?
    private var lastSequence = 0
    private var sessionID: String?
    private var refreshing = false
    private var needsRefresh = false
    private var buffered = ChangeBuffer()
    private var shuttingDown = false
    init() {
        let defaultURL = FileManager.default.urls(for:.downloadsDirectory,in:.userDomainMask).first!.appendingPathComponent("Fetchmunk",isDirectory:true)
        destination = UserDefaults.standard.string(forKey:"destination").map { URL(fileURLWithPath:$0) } ?? defaultURL
    }
    var visibleJobs: [Job] {
        jobs.filter { selection == "all" || (selection == "active" ? $0.canCancel : !$0.canCancel) }
            .sorted { if $0.isActive != $1.isActive { return $0.isActive }; return $0.created_at > $1.created_at }
    }
    var activeCount: Int { jobs.filter(\.canCancel).count }
    var completedCount: Int { jobs.filter { $0.state == "completed" }.count }
    func apply(_ job: Job) {
        if let index = jobs.firstIndex(where: { $0.id == job.id }) {
            if jobs[index].revision < job.revision { jobs[index] = job }
        } else { jobs.append(job) }
    }
    func start() async {
        guard !ready && !connecting else { return }
        connecting = true; message = nil; shuttingDown = false
        if let old = client { try? await old.shutdown() }
        eventTask?.cancel();lastSequence=0;sessionID=nil
        let backend = BackendClient(); client = backend
        let executable = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/FetchmunkBackend.app/Contents/MacOS/fetchmunk-backend")
        do {
            try await backend.start(executableURL:executable)
            eventTask = Task { [weak self] in
                for await event in backend.events {
                    guard !Task.isCancelled else { break }
                    await self?.consume(event)
                }
            }
            let dataDir = FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask).first!.appendingPathComponent("Fetchmunk",isDirectory:true)
            let result = try await backend.request(method:"session.initialize",params:.object(["data_dir":.string(dataDir.path),"default_destination":.string(destination.path)]))
            queueEnabled = result["queue_enabled"].bool ?? false
            try await refresh()
            ready = true
        } catch { message = error.localizedDescription }
        connecting = false
    }
    private func consume(_ event: JSONValue) async {
        if event["event"].string == "connection.closed" {
            ready = false
            if !shuttingDown { message = ClientError.disconnected.localizedDescription }
            return
        }
        let sequence = event["seq"].int ?? 0
        let session = event["session_id"].string
        let gap = (sessionID != nil && sessionID != session) || (lastSequence > 0 && sequence != lastSequence+1)
        sessionID = session;lastSequence = sequence
        if gap { do { try await refresh() } catch { message=error.localizedDescription }; return }
        if event["event"].string == "queue.changed" { queueEnabled=event["data"]["queue_enabled"].bool ?? queueEnabled }
        guard event["event"].string == "job.changed", let id=event["data"]["job_id"].string else { return }
        if refreshing {
            buffered.insert(id)
            if buffered.needsSnapshot { needsRefresh=true }
            return
        }
        do { try await fetch(id) } catch { message=error.localizedDescription }
    }
    private func fetch(_ id: String) async throws {
        guard let client else { throw ClientError.disconnected }
        let result=try await client.request(method:"jobs.get",params:.object(["job_id":.string(id)]))
        apply(try result.decoded(Job.self))
    }
    private func refresh() async throws {
        if refreshing { needsRefresh=true;return }
        guard let client else { throw ClientError.disconnected }
        refreshing=true
        defer { refreshing=false }
        repeat {
            needsRefresh=false;buffered.reset()
            var cursor: String?;var snapshotJobs:[Job]=[]
            repeat {
                var params:[String:JSONValue]=["limit":.number(100)]
                if let cursor { params["cursor"] = .string(cursor) }
                let page=try await client.request(method:"jobs.snapshot",params:.object(params))
                snapshotJobs += try page["jobs"].array.map { try $0.decoded(Job.self) }
                cursor=page["next_cursor"].string
            } while cursor != nil
            for job in snapshotJobs { apply(job) }
            while !buffered.isEmpty && !needsRefresh {
                let ids=buffered.drain()
                for id in ids { try await fetch(id) }
            }
        } while needsRefresh
    }
    func add() async {
        guard ready && !adding, let client else { return }
        let url=inputURL.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !url.isEmpty else { return }
        adding=true;message=nil
        defer { adding=false }
        do {
            let result=try await client.request(method:"jobs.create",params:.object(["operation_id":.string(UUID().uuidString),"url":.string(url),"destination":.string(destination.path)]))
            if inputURL.trimmingCharacters(in:.whitespacesAndNewlines)==url { inputURL="" }
            if let id=result["job_id"].string { try await fetch(id) }
        } catch { message=error.localizedDescription }
    }
    func jobAction(_ method: String, job: Job) async {
        guard ready, !pendingJobs.contains(job.id), let client else { return }
        pendingJobs.insert(job.id);defer { pendingJobs.remove(job.id) }
        do {
            let result=try await client.request(method:method,params:.object(["operation_id":.string(UUID().uuidString),"job_id":.string(job.id)]))
            apply(try result.decoded(Job.self));try await fetch(job.id)
        } catch { message=error.localizedDescription }
    }
    func toggleQueue() async {
        guard let client else { return }
        do {
            let result=try await client.request(method:"queue.set_enabled",params:.object(["operation_id":.string(UUID().uuidString),"enabled":.bool(!queueEnabled)]))
            queueEnabled=result["queue_enabled"].bool ?? queueEnabled
        } catch { message=error.localizedDescription }
    }
    func chooseDestination() {
        let panel=NSOpenPanel();panel.canChooseFiles=false;panel.canChooseDirectories=true;panel.canCreateDirectories=true
        panel.prompt="Wybierz katalog";panel.directoryURL=destination
        if panel.runModal() == .OK, let url=panel.url { destination=url;UserDefaults.standard.set(url.path,forKey:"destination") }
    }
    func reveal(_ job: Job) {
        guard FileManager.default.fileExists(atPath:job.output_dir) else { message="Katalog nie został jeszcze utworzony albo został przeniesiony.";return }
        NSWorkspace.shared.open(URL(fileURLWithPath:job.output_dir,isDirectory:true))
    }
    func shutdown() async {
        shuttingDown=true;ready=false
        try? await client?.shutdown();eventTask?.cancel()
    }
}

import SwiftUI
import AppKit

@MainActor final class AppModel: ObservableObject {
    @Published var history = HistoryState()
    @Published var currentJob: Job?
    @Published var totalCount = 0
    @Published var activeCount = 0
    @Published var historyCount = 0
    @Published var completedCount = 0
    @Published var inputURL = ""
    @Published var destination: URL
    @Published var ready = false
    @Published var connecting = false
    @Published var queueEnabled = true
    @Published var adding = false
    @Published var message: String?
    @Published var pendingJobs: Set<String> = []
    private var client: (any BackendConnection)?
    private var pendingCreation: JSONValue?
    private var eventTask: Task<Void, Never>?
    private var lastSequence = 0
    private var summarySequence = -1
    private var sessionID: String?
    private var shuttingDown = false
    init(client: (any BackendConnection)? = nil) {
        self.client = client
        let defaultURL = FileManager.default.urls(for:.downloadsDirectory,in:.userDomainMask).first!.appendingPathComponent("Fetchmunk",isDirectory:true)
        destination = UserDefaults.standard.string(forKey:"destination").map { URL(fileURLWithPath:$0) } ?? defaultURL
    }
    var selection: String { history.filter }
    var jobs: [Job] { history.jobs }
    var visibleJobs: [Job] { jobs.filter { $0.id != currentJob?.id } }
    func apply(_ job: Job) {
        history.apply(job)
        if let current = currentJob, current.id == job.id, current.revision < job.revision { currentJob = job.isActive ? job : nil }
    }
    func start() async {
        guard !ready && !connecting else { return }
        connecting = true;message = nil;shuttingDown = false
        if let old = client { try? await old.shutdown() }
        eventTask?.cancel();lastSequence = 0;summarySequence = -1;sessionID = nil
        let backend = BackendClient();client = backend
        let executable = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/FetchmunkBackend.app/Contents/MacOS/fetchmunk-backend")
        do {
            try await backend.start(executableURL:executable)
            guard await backend.capabilities.contains("paged_jobs") else { throw ClientError.backend("dependency_unsupported") }
            eventTask = Task { [weak self] in
                for await event in backend.events {
                    guard !Task.isCancelled else { break }
                    await self?.consume(event)
                }
            }
            let dataDir = FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask).first!.appendingPathComponent("Fetchmunk",isDirectory:true)
            let result = try await backend.request(method:"session.initialize",params:.object(["data_dir":.string(dataDir.path),"default_destination":.string(destination.path)]))
            queueEnabled = result["queue_enabled"].bool ?? false
            ready = true
            await refreshSummary()
            await loadPage()
        } catch { message = error.localizedDescription }
        connecting = false
    }
    func consume(_ event: JSONValue) async {
        if event["event"].string == "connection.closed" {
            ready = false
            if !shuttingDown { message = ClientError.disconnected.localizedDescription }
            return
        }
        let sequence = event["seq"].int ?? 0
        let session = event["session_id"].string
        let newSession = sessionID != nil && sessionID != session
        let gap = newSession || (lastSequence > 0 && sequence != lastSequence+1)
        sessionID = session;lastSequence = sequence
        if newSession { summarySequence = -1 }
        if gap {
            await refreshSummary()
            await loadPage(preserveAnchor:true)
            return
        }
        if event["event"].string == "queue.changed" { queueEnabled = event["data"]["queue_enabled"].bool ?? queueEnabled }
        guard event["event"].string == "job.changed", let id = event["data"]["job_id"].string else { return }
        await refreshSummary()
        // Invisible history never gets appended to the page.
        if jobs.contains(where: { $0.id == id }), let client {
            do {
                let result = try await client.request(method:"jobs.get",params:.object(["job_id":.string(id)]))
                let job = try result.decoded(Job.self)
                if jobs.first(where: { $0.id == id })?.state != job.state { history.stale = true }
                apply(job)
            } catch { message = error.localizedDescription }
        }
    }
    func refreshSummary() async {
        guard let client else { return }
        do {
            let result = try await client.request(method:"jobs.summary",params:.object([:]))
            let seq = result["at_seq"].int ?? -1
            guard seq >= summarySequence else { return }
            let total = result["total"].int ?? 0
            let active = result["active"].int ?? 0
            let completed = result["completed"].int ?? 0
            if total != totalCount || active != activeCount || completed != completedCount { history.stale = true }
            summarySequence = seq
            totalCount = total;activeCount = active;completedCount = completed
            historyCount = result["history"].int ?? 0
            queueEnabled = result["queue_enabled"].bool ?? queueEnabled
            currentJob = result["current_job"] == .null ? nil : try result["current_job"].decoded(Job.self)
        } catch { message = error.localizedDescription }
    }
    func select(_ filter: String) async {
        guard ["all","active","history"].contains(filter) else { return }
        await loadPage(filter:filter)
    }
    func loadPage(cursor: String? = nil, preserveAnchor: Bool = false, filter: String? = nil) async {
        guard let client else { return }
        let selected = filter ?? selection
        let fallbackAnchor = selected == selection ? history.anchor : nil
        let token = history.begin(filter:selected)
        defer { if token == history.generation { history.loading = false } }
        var params: [String:JSONValue] = ["limit":.number(100),"filter":.string(selected)]
        if let cursor { params["cursor"] = .string(cursor) }
        else if preserveAnchor, let fallbackAnchor { params["anchor"] = fallbackAnchor }
        do {
            let result: JSONValue
            do { result = try await client.request(method:"jobs.snapshot",params:.object(params)) }
            catch ClientError.backend("snapshot_expired") {
                guard token == history.generation else { return }
                params.removeValue(forKey:"cursor");params["anchor"] = fallbackAnchor
                result = try await client.request(method:"jobs.snapshot",params:.object(params))
                if token == history.generation { message = "Widok historii wygasł. Odświeżono listę w pobliżu poprzedniej pozycji." }
            }
            guard token == history.generation else { return }
            let page = try result.decoded(HistoryPage.self)
            if try history.accept(page,token:token), summarySequence > page.at_seq { history.stale = true }
        } catch { if token == history.generation { message = error.localizedDescription } }
    }
    func add() async {
        guard ready && !adding, let client else { return }
        let url=pendingCreation?["url"].string ?? inputURL.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !url.isEmpty else { return }
        adding=true;message=nil
        defer { adding=false }
        do {
            let params = pendingCreation ?? .object(["operation_id":.string(UUID().uuidString),"url":.string(url),"destination":.string(destination.path)])
            pendingCreation = params
            _ = try await client.request(method:"jobs.create",params:params)
            pendingCreation = nil
            if inputURL.trimmingCharacters(in:.whitespacesAndNewlines)==url { inputURL="" }
            await refreshSummary()
            await select("all")
        } catch ClientError.backend(let code) {
            pendingCreation = nil; message = errorMessage(code)
        } catch {
            message = error.localizedDescription + " Ponowne kliknięcie Pobierz sprawdzi poprzednie zgłoszenie."
        }
    }
    func jobAction(_ method: String, job: Job) async {
        guard ready, !pendingJobs.contains(job.id), let client else { return }
        pendingJobs.insert(job.id);defer { pendingJobs.remove(job.id) }
        do {
            let result=try await client.request(method:method,params:.object(["operation_id":.string(UUID().uuidString),"job_id":.string(job.id)]))
            apply(try result.decoded(Job.self))
            history.stale = true
            await refreshSummary()
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

import XCTest
@testable import Fetchmunk
final class BackendClientTests: XCTestCase {
    func fixture(_ body: String) throws -> URL {
        let dir=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
        let file=dir.appendingPathComponent("backend fixture.py")
        try ("#!/usr/bin/python3\nimport sys,json,time\n"+body).write(to:file,atomically:true,encoding:.utf8)
        try FileManager.default.setAttributes([.posixPermissions:0o700],ofItemAtPath:file.path)
        addTeardownBlock { try? FileManager.default.removeItem(at:dir) }
        return file
    }
    let hello="print(json.dumps({'protocol':1,'type':'hello','session_id':'s'}),flush=True)\n"
    func testHandshakeTimeoutTerminatesProcess() async throws {
        let url=try fixture("time.sleep(30)\n")
        let client=BackendClient(handshakeSeconds:0.05)
        do { try await client.start(executableURL:url); XCTFail("Expected timeout") }
        catch ClientError.timeout {} catch { XCTFail("Unexpected \(error)") }
        try await client.shutdown()
    }
    func testRetryPreservesOperationID() async throws {
        let url=try fixture(hello+"""
first=None
for line in sys.stdin:
 r=json.loads(line)
 if r['method']=='app.shutdown':
  print(json.dumps({'protocol':1,'type':'response','id':r['id'],'result':{}}),flush=True);break
 if first is None:
  first=r['params']['operation_id'];continue
 print(json.dumps({'protocol':1,'type':'response','id':r['id'],'result':{'same':first==r['params']['operation_id']}}),flush=True)

""")
        let client=BackendClient(requestSeconds:0.05)
        try await client.start(executableURL:url)
        let result=try await client.request(method:"jobs.create",params:.object(["operation_id":.string("same-id")]))
        XCTAssertEqual(result["same"].bool,true)
        try await client.shutdown()
    }
    func testConcurrentLargeRequestsAreNotInterleaved() async throws {
        let url=try fixture(hello+"""
for line in sys.stdin:
 r=json.loads(line)
 print(json.dumps({'protocol':1,'type':'response','id':r['id'],'result':{'ok':True}}),flush=True)
 if r['method']=='app.shutdown':break

""")
        let client=BackendClient()
        try await client.start(executableURL:url)
        try await withThrowingTaskGroup(of:Bool.self) { group in
            for _ in 0..<20 { group.addTask {
                let r=try await client.request(method:"echo",params:.object(["text":.string(String(repeating:"ż",count:10000))]))
                return r["ok"].bool==true
            }}
            for try await ok in group { XCTAssertTrue(ok) }
        }
        try await client.shutdown()
    }
    func testDisconnectFailsPendingRequest() async throws {
        let url=try fixture(hello+"sys.stdin.readline()\n")
        let client=BackendClient()
        try await client.start(executableURL:url)
        do { _ = try await client.request(method:"read",params:.object([:]));XCTFail("Expected disconnect") }
        catch ClientError.disconnected {} catch { XCTFail("Unexpected \(error)") }
        try await client.shutdown()
    }
    func testShutdownDeadlineIncludesRequestTimeout() async throws {
        let url = try fixture(hello+"time.sleep(30)\n")
        let client = BackendClient(requestSeconds:2, shutdownSeconds:0.2)
        try await client.start(executableURL:url)
        let started = Date()
        try await client.shutdown()
        XCTAssertLessThan(Date().timeIntervalSince(started), 1.5)
    }
    @MainActor func testManualRetryAfterTwoTimeoutsPreservesCreation() async throws {
        let url = try fixture(hello+"""
first=None
count=0
for line in sys.stdin:
 r=json.loads(line)
 if r['method']=='app.shutdown':break
 count+=1
 if first is None:first=r['params']['operation_id']
 if count<=2:continue
 print(json.dumps({'protocol':1,'type':'response','id':r['id'],'error':{'code':'invalid_url' if first==r['params']['operation_id'] else 'permission_denied'}}),flush=True)

""")
        let client=BackendClient(requestSeconds:0.05)
        try await client.start(executableURL:url)
        let model=AppModel(client:client);model.ready=true;model.inputURL="https://example.org/a.png"
        await model.add()
        XCTAssertFalse(model.adding)
        await model.add()
        XCTAssertEqual(model.message,errorMessage("invalid_url"))
        try await client.shutdown()
    }
    func testRepeatedImmediateExitDoesNotLeaveShutdownWaiting() async throws {
        let url=try fixture(hello)
        for _ in 0..<20 {
            let client=BackendClient(handshakeSeconds:1,shutdownSeconds:0.2)
            try await client.start(executableURL:url)
            try await client.shutdown()
        }
    }
}

import XCTest
@testable import Fetchmunk

final class CredentialModelTests: XCTestCase {
    @MainActor func testLoadRequestsOnlyMetadataAndDoesNotPrefillSecrets() async {
        var methods: [String] = []
        let model = CredentialModel { method, params in
            methods.append(method)
            XCTAssertEqual(params,.object([:]))
            if method == "auth.list" {
                return .object(["profiles":.array([.object([
                    "id":.string("saved-id"),"service":.string("cda"),"label":.string("Moje konto"),"kind":.string("password"),
                    "secret":.object(["password":.string("must-not-prefill")])])]),"reset":.bool(false)])
            }
            return .object(["browsers":.array([.object(["id":.string("firefox"),"status":.string("requires_consent")])])])
        }
        await model.load()
        XCTAssertEqual(methods,["auth.list","auth.browsers"])
        XCTAssertEqual(model.profiles.first?.label,"Moje konto")
        model.replace(model.profiles[0])
        XCTAssertEqual(model.password,""); XCTAssertEqual(model.username,"")
        XCTAssertEqual(model.profileID,"saved-id")
    }
    @MainActor func testPasswordIsClearedAfterFailureAndRetryKeepsID() async {
        var requests: [JSONValue] = []
        let model = CredentialModel { method, params in
            XCTAssertEqual(method,"auth.save"); requests.append(params);throw ClientError.timeout
        }
        model.username = "account"; model.password = "private"
        await model.savePassword()
        XCTAssertEqual(model.password,"")
        XCTAssertNotNil(model.message)
        model.password = "private"
        await model.savePassword()
        XCTAssertEqual(requests.count,2)
        XCTAssertEqual(requests[0]["id"],requests[1]["id"])
        XCTAssertEqual(requests[0]["secret"]["password"],.string("private"))
        XCTAssertEqual(requests[0]["kind"],.string("password"))
    }
    @MainActor func testBrowserImportRequiresExplicitConsentAndSendsChosenService() async {
        var methods: [String] = [];var received: JSONValue = .null
        let model = CredentialModel { method, params in
            methods.append(method);received = params;throw ClientError.backend("browser_import_failed")
        }
        model.selectService("youtube")
        model.browser = "firefox"
        await model.importBrowser()
        XCTAssertTrue(methods.isEmpty)
        model.consent = true
        await model.importBrowser()
        XCTAssertEqual(methods,["auth.import_browser"])
        XCTAssertEqual(received["service"],.string("youtube"))
        XCTAssertEqual(received["browser"],.string("firefox"))
        XCTAssertEqual(received["consent"],.bool(true))
        XCTAssertEqual(received["profile"],.null)
    }
    @MainActor func testResetMessageAndBoundedCookieImport() async {
        var requests: [String] = []
        let model = CredentialModel { method, _ in
            requests.append(method)
            if method == "auth.list" { return .object(["profiles":.array([]),"reset":.bool(true)]) }
            return .object(["browsers":.array([])])
        }
        await model.load()
        XCTAssertTrue(model.message?.contains("ponownie") == true)
        await model.importText(String(repeating:"a",count:524289))
        XCTAssertEqual(requests,["auth.list","auth.browsers"])
    }
    @MainActor func testDeleteSendsOnlyProfileID() async {
        var deletion: JSONValue = .null
        let model = CredentialModel { method, params in
            if method == "auth.delete" { deletion = params;return .object([:]) }
            return .object(["profiles":.array([]),"browsers":.array([])])
        }
        await model.delete(CredentialProfile(id:"id",service:"cda",label:"label",kind:"password"))
        XCTAssertEqual(deletion,.object(["id":.string("id")]))
    }
    func testBrowserLaunchUsesExplicitKnownApplications() {
        XCTAssertEqual(CredentialBrowser.bundleIDs["firefox"],"org.mozilla.firefox")
        XCTAssertEqual(CredentialBrowser.bundleIDs["chrome"],"com.google.Chrome")
        XCTAssertNil(CredentialBrowser.bundleIDs["untrusted"])
    }
}

final class CredentialTransportTests: XCTestCase {
    private func fixture(_ body: String) throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".py")
        try ("#!/usr/bin/python3\nimport sys,json,time\nprint(json.dumps({'protocol':1,'type':'hello'}),flush=True)\n" + body).write(to:url,atomically:true,encoding:.utf8)
        try FileManager.default.setAttributes([.posixPermissions:0o700],ofItemAtPath:url.path)
        addTeardownBlock { try? FileManager.default.removeItem(at:url) }
        return url
    }
    func testAuthUsesLongerTimeoutWithoutResendingSecret() async throws {
        let url = try fixture("""
count=0
for line in sys.stdin:
 r=json.loads(line)
 if r['method']=='app.shutdown':break
 count+=1
 time.sleep(0.08)
 print(json.dumps({'protocol':1,'type':'response','id':r['id'],'result':{'count':count}}),flush=True)

""")
        let client = BackendClient(requestSeconds:0.02,authRequestSeconds:0.3)
        try await client.start(executableURL:url)
        let result = try await client.request(method:"auth.save",params:.object([:]))
        XCTAssertEqual(result["count"],.number(1))
        try await client.shutdown()
    }
    func testAuthTimeoutDoesNotAutomaticallyRetry() async throws {
        let url = try fixture("""
count=0
for line in sys.stdin:
 r=json.loads(line)
 if r['method']=='app.shutdown':break
 if r['method']=='auth.save':
  count+=1
  if count==1:continue
 print(json.dumps({'protocol':1,'type':'response','id':r['id'],'result':{'count':count}}),flush=True)

""")
        let client = BackendClient(requestSeconds:0.02,authRequestSeconds:0.05)
        try await client.start(executableURL:url)
        do {
            _ = try await client.request(method:"auth.save",params:.object([:]))
            XCTFail("Auth must time out without automatic retry")
        } catch ClientError.timeout {} catch { XCTFail("Unexpected error") }
        let result = try await client.request(method:"auth.list",params:.object([:]))
        XCTAssertEqual(result["count"],.number(1))
        try await client.shutdown()
    }
}

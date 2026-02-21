import XCTest

final class TestBridgeUITests: XCTestCase {
    func testBridgeServer() throws {
        let port = Self.resolvePort()
        NSLog("TestBridge: Starting on port \(port)")
        let server = HTTPServer(port: port)
        let handlers = Handlers()
        handlers.register(on: server.router)
        server.start()
        // Block forever — Python kills the xcodebuild process when done.
        RunLoop.current.run()
    }

    /// Resolve the port to listen on.
    /// Python writes the port to /tmp/testbridge_<SIMULATOR_UDID>.port before
    /// launching xcodebuild. The simulator runtime sets SIMULATOR_UDID for every
    /// app process, so we can reliably find our port file.
    /// Falls back to 8615 if no file exists (single-device default).
    private static func resolvePort() -> UInt16 {
        if let udid = ProcessInfo.processInfo.environment["SIMULATOR_UDID"] {
            let path = "/tmp/testbridge_\(udid).port"
            if let contents = try? String(contentsOfFile: path, encoding: .utf8),
               let port = UInt16(contents.trimmingCharacters(in: .whitespacesAndNewlines)) {
                return port
            }
        }
        return 8615
    }
}

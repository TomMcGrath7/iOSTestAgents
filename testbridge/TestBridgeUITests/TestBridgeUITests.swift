import XCTest

final class TestBridgeUITests: XCTestCase {
    func testBridgeServer() throws {
        let server = HTTPServer(port: 8615)
        let handlers = Handlers()
        handlers.register(on: server.router)
        server.start()
        // Block forever — Python kills the xcodebuild process when done.
        RunLoop.current.run()
    }
}

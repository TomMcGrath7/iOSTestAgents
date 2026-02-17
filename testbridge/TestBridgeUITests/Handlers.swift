import XCTest
import Foundation

/// Registers all HTTP endpoint handlers for TestBridge.
/// All XCUITest API calls are dispatched to the main thread via DispatchQueue.main.sync,
/// since they require main-actor isolation. The RunLoop on the main thread processes these.
final class Handlers {

    /// Helper: run a block on the main thread and return its result.
    private func onMain<T>(_ block: @escaping () -> T) -> T {
        if Thread.isMainThread {
            return block()
        }
        var result: T!
        DispatchQueue.main.sync {
            result = block()
        }
        return result
    }

    func register(on router: Router) {
        router.register("GET /health") { _, _ in
            return HandlerResponse(status: 200, json: ["status": "ok"])
        }

        router.register("POST /tap") { [self] body, _ in
            guard let body = body,
                  let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
                  let x = json["x"] as? Double,
                  let y = json["y"] as? Double else {
                return HandlerResponse(status: 400, json: ["error": "Missing x/y in body"])
            }
            onMain {
                let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
                let coord = springboard.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0))
                    .withOffset(CGVector(dx: x, dy: y))
                coord.tap()
            }
            return HandlerResponse(status: 200, json: ["status": "ok", "x": x, "y": y])
        }

        router.register("POST /swipe") { [self] body, _ in
            guard let body = body,
                  let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
                  let fromX = json["fromX"] as? Double,
                  let fromY = json["fromY"] as? Double,
                  let toX = json["toX"] as? Double,
                  let toY = json["toY"] as? Double else {
                return HandlerResponse(status: 400, json: ["error": "Missing fromX/fromY/toX/toY in body"])
            }
            onMain {
                let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
                let from = springboard.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0))
                    .withOffset(CGVector(dx: fromX, dy: fromY))
                let to = springboard.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0))
                    .withOffset(CGVector(dx: toX, dy: toY))
                from.press(forDuration: 0.05, thenDragTo: to, withVelocity: .default, thenHoldForDuration: 0)
            }
            return HandlerResponse(status: 200, json: ["status": "ok"])
        }

        router.register("POST /type") { [self] body, _ in
            guard let body = body,
                  let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
                  let text = json["text"] as? String else {
                return HandlerResponse(status: 400, json: ["error": "Missing text in body"])
            }
            onMain {
                let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
                springboard.typeText(text)
            }
            return HandlerResponse(status: 200, json: ["status": "ok", "typed": text])
        }

        router.register("POST /pressButton") { [self] body, _ in
            guard let body = body,
                  let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
                  let button = json["button"] as? String else {
                return HandlerResponse(status: 400, json: ["error": "Missing button in body"])
            }
            onMain {
                switch button.lowercased() {
                case "home":
                    XCUIDevice.shared.press(.home)
                default:
                    XCUIDevice.shared.press(.home)
                }
            }
            return HandlerResponse(status: 200, json: ["status": "ok", "button": button])
        }

        router.register("GET /ui") { [self] _, queryString in
            // Parse bundleId from query string
            var bundleId = "com.apple.springboard"
            if let qs = queryString {
                for param in qs.split(separator: "&") {
                    let kv = param.split(separator: "=", maxSplits: 1)
                    if kv.count == 2 && kv[0] == "bundleId" {
                        bundleId = String(kv[1])
                    }
                }
            }

            // Snapshot with timeout: dispatch to main, wait with semaphore from this (background) thread
            var result: String?
            var snapshotError: String?
            let semaphore = DispatchSemaphore(value: 0)

            DispatchQueue.main.async {
                do {
                    let app = XCUIApplication(bundleIdentifier: bundleId)
                    let snapshot = try app.snapshot()
                    result = AccessibilitySerializer.serialize(snapshot)
                } catch {
                    snapshotError = String(describing: error)
                }
                semaphore.signal()
            }

            let timeout = semaphore.wait(timeout: .now() + 10)
            if timeout == .timedOut {
                return HandlerResponse(status: 504, json: ["error": "Snapshot timed out after 10s"])
            }
            if let error = snapshotError {
                return HandlerResponse(status: 500, json: ["error": error])
            }
            return HandlerResponse(status: 200, json: ["ui": result ?? ""])
        }

        router.register("GET /screenshot") { [self] _, _ in
            let pngData: Data = onMain {
                let screenshot = XCUIScreen.main.screenshot()
                return screenshot.pngRepresentation
            }
            return HandlerResponse(status: 200, data: pngData, contentType: "image/png")
        }
    }
}

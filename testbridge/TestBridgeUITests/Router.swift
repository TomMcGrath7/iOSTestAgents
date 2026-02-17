import Foundation

/// Response from a handler: status code, optional JSON body, optional raw data.
struct HandlerResponse {
    let status: Int
    let json: [String: Any]?
    let rawData: Data?
    let contentType: String?

    init(status: Int, json: [String: Any]) {
        self.status = status
        self.json = json
        self.rawData = nil
        self.contentType = nil
    }

    init(status: Int, data: Data, contentType: String) {
        self.status = status
        self.json = nil
        self.rawData = data
        self.contentType = contentType
    }
}

/// Maps "METHOD /path" → handler closure.
final class Router {
    typealias Handler = (Data?, String?) throws -> HandlerResponse

    private var routes: [String: Handler] = [:]

    func register(_ key: String, handler: @escaping Handler) {
        routes[key] = handler
    }

    func handler(for key: String) -> Handler? {
        return routes[key]
    }
}

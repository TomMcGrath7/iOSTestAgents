import Foundation
import Network

/// Lightweight HTTP/1.1 server using Network.framework (NWListener).
/// Accepts TCP connections, parses requests, dispatches to Router, and writes JSON responses.
final class HTTPServer {
    let port: UInt16
    let router = Router()
    private var listener: NWListener?

    init(port: UInt16) {
        self.port = port
    }

    func start() {
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        do {
            listener = try NWListener(using: params, on: NWEndpoint.Port(rawValue: port)!)
        } catch {
            fatalError("Failed to create listener: \(error)")
        }

        listener?.newConnectionHandler = { [weak self] connection in
            self?.handleConnection(connection)
        }
        listener?.stateUpdateHandler = { state in
            switch state {
            case .ready:
                NSLog("TestBridge: HTTP server listening on port \(self.port)")
            case .failed(let error):
                NSLog("TestBridge: Listener failed: \(error)")
            default:
                break
            }
        }
        listener?.start(queue: .global(qos: .userInitiated))
    }

    private func handleConnection(_ connection: NWConnection) {
        connection.start(queue: .global(qos: .userInitiated))
        receiveAll(connection: connection, buffer: Data()) { [weak self] data in
            guard let self = self else { return }
            self.processRequest(data: data, connection: connection)
        }
    }

    private func receiveAll(connection: NWConnection, buffer: Data, completion: @escaping (Data) -> Void) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { content, _, isComplete, error in
            var buf = buffer
            if let content = content { buf.append(content) }

            if error != nil || isComplete {
                completion(buf)
                return
            }

            // Check if we have the full HTTP request
            if let headerEnd = self.findHeaderEnd(in: buf) {
                let headerStr = String(data: buf[..<headerEnd], encoding: .utf8) ?? ""
                let contentLength = self.parseContentLength(from: headerStr)
                let bodyStart = headerEnd + 4 // skip \r\n\r\n
                let totalExpected = bodyStart + contentLength
                if buf.count >= totalExpected {
                    completion(buf)
                    return
                }
            }

            self.receiveAll(connection: connection, buffer: buf, completion: completion)
        }
    }

    private func findHeaderEnd(in data: Data) -> Int? {
        let separator: [UInt8] = [0x0D, 0x0A, 0x0D, 0x0A] // \r\n\r\n
        let bytes = [UInt8](data)
        guard bytes.count >= 4 else { return nil }
        for i in 0...(bytes.count - 4) {
            if bytes[i] == separator[0] && bytes[i+1] == separator[1]
                && bytes[i+2] == separator[2] && bytes[i+3] == separator[3] {
                return i
            }
        }
        return nil
    }

    private func parseContentLength(from header: String) -> Int {
        for line in header.components(separatedBy: "\r\n") {
            let parts = line.split(separator: ":", maxSplits: 1)
            if parts.count == 2 && parts[0].trimmingCharacters(in: .whitespaces).lowercased() == "content-length" {
                return Int(parts[1].trimmingCharacters(in: .whitespaces)) ?? 0
            }
        }
        return 0
    }

    private func processRequest(data: Data, connection: NWConnection) {
        guard let headerEnd = findHeaderEnd(in: data) else {
            sendResponse(connection: connection, status: 400, body: ["error": "Malformed request"])
            return
        }

        let headerStr = String(data: data[..<headerEnd], encoding: .utf8) ?? ""
        let lines = headerStr.components(separatedBy: "\r\n")
        guard let requestLine = lines.first else {
            sendResponse(connection: connection, status: 400, body: ["error": "No request line"])
            return
        }

        let parts = requestLine.split(separator: " ")
        guard parts.count >= 2 else {
            sendResponse(connection: connection, status: 400, body: ["error": "Invalid request line"])
            return
        }

        let method = String(parts[0])
        let fullPath = String(parts[1])

        // Separate path and query string
        let pathComponents = fullPath.split(separator: "?", maxSplits: 1)
        let path = String(pathComponents[0])
        let queryString = pathComponents.count > 1 ? String(pathComponents[1]) : nil

        let bodyStart = headerEnd + 4
        let body: Data? = data.count > bodyStart ? data[bodyStart...].prefix(data.count - bodyStart) : nil

        let key = "\(method) \(path)"
        guard let handler = router.handler(for: key) else {
            sendResponse(connection: connection, status: 404, body: ["error": "Not found: \(key)"])
            return
        }

        do {
            let result = try handler(body, queryString)
            if let rawData = result.rawData {
                sendRawResponse(connection: connection, status: result.status, contentType: result.contentType ?? "application/octet-stream", data: rawData)
            } else {
                sendResponse(connection: connection, status: result.status, body: result.json ?? [:])
            }
        } catch {
            sendResponse(connection: connection, status: 500, body: ["error": String(describing: error)])
        }
    }

    private func sendResponse(connection: NWConnection, status: Int, body: [String: Any]) {
        let jsonData = (try? JSONSerialization.data(withJSONObject: body)) ?? Data()
        let statusText = HTTPServer.statusText(for: status)
        let header = "HTTP/1.1 \(status) \(statusText)\r\nContent-Type: application/json\r\nContent-Length: \(jsonData.count)\r\nConnection: close\r\n\r\n"
        var response = header.data(using: .utf8)!
        response.append(jsonData)
        connection.send(content: response, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }

    private func sendRawResponse(connection: NWConnection, status: Int, contentType: String, data: Data) {
        let statusText = HTTPServer.statusText(for: status)
        let header = "HTTP/1.1 \(status) \(statusText)\r\nContent-Type: \(contentType)\r\nContent-Length: \(data.count)\r\nConnection: close\r\n\r\n"
        var response = header.data(using: .utf8)!
        response.append(data)
        connection.send(content: response, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }

    static func statusText(for code: Int) -> String {
        switch code {
        case 200: return "OK"
        case 400: return "Bad Request"
        case 404: return "Not Found"
        case 500: return "Internal Server Error"
        case 504: return "Gateway Timeout"
        default: return "Unknown"
        }
    }
}

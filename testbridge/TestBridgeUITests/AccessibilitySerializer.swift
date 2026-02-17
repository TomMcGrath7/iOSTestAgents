import XCTest

/// Recursively walks XCUIElementSnapshot tree and outputs a compact text format
/// that includes labels, identifiers, and values — whichever are available.
enum AccessibilitySerializer {
    static func serialize(_ snapshot: XCUIElementSnapshot, indent: Int = 0) -> String {
        var lines: [String] = []
        appendNode(snapshot, indent: indent, to: &lines)
        return lines.joined(separator: "\n")
    }

    private static func appendNode(_ node: XCUIElementSnapshot, indent: Int, to lines: inout [String]) {
        let prefix = String(repeating: "  ", count: indent)
        let typeName = elementTypeName(node.elementType)

        // Gather all available text identifiers
        let label = node.label
        let identifier = node.identifier
        let title = node.title
        let valueStr = (node.value as? String) ?? ""
        let placeholderValue = node.placeholderValue ?? ""

        // Build a display name from the best available source
        var displayName = ""
        if !label.isEmpty {
            displayName = "'\(label)'"
        } else if !title.isEmpty {
            displayName = "'\(title)'"
        } else if !identifier.isEmpty {
            displayName = "id='\(identifier)'"
        }

        // Skip unlabeled AXOther leaf nodes (noise reduction)
        let hasChildren = !node.children.isEmpty
        if typeName == "AXOther" && displayName.isEmpty && !hasChildren {
            return
        }

        let frame = node.frame
        // Only include elements that are on-screen (visible)
        guard frame.width > 0, frame.height > 0 else { return }
        let frameStr = "{{\(Int(frame.origin.x)), \(Int(frame.origin.y))}, {\(Int(frame.width)), \(Int(frame.height))}}"

        var extras: [String] = []
        if !valueStr.isEmpty && valueStr != label && valueStr != title {
            extras.append("value='\(valueStr)'")
        }
        if !placeholderValue.isEmpty {
            extras.append("placeholder='\(placeholderValue)'")
        }
        if node.isSelected { extras.append("selected") }
        if node.hasFocus { extras.append("focused") }
        if !node.isEnabled { extras.append("disabled") }

        let extrasStr = extras.isEmpty ? "" : " " + extras.joined(separator: ", ")

        lines.append("\(prefix)\(typeName) \(displayName) \(frameStr)\(extrasStr)")

        for child in node.children {
            appendNode(child, indent: indent + 1, to: &lines)
        }
    }

    private static func elementTypeName(_ type: XCUIElement.ElementType) -> String {
        switch type {
        case .application: return "Application"
        case .window: return "Window"
        case .button: return "Button"
        case .staticText: return "StaticText"
        case .textField: return "TextField"
        case .secureTextField: return "SecureTextField"
        case .image: return "Image"
        case .cell: return "Cell"
        case .table: return "Table"
        case .collectionView: return "CollectionView"
        case .scrollView: return "ScrollView"
        case .navigationBar: return "NavigationBar"
        case .tabBar: return "TabBar"
        case .toolbar: return "Toolbar"
        case .switch: return "Switch"
        case .slider: return "Slider"
        case .picker: return "Picker"
        case .alert: return "Alert"
        case .sheet: return "Sheet"
        case .link: return "Link"
        case .toggle: return "Toggle"
        case .searchField: return "SearchField"
        case .other: return "Other"
        case .group: return "Group"
        case .pageIndicator: return "PageIndicator"
        case .icon: return "Icon"
        case .activityIndicator: return "ActivityIndicator"
        case .segmentedControl: return "SegmentedControl"
        case .popUpButton: return "PopUpButton"
        case .menuButton: return "MenuButton"
        case .webView: return "WebView"
        case .key: return "Key"
        case .keyboard: return "Keyboard"
        case .statusBar: return "StatusBar"
        default: return "Element"
        }
    }
}

# CLAUDE.md — MobileTestAI

## What This Is

An AI-powered iOS app testing framework. LLM agents autonomously navigate and test iOS apps on simulators. The unique differentiator is **multi-device orchestration** — coordinating N agents across N simulators for multiplayer/collaborative app testing. Nobody else has built this.

Repo: `/Users/tom/Documents/GitHub/MobileAppTesterAgent`
Package: `mobiletestai`

## Current State (What's Already Built & Working)

### TestBridge — Custom XCUITest HTTP Bridge ✅ COMPLETE
A Swift XCUITest bundle that starts an HTTP server on `localhost:8615`, giving Python full control of a running simulator. **All 7 endpoints verified working on a live iOS 26.0 simulator with Xcode 26.1:**

| Endpoint | Function |
|---|---|
| `GET /health` | `{"status":"ok"}` |
| `POST /tap` | `{"x":100,"y":200}` |
| `POST /swipe` | `{"fromX":..,"fromY":..,"toX":..,"toY":..}` |
| `POST /type` | `{"text":"hello"}` |
| `POST /pressButton` | `{"button":"home"}` |
| `GET /ui` | Full accessibility tree (idb-compatible text) |
| `GET /screenshot` | PNG screenshot (~2.5MB) |

Files in `testbridge/`:
- `TestBridge.xcodeproj/` — Xcode project (app + UI test bundle, shared scheme)
- `TestBridgeApp.swift` — Trivial SwiftUI host app
- `TestBridgeUITests.swift` — Entry point, starts HTTP server on port 8615
- `HTTPServer.swift` — NWListener (Network.framework), ~150 lines
- `Router.swift` — HTTP routing with HandlerResponse, ~40 lines
- `Handlers.swift` — XCUITest API wrappers for all endpoints, ~120 lines
- `AccessibilitySerializer.swift` — Recursive XCUIElementSnapshot walker, ~60 lines

Build fixes applied: iOS 18.0 deployment target, Swift 5.0 on UITests target (Swift 6 @MainActor isolation workaround), `onMain {}` helper for main-thread XCUITest dispatch, removed simulator-unavailable button APIs (volumeUp/Down).

### Python Layer ✅ COMPLETE
- `device/bridge.py` — `BridgeDevice` class: tap, swipe, type_text, press_button, describe_ui via HTTP. `start()` launches xcodebuild as background process, polls /health. `stop()` terminates. Uses only `urllib.request` (stdlib).
- `device/simulator.py` — `SimulatorManager`: boot, install, launch, terminate, reset_app, screenshot, recording via `xcrun simctl`.
- `device/idb.py` — Legacy idb fallback (kept, not primary).
- `agent/loop.py` — Core observe→reason→act loop with stale UI detection (waits 2s if unchanged, reports stuck after 3 identical states). Token cost tracking per-step.
- `agent/prompts.py` — System/user prompt templates for Claude API.
- `agent/models.py` — Pydantic models for actions and results.
- `cli.py` — Typer CLI with `run` and `doctor` commands.
- `util/logging.py` — Rich logging.

### Tests ✅ 80 PASSING
- 15 BridgeDevice tests (HTTP methods, error handling, start/stop, availability)
- 52 original device/agent/CLI tests
- 13 updated tests (BridgeDevice patching)

## New Discovery: XcodeBuildMCP

**XcodeBuildMCP** (by Sentry/Cameron Cooke) is an MIT-licensed MCP server + CLI with **59 tools** for Xcode automation, including a full UI automation suite that overlaps with our TestBridge:

- Repo: https://github.com/getsentry/XcodeBuildMCP
- Website: https://www.xcodebuildmcp.com
- Install: `npm install -g xcodebuildmcp@latest` or `brew install xcodebuildmcp`
- Works as MCP server AND standalone CLI
- UI automation tools: `tap`, `swipe`, `type`, `describe_ui`, `screenshot`, `long_press`, `touch_down/up`, `gesture`, `press_button`
- Also: simulator lifecycle, project building, testing, debugging, **real device support**
- Integrates with Xcode 26.3's native agent system via `xcrun mcpbridge`

### Apple's Xcode 26.3 MCP (`xcrun mcpbridge`)
Apple shipped a native MCP server for agentic *coding* (build, test, search docs, fix errors). This is for **development workflows, not runtime UI testing** — it can't tap buttons or navigate apps. Different niche from us.

### Strategic Decision: Support Both Backends

Rather than replacing TestBridge, we support both via a pluggable backend:

- **XcodeBuildMCP** — Default for users who have Node.js. More features (real devices, debugging, 59 tools). Well-maintained.
- **TestBridge** — Fallback for zero-dependency setups (just Xcode). Our proprietary IP. Already proven working.

Our value-add is NOT the device control layer — it's the **multi-device AI test orchestrator** on top. Focus energy there.

## What To Build Next

### Step 1: Pluggable Device Backend

Create `device/base.py` with a `DeviceBackend` Protocol:

```python
from typing import Protocol

class DeviceBackend(Protocol):
    def describe_ui(self) -> str: ...
    def tap(self, x: float, y: float) -> None: ...
    def swipe(self, from_x: float, from_y: float, to_x: float, to_y: float) -> None: ...
    def type_text(self, text: str) -> None: ...
    def press_button(self, button: str) -> None: ...
    def screenshot(self, path: str) -> str: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

Make existing `BridgeDevice` conform to this protocol (should be minimal changes).

### Step 2: XcodeBuildMCP Backend

Create `device/xcodebuildmcp.py` with `XcodeBuildMCPDevice` implementing `DeviceBackend`:
- Wraps XcodeBuildMCP CLI via `subprocess.run()`
- `start()` → verify xcodebuildmcp is on PATH, boot simulator if needed
- `stop()` → no-op (CLI is stateless per-command)
- `describe_ui()` → `xcodebuildmcp ui-automation describe-ui`
- `tap(x, y)` → `xcodebuildmcp ui-automation tap --x {x} --y {y}`
- `screenshot(path)` → `xcodebuildmcp simulator screenshot --output {path}`
- `is_available()` (static) → checks `which xcodebuildmcp`

**IMPORTANT:** Run `xcodebuildmcp --help` and `xcodebuildmcp ui-automation --help` first to confirm exact CLI argument syntax before implementing. The commands above are from docs and may differ.

### Step 3: Refactor Agent Loop

`agent/loop.py` should accept a `DeviceBackend` instance — no direct imports of `BridgeDevice`. Backend-agnostic.

### Step 4: Update CLI

- Add `--backend` option (choices: `xcodebuildmcp`, `testbridge`; default: `xcodebuildmcp`)
- `doctor` command checks both backends, recommends XcodeBuildMCP
- Instantiate correct backend based on flag

### Step 5: First Real E2E Test

Run the full pipeline against Settings.app:
```bash
uv run mobiletestai run \
  --device "iPhone 16" \
  --app com.apple.Preferences \
  --goal "Navigate to General settings" \
  --record
```

Then Safari:
```bash
uv run mobiletestai run \
  --device "iPhone 16" \
  --app com.apple.mobilesafari \
  --goal "Open Safari and navigate to apple.com"
```

### Step 6: Multi-Device Orchestrator (THE PRODUCT)

This is the differentiator. Nobody else has built this.

```
orchestrator/
├── coordinator.py    # Manages N DeviceBackend+Agent pairs
├── scenario.py       # YAML scenario parser
└── sync.py           # Wait/barrier/condition primitives
```

Scenario format:
```yaml
name: multiplayer_game_join
app_bundle_id: com.example.myapp
players: 2
steps:
  - player: 1
    action: "Create a new game room"
    verify: "Room code visible"
    capture: room_code

  - player: 2
    action: "Join game using {room_code}"
    verify: "Both players shown in lobby"

  - all_players:
    verify: "Game screen is active"
```

Key orchestration primitives:
- **Cross-device variable passing**: `capture` extracts a value (room code, invite link), `{var}` injects it into another player's step
- **Barriers**: `all_players` steps block until all devices reach that point
- **Wait-for-condition**: Poll a device's UI until condition is met before proceeding
- **Sequenced steps**: Player 1 acts, then Player 2 acts (default serial execution)
- **Parallel steps**: Multiple players act simultaneously (explicit `parallel: true`)

## File Structure

```
MobileAppTesterAgent/
├── src/mobiletestai/
│   ├── __init__.py
│   ├── cli.py                    # Typer CLI
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py               # Core observe→reason→act loop
│   │   ├── prompts.py            # LLM prompt templates
│   │   └── models.py             # Pydantic models
│   ├── device/
│   │   ├── __init__.py
│   │   ├── base.py               # DeviceBackend protocol  ← NEW
│   │   ├── xcodebuildmcp.py      # XcodeBuildMCP backend   ← NEW
│   │   ├── bridge.py             # TestBridge backend (working)
│   │   ├── simulator.py          # SimulatorManager (working)
│   │   └── idb.py                # Legacy fallback
│   ├── orchestrator/             # Multi-device coordination  ← NEW
│   │   ├── __init__.py
│   │   ├── coordinator.py
│   │   ├── scenario.py
│   │   └── sync.py
│   └── util/
│       ├── __init__.py
│       └── logging.py
├── testbridge/                   # Swift XCUITest HTTP bridge (working)
│   ├── TestBridge.xcodeproj/
│   ├── TestBridgeApp.swift
│   ├── TestBridgeUITests.swift
│   ├── HTTPServer.swift
│   ├── Router.swift
│   ├── Handlers.swift
│   └── AccessibilitySerializer.swift
├── tests/
├── scenarios/
├── pyproject.toml
└── CLAUDE.md
```

## LLM Prompt Structure

```
System: You are a mobile app testing agent controlling an iOS simulator.
You see the current UI state and decide the next action.

Respond ONLY with JSON: {"action": "tap", "x": 100, "y": 200, "reasoning": "..."}

Available actions:
- {"action": "tap", "x": <num>, "y": <num>}
- {"action": "swipe", "direction": "up|down|left|right"}
- {"action": "type", "text": "<string>"} — text field MUST be focused first
- {"action": "press_button", "button": "home"}
- {"action": "wait", "seconds": <num>}
- {"action": "done", "reasoning": "..."}
- {"action": "fail", "reasoning": "..."}

Rules:
- Use coordinates from the UI state, never guess
- Tap a text field before typing
- If UI unchanged after an action, try a different approach
```

## Architecture References

- **DroidRun** (https://github.com/droidrun/droidrun) — Best mobile AI agent architecture. Android-only. €2.1M pre-seed. Key insight: structured text > vision.
- **Inditex iOS Simulator MCP** (https://github.com/InditexTech/mcp-server-simulator-ios-idb) — MCP server wrapping idb. Good reference.
- **Magnitude** — Dual-agent (Planner + Executor) pattern worth studying.

## Known Gotchas

- XcodeBuildMCP requires Node.js — doctor should check and advise
- `describe_ui` can take 1-3s on complex hierarchies — add timeouts
- SwiftUI views may need `.accessibilityIdentifier()` for reliable automation
- Multiple simulators: ~2GB RAM each. MacBook: 3-4 max. Mac Studio: 8+
- LLM non-determinism: use fuzzy assertions ("screen contains text matching X")
- Always tap text field before `type` action — include in system prompt
- Always terminate + relaunch app between scenarios for clean state
- TestBridge destination: use simulator UDID (`id=...`), not name (ambiguous across runtimes)

## Dev Setup

```bash
# Prerequisites: macOS, Xcode 26+, Python 3.11+, Node.js (for XcodeBuildMCP)

# XcodeBuildMCP (default backend)
npm install -g xcodebuildmcp@latest

# Project
cd MobileAppTesterAgent
uv sync --extra dev
export ANTHROPIC_API_KEY="..."

# Verify
uv run mobiletestai doctor

# Run
uv run mobiletestai run \
  --device "iPhone 16" \
  --app com.apple.Preferences \
  --goal "Navigate to General settings" \
  --record
```

## Conventions
- Python 3.11+ with type hints
- `uv` for deps (`uv sync`, `uv add`, `uv run`)
- `typer` for CLI
- Agent code never imports a specific backend directly — always via `DeviceBackend` protocol
- Async for multi-device orchestration (Phase 2)

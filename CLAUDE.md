# CLAUDE.md — iOSTestAgents

## What This Is

An AI-powered iOS app testing framework. LLM agents autonomously navigate and test iOS apps on simulators. The unique differentiator is **multi-device orchestration** — coordinating N agents across N simulators for multiplayer/collaborative app testing.

Repo: `https://github.com/TomMcGrath7/iOSTestAgents`
Package: `iostestagents`

## Architecture Overview

```
src/iostestagents/
├── cli.py                        # Typer CLI (run, doctor, orchestrate)
├── agent/
│   ├── loop.py                   # Core observe→reason→act loop
│   ├── prompts.py                # LLM prompt templates
│   ├── models.py                 # Pydantic models (actions, results)
│   └── ui_parser.py              # Accessibility tree parser + element resolution
├── device/
│   ├── base.py                   # DeviceBackend protocol + DeviceError
│   ├── xcodebuildmcp.py          # XcodeBuildMCP backend (default)
│   ├── bridge.py                 # TestBridge backend (HTTP to XCUITest)
│   ├── simulator.py              # SimulatorManager (xcrun simctl wrapper)
│   └── idb.py                    # Legacy idb fallback
├── llm/
│   ├── base.py                   # LLMProvider protocol
│   ├── registry.py               # Auto-detect provider from env
│   ├── anthropic.py              # Claude (ANTHROPIC_API_KEY)
│   ├── openai.py                 # GPT (OPENAI_API_KEY)
│   └── ollama.py                 # Local Ollama
├── orchestrator/
│   ├── coordinator.py            # N agents × N simulators
│   ├── scenario.py               # YAML scenario parser
│   └── sync.py                   # VariableStore, AbortEvent, barriers
└── util/
    └── logging.py                # Rich logging

testbridge/                       # Swift XCUITest HTTP bridge
├── TestBridge.xcodeproj/
├── TestBridgeApp.swift
├── TestBridgeUITests.swift
├── HTTPServer.swift
├── Router.swift
├── Handlers.swift
└── AccessibilitySerializer.swift

scenarios/                        # Example YAML scenarios
tests/                            # 187 tests
```

## Device Backends

Both implement `DeviceBackend` protocol (`device/base.py`):

- **XcodeBuildMCP** (default) — Wraps the `xcodebuildmcp` CLI. Requires Node.js. Supports real devices, 59+ tools.
- **TestBridge** — Our custom XCUITest HTTP bridge on `localhost:8615`. Zero external deps (just Xcode). 7 endpoints: health, tap, swipe, type, pressButton, ui, screenshot.

Backend is selected via `--backend` CLI flag. Agent code uses `DeviceBackend` protocol only — never imports a specific backend directly.

## LLM Providers

Auto-detected from environment via `llm/registry.py`:
1. `ANTHROPIC_API_KEY` set → Anthropic (Claude)
2. `OPENAI_API_KEY` set → OpenAI (GPT)
3. Ollama running on localhost:11434 → Ollama

Override with `--llm` CLI flag.

## Multi-Device Orchestration

The differentiator. `orchestrator/coordinator.py` manages N `DeviceBackend`+Agent pairs coordinated via YAML scenarios:

- **Cross-device variable passing**: `capture` extracts values, `{var}` injects into other players' steps
- **Barriers**: `all_players` steps block until all devices reach that point
- **Sequenced/parallel execution**: Serial by default, `parallel: true` for simultaneous

See `scenarios/` for examples.

## Known Gotchas

- XcodeBuildMCP requires Node.js — `doctor` command checks and advises
- `describe_ui` can take 1-3s on complex hierarchies — use timeouts
- SwiftUI views may need `.accessibilityIdentifier()` for reliable automation
- Multiple simulators: ~2GB RAM each. MacBook: 3-4 max. Mac Studio: 8+
- Always tap text field before `type` action
- Always terminate + relaunch app between scenarios for clean state
- TestBridge: use simulator UDID (`id=...`), not name (ambiguous across runtimes)

## Dev Setup

```bash
# Prerequisites: macOS, Xcode 26+, Python 3.11+, Node.js (for XcodeBuildMCP)

# XcodeBuildMCP (default backend)
npm install -g xcodebuildmcp@latest

# Project
git clone https://github.com/TomMcGrath7/iOSTestAgents.git
cd iOSTestAgents
uv sync --extra dev
export ANTHROPIC_API_KEY="..."

# Verify
uv run iostestagents doctor

# Run single-device
uv run iostestagents run \
  --device "iPhone 16" \
  --app com.apple.Preferences \
  --goal "Navigate to General settings"

# Run multi-device scenario
uv run iostestagents orchestrate scenarios/multiplayer_example.yaml
```

## Conventions
- Python 3.11+ with type hints
- `uv` for deps (`uv sync`, `uv add`, `uv run`)
- `hatchling` build backend
- `typer` for CLI
- Agent code uses `DeviceBackend` protocol — never imports a specific backend directly
- `ThreadPoolExecutor` for multi-device orchestration

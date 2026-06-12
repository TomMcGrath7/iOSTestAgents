# MobileTestAI

[![Tests](https://github.com/TomMcGrath7/iOSTestAgents/actions/workflows/tests.yml/badge.svg)](https://github.com/TomMcGrath7/iOSTestAgents/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/downloads/)

AI-powered iOS app testing framework. Describe what you want tested in plain English, and an LLM agent autonomously navigates your app on iOS simulators.

## Why MobileTestAI?

There are tools that let AI agents tap buttons on a phone. MobileTestAI is the only one that **coordinates multiple AI agents across multiple simulators simultaneously**.

Testing a multiplayer game? A chat app? A collaborative tool? You need two (or more) devices interacting with each other — Player 1 creates a room, Player 2 joins with the room code, both verify they're in the lobby. No other open-source tool does this.

### What makes it different

| | MobileTestAI | Appium | XCUITest | Arbigent |
|---|---|---|---|---|
| Natural language goals | Yes | No | No | Yes |
| Multi-device orchestration | **Yes** | Manual | No | No |
| Cross-device variable passing | **Yes** | Manual | No | No |
| AI-driven navigation | Yes | No | No | Yes |
| iOS support | Yes | Yes | Yes | Yes |
| No test code required | Yes | No | No | Yes |
| Local LLM support | Yes | N/A | N/A | No |

### Use cases

- **Multiplayer apps** — test game lobbies, matchmaking, real-time interactions across devices
- **Chat/messaging** — verify message delivery between users on separate simulators
- **Collaborative tools** — test shared documents, whiteboards, or workspaces
- **Single-device testing** — works great for standard UI testing too
- **Regression testing** — define YAML scenarios and rerun them after every build

## How It Works

Each step of the agent loop:

1. **Observe** — captures the UI accessibility tree (and optionally a screenshot) from the simulator
2. **Reason** — sends the UI state to an LLM with the goal and action history
3. **Act** — executes the chosen action (tap, swipe, type, etc.) on the simulator
4. **Repeat** — continues until the agent reports "done", "fail", or hits the step limit

The agent uses structured text from the accessibility tree rather than vision alone — this is faster, cheaper, and more reliable than screenshot-only approaches.

## Prerequisites

- macOS with Xcode 26+ and iOS simulators
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- At least one device backend (see below)
- At least one LLM provider (see below)

## Installation

```bash
# Clone the repo
git clone https://github.com/TomMcGrath7/iOSTestAgents.git
cd iOSTestAgents

# Install Python dependencies
uv sync --extra dev

# Install XcodeBuildMCP (recommended device backend)
npm install -g xcodebuildmcp@latest

# Verify everything is set up
uv run iostestagents doctor
```

## Setting Up an LLM Provider

MobileTestAI needs an LLM to read the UI and decide actions. It supports three providers and auto-detects which one to use based on available API keys.

### Option 1: Ollama (local, free)

Run models locally on your Mac. No API key, no cost, no data leaves your machine.

```bash
# Install Ollama: https://ollama.com
brew install ollama
ollama serve

# Pull a model
ollama pull qwen3:8b
```

MobileTestAI auto-detects Ollama when it's running on `localhost:11434`.

> **Note on local models:** Local models work but performance scales with model capability. Smaller models (7-8B parameters) can handle simple navigation tasks like "go to Settings > General". For complex multi-step flows, onboarding sequences, or apps with non-obvious UI patterns, cloud models (GPT-5.4, Claude) perform significantly better. We recommend starting with Ollama to try things out, then switching to a cloud provider for production use.

### Option 2: OpenAI

Best balance of speed and capability. GPT-5.4 is the recommended model (current generation at the old gpt-4o price point); use gpt-5.5 for the premium flagship.

```bash
export OPENAI_API_KEY="sk-..."
```

Get your API key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

### Option 3: Anthropic (Claude)

The default model is `claude-opus-4-8`. For cheaper per-step costs on simple navigation tasks, use `--model claude-haiku-4-5` ($1/$5 per 1M tokens vs $5/$25 for Opus).

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Get your API key at [console.anthropic.com](https://console.anthropic.com/).

### Choosing a provider

| Provider | Cost | Speed | Quality | Privacy |
|---|---|---|---|---|
| **Ollama** (qwen3:8b) | Free | ~15-20s/step | Good for simple tasks | Full — runs locally |
| **OpenAI** (gpt-5.4) | ~$0.01-0.03/step | ~3-5s/step | Excellent | Data sent to OpenAI |
| **Anthropic** (claude-opus-4-8) | ~$0.01-0.05/step | ~3-5s/step | Excellent | Data sent to Anthropic |
| **Anthropic** (claude-haiku-4-5) | ~$0.005-0.01/step | ~2-4s/step | Good | Data sent to Anthropic |

You can override the auto-detected provider with `--provider` and `--model`:

```bash
uv run iostestagents run --provider ollama --model qwen3:8b ...
uv run iostestagents run --provider openai --model gpt-5.4 ...
uv run iostestagents run --provider anthropic --model claude-haiku-4-5 ...  # cheap per-step option
```

## Quick Start

Run a single-device test:

```bash
uv run iostestagents run \
  --device "iPhone 17" \
  --app com.apple.Preferences \
  --goal "Navigate to General > About"
```

Run with a specific provider and screen recording:

```bash
uv run iostestagents run \
  --device "iPhone 17" \
  --app com.apple.mobilesafari \
  --goal "Open Safari, tap the address bar, type apple.com, and verify the page loads" \
  --provider openai --model gpt-5.4 \
  --record
```

Run a multi-device scenario:

```bash
uv run iostestagents scenario scenarios/multiplayer_example.yaml
```

## Multi-Device Scenarios

This is MobileTestAI's unique capability. Scenarios are YAML files that coordinate multiple agents across multiple simulators:

```yaml
name: multiplayer_join_test
app_bundle_id: com.example.myapp
app_path: "/path/to/MyApp.app"
players: 2
device: "iPhone 17"
backend: xcodebuildmcp
provider: openai
model: gpt-5.4
max_steps: 30

steps:
  - player: 1
    action: "Create a new game room"
    capture: room_code

  - player: 2
    action: "Join game using room code {room_code}"

  - all_players:
    action: "Verify both players are in the lobby"
    parallel: true
```

### Orchestration Features

- **Cross-device variable passing** — `capture` extracts a value from the screen (like a room code), `{var}` injects it into another player's step
- **Barriers** — `all_players` steps block until all devices reach that point
- **Sequential or parallel** — steps run one at a time by default, or `parallel: true` for simultaneous actions
- **Failure handling** — `on_failure: continue` to keep going when a step fails

See the `scenarios/` directory for more examples.

## CLI Reference

```
iostestagents run
  --device, -d    Simulator device name (required)
  --app, -a       App bundle identifier (required)
  --goal, -g      Natural language test goal (required)
  --max-steps     Maximum agent steps (default: 20)
  --backend, -b   Device backend: xcodebuildmcp or testbridge (default: testbridge)
  --provider      LLM provider: openai, anthropic, ollama (auto-detect if omitted)
  --model         LLM model to use (default per provider)
  --output, -o    Output directory (default: output)
  --verbose, -v   Verbose logging
  --step-delay    Delay between steps in seconds (default: 1.5)
  --record        Record screen video
  --no-reset      Skip app reset before run
  --app-path      Path to .app bundle for install
  --no-vision     Skip screenshots, use accessibility tree only (faster)

iostestagents scenario <path>
  Run a multi-device YAML scenario file

iostestagents doctor
  Check environment setup and backend availability
```

## Writing Good Goals

Goals should be specific and include any gates (onboarding, login) the agent needs to get through:

```
# Good — specific with clear completion criteria
"Tap Get Started, complete onboarding by tapping Continue on each screen, then navigate to Settings"

# Bad — no clear completion criteria
"Explore the app"

# Bad — assumes the agent can skip onboarding
"Go to Settings"
```

Think of goals as instructions for someone who has never seen the app before.

## Device Backends

| Backend | How it works | Multi-device | Setup |
|---|---|---|---|
| **XcodeBuildMCP** (recommended) | Stateless CLI calls | Yes | `npm install -g xcodebuildmcp@latest` |
| **TestBridge** | HTTP server via XCUITest | Single device only | Just Xcode (included in repo) |

**TestBridge** is a custom XCUITest HTTP bridge included in the `testbridge/` directory. It starts an HTTP server on `localhost:8615` giving the Python agent full control of a running simulator. No external dependencies — just Xcode.

**XcodeBuildMCP** is a third-party CLI by [Sentry](https://github.com/getsentry/XcodeBuildMCP) with 59+ tools for Xcode automation, including real device support.

## Architecture

```
src/iostestagents/
├── cli.py                    # Typer CLI
├── agent/
│   ├── loop.py               # Core observe → reason → act loop
│   ├── prompts.py            # LLM prompt templates
│   ├── models.py             # Pydantic action/result models
│   └── ui_parser.py          # Accessibility tree parser
├── device/
│   ├── base.py               # DeviceBackend protocol
│   ├── xcodebuildmcp.py      # XcodeBuildMCP backend
│   ├── bridge.py             # TestBridge backend
│   ├── simulator.py          # Simulator lifecycle (simctl)
│   └── idb.py                # Legacy idb fallback
├── llm/
│   ├── base.py               # LLM provider protocol
│   ├── openai.py             # OpenAI provider
│   ├── anthropic.py          # Anthropic provider
│   ├── ollama.py             # Ollama (local) provider
│   └── registry.py           # Provider auto-detection
├── orchestrator/             # Multi-device coordination
│   ├── coordinator.py
│   ├── scenario.py
│   └── sync.py
└── util/
    └── logging.py
```

## Development

```bash
# Run tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Check environment
uv run iostestagents doctor
```

## Limitations

- macOS only (requires Xcode and iOS simulators)
- Each simulator uses ~2GB RAM — a MacBook can handle 3-4 concurrent simulators, a Mac Studio 8+
- LLM agents are non-deterministic — the same goal may produce different action sequences across runs
- System dialogs (Mail compose, Share Sheet) are generally not automatable
- SwiftUI views may need `.accessibilityIdentifier()` for reliable element targeting
- `describe_ui` can take 1-3 seconds on complex view hierarchies
- Local models (7-8B) struggle with complex navigation — use cloud models for production

## Related Projects

- [XcodeBuildMCP](https://github.com/getsentry/XcodeBuildMCP) — MCP server and CLI for Xcode automation (used as a backend)
- [DroidRun](https://github.com/droidrun/droidrun) — Similar concept for Android
- [Arbigent](https://github.com/takahirom/arbigent) — AI agent for testing Android, iOS, and Web apps
- [Xcode MCP Bridge](https://developer.apple.com/documentation/xcode/giving-agentic-coding-tools-access-to-xcode) — Apple's native MCP for coding workflows (different niche — builds/tests, not UI automation)

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

# MobileTestAI Usage Guide

AI-powered iOS app testing. Point it at a simulator app, describe what you want tested in plain English, and an LLM agent navigates the UI autonomously.

## Prerequisites

- macOS with Xcode 26+
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- At least one LLM provider (see below)
- At least one device backend (see below)

## Quick Start

```bash
cd /path/to/iOSTestAgents
uv sync --extra dev

# Check everything is configured
uv run iostestagents doctor

# Run a test
uv run iostestagents run \
  --device "iPhone 16" \
  --app com.apple.Preferences \
  --goal "Navigate to General > About"
```

## LLM Providers

MobileTestAI uses an LLM to read the UI accessibility tree (and optionally screenshots) and decide actions. It auto-detects which provider to use based on what's available.

### Ollama (local, free) — Recommended for getting started

```bash
# Install Ollama: https://ollama.com
ollama pull qwen3:8b         # fast text model (default, recommended)
ollama pull qwen3-vl         # optional: vision model for screenshot analysis
```

The default model is `qwen3:8b` — a fast text model that works from the accessibility tree alone. This is plenty for most UI testing tasks and runs in ~15-20 seconds per step on Apple Silicon.

For vision support (sending screenshots to the model), use `--model qwen3-vl` but note this is significantly slower (~2 min/step) and requires `--no-vision` to be omitted.

No API key needed. MobileTestAI detects Ollama automatically when it's running on localhost:11434.

### Anthropic (Claude)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### OpenAI

```bash
export OPENAI_API_KEY="sk-..."
```

You can override the auto-detected provider with `--provider`:

```bash
uv run iostestagents run --provider ollama --model qwen3-vl ...
```

## Device Backends

A backend is what actually taps buttons and reads the screen on the simulator. Two options:

### TestBridge (default)

Our built-in XCUITest HTTP server. Zero external dependencies beyond Xcode. Starts automatically when you run a test.

```bash
uv run iostestagents run --backend testbridge ...
```

### XcodeBuildMCP

Third-party CLI by Sentry with 59+ tools. Supports real devices, debugging, and more.

```bash
npm install -g xcodebuildmcp@latest
uv run iostestagents run --backend xcodebuildmcp ...
```

## Commands

### `run` — Execute a test

```bash
uv run iostestagents run [OPTIONS]
```

| Option | Short | Description |
|---|---|---|
| `--device` | `-d` | Simulator device name (required) |
| `--app` | `-a` | App bundle identifier (required) |
| `--goal` | `-g` | What to test, in plain English (required) |
| `--backend` | `-b` | `testbridge` or `xcodebuildmcp` (default: `testbridge`) |
| `--model` | | LLM model override (e.g. `qwen3:8b`, `qwen3-vl`, `claude-sonnet-4-5-20250929`) |
| `--provider` | | Force LLM provider: `anthropic`, `openai`, `ollama` |
| `--no-vision` | | Skip sending screenshots to the LLM (use accessibility tree only, much faster) |
| `--max-steps` | | Max agent actions before giving up (default: 20) |
| `--step-delay` | | Seconds between actions (default: 1.5) |
| `--output` | `-o` | Directory for screenshots/logs (default: `output/`) |
| `--record` | | Record simulator screen to MP4 |
| `--no-reset` | | Skip app terminate/relaunch before the run |
| `--app-path` | | Path to `.app` bundle for reinstall |
| `--verbose` | `-v` | Show debug-level logs |

### `doctor` — Check setup

```bash
uv run iostestagents doctor
```

Verifies: Xcode CLI tools, device backends, available simulators, and LLM providers.

## Examples

**Navigate Settings:**
```bash
uv run iostestagents run \
  -d "iPhone 16" \
  -a com.apple.Preferences \
  -g "Navigate to General > About"
```

**Test Safari:**
```bash
uv run iostestagents run \
  -d "iPhone 16" \
  -a com.apple.mobilesafari \
  -g "Open Safari and navigate to apple.com"
```

**Use a specific model with recording:**
```bash
uv run iostestagents run \
  -d "iPhone 16 Pro" \
  -a com.example.myapp \
  -g "Log in with username 'test' and password 'test123'" \
  --model qwen3-vl \
  --record \
  --verbose
```

**Use XcodeBuildMCP backend:**
```bash
uv run iostestagents run \
  -d "iPhone 16" \
  -a com.apple.Preferences \
  -g "Toggle Wi-Fi off and back on" \
  --backend xcodebuildmcp
```

## Output

Each run creates files in the output directory (default `output/`):

- `<run_id>_step001.png`, `_step002.png`, ... — screenshot per step
- `<run_id>_result.json` — full result with steps, actions, tokens, cost
- `<run_id>_recording.mp4` — screen recording (if `--record`)
- `testbridge.log` — TestBridge build/server log (if using testbridge backend)

## Tips

- **Always use `doctor` first** to verify your setup before running tests.
- **System apps** (Settings, Safari, etc.) work out of the box — no `--app-path` needed.
- **Custom apps** need to be installed first. Pass `--app-path /path/to/YourApp.app` and the framework will install it on the simulator.
- **If the agent gets stuck**, try increasing `--max-steps` or rephrasing the goal to be more specific.
- **Lower `--step-delay`** (e.g. `0.5`) for faster runs, increase it if the app needs time to animate or load.
- **Ollama performance** depends on your hardware. On Apple Silicon Macs, `qwen3-vl` runs well for basic navigation tasks.

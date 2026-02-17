# mobiletestai

AI-powered iOS app testing framework. Give it a natural language goal, and it will observe the simulator's UI, reason about what to do via Claude, and execute actions to accomplish the goal.

## Prerequisites

- macOS with Xcode and iOS simulators installed
- [idb](https://fbidb.io/) (`brew install idb-companion`)
- Python 3.11+
- `ANTHROPIC_API_KEY` environment variable set

## Installation

```bash
uv sync --extra dev
```

## Quick Start

Check your environment:

```bash
uv run mobiletestai doctor
```

Run a test:

```bash
uv run mobiletestai run \
  --device "iPhone 16" \
  --app com.apple.Preferences \
  --goal "Navigate to General settings"
```

## CLI Options

```
mobiletestai run
  --device, -d    Simulator device name (required)
  --app, -a       App bundle identifier (required)
  --goal, -g      Natural language test goal (required)
  --max-steps     Maximum agent steps (default: 20)
  --model         Claude model to use (default: claude-sonnet-4-5-20250929)
  --output, -o    Output directory (default: output)
  --verbose, -v   Verbose logging
  --step-delay    Delay between steps in seconds (default: 1.5)
  --record        Record screen video
  --no-reset      Skip app reset before run
  --app-path      Path to .app for reinstall during reset
```

## How It Works

Each step of the agent loop:

1. **Observe** — captures the UI accessibility tree (via idb) and a screenshot
2. **Reason** — sends both to Claude with the goal and action history
3. **Act** — executes the chosen action (tap, swipe, type, etc.) on the simulator
4. **Check** — if the agent says "done" or "fail", the run ends; otherwise continues

## Development

```bash
uv run pytest              # Run unit tests
uv run mobiletestai doctor # Verify environment
uv add <package>           # Add a dependency
```

# Contributing to MobileTestAI

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/TomMcGrath7/MobileAppTesterAgent.git
cd MobileAppTesterAgent

# Install dependencies
uv sync --extra dev

# Verify your environment
uv run mobiletestai doctor

# Run tests
uv run pytest -v
```

### Prerequisites

- macOS with Xcode 26+ and iOS simulators
- Python 3.11+
- Node.js (for XcodeBuildMCP backend)
- [uv](https://docs.astral.sh/uv/) package manager

## How to Contribute

### Reporting Bugs

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your environment (macOS version, Xcode version, Python version)

### Suggesting Features

Open an issue describing the feature and why it would be useful. For multi-device orchestration ideas, include a sample YAML scenario if possible.

### Submitting Changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add or update tests as needed
4. Run `uv run pytest` and make sure all tests pass
5. Open a pull request

### Code Style

- Python 3.11+ with type hints
- Keep functions focused and small
- Agent code should never import a specific device backend directly — always use the `DeviceBackend` protocol

## Project Structure

- `src/mobiletestai/agent/` — LLM agent loop and prompts
- `src/mobiletestai/device/` — Device backend implementations
- `src/mobiletestai/llm/` — LLM provider integrations
- `src/mobiletestai/orchestrator/` — Multi-device coordination
- `testbridge/` — Swift XCUITest HTTP bridge
- `scenarios/` — Example YAML test scenarios
- `tests/` — pytest test suite

## Areas Where Help is Appreciated

- Adding new LLM provider integrations
- Improving the accessibility tree parser for complex UIs
- Writing example scenarios for popular apps
- Documentation and tutorials
- Android support (long-term goal)

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

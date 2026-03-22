# Changelog

## 0.1.0 (2026-02-18)

Initial release.

- Core agent loop: observe UI, reason with LLM, act on simulator
- Two device backends: XcodeBuildMCP (CLI) and TestBridge (XCUITest HTTP bridge)
- Three LLM providers: OpenAI, Anthropic, Ollama (local)
- Multi-device orchestration with YAML scenarios
- Cross-device variable passing (capture values from one device, inject into another)
- Barrier synchronization for multi-player test steps
- CLI with `run`, `scenario`, and `doctor` commands
- Screen recording support
- 80+ unit tests

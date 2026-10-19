# Changelog

## Unreleased

## 0.3.0 (2026-10-19)

Found by running the agent against ThoughtScape, an on-device iOS app.

- **`claude-cli` provider**: `--provider claude-cli` runs each step through the
  local `claude -p`, billed to a Claude subscription instead of per token. It
  takes the loop's content blocks (text and screenshots) as they are, with no
  tools, no user settings and no MCP servers. Never auto-detected: pass it.
- **System sheets**: a sheet drawn outside the app (Health access, permission
  alerts) leaves the app's accessibility tree empty, and the agent spent all 40
  steps tapping element numbers that did not exist. With nothing tappable, the
  step now always carries the screenshot and the prompt offers tapping by x/y
  in screen points.
- **Off-screen elements**: an element below the fold was tapped at its
  off-screen center, which landed on whatever sat at the screen edge (a Pro row
  that opened a paywall). Off-screen elements are now listed but marked, and
  cannot be tapped until the agent scrolls them into view.

## 0.2.0 (2026-06-12)

LLM layer modernization.

- **Structured outputs**: Anthropic (`client.messages.parse`) and OpenAI
  (`client.beta.chat.completions.parse`) now return schema-validated
  `AgentAction` objects directly — no markdown-fence stripping, no JSON
  retries on the happy path. New `LLMProvider.chat_structured()` method with a
  `supports_structured_output` capability flag; Ollama keeps the text +
  `_parse_action` fallback path. Action-name aliases (`click`→`tap`,
  `scroll_down`→`swipe_down`, `back`→`press_button`, …) moved into the
  `AgentAction` model so both paths normalize them.
- **Current models + per-model pricing**: Anthropic default is now
  `claude-opus-4-8` ($5/$25 per 1M tokens). Pricing is a per-model table
  (`claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5` — the cheap
  per-step option at $1/$5) keyed by the model actually used per step; unknown
  models fall back to opus-4-8 rates with a warning. Provider-level
  `cost_per_input_token`/`cost_per_output_token` properties replaced by
  `estimate_cost()`. OpenAI default updated from `gpt-4o` to `gpt-5.4`
  ($2.50/$15 — same input price as gpt-4o; `gpt-5.5` is the $5/$30 flagship).
  `anthropic` dependency floor bumped to 0.109.1; `openai` to 1.50 (needed for
  the structured-output parse API).
- **Quality tooling**: ruff (lint + format) and mypy now gate CI alongside the
  test suite, with coverage enforced at 78% via pytest-cov. CI lint/test jobs
  moved to ubuntu runners (unit tests are fully mocked) with a single macOS
  job kept as a platform backstop. Dependabot configured for weekly grouped
  Python and GitHub Actions updates. Fixed a protocol mismatch mypy surfaced:
  `DeviceBackend.is_running` was declared static but implemented as an
  instance method.
- **Prompt caching**: the system prompt is sent as a content-block list with
  `cache_control: {type: ephemeral}`. `cache_read_input_tokens` /
  `cache_creation_input_tokens` are logged per call, tracked in `TokenUsage`,
  and priced in cost estimates (reads at 0.1x input rate, writes at 1.25x).

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

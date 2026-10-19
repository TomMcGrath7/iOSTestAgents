"""Claude via the local `claude` CLI (`claude -p`), billed to a Claude subscription."""

from __future__ import annotations

import json
import shutil
import subprocess

from iostestagents.llm.base import LLMProvider, LLMResponse
from iostestagents.util.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT_S = 180


def _build_command(model: str, system: str) -> list[str]:
    # --tools "" leaves the model with no tools: it only answers. The empty
    # setting sources and strict MCP config keep the user's own hooks, CLAUDE.md
    # and MCP servers out of every step.
    return [
        "claude",
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--system-prompt",
        system,
        "--tools",
        "",
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]


def _build_stdin(messages_content: list[dict]) -> str:
    # The agent loop already builds Anthropic-format content blocks (text and
    # base64 images), which stream-json input takes as they are.
    message = {"type": "user", "message": {"role": "user", "content": messages_content}}
    return json.dumps(message) + "\n"


def _parse_result(stdout: str) -> dict:
    """Return the final `result` event from a stream-json transcript."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            if event.get("is_error"):
                raise RuntimeError(f"claude CLI returned an error: {event.get('result')!r}")
            return event
    raise RuntimeError("claude CLI produced no result event")


class ClaudeCliProvider(LLMProvider):
    def __init__(self) -> None:
        if shutil.which("claude") is None:
            raise RuntimeError("The claude CLI is not on PATH. Install Claude Code and log in.")

    @property
    def name(self) -> str:
        return "claude-cli"

    @property
    def default_model(self) -> str:
        return "sonnet"

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_input_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
    ) -> float:
        return 0.0  # billed to the subscription, not per token

    def chat(
        self,
        model: str,
        system: str,
        messages_content: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        try:
            proc = subprocess.run(
                _build_command(model, system),
                input=_build_stdin(messages_content),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"claude CLI timed out after {_TIMEOUT_S}s") from e
        if proc.returncode != 0 and not proc.stdout:
            raise RuntimeError(f"claude CLI exited {proc.returncode}: {proc.stderr.strip()[:500]}")

        event = _parse_result(proc.stdout)
        usage = event.get("usage") or {}
        logger.info(f"claude CLI usage: input={usage.get('input_tokens', 0)}, output={usage.get('output_tokens', 0)}")
        return LLMResponse(
            text=event.get("result", ""),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
            cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
        )

"""Provider registry and auto-detection."""

from __future__ import annotations

import os
import urllib.request

from mobiletestai.llm.base import LLMProvider

ENV_KEYS: dict[str, str | None] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "ollama": None,
}


def _ollama_available() -> bool:
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/version", method="GET"
        )
        with urllib.request.urlopen(req, timeout=2):
            return True
    except Exception:
        return False


def _create_provider(name: str) -> LLMProvider:
    if name == "anthropic":
        from mobiletestai.llm.anthropic import AnthropicProvider

        return AnthropicProvider()
    elif name == "openai":
        from mobiletestai.llm.openai import OpenAIProvider

        return OpenAIProvider()
    elif name == "ollama":
        from mobiletestai.llm.ollama import OllamaProvider

        return OllamaProvider()
    else:
        raise ValueError(f"Unknown provider: {name!r}. Choose from: anthropic, openai, ollama")


def get_provider(name: str | None = None) -> LLMProvider:
    """Get an LLM provider by name, or auto-detect from environment."""
    if name is not None:
        return _create_provider(name)

    # Auto-detect
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _create_provider("anthropic")
    if os.environ.get("OPENAI_API_KEY"):
        return _create_provider("openai")
    if _ollama_available():
        return _create_provider("ollama")

    raise RuntimeError(
        "No LLM provider available. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
        "or start Ollama locally."
    )

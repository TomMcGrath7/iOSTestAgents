"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

import anthropic

from mobiletestai.llm.base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = anthropic.Anthropic()

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def default_model(self) -> str:
        return "claude-sonnet-4-5-20250929"

    @property
    def cost_per_input_token(self) -> float:
        return 3.0 / 1_000_000

    @property
    def cost_per_output_token(self) -> float:
        return 15.0 / 1_000_000

    def chat(
        self,
        model: str,
        system: str,
        messages_content: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": messages_content}],
        )
        return LLMResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

from typing import cast

import anthropic
from anthropic.types import MessageParam, TextBlockParam
from pydantic import BaseModel

from iostestagents.llm.base import LLMProvider, LLMResponse, StructuredLLMResponse
from iostestagents.util.logging import get_logger

logger = get_logger(__name__)

# USD per 1M tokens: (input, output). Model IDs are current as of mid-2026.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

_FALLBACK_PRICING_MODEL = "claude-opus-4-8"

# Cache reads bill at 0.1x the input rate; cache writes at 1.25x.
CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25


def get_model_pricing(model: str) -> tuple[float, float]:
    """Look up (input, output) USD-per-1M-token rates for a model.

    Date-suffixed IDs (e.g. claude-haiku-4-5-20251001) match their base
    model. Unknown models fall back to opus-4-8 rates with a warning.
    """
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    for known, pricing in MODEL_PRICING.items():
        if model.startswith(known):
            return pricing
    logger.warning(f"No pricing for Anthropic model {model!r} — falling back to {_FALLBACK_PRICING_MODEL} rates")
    return MODEL_PRICING[_FALLBACK_PRICING_MODEL]


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = anthropic.Anthropic()

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def default_model(self) -> str:
        return "claude-opus-4-8"

    @property
    def supports_structured_output(self) -> bool:
        return True

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_input_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
    ) -> float:
        input_rate, output_rate = get_model_pricing(model)
        return (
            input_tokens * input_rate
            + cache_read_input_tokens * input_rate * CACHE_READ_MULTIPLIER
            + cache_creation_input_tokens * input_rate * CACHE_WRITE_MULTIPLIER
            + output_tokens * output_rate
        ) / 1_000_000

    @staticmethod
    def _cached_system(system: str) -> list[TextBlockParam]:
        # cache_control marks the system prompt as a reusable cached prefix.
        # Prompts below the model's minimum cacheable length silently don't
        # cache — the marker is harmless in that case.
        return [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    @staticmethod
    def _user_message(messages_content: list[dict]) -> MessageParam:
        # Content blocks are built dynamically by the agent loop; cast to the
        # SDK's message param type at this boundary.
        return cast(MessageParam, {"role": "user", "content": messages_content})

    @staticmethod
    def _usage_tokens(response) -> tuple[int, int, int, int]:
        usage = response.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        logger.info(
            f"Anthropic usage: input={input_tokens}, output={output_tokens}, "
            f"cache_read={cache_read}, cache_creation={cache_creation}"
        )
        return input_tokens, output_tokens, cache_read, cache_creation

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
            system=self._cached_system(system),
            messages=[self._user_message(messages_content)],
        )
        input_tokens, output_tokens, cache_read, cache_creation = self._usage_tokens(response)
        text = next((block.text for block in response.content if block.type == "text"), "")
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        )

    def chat_structured(
        self,
        model: str,
        system: str,
        messages_content: list[dict],
        output_model: type[BaseModel],
        max_tokens: int,
    ) -> StructuredLLMResponse:
        response = self._client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=self._cached_system(system),
            messages=[self._user_message(messages_content)],
            output_format=output_model,
        )
        input_tokens, output_tokens, cache_read, cache_creation = self._usage_tokens(response)
        return StructuredLLMResponse(
            parsed=response.parsed_output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        )

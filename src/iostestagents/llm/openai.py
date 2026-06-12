"""OpenAI LLM provider."""

from __future__ import annotations

from typing import cast

import openai
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from iostestagents.llm.base import LLMProvider, LLMResponse, StructuredLLMResponse

# USD per 1M tokens: (input, output)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
}

_DEFAULT_PRICING = (2.50, 15.00)


def _translate_content(messages_content: list[dict]) -> list[dict]:
    """Translate Anthropic-style content blocks to OpenAI format."""
    parts = []
    for block in messages_content:
        if block.get("type") == "text":
            parts.append({"type": "text", "text": block["text"]})
        elif block.get("type") == "image":
            source = block["source"]
            media_type = source.get("media_type", "image/png")
            data = source["data"]
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{data}"},
                }
            )
    return parts


class OpenAIProvider(LLMProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        kwargs: dict = {}
        if base_url:
            kwargs["base_url"] = base_url
        if api_key:
            kwargs["api_key"] = api_key
        self._client = openai.OpenAI(**kwargs)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def default_model(self) -> str:
        # Current-generation general model at gpt-4o's old price point.
        # gpt-5.5 ($5/$30) is the premium flagship — pass it via --model.
        return "gpt-5.4"

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
        input_rate, output_rate = MODEL_PRICING.get(model, _DEFAULT_PRICING)
        return (
            input_tokens * input_rate
            + cache_read_input_tokens * input_rate * 0.1
            + cache_creation_input_tokens * input_rate
            + output_tokens * output_rate
        ) / 1_000_000

    def _build_messages(self, system: str, messages_content: list[dict]) -> list[ChatCompletionMessageParam]:
        # The content blocks are built dynamically from Anthropic-style dicts;
        # cast to the SDK's message param type at this boundary.
        return cast(
            "list[ChatCompletionMessageParam]",
            [
                {"role": "system", "content": system},
                {"role": "user", "content": _translate_content(messages_content)},
            ],
        )

    def chat(
        self,
        model: str,
        system: str,
        messages_content: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=model,
            max_completion_tokens=max_tokens,
            messages=self._build_messages(system, messages_content),
        )
        usage = response.usage
        return LLMResponse(
            text=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    def chat_structured(
        self,
        model: str,
        system: str,
        messages_content: list[dict],
        output_model: type[BaseModel],
        max_tokens: int,
    ) -> StructuredLLMResponse:
        completion = self._client.beta.chat.completions.parse(
            model=model,
            max_completion_tokens=max_tokens,
            messages=self._build_messages(system, messages_content),
            response_format=output_model,
        )
        usage = completion.usage
        return StructuredLLMResponse(
            parsed=completion.choices[0].message.parsed,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

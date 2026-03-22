"""OpenAI LLM provider."""

from __future__ import annotations

import openai

from iostestagents.llm.base import LLMProvider, LLMResponse


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
        return "gpt-4o"

    @property
    def cost_per_input_token(self) -> float:
        return 2.50 / 1_000_000

    @property
    def cost_per_output_token(self) -> float:
        return 10.0 / 1_000_000

    def chat(
        self,
        model: str,
        system: str,
        messages_content: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": _translate_content(messages_content)},
        ]
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
        usage = response.usage
        return LLMResponse(
            text=response.choices[0].message.content,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

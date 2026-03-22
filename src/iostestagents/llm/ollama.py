"""Ollama LLM provider using native Ollama API with thinking disabled."""

from __future__ import annotations

import json
import urllib.request
import urllib.error

from iostestagents.llm.base import LLMProvider, LLMResponse
from iostestagents.util.logging import get_logger

logger = get_logger(__name__)

_OLLAMA_BASE = "http://localhost:11434"


def _translate_to_ollama_content(messages_content: list[dict]) -> str | list[dict]:
    """Translate content blocks to Ollama native format.

    For text-only messages, return a plain string.
    For messages with images, return Ollama's images + content format.
    """
    images = []
    text_parts = []
    for block in messages_content:
        if block.get("type") == "text":
            text_parts.append(block["text"])
        elif block.get("type") == "image":
            # Ollama native API takes base64 images directly
            images.append(block["source"]["data"])

    text = "\n\n".join(text_parts)
    if images:
        return {"content": text, "images": images}
    return text


class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def default_model(self) -> str:
        return "qwen3:8b"

    @property
    def cost_per_input_token(self) -> float:
        return 0.0

    @property
    def cost_per_output_token(self) -> float:
        return 0.0

    def chat(
        self,
        model: str,
        system: str,
        messages_content: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        # Build user message (text or text+images)
        user_payload = _translate_to_ollama_content(messages_content)

        user_msg: dict = {"role": "user"}
        if isinstance(user_payload, dict):
            user_msg["content"] = user_payload["content"]
            user_msg["images"] = user_payload["images"]
        else:
            user_msg["content"] = user_payload

        body = {
            "model": model,
            "stream": False,
            "think": False,
            "options": {"num_predict": max_tokens},
            "messages": [
                {"role": "system", "content": system},
                user_msg,
            ],
        }

        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{_OLLAMA_BASE}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read())
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama not reachable at {_OLLAMA_BASE}: {exc}") from exc

        text = result.get("message", {}).get("content", "")
        eval_count = result.get("eval_count", 0)
        prompt_eval_count = result.get("prompt_eval_count", 0)

        logger.info(
            f"Ollama response: content_len={len(text)}, "
            f"done_reason={result.get('done_reason')}, "
            f"eval_count={eval_count}"
        )

        return LLMResponse(
            text=text,
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
        )

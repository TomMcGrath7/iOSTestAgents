"""Base LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class StructuredLLMResponse:
    """Response from a schema-enforced chat call. `parsed` is a validated
    instance of the Pydantic model passed as `output_model`."""

    parsed: Any
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class LLMProvider(ABC):
    @abstractmethod
    def chat(
        self,
        model: str,
        system: str,
        messages_content: list[dict],
        max_tokens: int,
    ) -> LLMResponse: ...

    @property
    def supports_structured_output(self) -> bool:
        """Whether chat_structured() is available for this provider."""
        return False

    def chat_structured(
        self,
        model: str,
        system: str,
        messages_content: list[dict],
        output_model: type[BaseModel],
        max_tokens: int,
    ) -> StructuredLLMResponse:
        """Schema-enforced chat: the provider guarantees the response parses
        into `output_model`. Only available when supports_structured_output."""
        raise NotImplementedError(f"{self.name} provider does not support structured output")

    @property
    @abstractmethod
    def default_model(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_input_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
    ) -> float:
        """Estimate USD cost for a call, priced by the model actually used."""
        ...

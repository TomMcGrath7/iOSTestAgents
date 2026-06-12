"""Tests for the LLM provider abstraction."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from iostestagents.agent.models import ActionType, AgentAction
from iostestagents.llm.anthropic import AnthropicProvider, get_model_pricing
from iostestagents.llm.base import LLMResponse, StructuredLLMResponse
from iostestagents.llm.ollama import OllamaProvider, _translate_to_ollama_content
from iostestagents.llm.openai import OpenAIProvider, _translate_content
from iostestagents.llm.registry import get_provider


class TestLLMResponse:
    def test_fields(self):
        r = LLMResponse(text="hello", input_tokens=10, output_tokens=5)
        assert r.text == "hello"
        assert r.input_tokens == 10
        assert r.output_tokens == 5
        assert r.cache_read_input_tokens == 0
        assert r.cache_creation_input_tokens == 0

    def test_structured_fields(self):
        action = AgentAction(action=ActionType.DONE, message="ok")
        r = StructuredLLMResponse(parsed=action, input_tokens=10, output_tokens=5)
        assert r.parsed is action
        assert r.cache_read_input_tokens == 0


class TestTranslateContent:
    def test_text_block(self):
        blocks = [{"type": "text", "text": "hello"}]
        result = _translate_content(blocks)
        assert result == [{"type": "text", "text": "hello"}]

    def test_image_block(self):
        blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": "AAAA",
                },
            }
        ]
        result = _translate_content(blocks)
        assert len(result) == 1
        assert result[0]["type"] == "image_url"
        assert result[0]["image_url"]["url"] == "data:image/png;base64,AAAA"

    def test_mixed_blocks(self):
        blocks = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": "XX"},
            },
            {"type": "text", "text": "describe this"},
        ]
        result = _translate_content(blocks)
        assert len(result) == 2
        assert result[0]["type"] == "image_url"
        assert result[1]["type"] == "text"


class TestOllamaTranslateContent:
    def test_text_only(self):
        blocks = [{"type": "text", "text": "hello"}]
        result = _translate_to_ollama_content(blocks)
        assert result == "hello"

    def test_with_image(self):
        blocks = [
            {"type": "image", "source": {"data": "AAAA"}},
            {"type": "text", "text": "describe"},
        ]
        result = _translate_to_ollama_content(blocks)
        assert isinstance(result, dict)
        assert result["content"] == "describe"
        assert result["images"] == ["AAAA"]

    def test_multiple_text(self):
        blocks = [
            {"type": "text", "text": "part 1"},
            {"type": "text", "text": "part 2"},
        ]
        result = _translate_to_ollama_content(blocks)
        assert "part 1" in result
        assert "part 2" in result


class TestProviderProperties:
    @patch("iostestagents.llm.anthropic.anthropic.Anthropic")
    def test_anthropic_defaults(self, mock_cls):
        p = AnthropicProvider()
        assert p.name == "anthropic"
        assert p.default_model == "claude-opus-4-8"
        assert p.supports_structured_output is True

    @patch("iostestagents.llm.openai.openai.OpenAI")
    def test_openai_defaults(self, mock_cls):
        p = OpenAIProvider()
        assert p.name == "openai"
        assert p.default_model == "gpt-5.4"
        assert p.supports_structured_output is True

    def test_ollama_defaults(self):
        p = OllamaProvider()
        assert p.name == "ollama"
        assert p.default_model == "qwen3:8b"
        assert p.supports_structured_output is False
        assert p.estimate_cost("qwen3:8b", 1000, 1000) == 0.0

    def test_ollama_structured_not_implemented(self):
        p = OllamaProvider()
        with pytest.raises(NotImplementedError):
            p.chat_structured("qwen3:8b", "sys", [], AgentAction, 1024)


class TestAnthropicPricing:
    def test_known_model_pricing(self):
        assert get_model_pricing("claude-opus-4-8") == (5.00, 25.00)
        assert get_model_pricing("claude-sonnet-4-6") == (3.00, 15.00)
        assert get_model_pricing("claude-haiku-4-5") == (1.00, 5.00)

    def test_date_suffixed_model_matches_base(self):
        assert get_model_pricing("claude-haiku-4-5-20251001") == (1.00, 5.00)

    def test_unknown_model_falls_back_to_opus_with_warning(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            pricing = get_model_pricing("claude-future-9")
        assert pricing == (5.00, 25.00)
        assert any("No pricing" in r.message for r in caplog.records)

    @patch("iostestagents.llm.anthropic.anthropic.Anthropic")
    def test_estimate_cost_per_model(self, mock_cls):
        p = AnthropicProvider()
        # 1M input + 1M output at opus rates
        assert p.estimate_cost("claude-opus-4-8", 1_000_000, 1_000_000) == pytest.approx(30.0)
        # haiku is the cheap option
        assert p.estimate_cost("claude-haiku-4-5", 1_000_000, 1_000_000) == pytest.approx(6.0)

    @patch("iostestagents.llm.anthropic.anthropic.Anthropic")
    def test_estimate_cost_cache_read_at_tenth_input_rate(self, mock_cls):
        p = AnthropicProvider()
        # 1M cache-read tokens on sonnet = $3.00 * 0.1 = $0.30
        cost = p.estimate_cost("claude-sonnet-4-6", 0, 0, cache_read_input_tokens=1_000_000)
        assert cost == pytest.approx(0.30)

    @patch("iostestagents.llm.anthropic.anthropic.Anthropic")
    def test_estimate_cost_cache_write_at_1_25x_input_rate(self, mock_cls):
        p = AnthropicProvider()
        cost = p.estimate_cost("claude-opus-4-8", 0, 0, cache_creation_input_tokens=1_000_000)
        assert cost == pytest.approx(6.25)


def _mock_anthropic_usage(input_tokens=100, output_tokens=20, cache_read=0, cache_creation=0):
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_read_input_tokens = cache_read
    usage.cache_creation_input_tokens = cache_creation
    return usage


class TestAnthropicChat:
    @patch("iostestagents.llm.anthropic.anthropic.Anthropic")
    def test_chat_sends_system_with_cache_control(self, mock_cls):
        client = mock_cls.return_value
        response = MagicMock()
        response.content = [MagicMock(type="text", text='{"action": "done"}')]
        response.usage = _mock_anthropic_usage(cache_read=500)
        client.messages.create.return_value = response

        p = AnthropicProvider()
        result = p.chat("claude-opus-4-8", "you are a tester", [{"type": "text", "text": "hi"}], 1024)

        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["system"] == [
            {
                "type": "text",
                "text": "you are a tester",
                "cache_control": {"type": "ephemeral"},
            }
        ]
        assert result.text == '{"action": "done"}'
        assert result.cache_read_input_tokens == 500

    @patch("iostestagents.llm.anthropic.anthropic.Anthropic")
    def test_chat_structured_returns_parsed_action(self, mock_cls):
        client = mock_cls.return_value
        action = AgentAction(action=ActionType.TAP, element=3, reasoning="tap it")
        response = MagicMock()
        response.parsed_output = action
        response.usage = _mock_anthropic_usage(input_tokens=200, output_tokens=30, cache_read=150)
        client.messages.parse.return_value = response

        p = AnthropicProvider()
        result = p.chat_structured("claude-opus-4-8", "system", [{"type": "text", "text": "next?"}], AgentAction, 1024)

        kwargs = client.messages.parse.call_args.kwargs
        assert kwargs["output_format"] is AgentAction
        assert kwargs["model"] == "claude-opus-4-8"
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert result.parsed is action
        assert result.parsed.element == 3
        assert result.input_tokens == 200
        assert result.cache_read_input_tokens == 150

    @patch("iostestagents.llm.anthropic.anthropic.Anthropic")
    def test_chat_handles_missing_cache_usage(self, mock_cls):
        """Older SDK usage objects without cache fields default to 0."""
        client = mock_cls.return_value
        usage = MagicMock(spec=["input_tokens", "output_tokens"])
        usage.input_tokens = 10
        usage.output_tokens = 5
        response = MagicMock()
        response.content = [MagicMock(type="text", text="ok")]
        response.usage = usage
        client.messages.create.return_value = response

        p = AnthropicProvider()
        result = p.chat("claude-opus-4-8", "sys", [{"type": "text", "text": "hi"}], 1024)
        assert result.cache_read_input_tokens == 0
        assert result.cache_creation_input_tokens == 0


class TestOpenAIStructured:
    @patch("iostestagents.llm.openai.openai.OpenAI")
    def test_chat_structured_returns_parsed_action(self, mock_cls):
        client = mock_cls.return_value
        action = AgentAction(action=ActionType.DONE, message="finished")
        completion = MagicMock()
        completion.choices = [MagicMock(message=MagicMock(parsed=action))]
        completion.usage = MagicMock(prompt_tokens=120, completion_tokens=25)
        client.beta.chat.completions.parse.return_value = completion

        p = OpenAIProvider()
        result = p.chat_structured("gpt-5.5", "system", [{"type": "text", "text": "next?"}], AgentAction, 1024)

        kwargs = client.beta.chat.completions.parse.call_args.kwargs
        assert kwargs["response_format"] is AgentAction
        assert kwargs["max_completion_tokens"] == 1024
        assert result.parsed is action
        assert result.input_tokens == 120
        assert result.output_tokens == 25


class TestOllamaChat:
    def test_chat_sends_correct_request(self):
        """Ollama chat sends native API request with think=False."""
        p = OllamaProvider()
        mock_response = json.dumps(
            {
                "message": {"role": "assistant", "content": '{"action": "done", "reasoning": "ok"}'},
                "done": True,
                "done_reason": "stop",
                "eval_count": 20,
                "prompt_eval_count": 100,
            }
        ).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = p.chat("qwen3:8b", "system prompt", [{"type": "text", "text": "test"}], 1024)

        assert result.text == '{"action": "done", "reasoning": "ok"}'
        assert result.input_tokens == 100
        assert result.output_tokens == 20

        # Verify the request body
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data)
        assert body["think"] is False
        assert body["stream"] is False
        assert body["model"] == "qwen3:8b"

    def test_chat_raises_on_connection_error(self):
        import urllib.error

        p = OllamaProvider()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with pytest.raises(RuntimeError, match="not reachable"):
                p.chat("qwen3:8b", "sys", [{"type": "text", "text": "t"}], 1024)


class TestRegistry:
    @patch("iostestagents.llm.anthropic.anthropic.Anthropic")
    def test_get_provider_by_name(self, mock_cls):
        p = get_provider("anthropic")
        assert isinstance(p, AnthropicProvider)

    def test_get_provider_unknown(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent")

    @patch("iostestagents.llm.anthropic.anthropic.Anthropic")
    def test_auto_detect_anthropic(self, mock_cls):
        env = os.environ.copy()
        env["ANTHROPIC_API_KEY"] = "test-key"
        env.pop("OPENAI_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            p = get_provider(None)
        assert isinstance(p, AnthropicProvider)

    @patch("iostestagents.llm.openai.openai.OpenAI")
    def test_auto_detect_openai(self, mock_cls):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env["OPENAI_API_KEY"] = "test-key"
        with patch.dict(os.environ, env, clear=True):
            p = get_provider(None)
        assert isinstance(p, OpenAIProvider)

    @patch("iostestagents.llm.registry._ollama_available", return_value=True)
    def test_auto_detect_ollama(self, mock_ollama):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            p = get_provider(None)
        assert isinstance(p, OllamaProvider)

    @patch("iostestagents.llm.registry._ollama_available", return_value=False)
    def test_auto_detect_none_raises(self, mock_ollama):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="No LLM provider available"):
                get_provider(None)

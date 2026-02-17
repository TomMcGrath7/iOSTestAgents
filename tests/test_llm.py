"""Tests for the LLM provider abstraction."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from mobiletestai.llm.base import LLMProvider, LLMResponse
from mobiletestai.llm.anthropic import AnthropicProvider
from mobiletestai.llm.openai import OpenAIProvider, _translate_content
from mobiletestai.llm.ollama import OllamaProvider, _translate_to_ollama_content
from mobiletestai.llm.registry import get_provider


class TestLLMResponse:
    def test_fields(self):
        r = LLMResponse(text="hello", input_tokens=10, output_tokens=5)
        assert r.text == "hello"
        assert r.input_tokens == 10
        assert r.output_tokens == 5


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
    @patch("mobiletestai.llm.anthropic.anthropic.Anthropic")
    def test_anthropic_defaults(self, mock_cls):
        p = AnthropicProvider()
        assert p.name == "anthropic"
        assert "claude" in p.default_model
        assert p.cost_per_input_token > 0

    @patch("mobiletestai.llm.openai.openai.OpenAI")
    def test_openai_defaults(self, mock_cls):
        p = OpenAIProvider()
        assert p.name == "openai"
        assert "gpt" in p.default_model
        assert p.cost_per_input_token > 0

    def test_ollama_defaults(self):
        p = OllamaProvider()
        assert p.name == "ollama"
        assert p.default_model == "qwen3:8b"
        assert p.cost_per_input_token == 0.0
        assert p.cost_per_output_token == 0.0


class TestOllamaChat:
    def test_chat_sends_correct_request(self):
        """Ollama chat sends native API request with think=False."""
        p = OllamaProvider()
        mock_response = json.dumps({
            "message": {"role": "assistant", "content": '{"action": "done", "reasoning": "ok"}'},
            "done": True,
            "done_reason": "stop",
            "eval_count": 20,
            "prompt_eval_count": 100,
        }).encode()

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
        p = OllamaProvider()
        with patch("urllib.request.urlopen", side_effect=Exception("refused")):
            with pytest.raises(Exception):
                p.chat("qwen3:8b", "sys", [{"type": "text", "text": "t"}], 1024)


class TestRegistry:
    @patch("mobiletestai.llm.anthropic.anthropic.Anthropic")
    def test_get_provider_by_name(self, mock_cls):
        p = get_provider("anthropic")
        assert isinstance(p, AnthropicProvider)

    def test_get_provider_unknown(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent")

    @patch("mobiletestai.llm.anthropic.anthropic.Anthropic")
    def test_auto_detect_anthropic(self, mock_cls):
        env = os.environ.copy()
        env["ANTHROPIC_API_KEY"] = "test-key"
        env.pop("OPENAI_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            p = get_provider(None)
        assert isinstance(p, AnthropicProvider)

    @patch("mobiletestai.llm.openai.openai.OpenAI")
    def test_auto_detect_openai(self, mock_cls):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env["OPENAI_API_KEY"] = "test-key"
        with patch.dict(os.environ, env, clear=True):
            p = get_provider(None)
        assert isinstance(p, OpenAIProvider)

    @patch("mobiletestai.llm.registry._ollama_available", return_value=True)
    def test_auto_detect_ollama(self, mock_ollama):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            p = get_provider(None)
        assert isinstance(p, OllamaProvider)

    @patch("mobiletestai.llm.registry._ollama_available", return_value=False)
    def test_auto_detect_none_raises(self, mock_ollama):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="No LLM provider available"):
                get_provider(None)

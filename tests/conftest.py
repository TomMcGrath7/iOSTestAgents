"""Shared test fixtures."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_subprocess_run():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        yield mock_run


@pytest.fixture
def simctl_devices_json():
    """Realistic xcrun simctl list devices output."""
    return json.dumps(
        {
            "devices": {
                "com.apple.CoreSimulator.SimRuntime.iOS-18-2": [
                    {
                        "name": "iPhone 16",
                        "udid": "AAAA-BBBB-CCCC-DDDD",
                        "state": "Shutdown",
                        "isAvailable": True,
                    },
                    {
                        "name": "iPhone 16 Pro",
                        "udid": "EEEE-FFFF-0000-1111",
                        "state": "Shutdown",
                        "isAvailable": True,
                    },
                ],
                "com.apple.CoreSimulator.SimRuntime.iOS-17-5": [
                    {
                        "name": "iPhone 16",
                        "udid": "OLD1-OLD2-OLD3-OLD4",
                        "state": "Shutdown",
                        "isAvailable": True,
                    },
                ],
            }
        }
    )


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider that returns a valid action JSON."""
    from iostestagents.llm.base import LLMResponse

    provider = MagicMock()
    provider.name = "mock"
    provider.default_model = "mock-model"
    provider.cost_per_input_token = 3.0 / 1_000_000
    provider.cost_per_output_token = 15.0 / 1_000_000
    provider.chat.return_value = LLMResponse(
        text='{"action": "done", "reasoning": "Goal achieved", "message": "Success"}',
        input_tokens=500,
        output_tokens=50,
    )
    with (
        patch("iostestagents.agent.loop.get_provider", return_value=provider),
        patch("iostestagents.agent.loop.BridgeDevice"),
    ):
        yield provider

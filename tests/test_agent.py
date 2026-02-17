"""Tests for agent models, prompts, and loop."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from mobiletestai.agent.models import ActionType, AgentAction, RunResult, StepRecord, TokenUsage
from mobiletestai.agent.prompts import build_user_prompt, SYSTEM_PROMPT
from mobiletestai.agent.loop import _parse_action, _execute_action, run_agent


class TestModels:
    def test_action_type_values(self):
        assert ActionType.TAP == "tap"
        assert ActionType.DONE == "done"
        assert ActionType.FAIL == "fail"

    def test_agent_action_tap(self):
        action = AgentAction(action=ActionType.TAP, reasoning="tap button", x=100, y=200)
        assert action.x == 100
        assert action.y == 200

    def test_agent_action_type_text(self):
        action = AgentAction(action=ActionType.TYPE, text="hello")
        assert action.text == "hello"

    def test_agent_action_done(self):
        action = AgentAction(action=ActionType.DONE, message="completed")
        assert action.message == "completed"

    def test_run_result_defaults(self):
        result = RunResult()
        assert result.status == "running"
        assert result.steps == []
        assert len(result.run_id) == 12

    def test_token_usage(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100


class TestPrompts:
    def test_system_prompt_has_actions(self):
        assert "tap" in SYSTEM_PROMPT.lower()
        assert "swipe_up" in SYSTEM_PROMPT
        assert "done" in SYSTEM_PROMPT.lower()
        assert "fail" in SYSTEM_PROMPT.lower()

    def test_build_user_prompt_basic(self):
        prompt = build_user_prompt(
            goal="Open settings",
            step=1,
            max_steps=10,
            action_history=[],
            ui_state="AXButton 'Settings'",
            element_list="[1] Button 'Settings' center=(196, 522)",
        )
        assert "Open settings" in prompt
        assert "1/10" in prompt
        assert "[1] Button 'Settings'" in prompt

    def test_build_user_prompt_with_history(self):
        history = [
            {"action": "tap", "reasoning": "tapped button"},
            {"action": "wait", "reasoning": "loading"},
        ]
        prompt = build_user_prompt(
            goal="test", step=3, max_steps=10,
            action_history=history, ui_state="tree",
        )
        assert "Recent actions" in prompt
        assert "tapped button" in prompt

    def test_build_user_prompt_stuck(self):
        prompt = build_user_prompt(
            goal="test", step=5, max_steps=10,
            action_history=[], ui_state="tree", ui_stuck=True,
        )
        assert "not changed" in prompt.lower() or "warning" in prompt.lower()

    def test_build_user_prompt_with_element_list(self):
        prompt = build_user_prompt(
            goal="test", step=1, max_steps=10,
            action_history=[], ui_state="tree",
            element_list="[1] Button 'OK' center=(40, 22)",
        )
        assert "Tappable elements" in prompt
        assert "[1] Button 'OK'" in prompt

    def test_build_user_prompt_with_error_in_history(self):
        history = [{"action": "tap", "reasoning": "try", "error": "element not found"}]
        prompt = build_user_prompt(
            goal="test", step=2, max_steps=10,
            action_history=history, ui_state="tree",
        )
        assert "ERROR" in prompt


class TestParseAction:
    def test_parse_valid_json(self):
        raw = '{"action": "tap", "reasoning": "click it", "x": 100, "y": 200}'
        action = _parse_action(raw)
        assert action.action == ActionType.TAP
        assert action.x == 100

    def test_parse_with_markdown_fences(self):
        raw = '```json\n{"action": "done", "reasoning": "done", "message": "ok"}\n```'
        action = _parse_action(raw)
        assert action.action == ActionType.DONE

    def test_parse_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_action("not json at all")

    def test_parse_invalid_action_type(self):
        with pytest.raises(Exception):
            _parse_action('{"action": "fly", "reasoning": "impossible"}')


    def test_parse_with_element_reference(self):
        from mobiletestai.agent.ui_parser import parse_ui_elements
        ui = "Cell 'General' {{0, 500}, {393, 44}}"
        elements = parse_ui_elements(ui)
        raw = '{"action": "tap", "element": 1, "reasoning": "tap General"}'
        action = _parse_action(raw, ui_elements=elements)
        assert action.action == ActionType.TAP
        assert action.x == 196
        assert action.y == 522

    def test_parse_with_target_name(self):
        from mobiletestai.agent.ui_parser import parse_ui_elements
        ui = "Button 'Back' {{0, 44}, {80, 44}}"
        elements = parse_ui_elements(ui)
        raw = '{"action": "tap", "target": "Back", "reasoning": "go back"}'
        action = _parse_action(raw, ui_elements=elements)
        assert action.action == ActionType.TAP
        assert action.x == 40
        assert action.y == 66

    def test_parse_element_without_ui_elements(self):
        """Element ref without ui_elements should not crash, just no coordinates."""
        raw = '{"action": "tap", "element": 1, "reasoning": "tap"}'
        action = _parse_action(raw)
        assert action.action == ActionType.TAP
        assert action.x is None


class TestExecuteAction:
    def test_execute_tap(self):
        idb = MagicMock()
        action = AgentAction(action=ActionType.TAP, x=50, y=100)
        _execute_action(action, idb)
        idb.tap.assert_called_once_with(50, 100)

    def test_execute_type(self):
        idb = MagicMock()
        action = AgentAction(action=ActionType.TYPE, text="hello")
        _execute_action(action, idb)
        idb.type_text.assert_called_once_with("hello")

    def test_execute_swipe_up(self):
        idb = MagicMock()
        action = AgentAction(action=ActionType.SWIPE_UP)
        _execute_action(action, idb)
        idb.swipe.assert_called_once()

    def test_execute_press_button(self):
        idb = MagicMock()
        action = AgentAction(action=ActionType.PRESS_BUTTON, button="HOME")
        _execute_action(action, idb)
        idb.press_button.assert_called_once_with("HOME")

    def test_execute_done_no_device_call(self):
        idb = MagicMock()
        action = AgentAction(action=ActionType.DONE, message="done")
        _execute_action(action, idb)
        idb.tap.assert_not_called()
        idb.swipe.assert_not_called()

    def test_execute_wait(self):
        idb = MagicMock()
        action = AgentAction(action=ActionType.WAIT)
        with patch("mobiletestai.agent.loop.time.sleep"):
            _execute_action(action, idb)
        idb.tap.assert_not_called()


def _make_mock_provider(chat_return=None, chat_side_effect=None):
    """Create a mock LLM provider."""
    from mobiletestai.llm.base import LLMResponse

    provider = MagicMock()
    provider.name = "mock"
    provider.default_model = "mock-model"
    provider.cost_per_input_token = 3.0 / 1_000_000
    provider.cost_per_output_token = 15.0 / 1_000_000
    if chat_side_effect:
        provider.chat.side_effect = chat_side_effect
    elif chat_return:
        provider.chat.return_value = chat_return
    return provider


class TestRunAgent:
    @patch("mobiletestai.agent.loop.time.sleep")
    @patch("mobiletestai.agent.loop._encode_image", return_value="AAAA")
    @patch("mobiletestai.agent.loop.BridgeDevice")
    @patch("mobiletestai.agent.loop.SimulatorManager")
    @patch("mobiletestai.agent.loop.get_provider")
    def test_run_agent_done_on_first_step(
        self, mock_get_provider, mock_sim_cls, mock_bridge_cls, mock_encode, mock_sleep, tmp_path
    ):
        from mobiletestai.llm.base import LLMResponse

        # Setup simulator mock
        mock_sim = mock_sim_cls.return_value
        mock_sim.find_device.return_value = MagicMock(
            name="iPhone 16", udid="test-udid"
        )

        # Setup Bridge mock
        mock_bridge = mock_bridge_cls.return_value
        mock_bridge.describe_ui.return_value = "AXButton 'Settings'"

        # Setup provider mock
        mock_get_provider.return_value = _make_mock_provider(
            chat_return=LLMResponse(
                text='{"action": "done", "reasoning": "found it", "message": "Done"}',
                input_tokens=500,
                output_tokens=50,
            )
        )

        result = run_agent(
            goal="Open settings",
            device_name="iPhone 16",
            bundle_id="com.apple.Preferences",
            output_dir=tmp_path,
            step_delay=0,
        )

        assert result.status == "success"
        assert len(result.steps) == 1
        assert result.total_tokens.input_tokens == 500
        assert result.total_tokens.output_tokens == 50
        assert result.estimated_cost > 0
        mock_bridge.start.assert_called_once()
        mock_bridge.stop.assert_called_once()

    @patch("mobiletestai.agent.loop.time.sleep")
    @patch("mobiletestai.agent.loop._encode_image", return_value="AAAA")
    @patch("mobiletestai.agent.loop.BridgeDevice")
    @patch("mobiletestai.agent.loop.SimulatorManager")
    @patch("mobiletestai.agent.loop.get_provider")
    def test_run_agent_max_steps(
        self, mock_get_provider, mock_sim_cls, mock_bridge_cls, mock_encode, mock_sleep, tmp_path
    ):
        from mobiletestai.llm.base import LLMResponse

        mock_sim = mock_sim_cls.return_value
        mock_sim.find_device.return_value = MagicMock(name="iPhone 16", udid="udid")

        mock_bridge = mock_bridge_cls.return_value
        mock_bridge.describe_ui.return_value = "some UI"

        mock_get_provider.return_value = _make_mock_provider(
            chat_return=LLMResponse(
                text='{"action": "tap", "reasoning": "trying", "x": 100, "y": 200}',
                input_tokens=100,
                output_tokens=20,
            )
        )

        result = run_agent(
            goal="Never finish",
            device_name="iPhone 16",
            bundle_id="com.test",
            max_steps=3,
            output_dir=tmp_path,
            step_delay=0,
        )

        assert result.status == "max_steps_reached"
        assert len(result.steps) == 3

    @patch("mobiletestai.agent.loop.time.sleep")
    @patch("mobiletestai.agent.loop._encode_image", return_value="AAAA")
    @patch("mobiletestai.agent.loop.BridgeDevice")
    @patch("mobiletestai.agent.loop.SimulatorManager")
    @patch("mobiletestai.agent.loop.get_provider")
    def test_run_agent_fail_action(
        self, mock_get_provider, mock_sim_cls, mock_bridge_cls, mock_encode, mock_sleep, tmp_path
    ):
        from mobiletestai.llm.base import LLMResponse

        mock_sim = mock_sim_cls.return_value
        mock_sim.find_device.return_value = MagicMock(name="iPhone 16", udid="udid")

        mock_bridge = mock_bridge_cls.return_value
        mock_bridge.describe_ui.return_value = "empty screen"

        mock_get_provider.return_value = _make_mock_provider(
            chat_return=LLMResponse(
                text='{"action": "fail", "reasoning": "app crashed", "message": "App not responding"}',
                input_tokens=100,
                output_tokens=20,
            )
        )

        result = run_agent(
            goal="Test",
            device_name="iPhone 16",
            bundle_id="com.test",
            output_dir=tmp_path,
            step_delay=0,
        )

        assert result.status == "failure"
        assert "not responding" in result.message

    @patch("mobiletestai.agent.loop.time.sleep")
    @patch("mobiletestai.agent.loop._encode_image", return_value="AAAA")
    @patch("mobiletestai.agent.loop.BridgeDevice")
    @patch("mobiletestai.agent.loop.SimulatorManager")
    @patch("mobiletestai.agent.loop.get_provider")
    def test_run_agent_token_accumulation(
        self, mock_get_provider, mock_sim_cls, mock_bridge_cls, mock_encode, mock_sleep, tmp_path
    ):
        from mobiletestai.llm.base import LLMResponse

        mock_sim = mock_sim_cls.return_value
        mock_sim.find_device.return_value = MagicMock(name="iPhone 16", udid="udid")

        mock_bridge = mock_bridge_cls.return_value
        # Return different UI each time to avoid stale detection
        mock_bridge.describe_ui.side_effect = ["UI v1", "UI v2", "UI v3"]

        responses = [
            LLMResponse(text='{"action": "tap", "reasoning": "try", "x": 10, "y": 10}', input_tokens=100, output_tokens=20),
            LLMResponse(text='{"action": "tap", "reasoning": "try", "x": 10, "y": 10}', input_tokens=100, output_tokens=20),
            LLMResponse(text='{"action": "done", "reasoning": "ok", "message": "done"}', input_tokens=100, output_tokens=20),
        ]
        mock_get_provider.return_value = _make_mock_provider(chat_side_effect=responses)

        result = run_agent(
            goal="Test",
            device_name="iPhone 16",
            bundle_id="com.test",
            max_steps=10,
            output_dir=tmp_path,
            step_delay=0,
        )

        assert result.status == "success"
        assert result.total_tokens.input_tokens == 300
        assert result.total_tokens.output_tokens == 60

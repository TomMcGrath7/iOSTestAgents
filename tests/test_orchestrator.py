"""Tests for the multi-device orchestrator."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mobiletestai.agent.models import OrchestratorResult, RunResult, StepRecord, TokenUsage
from mobiletestai.device.simulator import DeviceInfo
from mobiletestai.orchestrator.coordinator import Orchestrator, OrchestratorError
from mobiletestai.orchestrator.scenario import Scenario, ScenarioStep, load_scenario
from mobiletestai.orchestrator.sync import AbortEvent, VariableStore


# ---------------------------------------------------------------------------
# VariableStore tests
# ---------------------------------------------------------------------------

class TestVariableStore:
    def test_set_and_get(self):
        store = VariableStore()
        store.set("key", "value")
        assert store.get("key") == "value"

    def test_get_default(self):
        store = VariableStore()
        assert store.get("missing") == ""
        assert store.get("missing", "fallback") == "fallback"

    def test_snapshot_is_copy(self):
        store = VariableStore()
        store.set("a", "1")
        snap = store.snapshot()
        store.set("a", "2")
        assert snap["a"] == "1"  # snapshot not affected by later writes

    def test_thread_safety(self):
        store = VariableStore()
        errors = []

        def writer(key, value):
            try:
                for _ in range(100):
                    store.set(key, value)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(f"k{i}", f"v{i}")) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors


# ---------------------------------------------------------------------------
# AbortEvent tests
# ---------------------------------------------------------------------------

class TestAbortEvent:
    def test_not_aborted_initially(self):
        ev = AbortEvent()
        assert not ev.is_aborted()
        assert ev.reason == ""

    def test_abort_sets_flag(self):
        ev = AbortEvent()
        ev.abort("something failed")
        assert ev.is_aborted()
        assert ev.reason == "something failed"

    def test_idempotent_first_reason_wins(self):
        ev = AbortEvent()
        ev.abort("first")
        ev.abort("second")
        assert ev.reason == "first"

    def test_abort_without_reason(self):
        ev = AbortEvent()
        ev.abort()
        assert ev.is_aborted()
        assert ev.reason == ""


# ---------------------------------------------------------------------------
# ScenarioStep tests
# ---------------------------------------------------------------------------

class TestScenarioStep:
    def test_build_goal_action_only(self):
        step = ScenarioStep(player=1, action="Tap login button")
        assert step.build_goal({}) == "Tap login button"

    def test_build_goal_with_verify(self):
        step = ScenarioStep(player=1, action="Create room", verify="Room code shown")
        goal = step.build_goal({})
        assert "Create room" in goal
        assert "Verify: Room code shown" in goal

    def test_build_goal_variable_substitution(self):
        step = ScenarioStep(player=2, action="Join room {room_code}", verify="Joined")
        goal = step.build_goal({"room_code": "ABCD1234"})
        assert "ABCD1234" in goal

    def test_build_goal_missing_variable_empty_string(self):
        step = ScenarioStep(player=2, action="Join {room_code}")
        # Missing variable should produce empty string via defaultdict, not raise KeyError
        goal = step.build_goal({})
        assert "{room_code}" not in goal
        assert "Join " in goal

    def test_player_list_int(self):
        step = ScenarioStep(player=1, action="x")
        assert step.player_list(3) == [1]

    def test_player_list_list(self):
        step = ScenarioStep(player=[1, 2], action="x", parallel=True)
        assert step.player_list(3) == [1, 2]

    def test_player_list_all(self):
        step = ScenarioStep(player="all", action="x")
        assert step.player_list(3) == [1, 2, 3]

    def test_is_all_players_true(self):
        step = ScenarioStep(player="all", action="x")
        assert step.is_all_players()

    def test_is_all_players_false(self):
        step = ScenarioStep(player=1, action="x")
        assert not step.is_all_players()

    def test_all_players_shorthand_normalization(self):
        # YAML shorthand: {all_players: {verify: "..."}}
        step = ScenarioStep.model_validate({"all_players": {"verify": "Game ready"}})
        assert step.player == "all"
        assert step.verify == "Game ready"

    def test_all_players_shorthand_with_on_failure(self):
        step = ScenarioStep.model_validate(
            {"all_players": {"verify": "Done", "on_failure": "continue"}}
        )
        assert step.player == "all"
        assert step.on_failure == "continue"


# ---------------------------------------------------------------------------
# load_scenario tests
# ---------------------------------------------------------------------------

class TestLoadScenario:
    def test_load_valid_yaml(self, tmp_path):
        yaml_content = """
name: test_scenario
app_bundle_id: com.example.app
players: 2
device: "iPhone 16"
steps:
  - player: 1
    action: "Do something"
    verify: "It worked"
  - player: 2
    action: "Also do something"
"""
        f = tmp_path / "scenario.yaml"
        f.write_text(yaml_content)
        sc = load_scenario(f)
        assert sc.name == "test_scenario"
        assert sc.players == 2
        assert len(sc.steps) == 2
        assert sc.steps[0].player == 1

    def test_load_all_players_shorthand(self, tmp_path):
        yaml_content = """
name: test
app_bundle_id: com.example.app
players: 2
steps:
  - all_players:
      verify: "Both ready"
      on_failure: continue
"""
        f = tmp_path / "scenario.yaml"
        f.write_text(yaml_content)
        sc = load_scenario(f)
        step = sc.steps[0]
        assert step.player == "all"
        assert step.verify == "Both ready"
        assert step.on_failure == "continue"

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_scenario(tmp_path / "does_not_exist.yaml")

    def test_load_with_capture(self, tmp_path):
        yaml_content = """
name: capture_test
app_bundle_id: com.example.app
players: 1
steps:
  - player: 1
    action: "Create room"
    capture: room_code
"""
        f = tmp_path / "scenario.yaml"
        f.write_text(yaml_content)
        sc = load_scenario(f)
        assert sc.steps[0].capture == "room_code"


# ---------------------------------------------------------------------------
# Orchestrator tests (all mocked — no real devices or XcodeBuildMCP)
# ---------------------------------------------------------------------------

def _make_scenario(players=1, steps=None, on_failure="fail_fast") -> Scenario:
    if steps is None:
        steps = [ScenarioStep(player=1, action="Do something", verify="Done")]
    return Scenario(
        name="test_scenario",
        app_bundle_id="com.example.test",
        players=players,
        device="iPhone 16",
        steps=steps,
        max_steps=5,
        step_delay=0.0,
        on_failure=on_failure,
    )


def _make_mock_sim(n_devices=1) -> MagicMock:
    sim = MagicMock()
    devices = [
        DeviceInfo(f"iPhone 16", f"udid-{i}", "Booted", "iOS-18")
        for i in range(1, n_devices + 1)
    ]
    sim.list_devices_by_name.return_value = devices
    sim.boot.return_value = None
    sim.install_app.return_value = None
    sim.launch_app.return_value = None
    return sim


def _make_mock_backend() -> MagicMock:
    backend = MagicMock()
    backend.start.return_value = None
    backend.stop.return_value = None
    return backend


def _make_success_result(goal="Do something") -> RunResult:
    step = StepRecord(step_number=1, ui_state="UI state text", action=None)
    return RunResult(
        status="success",
        message="Done",
        goal=goal,
        steps=[step],
        total_tokens=TokenUsage(input_tokens=100, output_tokens=50),
    )


class TestOrchestratorSinglePlayerSuccess:
    def test_success(self, tmp_path):
        sc = _make_scenario(players=1)
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=1)
        mock_result = _make_success_result()

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=mock_result) as mock_run:
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        assert result.status == "success"
        assert 1 in result.players
        assert result.players[1].status == "success"
        mock_run.assert_called_once()

    def test_tokens_accumulated(self, tmp_path):
        sc = _make_scenario(players=1)
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=1)
        mock_result = _make_success_result()
        mock_result.total_tokens = TokenUsage(input_tokens=200, output_tokens=100)

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=mock_result):
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        assert result.total_tokens.input_tokens == 200
        assert result.total_tokens.output_tokens == 100


class TestOrchestratorTwoPlayersSerial:
    def test_two_serial_steps(self, tmp_path):
        steps = [
            ScenarioStep(player=1, action="Step A"),
            ScenarioStep(player=2, action="Step B"),
        ]
        sc = _make_scenario(players=2, steps=steps)
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=2)
        mock_result = _make_success_result()

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=mock_result) as mock_run:
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        assert result.status == "success"
        assert mock_run.call_count == 2
        # Player 1 and 2 both have results
        assert 1 in result.players
        assert 2 in result.players


class TestOrchestratorFailFast:
    def test_abort_after_step_failure(self, tmp_path):
        steps = [
            ScenarioStep(player=1, action="Step A"),
            ScenarioStep(player=1, action="Step B"),
        ]
        sc = _make_scenario(players=1, steps=steps, on_failure="fail_fast")
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=1)
        failure_result = RunResult(status="failure", message="Could not complete", goal="Step A")

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=failure_result) as mock_run:
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        # Only first step should have been called (fail-fast)
        assert mock_run.call_count == 1
        assert result.status == "aborted"

    def test_continue_on_failure(self, tmp_path):
        steps = [
            ScenarioStep(player=1, action="Step A"),
            ScenarioStep(player=1, action="Step B"),
        ]
        sc = _make_scenario(players=1, steps=steps, on_failure="continue")
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=1)
        failure_result = RunResult(status="failure", message="Failed", goal="Step A")

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=failure_result) as mock_run:
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        # Both steps should have been called
        assert mock_run.call_count == 2


class TestOrchestratorVariableCapture:
    def test_capture_stores_value(self, tmp_path):
        steps = [
            ScenarioStep(player=1, action="Create room", capture="room_code"),
            ScenarioStep(player=2, action="Join {room_code}"),
        ]
        sc = _make_scenario(players=2, steps=steps)
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=2)
        success_result = _make_success_result()

        mock_llm = MagicMock()
        from mobiletestai.llm.base import LLMResponse
        mock_llm.chat.return_value = LLMResponse(text="ABCD1234", input_tokens=10, output_tokens=5)
        mock_llm.default_model = "test-model"
        mock_llm.cost_per_input_token = 0.0
        mock_llm.cost_per_output_token = 0.0

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=success_result):
            with patch("mobiletestai.orchestrator.coordinator.get_provider", return_value=mock_llm):
                orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
                orch._sim = mock_sim
                result = orch.run()

        assert "room_code" in result.captured_variables
        assert result.captured_variables["room_code"] == "ABCD1234"
        mock_llm.chat.assert_called_once()

    def test_no_capture_when_step_fails(self, tmp_path):
        steps = [
            ScenarioStep(player=1, action="Create room", capture="room_code", on_failure="continue"),
        ]
        sc = _make_scenario(players=1, steps=steps, on_failure="continue")
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=1)
        failure_result = RunResult(status="failure", message="Failed", goal="Create room")

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=failure_result):
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        assert "room_code" not in result.captured_variables


class TestOrchestratorParallelStep:
    def test_parallel_runs_all_players(self, tmp_path):
        steps = [
            ScenarioStep(player=[1, 2], action="Verify lobby", parallel=True),
        ]
        sc = _make_scenario(players=2, steps=steps)
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=2)
        mock_result = _make_success_result()

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=mock_result) as mock_run:
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        # Both players ran
        assert mock_run.call_count == 2
        assert result.status == "success"

    def test_all_players_step_runs_all(self, tmp_path):
        steps = [
            ScenarioStep(player="all", action="Check game state"),
        ]
        sc = _make_scenario(players=3, steps=steps)
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=3)
        mock_result = _make_success_result()

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=mock_result) as mock_run:
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        assert mock_run.call_count == 3


class TestOrchestratorReport:
    def test_report_json_written(self, tmp_path):
        sc = _make_scenario(players=1)
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=1)
        mock_result = _make_success_result()

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=mock_result):
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        report_path = tmp_path / result.run_id / "report.json"
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert data["scenario_name"] == "test_scenario"
        assert data["status"] == "success"

    def test_report_contains_players(self, tmp_path):
        sc = _make_scenario(players=1)
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=1)
        mock_result = _make_success_result()

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=mock_result):
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        report_path = tmp_path / result.run_id / "report.json"
        data = json.loads(report_path.read_text())
        assert "players" in data
        assert "1" in data["players"]


class TestOrchestratorCleanup:
    def test_backend_stop_called_on_crash(self, tmp_path):
        """backend.stop() must be called even when run_agent raises."""
        sc = _make_scenario(players=1)
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=1)

        with patch(
            "mobiletestai.orchestrator.coordinator.run_agent",
            side_effect=RuntimeError("crash"),
        ):
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            result = orch.run()

        # Backend stop should have been called in finally block
        mock_backend.stop.assert_called()
        # Result status should reflect the error
        assert result.status in ("failure", "aborted")

    def test_backend_stop_called_on_success(self, tmp_path):
        sc = _make_scenario(players=1)
        mock_backend = _make_mock_backend()
        mock_sim = _make_mock_sim(n_devices=1)
        mock_result = _make_success_result()

        with patch("mobiletestai.orchestrator.coordinator.run_agent", return_value=mock_result):
            orch = Orchestrator(sc, output_dir=tmp_path, backend_cls=lambda u, b: mock_backend)
            orch._sim = mock_sim
            orch.run()

        mock_backend.stop.assert_called()


# ---------------------------------------------------------------------------
# SimulatorManager.list_devices_by_name tests
# ---------------------------------------------------------------------------

class TestSimulatorManagerListByName:
    def test_returns_matching_devices(self):
        from mobiletestai.device.simulator import SimulatorManager

        raw_output = json.dumps({
            "devices": {
                "com.apple.CoreSimulator.SimRuntime.iOS-18-0": [
                    {"name": "iPhone 16", "udid": "aaa", "state": "Booted", "isAvailable": True},
                    {"name": "iPhone 15", "udid": "bbb", "state": "Shutdown", "isAvailable": True},
                ],
                "com.apple.CoreSimulator.SimRuntime.iOS-17-0": [
                    {"name": "iPhone 16", "udid": "ccc", "state": "Shutdown", "isAvailable": True},
                ],
            }
        })

        sim = SimulatorManager()
        sim._run = MagicMock(return_value=raw_output)
        devices = sim.list_devices_by_name("iPhone 16")

        assert len(devices) == 2
        assert all(d.name == "iPhone 16" for d in devices)
        # Sorted newest runtime first (iOS-18 before iOS-17)
        assert devices[0].runtime == "com.apple.CoreSimulator.SimRuntime.iOS-18-0"

    def test_returns_empty_for_no_match(self):
        from mobiletestai.device.simulator import SimulatorManager

        raw_output = json.dumps({
            "devices": {
                "com.apple.CoreSimulator.SimRuntime.iOS-18-0": [
                    {"name": "iPhone 15", "udid": "aaa", "state": "Booted", "isAvailable": True},
                ],
            }
        })

        sim = SimulatorManager()
        sim._run = MagicMock(return_value=raw_output)
        devices = sim.list_devices_by_name("iPhone 16")

        assert devices == []

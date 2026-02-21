"""Orchestrator — coordinates N agents across N simulators for multi-device testing."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from mobiletestai.agent.loop import run_agent
from mobiletestai.agent.models import OrchestratorResult, PlayerResult, RunResult, TimelineEvent
from mobiletestai.device.base import DeviceBackend
from mobiletestai.device.simulator import DeviceInfo, SimulatorManager
from mobiletestai.llm.base import LLMProvider
from mobiletestai.llm.registry import get_provider
from mobiletestai.orchestrator.scenario import Scenario, ScenarioStep
from mobiletestai.orchestrator.sync import AbortEvent, VariableStore
from mobiletestai.util.logging import get_logger

logger = get_logger(__name__)


class OrchestratorError(Exception):
    """Raised when orchestrator setup or coordination fails."""


class Orchestrator:
    """Coordinates N agents across N simulators for a multi-device scenario."""

    def __init__(
        self,
        scenario: Scenario,
        output_dir: Path,
        backend_cls=None,
    ) -> None:
        """
        Args:
            scenario: The parsed scenario to run.
            output_dir: Base output directory. Orchestrator creates a run_id subdirectory.
            backend_cls: Optional callable(udid, bundle_id) -> DeviceBackend for testing.
                         If None, the backend is resolved from scenario.backend.
        """
        self._scenario = scenario
        self._output_dir = Path(output_dir)
        self._backend_cls = backend_cls
        self._sim = SimulatorManager()
        self._var_store = VariableStore()
        self._abort = AbortEvent()
        self._backends: dict[int, DeviceBackend] = {}
        self._udids: dict[int, str] = {}
        self._device_infos: dict[int, DeviceInfo] = {}
        self._result = OrchestratorResult(scenario_name=scenario.name)
        self._run_dir = self._output_dir / self._result.run_id
        self._llm: LLMProvider | None = None

    def run(self) -> OrchestratorResult:
        """Run the scenario. Returns OrchestratorResult with full report."""
        self._result.timeline.append(TimelineEvent(
            event_type="start",
            detail=f"Scenario: {self._scenario.name}, players: {self._scenario.players}",
        ))

        try:
            self._allocate_devices()
            self._init_player_results()

            for step_idx, step in enumerate(self._scenario.steps):
                if self._abort.is_aborted():
                    self._result.timeline.append(TimelineEvent(
                        event_type="abort",
                        detail=self._abort.reason,
                    ))
                    break

                player_nums = step.player_list(self._scenario.players)
                is_parallel = step.parallel or (step.is_all_players() and len(player_nums) > 1)

                self._result.timeline.append(TimelineEvent(
                    event_type="step_start",
                    step_index=step_idx,
                    detail=f"players={player_nums}, parallel={is_parallel}",
                ))

                if is_parallel and len(player_nums) > 1:
                    self._run_step_parallel(step, step_idx, player_nums)
                else:
                    for p in player_nums:
                        if self._abort.is_aborted():
                            break
                        run_result = self._run_step_for_player(step, step_idx, p)
                        self._process_step_result(step, step_idx, p, run_result)

                if self._scenario.step_delay > 0 and not self._abort.is_aborted():
                    time.sleep(self._scenario.step_delay)

        finally:
            self._stop_all_backends()
            self._finalize_result()
            self._write_report()

        return self._result

    def _allocate_devices(self) -> None:
        """Boot N simulators, install/launch app, and start backends for each player."""
        n = self._scenario.players
        name = self._scenario.device
        bundle_id = self._scenario.app_bundle_id

        available = self._sim.list_devices_by_name(name)

        for i in range(n):
            player_num = i + 1
            if i < len(available):
                device_info = available[i]
            else:
                logger.info(f"Creating new simulator '{name}' for player {player_num}")
                device_info = self._sim.create_device(name)

            udid = device_info.udid
            self._udids[player_num] = udid
            self._device_infos[player_num] = device_info

            self._sim.boot(udid)

            if self._scenario.app_path:
                self._sim.install_app(udid, self._scenario.app_path)

            self._sim.launch_app(udid, bundle_id)

            backend = self._create_backend(udid)
            backend.start(output_dir=self._run_dir)
            self._backends[player_num] = backend
            logger.info(f"Player {player_num}: device={name} udid={udid[:8]}...")

    def _create_backend(self, udid: str) -> DeviceBackend:
        """Instantiate the device backend for a given simulator UDID."""
        bundle_id = self._scenario.app_bundle_id

        if self._backend_cls is not None:
            return self._backend_cls(udid, bundle_id)

        backend_name = self._scenario.backend
        if backend_name == "xcodebuildmcp":
            from mobiletestai.device.xcodebuildmcp import XcodeBuildMCPDevice
            return XcodeBuildMCPDevice(udid, bundle_id=bundle_id)
        elif backend_name == "testbridge":
            from mobiletestai.device.bridge import BridgeDevice, BRIDGE_PORT
            port = BRIDGE_PORT + len(self._backends)
            return BridgeDevice(udid, bundle_id=bundle_id, port=port)
        else:
            raise OrchestratorError(f"Unknown backend: {backend_name!r}")

    def _init_player_results(self) -> None:
        """Initialize PlayerResult entries for all players."""
        for player_num in range(1, self._scenario.players + 1):
            self._result.players[player_num] = PlayerResult(
                player_number=player_num,
                device_udid=self._udids.get(player_num, ""),
            )

    def _run_step_for_player(
        self, step: ScenarioStep, step_idx: int, player_num: int
    ) -> RunResult:
        """Run a single scenario step for one player. Returns RunResult (never raises)."""
        goal = step.build_goal(self._var_store.snapshot())
        device_info = self._device_infos[player_num]
        player_output_dir = self._run_dir / f"player_{player_num}" / f"step_{step_idx:03d}"
        player_output_dir.mkdir(parents=True, exist_ok=True)
        max_steps = step.max_steps or self._scenario.max_steps

        logger.info(
            f"Player {player_num} step {step_idx}: goal={goal!r}, max_steps={max_steps}"
        )

        try:
            return run_agent(
                goal=goal,
                device_name=device_info.name,
                bundle_id=self._scenario.app_bundle_id,
                max_steps=max_steps,
                model=self._scenario.model,
                provider=self._scenario.provider,
                output_dir=player_output_dir,
                step_delay=self._scenario.step_delay,
                record=False,
                reset=False,
                app_path=None,
                backend=self._backends[player_num],
                vision=True,
                device_udid=device_info.udid,
            )
        except Exception as exc:
            logger.error(f"Player {player_num} step {step_idx} raised exception: {exc}")
            return RunResult(status="error", message=str(exc), goal=goal)

    def _run_step_parallel(
        self, step: ScenarioStep, step_idx: int, player_nums: list[int]
    ) -> None:
        """Run a step for multiple players in parallel; block until all complete."""
        with ThreadPoolExecutor(max_workers=len(player_nums)) as executor:
            futures = {
                executor.submit(self._run_step_for_player, step, step_idx, p): p
                for p in player_nums
            }
            # Process results in the main thread as each future completes (as_completed loop)
            for future in as_completed(futures):
                p = futures[future]
                try:
                    run_result = future.result()
                except Exception as exc:
                    run_result = RunResult(status="error", message=str(exc))
                self._process_step_result(step, step_idx, p, run_result)

    def _process_step_result(
        self,
        step: ScenarioStep,
        step_idx: int,
        player_num: int,
        run_result: RunResult,
    ) -> None:
        """Store result, accumulate tokens, capture variables, and signal abort if needed.

        Must be called from the main thread (not from worker thread callbacks).
        """
        self._result.players[player_num].step_results[step_idx] = run_result

        # Accumulate tokens
        self._result.total_tokens.input_tokens += run_result.total_tokens.input_tokens
        self._result.total_tokens.output_tokens += run_result.total_tokens.output_tokens

        self._result.timeline.append(TimelineEvent(
            event_type="step_complete",
            player=player_num,
            step_index=step_idx,
            detail=f"status={run_result.status}",
        ))

        # Variable capture on success
        if run_result.status == "success" and step.capture:
            self._capture_variable(step, step_idx, player_num, run_result)

        # Fail-fast on non-success
        if run_result.status != "success":
            effective_on_failure = (
                step.on_failure
                if step.on_failure is not None
                else self._scenario.on_failure
            )
            if effective_on_failure == "fail_fast" and not self._abort.is_aborted():
                reason = (
                    f"Player {player_num} step {step_idx} failed "
                    f"(status={run_result.status}): {run_result.message}"
                )
                self._abort.abort(reason)
                logger.warning(f"Fail-fast triggered: {reason}")

    def _capture_variable(
        self,
        step: ScenarioStep,
        step_idx: int,
        player_num: int,
        run_result: RunResult,
    ) -> None:
        """Extract a variable value from the last UI state using an LLM call."""
        if not step.capture:
            return
        if not run_result.steps:
            logger.warning(
                f"No steps in result for player {player_num} step {step_idx} "
                f"— cannot capture {step.capture!r}"
            )
            return

        last_ui_state = run_result.steps[-1].ui_state
        if not last_ui_state:
            logger.warning(f"Empty UI state for capture of {step.capture!r}")
            return

        if self._llm is None:
            self._llm = get_provider(self._scenario.provider)
        model = self._scenario.model or self._llm.default_model

        system = (
            "You are a data extraction assistant. Extract the requested value from "
            "the iOS app UI state and return ONLY the value, no explanation."
        )
        user = (
            f"From the iOS app UI state below, extract the value of: {step.capture}.\n"
            f"Reply with ONLY the extracted value. No quotes, no punctuation.\n\n"
            f"UI STATE:\n{last_ui_state}"
        )

        try:
            response = self._llm.chat(
                model=model,
                system=system,
                messages_content=[{"type": "text", "text": user}],
                max_tokens=64,
            )
            extracted = response.text.strip()
            if extracted:
                self._var_store.set(step.capture, extracted)
                self._result.captured_variables[step.capture] = extracted
                self._result.timeline.append(TimelineEvent(
                    event_type="variable_captured",
                    player=player_num,
                    step_index=step_idx,
                    detail=f"{step.capture}={extracted!r}",
                ))
                logger.info(f"Captured variable {step.capture!r} = {extracted!r}")
            else:
                logger.warning(f"LLM returned empty extraction for {step.capture!r}")
        except Exception as exc:
            logger.warning(f"Variable capture failed for {step.capture!r}: {exc}")

    def _stop_all_backends(self) -> None:
        """Stop all device backends (no-op for XcodeBuildMCP; terminates TestBridge)."""
        for player_num, backend in self._backends.items():
            try:
                backend.stop()
            except Exception as exc:
                logger.warning(f"Error stopping backend for player {player_num}: {exc}")

    def _finalize_result(self) -> None:
        """Compute per-player and overall status, and estimated cost."""
        from datetime import datetime, timezone
        self._result.finished_at = datetime.now(timezone.utc).isoformat()

        # Per-player status
        for player_result in self._result.players.values():
            if not player_result.step_results:
                player_result.status = "aborted"
            elif all(r.status == "success" for r in player_result.step_results.values()):
                player_result.status = "success"
            elif any(r.status in ("error", "failure") for r in player_result.step_results.values()):
                player_result.status = "failure"
            else:
                player_result.status = "aborted"

        # Overall status
        if self._abort.is_aborted():
            self._result.status = "aborted"
        elif all(p.status == "success" for p in self._result.players.values()):
            self._result.status = "success"
        else:
            self._result.status = "failure"

        # Estimated cost — sum from individual run results
        total_cost = 0.0
        for player_result in self._result.players.values():
            for run_result in player_result.step_results.values():
                total_cost += run_result.estimated_cost
        self._result.estimated_cost = total_cost

    def _write_report(self) -> None:
        """Write the orchestrator result to report.json in the run directory."""
        self._run_dir.mkdir(parents=True, exist_ok=True)
        report_path = self._run_dir / "report.json"
        report_path.write_text(self._result.model_dump_json(indent=2))
        logger.info(f"Report written to {report_path}")

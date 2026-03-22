"""Pydantic models for agent actions and run results."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    TAP = "tap"
    SWIPE_UP = "swipe_up"
    SWIPE_DOWN = "swipe_down"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    TYPE = "type"
    TAP_AND_TYPE = "tap_and_type"
    PRESS_BUTTON = "press_button"
    WAIT = "wait"
    DONE = "done"
    FAIL = "fail"


class AgentAction(BaseModel):
    """Action decided by the LLM agent. Optional fields are conditional on action type."""

    action: ActionType
    reasoning: str = ""
    x: int | None = None
    y: int | None = None
    text: str | None = None
    button: str | None = None
    message: str | None = None


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class StepRecord(BaseModel):
    step_number: int
    ui_state: str = ""
    screenshot_path: str | None = None
    action: AgentAction | None = None
    success: bool = True
    error: str | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)


class RunResult(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    goal: str = ""
    device: str = ""
    status: str = "running"  # success, failure, max_steps_reached, error
    steps: list[StepRecord] = Field(default_factory=list)
    message: str = ""
    total_tokens: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost: float = 0.0


class TimelineEvent(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str  # "step_start", "step_complete", "variable_captured", "abort", etc.
    player: int | None = None  # None = orchestrator-level event
    step_index: int | None = None
    detail: str = ""


class PlayerResult(BaseModel):
    player_number: int
    device_udid: str
    step_results: dict[int, RunResult] = Field(default_factory=dict)  # keyed by step_index
    status: str = "pending"  # "success", "failure", "aborted"


class OrchestratorResult(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    scenario_name: str = ""
    status: str = "running"  # "success", "failure", "aborted", "error"
    players: dict[int, PlayerResult] = Field(default_factory=dict)
    captured_variables: dict[str, str] = Field(default_factory=dict)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    total_tokens: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost: float = 0.0

"""Pydantic models for agent actions and run results."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ActionType(StrEnum):
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


# Common LLM action-name variations, normalized before enum validation.
# "back" additionally implies pressing the HOME button.
ACTION_ALIASES: dict[str, str] = {
    "click": "tap",
    "press": "tap",
    "scroll_down": "swipe_down",
    "scroll_up": "swipe_up",
    "scroll_left": "swipe_left",
    "scroll_right": "swipe_right",
    "swipe": "swipe_down",
    "scroll": "swipe_down",
    "back": "press_button",
}


class AgentAction(BaseModel):
    """Action decided by the LLM agent. Optional fields are conditional on action type.

    Used directly as the structured-output schema for providers that support
    it — `element` references a numbered UI element and is resolved to x/y
    coordinates by the agent loop.
    """

    action: ActionType
    reasoning: str = ""
    element: int | None = None
    target: str | None = None
    x: int | None = None
    y: int | None = None
    text: str | None = None
    button: str | None = None
    message: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_action_aliases(cls, data):
        if isinstance(data, dict):
            action = data.get("action")
            if isinstance(action, str) and action in ACTION_ALIASES:
                data = dict(data)
                data["action"] = ACTION_ALIASES[action]
                if action == "back" and not data.get("button"):
                    data["button"] = "HOME"
        return data


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


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
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
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
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    total_tokens: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost: float = 0.0

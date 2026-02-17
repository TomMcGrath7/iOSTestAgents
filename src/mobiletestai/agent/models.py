"""Pydantic models for agent actions and run results."""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    TAP = "tap"
    SWIPE_UP = "swipe_up"
    SWIPE_DOWN = "swipe_down"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    TYPE = "type"
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

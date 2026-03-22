"""Scenario model and YAML loader for multi-device test scenarios."""

from __future__ import annotations

import collections
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ScenarioStep(BaseModel):
    player: int | list[int] | Literal["all"]
    action: str = ""
    verify: str = ""
    capture: str | None = None  # variable name to extract after this step
    parallel: bool = False  # run listed players simultaneously
    max_steps: int | None = None  # per-step override of scenario max_steps
    on_failure: Literal["fail_fast", "continue"] | None = None  # None = use scenario default

    @model_validator(mode="before")
    @classmethod
    def normalize_all_players(cls, data: dict) -> dict:
        """Convert {all_players: {verify: ...}} YAML shorthand to {player: "all", ...}."""
        if isinstance(data, dict) and "all_players" in data:
            nested = data.pop("all_players") or {}
            data["player"] = "all"
            if isinstance(nested, dict):
                data.update(nested)
        return data

    def build_goal(self, variables: dict[str, str]) -> str:
        """Build the goal string, substituting captured variables.

        Uses a defaultdict fallback so missing variables produce empty strings
        rather than raising KeyError, keeping failures visible in step results.
        """
        parts = []
        if self.action:
            parts.append(self.action)
        if self.verify:
            parts.append(f"Verify: {self.verify}")
        goal = ". ".join(parts)
        fallback: dict[str, str] = collections.defaultdict(str, variables)
        return goal.format_map(fallback)

    def player_list(self, total_players: int) -> list[int]:
        """Expand player spec to a concrete list of player numbers."""
        if self.player == "all":
            return list(range(1, total_players + 1))
        if isinstance(self.player, int):
            return [self.player]
        return list(self.player)

    def is_all_players(self) -> bool:
        return self.player == "all"


class Scenario(BaseModel):
    name: str
    app_bundle_id: str
    players: int = 1
    device: str = "iPhone 16"
    steps: list[ScenarioStep]
    max_steps: int = 20
    backend: str = "xcodebuildmcp"
    provider: str | None = None
    model: str | None = None
    app_path: str | None = None
    step_delay: float = 1.5
    on_failure: Literal["fail_fast", "continue"] = "fail_fast"


def load_scenario(path: str | Path) -> Scenario:
    """Load a scenario from a YAML file.

    Raises:
        FileNotFoundError: If the file does not exist.
        pydantic.ValidationError: If the YAML does not match the Scenario schema.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")
    raw = yaml.safe_load(path.read_text())
    return Scenario.model_validate(raw)

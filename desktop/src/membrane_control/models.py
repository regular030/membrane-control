"""Validated data models shared by the UI, simulator and serial client."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

VALVE_COUNT = 7
MAX_STEPS = 32
MAX_RUN_SECONDS = 604800


def number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be between {low:g} and {high:g}") from error
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return result


def integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")
    return value


def text(value: Any, name: str, limit: int = 64) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must contain 1-{limit} characters")
    value = value.strip()
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{name} must not contain control characters")
    if utf8_length(value, name) > 80:
        raise ValueError(f"{name} is too long; use a shorter name")
    return value


def utf8_length(value: str, name: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeError as error:
        raise ValueError(f"{name} contains invalid text") from error


def valve_states(value: Any) -> tuple[bool, ...]:
    if not isinstance(value, (tuple, list)) or len(value) != VALVE_COUNT:
        raise ValueError("Specify exactly seven valve states")
    if any(type(v) is not bool for v in value):
        raise ValueError("Valve states must be true or false")
    return tuple(value)


@dataclass
class Step:
    name: str = "New step"
    duration_s: float = 10.0
    valves: tuple[bool, ...] = (False,) * VALVE_COUNT
    pump_percent: float = 0.0

    def validate(self) -> None:
        self.name = text(self.name, "Step name")
        self.duration_s = number(self.duration_s, "Step duration", 0.1, 86400)
        self.valves = valve_states(self.valves)
        self.pump_percent = number(self.pump_percent, "Pump setting", 0, 100)

    def to_dict(self) -> dict:
        self.validate()
        return {"name": self.name, "duration_s": self.duration_s,
                "valves": list(self.valves), "pump_percent": self.pump_percent}

    @classmethod
    def from_dict(cls, data: dict) -> Step:
        if not isinstance(data, dict):
            raise ValueError("Each step must be an object")
        result = cls(data.get("name"), data.get("duration_s"),
                     data.get("valves"), data.get("pump_percent"))
        result.validate()
        return result


@dataclass
class Recipe:
    name: str = "Custom sequence"
    description: str = "User-created sequence"
    hardware_approved: bool = False
    repeat: int = 1
    sample_interval_s: float = 1.0
    require_balance: bool = False
    steps: list[Step] = field(default_factory=lambda: [Step()])
    desired_flow_ml_min: float = 0.0

    def validate(self) -> None:
        self.name = text(self.name, "Recipe name")
        if not isinstance(self.description, str) or len(self.description) > 512:
            raise ValueError("Description must be at most 512 characters")
        if "\0" in self.description or utf8_length(self.description, "Description") > 1000:
            raise ValueError("Description contains invalid text or is too long; shorten the notes")
        if type(self.hardware_approved) is not bool or type(self.require_balance) is not bool:
            raise ValueError("Approval and balance requirement must be booleans")
        integer(self.repeat, "Repeat count", 1, 100)
        self.sample_interval_s = number(self.sample_interval_s, "Recording interval", 0.1, 3600)
        self.desired_flow_ml_min = number(self.desired_flow_ml_min, "Desired flow (mL/min)", 0, 1_000_000)
        if not isinstance(self.steps, list) or not 1 <= len(self.steps) <= MAX_STEPS:
            raise ValueError(f"A sequence needs 1-{MAX_STEPS} steps")
        for step in self.steps:
            if not isinstance(step, Step):
                raise ValueError("Invalid step")
            step.validate()
        if self.duration_s > MAX_RUN_SECONDS:
            raise ValueError("Total repeated duration must be seven days or less")

    @property
    def duration_s(self) -> float:
        return sum(s.duration_s for s in self.steps) * self.repeat

    def to_dict(self) -> dict:
        self.validate()
        return {"schema_version": 1, "name": self.name, "description": self.description,
                "hardware_approved": self.hardware_approved, "repeat": self.repeat,
                "sample_interval_s": self.sample_interval_s,
                "require_balance": self.require_balance,
                "desired_flow_ml_min": self.desired_flow_ml_min,
                "steps": [s.to_dict() for s in self.steps]}

    def to_wire_dict(self) -> dict:
        """Keep the desktop comparison target out of firmware output commands."""
        data = self.to_dict()
        data.pop("desired_flow_ml_min")
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Recipe:
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ValueError("Unsupported recipe schema; expected version 1")
        steps = data.get("steps")
        if not isinstance(steps, list):
            raise ValueError("Recipe steps must be a list")
        result = cls(data.get("name"), data.get("description", ""),
                     data.get("hardware_approved", False), data.get("repeat", 1),
                     data.get("sample_interval_s", 1.0), data.get("require_balance", False),
                     [Step.from_dict(s) for s in steps],
                     data.get("desired_flow_ml_min", 0.0))
        result.validate()
        return result

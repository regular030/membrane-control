"""Deterministic sequence runner used by the desktop simulator."""
from __future__ import annotations
import copy
from .models import Recipe, valve_states, number


class SequenceEngine:
    def __init__(self):
        self.recipe = None
        self.state = "idle"
        self.fault = None
        self.started = 0.0
        self.step_index = -1
        self.cycle = 0
        self.remaining_s = 0.0
        self.valves = (False,) * 7
        self.pump_percent = 0.0

    def load(self, recipe: Recipe):
        if self.state in ("running", "manual"):
            raise ValueError("Stop before changing the sequence")
        recipe.validate()
        self.recipe = copy.deepcopy(recipe)

    def start(self, now: float):
        if self.state == "fault":
            raise ValueError("Clear the fault before starting")
        if self.state != "idle" or self.recipe is None:
            raise ValueError("Load a sequence and stop manual operation first")
        self.state = "running"
        self.started = now
        self.tick(now)

    def tick(self, now: float):
        if self.state != "running":
            return
        elapsed = max(0.0, now - self.started)
        period = sum(s.duration_s for s in self.recipe.steps)
        if elapsed >= self.recipe.duration_s:
            self.stop()
            return
        self.cycle = int(elapsed // period) + 1
        offset = elapsed % period
        for i, step in enumerate(self.recipe.steps):
            if offset < step.duration_s:
                self.step_index = i
                self.remaining_s = step.duration_s - offset
                self.valves = step.valves
                self.pump_percent = step.pump_percent
                break
            offset -= step.duration_s

    def manual(self, valves, pump_percent):
        if self.state not in ("idle", "manual"):
            raise ValueError("Stop the sequence or clear the fault before manual control")
        checked_valves = valve_states(valves)
        checked_pump = number(pump_percent, "Pump setting", 0, 100)
        self.valves, self.pump_percent = checked_valves, checked_pump
        self.state = "manual" if any(self.valves) or self.pump_percent else "idle"

    def stop(self):
        self.valves = (False,) * 7
        self.pump_percent = 0.0
        self.step_index = -1
        self.cycle = 0
        self.remaining_s = 0.0
        if self.state != "fault":
            self.state = "idle"

    def fail(self, message):
        self.stop()
        self.state = "fault"
        self.fault = message

    def clear_fault(self):
        self.stop()
        self.fault = None
        self.state = "idle"

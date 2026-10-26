"""Desired flow is saved experiment metadata, independent of actuator commands."""
import copy
import csv
import json

import pytest

from membrane_control.controller import AppController
from membrane_control.models import Recipe, Step


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def app(tmp_path):
    clock = Clock()
    controller = AppController(tmp_path, clock)
    controller.tick()
    yield controller, clock
    controller.close()


def sequence(target=125.5):
    return Recipe(name="Desired flow example", desired_flow_ml_min=target,
                  steps=[Step("Observe", 10, (True,) + (False,) * 6, 17)])


def test_desired_flow_snapshot_and_saved_recipe_use_loaded_copy(app, tmp_path):
    controller, _ = app
    assert controller.snapshot["desired_flow_ml_min"] == controller.recipe.desired_flow_ml_min == 0
    recipe = sequence()
    controller.load_recipe(recipe)
    assert controller.snapshot["desired_flow_ml_min"] == 125.5
    recipe.desired_flow_ml_min = 999
    assert controller.recipe.desired_flow_ml_min == 125.5
    assert controller.snapshot["desired_flow_ml_min"] == 125.5

    exported = tmp_path / "recipe.json"
    controller.save_recipe(exported, controller.recipe)
    assert json.loads(exported.read_text(encoding="utf-8"))["desired_flow_ml_min"] == 125.5
    assert controller.load_recipe_file(exported).desired_flow_ml_min == 125.5
    assert controller.list_presets()["Desired flow example"].desired_flow_ml_min == 125.5


def test_desired_target_does_not_change_wire_recipe_or_pump_setting(app):
    controller, _ = app
    controller.load_recipe(sequence())
    sent = []
    original_send = controller.driver.send

    def capture(packet):
        sent.append(copy.deepcopy(packet))
        original_send(packet)

    controller.driver.send = capture
    controller.start_run()
    packet = next(packet for packet in sent if packet["cmd"] == "load_recipe")
    assert "desired_flow_ml_min" not in packet["recipe"]
    assert packet["recipe"] == controller.recipe.to_wire_dict()
    assert packet["recipe"]["steps"][0]["pump_percent"] == 17
    assert controller.recipe.to_dict()["desired_flow_ml_min"] == 125.5
    controller.tick()
    controller.tick()
    assert controller.snapshot["pump_percent"] == 17
    assert controller.snapshot["flow_ml_min"] != 125.5
    assert controller.snapshot["desired_flow_ml_min"] == 125.5


def test_set_desired_flow_updates_only_target_without_commands_or_pump_changes(app):
    controller, _ = app
    controller.load_recipe(sequence())
    old_recipe = controller.recipe.to_dict()
    old_pump = controller.snapshot["pump_percent"]
    old_flow = controller.snapshot["flow_ml_min"]
    sent = []
    controller.driver.send = lambda packet: sent.append(copy.deepcopy(packet))

    controller.set_desired_flow(325.75)
    assert sent == []
    assert controller.snapshot["desired_flow_ml_min"] == controller.recipe.desired_flow_ml_min == 325.75
    assert controller.snapshot["pump_percent"] == old_pump
    assert controller.snapshot["flow_ml_min"] == old_flow
    updated = controller.recipe.to_dict()
    updated.pop("desired_flow_ml_min")
    old_recipe.pop("desired_flow_ml_min")
    assert updated == old_recipe
    assert "Desired flow set to 325.75 mL/min" in controller.log[-1]


@pytest.mark.parametrize("value", [-1, 1_000_001, True, "125", None, float("inf"), float("nan")])
def test_invalid_desired_flow_setter_is_atomic(app, value):
    controller, _ = app
    controller.load_recipe(sequence())
    with pytest.raises(ValueError, match="Desired flow"):
        controller.set_desired_flow(value)
    assert controller.recipe.desired_flow_ml_min == controller.snapshot["desired_flow_ml_min"] == 125.5


@pytest.mark.parametrize("operation", ["loading", "running", "manual", "stopping"])
def test_active_operation_prevents_changing_desired_target(app, operation):
    controller, _ = app
    controller.load_recipe(sequence())
    if operation == "manual":
        controller.set_manual([False] * 7, 0)
        controller.tick()
    else:
        controller.start_run()
        if operation in ("running", "stopping"):
            controller.tick()
            controller.tick()
        if operation == "stopping":
            controller.stop_run()
    with pytest.raises(ValueError, match="Stop before changing"):
        controller.load_recipe(sequence(450))
    with pytest.raises(ValueError, match="Stop before changing desired flow"):
        controller.set_desired_flow(450)
    assert controller.recipe.desired_flow_ml_min == 125.5
    assert controller.snapshot["desired_flow_ml_min"] == 125.5


def test_flow_telemetry_cannot_replace_desired_target(app):
    controller, clock = app
    controller.load_recipe(sequence())
    packet = controller.driver.poll(clock())[-1]
    packet["flow_ml_min"] = 42.25
    packet["desired_flow_ml_min"] = 999  # Extra device metadata cannot set the operator's target.
    controller._handle_packet(packet, clock())
    assert controller.snapshot["flow_ml_min"] == 42.25
    assert controller.snapshot["desired_flow_ml_min"] == 125.5
    assert controller.snapshot["pump_percent"] == 0


def test_run_metadata_samples_and_csv_keep_original_target(app, tmp_path):
    controller, _ = app
    controller.load_recipe(sequence())
    controller.start_run()
    controller.tick()
    controller.tick()
    run_id = controller.run_id
    assert run_id is not None
    controller.stop_run()
    controller.tick()
    controller.load_recipe(sequence(450))
    assert controller.snapshot["desired_flow_ml_min"] == 450

    row = controller.store.connection.execute("SELECT recipe_json FROM runs WHERE id=?", (run_id,)).fetchone()
    assert json.loads(row[0])["desired_flow_ml_min"] == 125.5
    samples = controller.store.connection.execute("SELECT payload_json FROM samples WHERE run_id=?", (run_id,)).fetchall()
    assert samples
    assert all(json.loads(row[0])["desired_flow_ml_min"] == 125.5 for row in samples)
    assert any(json.loads(row[0])["flow_ml_min"] != 125.5 for row in samples)

    exported = tmp_path / "run.csv"
    controller.export_csv(exported, run_id)
    with exported.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and all(float(row["desired_flow_ml_min"]) == 125.5 for row in rows)
    metadata = json.loads(exported.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert metadata["recipe"]["desired_flow_ml_min"] == 125.5

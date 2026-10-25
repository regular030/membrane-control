import copy
import json
import math
import pytest
from membrane_control.models import Recipe, Step
from membrane_control.engine import SequenceEngine
from membrane_control.recipes import built_in_recipes, read_recipe, write_recipe


def example():
    return Recipe(name="Test", steps=[Step("First", 2, (True, False, False, False, False, False, False), 10), Step("Second", 3)])


@pytest.mark.parametrize("field,value", [("duration_s", 0), ("duration_s", float('nan')),
    ("duration_s", True), ("pump_percent", 101), ("pump_percent", float('inf')),
    ("valves", [0]*7), ("valves", [False]*8)])
def test_invalid_steps_rejected(field, value):
    data = Step().to_dict()
    data[field] = value
    with pytest.raises(ValueError):
        Step.from_dict(data)


def test_recipe_validation_and_json_round_trip(tmp_path):
    recipe = example()
    recipe.repeat = 2
    write_recipe(tmp_path / "example.json", recipe)
    assert read_recipe(tmp_path / "example.json").to_dict() == recipe.to_dict()
    recipe.repeat = 0
    with pytest.raises(ValueError):
        recipe.validate()
    data = example().to_dict()
    data["schema_version"] = True
    with pytest.raises(ValueError):
        Recipe.from_dict(data)


def test_demo_presets_are_unapproved_and_valid():
    presets = built_in_recipes()
    assert set(presets) == {"CIP demo", "CWF demo", "Fouling demo"}
    for recipe in presets.values():
        recipe.validate()
        assert recipe.hardware_approved is False


def test_step_repeat_boundaries_and_completion():
    engine = SequenceEngine()
    recipe = example()
    recipe.repeat = 2
    engine.load(recipe)
    engine.start(100)
    assert (engine.step_index, engine.cycle, engine.pump_percent) == (0, 1, 10)
    engine.tick(102)
    assert (engine.step_index, engine.cycle) == (1, 1)
    engine.tick(105)
    assert (engine.step_index, engine.cycle) == (0, 2)
    engine.tick(110)
    assert engine.state == "idle"
    assert not any(engine.valves) and engine.pump_percent == 0


def test_fault_latches_and_no_manual_or_restart_until_cleared():
    engine = SequenceEngine()
    engine.load(example())
    engine.start(0)
    engine.fail("Overpressure")
    assert not any(engine.valves) and engine.pump_percent == 0
    engine.stop()
    with pytest.raises(ValueError):
        engine.start(1)
    with pytest.raises(ValueError):
        engine.manual([True]*7, 30)
    engine.clear_fault()
    assert engine.state == "idle" and engine.fault is None


def test_invalid_manual_command_does_not_partially_change_outputs():
    engine = SequenceEngine()
    engine.manual([True]*7, 10)
    with pytest.raises(ValueError):
        engine.manual([False]*7, 101)
    assert all(engine.valves) and engine.pump_percent == 10


def test_loading_recipe_is_an_immutable_snapshot():
    recipe = example()
    engine = SequenceEngine()
    engine.load(recipe)
    recipe.steps[0].pump_percent = 99
    engine.start(0)
    assert engine.pump_percent == 10


@pytest.mark.parametrize("name", ["A\0B", "A\nB", "\ud800", "界" * 30])
def test_recipe_names_reject_controls_invalid_unicode_and_controller_byte_overflow(name):
    recipe = Recipe(name=name)
    with pytest.raises(ValueError):
        recipe.validate()


def test_unicode_recipe_round_trip_and_overlarge_number_are_handled(tmp_path):
    recipe = Recipe(name="Échantillon", description="Membrane à tester")
    write_recipe(tmp_path / "unicode.json", recipe)
    assert "Échantillon" in (tmp_path / "unicode.json").read_text(encoding="utf-8")
    assert read_recipe(tmp_path / "unicode.json").name == recipe.name
    with pytest.raises(ValueError):
        Step(duration_s=10**500).validate()


def test_zero_manual_remains_manual_and_cannot_load_or_clear_until_stopped():
    engine = SequenceEngine()
    engine.manual([False]*7, 0)
    assert engine.state == "manual"
    with pytest.raises(ValueError):
        engine.load(example())
    with pytest.raises(ValueError):
        engine.clear_fault()
    engine.stop()
    engine.load(example())
    engine.fail("Test fault")
    with pytest.raises(ValueError):
        engine.load(example())
    engine.clear_fault()
    engine.load(example())

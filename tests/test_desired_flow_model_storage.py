import csv
import json

import pytest

from membrane_control.models import Recipe, Step
from membrane_control.recipes import read_recipe, write_recipe
from membrane_control.storage import RunStore


def test_target_round_trip_and_legacy_recipe_default(tmp_path):
    recipe = Recipe(name="Flow comparison", desired_flow_ml_min=125.5,
                    steps=[Step(pump_percent=20)])
    path = tmp_path / "recipe.json"
    write_recipe(path, recipe)
    restored = read_recipe(path)
    assert restored.desired_flow_ml_min == 125.5
    assert restored.steps[0].pump_percent == 20
    legacy = restored.to_dict()
    legacy.pop("desired_flow_ml_min")
    assert Recipe.from_dict(legacy).desired_flow_ml_min == 0


@pytest.mark.parametrize("invalid", [-1, 1_000_001, float("nan"), float("inf"), True, "125", None])
def test_import_rejects_invalid_target(invalid):
    data = Recipe().to_dict()
    data["desired_flow_ml_min"] = invalid
    with pytest.raises(ValueError, match="Desired flow"):
        Recipe.from_dict(data)


def test_target_is_metadata_not_a_firmware_command():
    recipe = Recipe(desired_flow_ml_min=250, steps=[Step(pump_percent=15)])
    wire = recipe.to_wire_dict()
    assert "desired_flow_ml_min" not in wire
    assert wire["steps"][0]["pump_percent"] == 15
    assert recipe.to_dict()["desired_flow_ml_min"] == 250


def test_target_and_measurement_export_separately_with_old_samples(tmp_path):
    store = RunStore(tmp_path / "data")
    try:
        run_id = store.start(Recipe(desired_flow_ml_min=125.5), {}, {})
        store.sample(run_id, {"flow_ml_min": 90, "desired_flow_ml_min": 125.5, "valves": [False] * 7})
        # A database created before desired-flow recording remains exportable.
        store.connection.execute(
            "INSERT INTO samples(run_id,time_utc,payload_json) VALUES(?,?,?)",
            (run_id, "2026-10-26T12:00:00Z", json.dumps({"flow_ml_min": 88})))
        store.connection.commit()
        path = tmp_path / "run.csv"
        store.export(path, run_id)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert float(rows[0]["flow_ml_min"]) == 90
        assert float(rows[0]["desired_flow_ml_min"]) == 125.5
        assert rows[1]["desired_flow_ml_min"] == ""
        metadata = json.loads(path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
        assert metadata["recipe"]["desired_flow_ml_min"] == 125.5
    finally:
        store.close()

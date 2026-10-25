import csv
import json
import pytest
from membrane_control.balance import MassFlow, parse_mass
from membrane_control.storage import RunStore
from membrane_control.models import Recipe


@pytest.mark.parametrize("line,expected", [("+ 123.4 g\r\n", 123.4), ("0.01 kg", 10), ("-2 mg", -0.002), ("ST, 5.5 g", 5.5)])
def test_mass_units(line, expected):
    assert parse_mass(line) == pytest.approx(expected)


@pytest.mark.parametrize("line", ["OVERLOAD", "123", "nan g", "10 oz", "DATE 5 g", "1 g garbage"])
def test_invalid_mass_is_not_a_valid_reading(line):
    with pytest.raises(ValueError):
        parse_mass(line)


def test_mass_slope_density_and_tare_reset():
    flow = MassFlow()
    for t in range(6):
        value = flow.update(t, 100 + t, 1.0)
    assert value == pytest.approx(60)
    assert flow.update(6, 0, 1.0) is None
    assert flow.update(12, 100, 1.0) is None  # stale gap cannot create a spike


def test_storage_export_and_interruption_recovery(tmp_path):
    store = RunStore(tmp_path)
    run = store.start(Recipe(), {"density_g_ml": 1}, {"simulation": True})
    store.sample(run, {"elapsed_s": 1, "valves": [False]*7, "simulation": True, "mass_g": 2,
                       "pump_feedback_v": 2.5, "controller_status": "Connected", "balance_status": "Weight data stale"})
    store.export(tmp_path / "run.csv", run)
    with (tmp_path / "run.csv").open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["mass_g"] == "2"
    assert rows[0]["pump_feedback_v"] == "2.5"
    assert rows[0]["controller_status"] == "Connected"
    assert rows[0]["balance_status"] == "Weight data stale"
    metadata = json.loads((tmp_path / "run.metadata.json").read_text())
    assert metadata["recipe"]["schema_version"] == 1
    store.close()
    store = RunStore(tmp_path)
    assert store.list_runs()[0]["status"] == "interrupted"
    store.close()

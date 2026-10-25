import pytest

from membrane_control.device_status import device_statuses


def statuses(snapshot=None, demo=False):
    return {row["key"]: row for row in device_statuses(snapshot or {}, demo)}


def test_demo_never_claims_physical_connections():
    rows = statuses({"controller_connected": True, "balance_connected": True}, demo=True)
    assert len(rows) == 6
    assert all(row["status"] == "Simulated" for row in rows.values())
    assert all(row["level"] == "warning" for row in rows.values())


def test_disconnected_controller_cannot_leave_old_sensor_values_green():
    rows = statuses({"controller_connected": False, "simulation": False,
                     "pressure_psi": 12, "flow_ml_min": 100, "pump_feedback_v": 5})
    assert rows["controller"]["status"] == "Not connected"
    assert all(rows[key]["status"] == "No reading" for key in ("pressure", "flow", "pump_feedback"))
    assert rows["outputs"]["status"] == "Not monitored"


def test_real_balance_can_connect_alongside_dry_run_firmware():
    rows = statuses({"controller_connected": True, "simulation": True,
                     "balance_connected": True, "mass_g": 12.3})
    assert rows["controller"]["status"] == "Connected (dry run)"
    assert rows["balance"]["status"] == "Connected"
    assert all(rows[key]["status"] == "Simulated" for key in ("pressure", "flow", "pump_feedback", "outputs"))


def test_live_analog_readings_are_not_reported_as_verified_connections():
    rows = statuses({"controller_connected": True, "simulation": False,
                     "pressure_psi": 0, "flow_ml_min": 0, "pump_feedback_v": 0,
                     "hardware_verified": True, "valves": [True] * 7, "pump_percent": 50})
    assert rows["controller"]["status"] == "Connected"
    assert all(rows[key]["status"] == "Reading received" for key in ("pressure", "flow", "pump_feedback"))
    assert rows["balance"]["status"] == "Not connected"
    assert rows["outputs"]["status"] == "Not monitored"


@pytest.mark.parametrize("invalid", [None, True, float("nan"), float("inf"), "12.3"])
def test_invalid_analog_and_mass_values_do_not_report_available(invalid):
    rows = statuses({"controller_connected": True, "simulation": False,
                     "pressure_psi": invalid, "balance_connected": True, "mass_g": invalid})
    assert rows["pressure"]["status"] == "No reading"
    assert rows["balance"]["status"] == "Not connected"

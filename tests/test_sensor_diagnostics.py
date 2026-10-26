"""Optional firmware diagnostics explain missing data without changing controls."""
import copy

import pytest

from membrane_control.controller import AppController
from membrane_control.device_status import (
    checked_controller_diagnostics,
    checked_sensor_status,
    device_statuses,
)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FakeDriver:
    port = "FAKE-DIAGNOSTICS-ONLY"

    def __init__(self):
        self.sent = []

    def send(self, packet):
        self.sent.append(packet)

    def poll(self, now):
        return []

    def close(self):
        pass


@pytest.fixture
def app(tmp_path):
    clock = Clock()
    controller = AppController(tmp_path, clock)
    controller.set_simulation(False)
    controller.driver = FakeDriver()
    yield controller, clock
    controller.close()


def hello(controller, clock, **extra):
    request_id = controller._request("hello")
    packet = {"v": 1, "id": request_id, "type": "hello", "ok": True,
              "device": "basu-membrane-control", "protocol_version": 1,
              "firmware_version": "diagnostic-test", "valve_count": 7,
              "simulation": False, "hardware_verified": False, **extra}
    controller._handle_packet(packet, clock())
    return packet


def telemetry(controller, clock, **extra):
    packet = {"v": 1, "type": "telemetry", "uptime_ms": 1000,
              "state": "idle", "simulation": False, "hardware_verified": False,
              "valves": [False] * 7, "pump_percent": 0, "step_index": -1,
              "cycle": 0, "remaining_s": 0, "fault": None,
              "pressure_psi": None, "flow_ml_min": None, "pump_feedback_v": None,
              **extra}
    controller._handle_packet(packet, clock())


def rows(snapshot):
    return {row["key"]: row for row in device_statuses(snapshot, False)}


def diagnostics():
    return {
        "controller_mode": "physical",
        "hardware_status": "board profile has not been verified",
        "sensor_inputs": {
            "pressure": {"source": "native_adc1", "pin": 34, "calibration_verified": False},
            "flow": {"source": "disabled", "calibration_verified": False},
            "pump_feedback": {"source": "ads1115", "channel": -1, "calibration_verified": False},
        },
    }


def test_new_hello_metadata_is_sanitized_and_exposed_without_unlocking(app):
    controller, clock = app
    metadata = diagnostics()
    metadata["sensor_inputs"]["pressure"]["raw_volts"] = 10
    metadata["sensor_inputs"]["surprise"] = {"source": "native_adc1", "pin": 35}
    metadata["sensor_status"] = {"pressure": "reading_received"}  # Telemetry only.
    packet = hello(controller, clock, **metadata)
    expected = diagnostics()
    assert controller.snapshot["controller_connected"]
    assert not controller.snapshot["hardware_verified"]
    assert controller.local_fault is None
    for key, value in expected.items():
        assert controller.snapshot[key] == value
        assert controller.device[key] == value
    assert controller.snapshot["sensor_status"] == {}
    assert "sensor_status" not in controller.device
    packet["sensor_inputs"]["pressure"]["pin"] = 35
    controller.snapshot["sensor_inputs"]["pressure"]["pin"] = 36
    assert controller.device["sensor_inputs"]["pressure"]["pin"] == 34
    telemetry(controller, clock)
    with pytest.raises(ValueError, match="verified firmware"):
        controller.start_run()


def test_old_firmware_without_diagnostics_keeps_existing_connection_behavior(app):
    controller, clock = app
    hello(controller, clock)
    telemetry(controller, clock, pressure_psi=0)
    assert controller.snapshot["controller_mode"] is None
    assert controller.snapshot["hardware_status"] is None
    assert controller.snapshot["sensor_inputs"] == controller.snapshot["sensor_status"] == {}
    assert rows(controller.snapshot)["pressure"]["status"] == "Reading received"
    assert rows(controller.snapshot)["flow"]["status"] == "No reading"
    assert controller.local_fault is None


@pytest.mark.parametrize("bad", [None, True, [], "unknown", {"pressure": []},
    {"pressure": {"source": ["native_adc1"], "calibration_verified": False}},
    {"pressure": {"source": "native_adc1", "pin": True, "calibration_verified": False}},
    {"flow": {"source": "ads1115", "channel": 4, "calibration_verified": False}},
    {"pressure": {"source": "native_adc1", "pin": 34, "calibration_verified": "yes"}}])
def test_malformed_optional_hello_metadata_does_not_fault_or_reject_identity(app, bad):
    controller, clock = app
    hello(controller, clock, sensor_inputs=bad, controller_mode=[], hardware_status={"bad": True})
    telemetry(controller, clock, flow_ml_min=0)
    assert controller.snapshot["controller_connected"]
    assert controller.snapshot["sensor_inputs"] == {}
    assert controller.snapshot["controller_mode"] is None
    assert controller.snapshot["hardware_status"] is None
    assert controller.local_fault is None
    assert rows(controller.snapshot)["flow"]["status"] == "Reading received"


@pytest.mark.parametrize("reason", ["x" * 161, "bad\x00status", "two\nlines", 12, [], ""])
def test_hardware_reason_is_bounded_and_plain_text(reason):
    result = checked_controller_diagnostics({"simulation": False, "hardware_status": reason})
    assert "hardware_status" not in result


def test_known_diagnostic_keys_only_and_mode_cannot_contradict_simulation():
    packet = diagnostics()
    packet.update(simulation=True, sensor_status={"flow": "reading_received"})
    packet["sensor_inputs"]["flow"]["pin"] = 30
    checked = checked_controller_diagnostics(packet)
    assert "controller_mode" not in checked
    assert "sensor_status" not in checked
    assert checked["sensor_inputs"]["flow"] == {"source": "disabled", "calibration_verified": False}
    assert checked_controller_diagnostics({"simulation": True, "controller_mode": "dry_run"}) == {
        "controller_mode": "dry_run"}


def test_unmapped_selected_input_metadata_is_preserved_without_reading():
    metadata = {"simulation": False, "sensor_inputs": {
        "pressure": {"source": "native_adc1", "pin": -1, "calibration_verified": False},
        "flow": {"source": "ads1115", "channel": -1, "calibration_verified": False}}}
    assert checked_controller_diagnostics(metadata)["sensor_inputs"] == metadata["sensor_inputs"]


@pytest.mark.parametrize("code,status", [
    ("not_configured", "Not configured: real flow channel not set"),
    ("profile_locked", "Profile locked: inputs not read"),
    ("hardware_unavailable", "Input hardware unavailable"),
    ("uncalibrated", "Input not calibrated"),
    ("out_of_range", "Reading invalid/out of range"),
    ("stale", "Reading stale"),
    ("simulated", "Simulated: no real reading"),
    ("reading_received", "No reading"),
])
def test_optional_sensor_reason_explains_null_but_does_not_create_data(app, code, status):
    controller, clock = app
    hello(controller, clock)
    telemetry(controller, clock, sensor_status={"flow": code})
    assert controller.snapshot["flow_ml_min"] is None
    assert controller.snapshot["flux_lmh"] is None
    row = rows(controller.snapshot)["flow"]
    assert row["status"] == status
    assert row["level"] == "warning"
    assert controller.local_fault is None


@pytest.mark.parametrize("code", ["not_configured", "profile_locked", "hardware_unavailable",
    "uncalibrated", "out_of_range", "stale", "simulated", "reading_received"])
def test_valid_zero_always_wins_over_optional_diagnostic_claims(app, code):
    controller, clock = app
    hello(controller, clock, **diagnostics())
    telemetry(controller, clock, pressure_psi=0, flow_ml_min=0, pump_feedback_v=0,
              sensor_status={key: code for key in ("pressure", "flow", "pump_feedback")})
    for key in ("pressure", "flow", "pump_feedback"):
        assert rows(controller.snapshot)[key]["status"] == "Reading received"
        assert rows(controller.snapshot)[key]["level"] == "success"


@pytest.mark.parametrize("bad", [None, [], "stale", {"flow": []}, {"flow": True},
    {"flow": "unknown"}, {"flow": "x" * 8192}])
def test_bad_optional_sensor_status_does_not_discard_valid_telemetry(app, bad):
    controller, clock = app
    hello(controller, clock)
    clock.now += 0.25
    telemetry(controller, clock, flow_ml_min=5, sensor_status=bad)
    assert controller.last_telemetry == clock()
    assert controller.snapshot["flow_ml_min"] == 5
    assert controller.snapshot["sensor_status"] == {}
    assert controller.local_fault is None


def test_unknown_status_entries_ignored_independently():
    assert checked_sensor_status({"flow": "not_configured", "pressure": [],
                                  "unexpected": "profile_locked"}) == {"flow": "not_configured"}


def test_new_telemetry_missing_metadata_clears_old_diagnostic_reason(app):
    controller, clock = app
    hello(controller, clock)
    telemetry(controller, clock, sensor_status={"flow": "out_of_range"})
    clock.now += 0.25
    telemetry(controller, clock, uptime_ms=1250)
    assert controller.snapshot["sensor_status"] == {}
    assert rows(controller.snapshot)["flow"]["status"] == "No reading"


def test_disabled_input_can_be_explained_from_hello_before_first_telemetry(app):
    controller, clock = app
    hello(controller, clock, **diagnostics())
    assert rows(controller.snapshot)["flow"]["status"] == "Not configured: real flow channel not set"


def test_stale_and_disconnected_controller_take_priority_over_sensor_reasons(app):
    controller, clock = app
    hello(controller, clock, **diagnostics())
    telemetry(controller, clock, sensor_status={"flow": "not_configured"})
    clock.now += 2.1
    controller.tick()
    assert controller.snapshot["controller_status"] == "Telemetry stale"
    assert rows(controller.snapshot)["flow"]["status"] == "No reading"
    controller.disconnect_controller()
    assert controller.snapshot["sensor_inputs"] == controller.snapshot["sensor_status"] == {}
    assert controller.snapshot["controller_mode"] is None
    assert controller.snapshot["hardware_status"] is None


def test_dry_run_and_desktop_simulation_cannot_be_disguised_by_diagnostics():
    snapshot = {"controller_connected": True, "simulation": True,
                "sensor_status": {"flow": "reading_received"}, "flow_ml_min": 100}
    assert rows(snapshot)["flow"]["status"] == "Simulated"
    assert all(row["status"] == "Simulated" for row in device_statuses(snapshot, True))


@pytest.mark.parametrize("invalid", [True, float("nan"), "1.0"])
def test_diagnostics_do_not_explain_non_null_invalid_values_as_physical_data(invalid):
    snapshot = {"controller_connected": True, "simulation": False, "flow_ml_min": invalid,
                "sensor_status": {"flow": "not_configured"}}
    assert rows(snapshot)["flow"]["status"] == "No reading"


def test_malformed_required_telemetry_cannot_update_diagnostics_or_freshness(app):
    controller, clock = app
    hello(controller, clock)
    telemetry(controller, clock, sensor_status={"flow": "not_configured"})
    before = copy.deepcopy(controller.snapshot)
    old_time = controller.last_telemetry
    clock.now += 0.25
    telemetry(controller, clock, valves=[1] * 7, sensor_status={"flow": "reading_received"})
    assert controller.snapshot == before
    assert controller.last_telemetry == old_time


def test_diagnostics_cannot_bypass_controller_identity_or_existing_reset_fault(app):
    controller, clock = app
    hello(controller, clock, device="other-device", **diagnostics())
    assert not controller.snapshot["controller_connected"]
    assert controller.snapshot["sensor_inputs"] == {}
    hello(controller, clock, **diagnostics())
    telemetry(controller, clock, uptime_ms=10000, sensor_status={"flow": "not_configured"})
    clock.now += 0.25
    telemetry(controller, clock, uptime_ms=0, sensor_status={"flow": "reading_received"})
    assert "restarted" in controller.local_fault
    assert not controller.snapshot["controller_connected"]
    assert controller.snapshot["sensor_inputs"] == controller.snapshot["sensor_status"] == {}

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


def test_reviewed_manual_pump_profile_guards_takeover_without_recipe_approval(app):
    controller, clock = app
    valves = [True, False, True, False, False, False, False]
    profile = {"max_percent": 50, "valves": valves}
    hello(controller, clock, hardware_verified=True, manual_pump_profile=profile)
    telemetry(controller, clock, hardware_verified=True, pressure_psi=0)
    assert controller.snapshot["manual_pump_profile"] == profile
    assert not controller.recipe.hardware_approved

    with pytest.raises(ValueError, match="at most 50%"):
        controller.set_manual(valves, 51)
    with pytest.raises(ValueError, match="V1 and V3"):
        controller.set_manual([False] * 7, 35)

    controller.snapshot.update(state="manual_valves", valves=[False] * 7)
    with pytest.raises(ValueError, match="Stop manual valves"):
        controller.set_manual(valves, 35)
    controller.snapshot["valves"] = valves.copy()
    controller.snapshot["pressure_psi"] = None
    with pytest.raises(ValueError, match="valid pressure"):
        controller.set_manual(valves, 35)
    controller.snapshot["pressure_psi"] = 21
    with pytest.raises(ValueError, match="desktop stop threshold"):
        controller.set_manual(valves, 35)

    controller.snapshot["pressure_psi"] = 0
    controller.set_manual(valves, 50)
    assert controller.driver.sent[-1]["cmd"] == "manual"
    assert controller.driver.sent[-1]["valves"] == valves
    assert controller.driver.sent[-1]["pump_percent"] == 50
    controller.disconnect_controller(request_stop=False)
    assert controller.snapshot["manual_pump_profile"] is None


@pytest.mark.parametrize("startup_ms", [1000, 10_000])
def test_manual_pressure_startup_uses_firmware_status_and_keeps_loss_stop(app, startup_ms):
    controller, clock = app
    valves = [True, False, True, False, False, False, False]
    profile = {"max_percent": 50, "valves": valves, "pressure_startup_ms": startup_ms}
    hello(controller, clock, hardware_verified=True, manual_pump_profile=profile)
    telemetry(controller, clock, hardware_verified=True, pressure_startup="available", pressure_adc_mv=74)
    assert controller.snapshot["manual_pump_profile"] == profile
    assert controller.snapshot["pressure_startup"] == "available"
    assert controller.snapshot["pressure_psi"] is None
    assert controller.snapshot["pressure_adc_mv"] == 74
    controller.recipe.hardware_approved = True
    with pytest.raises(ValueError, match="valid pressure"):
        controller.start_run()
    controller.set_manual(valves, 25)
    request = controller.driver.sent[-1]
    assert request["cmd"] == "manual"
    assert request["allow_pressure_startup"] is True
    controller._handle_packet({"v": 1, "type": "ack", "ok": True, "id": request["id"]}, clock())

    running = {"hardware_verified": True, "state": "manual", "valves": valves, "pump_percent": 25}
    for uptime_ms in range(1250, 1000 + startup_ms, 250):
        clock.now += 0.25
        telemetry(controller, clock, **running, uptime_ms=uptime_ms, pressure_startup="active", pressure_adc_mv=74)
        controller.tick()
    assert controller.snapshot["pressure_startup"] == "active"
    assert controller.local_fault is None
    assert controller.driver.sent[-1]["cmd"] == "heartbeat"
    with pytest.raises(ValueError, match="before changing pump speed"):
        controller.set_manual(valves, 35)

    clock.now += 0.25
    telemetry(controller, clock, **running, uptime_ms=1000 + startup_ms, pressure_psi=12, pressure_adc_mv=121)
    assert controller.snapshot["pressure_psi"] == 12
    assert controller.snapshot["pressure_startup"] is None
    clock.now += 0.25
    telemetry(controller, clock, **running, uptime_ms=1250 + startup_ms, pressure_adc_mv=True)
    assert controller.snapshot["pressure_adc_mv"] is None
    assert controller.local_fault == "Pressure reading unavailable during physical operation"
    assert controller.driver.sent[-1]["cmd"] == "stop"


@pytest.mark.parametrize("startup_ms", [None, False, 0, 10_001, 10_000.0, "10000"])
def test_missing_or_invalid_startup_capability_never_unlocks_pump(app, startup_ms):
    controller, clock = app
    valves = [True, False, True, False, False, False, False]
    hello(controller, clock, hardware_verified=True, manual_pump_profile={
        "max_percent": 50, "valves": valves, "pressure_startup_ms": startup_ms})
    telemetry(controller, clock, hardware_verified=True, pressure_startup="available", pressure_adc_mv=74)
    assert controller.snapshot["manual_pump_profile"] == {"max_percent": 50, "valves": valves}
    assert controller.snapshot["pressure_startup"] is controller.snapshot["pressure_adc_mv"] is None
    with pytest.raises(ValueError, match="valid pressure"):
        controller.set_manual(valves, 25)


def test_startup_phase_does_not_override_valid_overpressure(app):
    controller, clock = app
    valves = [True, False, True, False, False, False, False]
    hello(controller, clock, hardware_verified=True, manual_pump_profile={
        "max_percent": 50, "valves": valves, "pressure_startup_ms": 10_000})
    controller.settings["max_pressure_psi"] = 80
    telemetry(controller, clock, hardware_verified=True, state="manual", valves=valves, pump_percent=25,
              pressure_startup="active", pressure_psi=81)
    assert controller.snapshot["pressure_startup"] is None
    assert controller.local_fault == "Desktop pressure limit exceeded"


@pytest.mark.parametrize("verified,maximum,valves", [
    (False, 50, [True, False, True, False, False, False, False]),
    (True, 51, [True, False, True, False, False, False, False]),
    (True, True, [True, False, True, False, False, False, False]),
    (True, float("nan"), [True, False, True, False, False, False, False]),
    (True, 50, [1, False, True, False, False, False, False]),
    (True, 50, [True, False, True, False, False, False, True]),
])
def test_unverified_or_invalid_manual_pump_profile_cannot_bypass_recipe(app, verified, maximum, valves):
    controller, clock = app
    hello(controller, clock, hardware_verified=verified,
          manual_pump_profile={"max_percent": maximum, "valves": valves})
    telemetry(controller, clock, hardware_verified=verified, pressure_psi=0)
    assert controller.snapshot["manual_pump_profile"] is None
    with pytest.raises(ValueError, match="hardware and recipe are approved"):
        controller.set_manual([True, False, True, False, False, False, False], 35)


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

def test_sensor_voltage_check_is_separate_from_calibrated_telemetry(app):
    controller, clock = app
    hello(controller, clock, sensor_test_available=True)
    telemetry(controller, clock)
    controller.read_sensor_inputs()
    request = controller.driver.sent[-1]
    assert request["cmd"] == "read_sensor_inputs"
    assert controller.sensor_test_pending
    voltages = {"pressure": 800, "flow": 0, "pump_feedback": 1800}
    controller._handle_packet({"v": 1, "type": "ack", "ok": True,
                               "id": request["id"], "adc_pin_mv": voltages}, clock())
    assert not controller.sensor_test_pending
    assert controller.snapshot["sensor_test_voltages"] == voltages
    assert all(controller.snapshot[key] is None
               for key in ("pressure_psi", "flow_ml_min", "pump_feedback_v"))
    assert not controller.snapshot["hardware_verified"]
    controller.disconnect_controller(request_stop=False)
    assert not controller.snapshot["sensor_test_available"]
    assert not controller.snapshot["sensor_test_voltages"]


def test_live_sensor_zero_is_a_session_display_baseline_only(app):
    controller, clock = app
    hello(controller, clock, sensor_test_available=True)
    readings = {"pressure": 108, "flow": 0, "pump_feedback": 250}
    telemetry(controller, clock, adc_pin_mv=readings)
    sent = list(controller.driver.sent)
    baseline = controller.zero_live_sensors()
    assert baseline == {"pressure": 108, "flow": 0}
    baseline["pressure"] = 900
    assert controller.snapshot["live_sensor_zero"] == {"pressure": 108, "flow": 0}
    assert controller.snapshot["live_sensor_voltages"] == readings
    assert all(controller.snapshot[key] is None
               for key in ("pressure_psi", "flow_ml_min", "pump_feedback_v"))
    assert controller.driver.sent == sent and not controller.snapshot["hardware_verified"]
    controller.clear_live_sensor_zero()
    assert controller.snapshot["live_sensor_zero"] == {}
    controller.zero_live_sensors()
    controller.disconnect_controller(request_stop=False)
    assert controller.snapshot["live_sensor_zero"] == {}


@pytest.mark.parametrize("blocked", ["stale", "no readings", "pending stop", "fault", "dry run", "reviewed"])
def test_live_sensor_zero_requires_fresh_idle_factory_telemetry(app, blocked):
    controller, clock = app
    hello(controller, clock, sensor_test_available=True)
    telemetry(controller, clock, adc_pin_mv={"pressure": 108, "flow": 0, "pump_feedback": 250})
    if blocked == "stale":
        clock.now += 2.1
    elif blocked == "no readings":
        telemetry(controller, clock)
    elif blocked == "pending stop":
        controller.stop_run()
    elif blocked == "fault":
        controller.snapshot["fault"] = "check controller"
    elif blocked == "dry run":
        controller.snapshot["simulation"] = True
    elif blocked == "reviewed":
        controller.snapshot["hardware_verified"] = True
    with pytest.raises(ValueError):
        controller.zero_live_sensors()
    assert controller.snapshot["live_sensor_zero"] == {}


@pytest.mark.parametrize("response", [
    {},
    {"adc_pin_mv": {"pressure": True, "flow": 0, "pump_feedback": 2000}},
    {"adc_pin_mv": {"pressure": 5000, "flow": 0, "pump_feedback": 2000}},
])
def test_invalid_sensor_check_response_does_not_fill_values_or_trigger_stop(app, response):
    controller, clock = app
    hello(controller, clock, sensor_test_available=True)
    telemetry(controller, clock)
    controller.read_sensor_inputs()
    request = controller.driver.sent[-1]
    controller._handle_packet({"v": 1, "type": "ack", "ok": True, "id": request["id"], **response}, clock())
    assert controller.snapshot["sensor_test_voltages"] == {}
    assert "Invalid sensor voltage response" in controller.snapshot["sensor_test_status"]
    assert not controller.stop_pending


def test_sensor_check_times_out_without_stopping_healthy_controller(app):
    controller, clock = app
    hello(controller, clock, sensor_test_available=True)
    telemetry(controller, clock)
    controller.read_sensor_inputs()
    clock.now += 3.1
    telemetry(controller, clock, uptime_ms=4100)
    controller.tick()
    assert "timed out" in controller.snapshot["sensor_test_status"]
    assert not controller.sensor_test_pending
    assert controller.snapshot["controller_connected"]
    assert not any(packet["cmd"] == "stop" for packet in controller.driver.sent)


def test_hello_without_telemetry_releases_port_without_heartbeat(app):
    controller, clock = app
    controller.connect_started = clock.now - 7
    driver = controller.driver
    hello(controller, clock)
    controller.tick()
    assert controller.driver is driver
    clock.now += 2.1
    controller.tick()
    assert controller.driver is None
    assert "sent no valid telemetry" in controller.snapshot["controller_status"]
    assert [packet["cmd"] for packet in driver.sent] == ["hello"]

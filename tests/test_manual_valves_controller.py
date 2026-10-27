"""Normal six-valve controls remain independent of pump/experiment approvals."""
import pytest

from membrane_control.controller import AppController
from membrane_control.device_status import checked_valve_control, device_statuses


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


class Driver:
    port = "FAKE-VALVES"

    def __init__(self):
        self.sent = []
        self.closed = False
        self.error = None

    def send(self, packet):
        if self.error:
            raise RuntimeError(self.error)
        self.sent.append(packet)

    def poll(self, now):
        return []

    def close(self):
        self.closed = True


def identify(controller, clock, **changes):
    request_id = controller._request("hello")
    packet = {"v": 1, "type": "hello", "id": request_id, "ok": True,
              "device": "basu-membrane-control", "protocol_version": 1,
              "firmware_version": "valve-test", "valve_count": 7,
              "simulation": False, "hardware_verified": False,
              "valve_control_ready": True, "manual_valve_count": 6,
              "manual_valve_ids": [1, 2, 3, 4, 5, 7], "valve_bits": [0, 1, 2, 3, 5, 6],
              **changes}
    controller._handle_packet(packet, clock())


def telemetry(controller, clock, **changes):
    controller._handle_packet({"v": 1, "type": "telemetry", "uptime_ms": 1000,
        "simulation": False, "hardware_verified": False, "valve_control_ready": True,
        "state": "idle", "valves": [False] * 7, "pump_percent": 0,
        "pressure_psi": None, "flow_ml_min": None, "pump_feedback_v": None,
        "step_index": -1, "cycle": 0, "remaining_s": 0, "fault": None,
        **changes}, clock())


@pytest.fixture
def app(tmp_path):
    clock = Clock()
    controller = AppController(tmp_path, clock)
    controller.set_simulation(False)
    controller.driver = Driver()
    identify(controller, clock)
    telemetry(controller, clock)
    yield controller, clock
    controller.close()


def acknowledge(controller, clock, *, ok=True):
    request_id = next(key for key, value in controller.pending.items() if value[0] == "manual_valves")
    controller._handle_packet({"v": 1, "type": "ack" if ok else "error", "id": request_id,
                              "ok": ok, "error": "Rejected test command"}, clock())


def test_six_valve_command_inserts_unused_v6_slot_and_waits_for_ack_without_sensors(app):
    controller, clock = app
    controller.recipe.require_balance = True
    controller.settings["require_balance"] = True
    requested = [True, False, True, False, False, True]
    controller.set_manual_valves(requested)
    packet = controller.driver.sent[-1]
    assert packet["cmd"] == "manual_valves" and packet["valves"] == [True, False, True, False, False, False, True]
    assert "pump_percent" not in packet
    assert controller.manual_pending and controller.snapshot["state"] == "idle"
    assert not any(controller.snapshot["valves"])
    controller.tick()  # A saved balance requirement cannot abort valve-only pending control.
    assert controller.local_fault is None
    acknowledge(controller, clock)
    assert controller.snapshot["state"] == "manual_valves"
    assert controller.snapshot["pump_percent"] == 0
    assert controller.snapshot["valves"] == [True, False, True, False, False, False, True]
    controller.tick()
    assert controller.local_fault is None
    assert not controller.snapshot["hardware_verified"]
    assert controller.snapshot["pressure_psi"] is None


def test_valve_only_telemetry_needs_no_pressure_or_balance_and_remains_active(app):
    controller, clock = app
    controller.settings["require_balance"] = True
    controller.set_manual_valves([True] * 6)
    acknowledge(controller, clock)
    telemetry(controller, clock, state="manual_valves", valves=[True] * 5 + [False, True])
    controller.tick()
    assert controller._active() and controller.local_fault is None
    with pytest.raises(ValueError, match="active"):
        controller.start_run()
    with pytest.raises(ValueError, match="Stop"):
        controller.set_manual([False] * 7, 0)
    with pytest.raises(ValueError, match="Stop"):
        controller.set_simulation(True)


def test_all_off_is_still_manual_valves_until_stop_ack(app):
    controller, clock = app
    controller.set_manual_valves([False] * 7)
    acknowledge(controller, clock)
    assert controller.snapshot["state"] == "manual_valves"
    controller.stop_run()
    assert controller.stop_pending
    stop_id = next(key for key, value in controller.pending.items() if value[0] == "stop")
    controller._handle_packet({"v": 1, "type": "ack", "id": stop_id, "ok": True}, clock())
    assert controller.snapshot["state"] == "idle" and not controller._active()


@pytest.mark.parametrize("values", [[True] * 7, [True] * 5, [1] * 6,
    [False] * 5 + [None], "000000", None])
def test_only_six_exact_boolean_valves_can_be_commanded(app, values):
    controller, _ = app
    before = list(controller.driver.sent)
    with pytest.raises(ValueError):
        controller.set_manual_valves(values)
    assert controller.driver.sent == before
    assert not controller.manual_pending


@pytest.mark.parametrize("changes", [
    {"valve_control_ready": False}, {"valve_control_ready": 1},
    {"manual_valve_count": 7, "valve_bits": list(range(7))},
    {"manual_valve_count": True}, {"valve_bits": [0, 1, 2, 3, 4, 4]},
    {"valve_bits": [0, 1, 2, 3, 4, True]}, {"valve_bits": [0, 1, 2, 3, 4, 16]},
    {"manual_valve_ids": [1, 2, 3, 4, 5, 6]},
    {"manual_valve_ids": [True, 2, 3, 4, 5, 7]},
    {"manual_valve_ids": [1, 2, 3, 4, 7, 5]},
    {"valve_bits": [0, 1, 2, 3, 4, 5]},
])
def test_bad_capability_cannot_unlock_valves(app, changes):
    controller, clock = app
    identify(controller, clock, **changes)
    assert controller.snapshot["valve_control_ready"] is False
    before = len(controller.driver.sent)
    with pytest.raises(ValueError):
        controller.set_manual_valves([False] * 6)
    assert len(controller.driver.sent) == before
    assert controller.local_fault is None


def test_older_firmware_defaults_to_no_valve_only_capability():
    assert checked_valve_control({}) == {"valve_control_ready": False,
        "manual_valve_count": 0, "manual_valve_ids": [], "valve_bits": [],
        "valve_control_status": "Update controller firmware to 0.1.16 or later for the confirmed V1-V5 and V7 mapping"}


def test_v15_without_ids_stays_connected_but_cannot_misroute_valve_commands(app):
    controller, clock = app
    identify(controller, clock, manual_valve_ids=None, valve_bits=[0, 1, 2, 3, 4, 5],
             firmware_version="0.1.15")
    telemetry(controller, clock)  # v15's own advertised readiness is still True.
    assert controller.snapshot["controller_connected"] and controller.local_fault is None
    assert not controller.snapshot["valve_control_ready"]
    assert controller.snapshot["manual_valve_ids"] == []
    assert "0.1.16" in controller.snapshot["valve_control_status"]
    before = len(controller.driver.sent)
    with pytest.raises(ValueError, match="Update controller firmware to 0.1.16"):
        controller.set_manual_valves([False, False, False, False, False, True])
    assert len(controller.driver.sent) == before


@pytest.mark.parametrize("ui_index,wire_index", [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 6)])
def test_each_installed_physical_id_uses_its_own_legacy_wire_slot(app, ui_index, wire_index):
    controller, _ = app
    requested = [False] * 6
    requested[ui_index] = True
    controller.set_manual_valves(requested)
    actual = controller.driver.sent[-1]["valves"]
    assert actual[wire_index] is True
    assert sum(actual) == 1
    assert actual[5] is False


def test_seven_slot_input_and_telemetry_allow_v7_but_not_unused_v6(app):
    controller, clock = app
    requested = [False, False, False, False, False, False, True]
    controller.set_manual_valves(requested)
    assert controller.driver.sent[-1]["valves"] == requested
    acknowledge(controller, clock)
    clock.now += 0.25
    telemetry(controller, clock, state="manual_valves", valves=requested, uptime_ms=1250)
    assert controller.snapshot["state"] == "manual_valves"
    assert controller.snapshot["valves"] == requested
    assert controller.last_telemetry == clock()
    assert controller.local_fault is None
    invalid = [False, False, False, False, False, True, False]
    with pytest.raises(ValueError, match="V6 is not installed"):
        controller.set_manual_valves(invalid)
    clock.now += 0.25
    telemetry(controller, clock, state="manual_valves", valves=invalid, uptime_ms=1500)
    assert controller.snapshot["valves"] == requested
    assert controller.last_telemetry == clock() - 0.25


@pytest.mark.parametrize("gate", ["disconnected", "stale", "pending", "stopping", "manual", "running", "fault"])
def test_valve_only_controls_keep_connection_ack_operation_and_fault_gates(app, gate):
    controller, clock = app
    if gate == "disconnected":
        controller.snapshot["controller_connected"] = False
    elif gate == "stale":
        clock.now += 2.1
    elif gate == "pending":
        controller.set_manual_valves([False] * 6)
    elif gate == "stopping":
        controller.stop_run()
    elif gate == "fault":
        controller.local_fault = "Existing fault"
    else:
        controller.snapshot["state"] = gate
    before = len(controller.driver.sent)
    with pytest.raises(ValueError):
        controller.set_manual_valves([True] * 6)
    assert len(controller.driver.sent) == before


def test_rejected_valve_command_latches_fault_and_requests_stop(app):
    controller, clock = app
    controller.set_manual_valves([True] * 6)
    acknowledge(controller, clock, ok=False)
    assert controller.local_fault == "Rejected test command"
    assert controller.stop_pending
    assert controller.driver.sent[-1]["cmd"] == "stop"
    assert controller.snapshot["state"] == "fault"


def test_unsent_valve_command_restores_pending_state(app):
    controller, _ = app
    controller.driver.error = "Fake write failed"
    with pytest.raises(RuntimeError, match="Fake write failed"):
        controller.set_manual_valves([True] * 6)
    assert not controller.manual_pending and controller.manual_requested is None
    assert not controller.snapshot["manual_pending"]


def test_valve_capability_does_not_unlock_pump_or_experiments(app):
    controller, _ = app
    controller.recipe.hardware_approved = True
    with pytest.raises(ValueError, match="locked"):
        controller.set_manual([True] * 7, 25)
    with pytest.raises(ValueError, match="verified firmware"):
        controller.start_run()


@pytest.mark.parametrize("changes", [{"pump_percent": 1}, {"valves": [True] * 7},
                                    {"valve_control_ready": False}])
def test_invalid_valve_mode_telemetry_cannot_refresh_readings(app, changes):
    controller, clock = app
    before = controller.last_telemetry
    clock.now += 0.25
    telemetry(controller, clock, state="manual_valves", **changes)
    assert controller.last_telemetry == before
    assert controller.snapshot["state"] != "manual_valves"


def test_changed_capability_disconnects_instead_of_silently_unlocking(app):
    controller, clock = app
    telemetry(controller, clock, valve_control_ready=False)
    assert controller.driver is None
    assert "capability changed" in controller.local_fault
    assert not controller.snapshot["valve_control_ready"]


def test_valve_only_telemetry_staleness_faults_and_disconnection_clears_capability(app):
    controller, clock = app
    controller.set_manual_valves([True] * 6)
    acknowledge(controller, clock)
    clock.now += 2.1
    controller.tick()
    assert controller.local_fault == "Controller telemetry is stale"
    controller.disconnect_controller()
    assert not controller.snapshot["valve_control_ready"]
    assert controller.snapshot["valve_bits"] == []


def test_simulation_uses_existing_simulator_with_v7_available_and_v6_off(tmp_path):
    controller = AppController(tmp_path, Clock())
    try:
        controller.tick()
        controller.set_manual_valves([True] * 6)
        controller.tick()
        assert controller.snapshot["valves"] == [True] * 5 + [False, True]
        assert controller.snapshot["pump_percent"] == 0
        with pytest.raises(ValueError, match="V6 is not installed"):
            controller.set_manual_valves([True] * 7)
    finally:
        controller.close()


def test_device_status_does_not_claim_valve_motion_is_monitored(app):
    controller, _ = app
    output = next(row for row in device_statuses(controller.snapshot, False) if row["key"] == "outputs")
    assert output["status"] == "Valve control ready"
    assert output["level"] != "success"
    assert "not monitored" in output["detail"]

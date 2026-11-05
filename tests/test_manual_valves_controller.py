"""Normal six-valve controls remain independent of pump/experiment approvals."""
import json

import pytest

import membrane_control.controller as controller_module
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
        self.events = []
        self.closed = False
        self.error = None

    def send(self, packet):
        if self.error:
            raise RuntimeError(self.error)
        self.sent.append(packet)

    def poll(self, now):
        events, self.events = self.events, []
        return events

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


def test_exact_new_telemetry_receipt_completes_valve_request_after_lost_ack(app):
    controller, clock = app
    driver = controller.driver
    controller.set_manual_valves([True, False, False, False, False, False])
    command = driver.sent[-1]
    driver.events.append({"type": "parse_error", "error": "Malformed serial data"})
    controller.tick()
    assert controller.manual_pending
    clock.now += 0.25
    telemetry(controller, clock, state="manual_valves", valves=command["valves"],
              uptime_ms=1250, manual_valves_receipt_id=command["id"])
    assert not controller.manual_pending and not controller.snapshot["manual_pending"]
    assert controller.manual_requested is None and command["id"] not in controller.pending
    assert controller.snapshot["valves"] == command["valves"]
    clock.now += 3
    telemetry(controller, clock, state="manual_valves", valves=command["valves"],
              uptime_ms=4250, manual_valves_receipt_id=command["id"])
    controller.tick()
    assert controller.local_fault is None and not controller.stop_pending
    assert [packet["cmd"] for packet in driver.sent if packet["cmd"] in ("manual_valves", "stop")] == ["manual_valves"]
    records = [json.loads(line) for line in controller.esp32_log_text().splitlines()]
    results = [row for row in records if row.get("request_id") == command["id"]]
    assert [row["event"] for row in results] == ["request_queued", "manual_valves_receipt"]
    assert results[-1]["request_age_ms"] == 250


@pytest.mark.parametrize("changes", [
    {"manual_valves_receipt_id": None},  # Legacy frame, or an omitted receipt.
    {"manual_valves_receipt_id": True},
    {"manual_valves_receipt_id": 0},
    {"manual_valves_receipt_id": 0x100000000},
    {"manual_valves_receipt_id": 0xffffffff},  # Valid ID for a different request.
    {"valves": [False] * 7},
    {"state": "idle"},
    {"pump_percent": 1},
    {"fault": "reported fault"},
    {"uptime_ms": 1000},  # Duplicate uptime cannot confirm a new request.
])
def test_nonmatching_or_invalid_receipt_cannot_complete_valve_request(app, changes):
    controller, clock = app
    controller.set_manual_valves([True, False, False, False, False, False])
    command = controller.driver.sent[-1]
    clock.now += 0.25
    packet = {"state": "manual_valves", "valves": command["valves"], "uptime_ms": 1250,
              "manual_valves_receipt_id": command["id"], **changes}
    telemetry(controller, clock, **packet)
    assert controller.manual_pending and command["id"] in controller.pending
    assert '"event":"manual_valves_receipt"' not in controller.esp32_log_text()


def test_exact_receipt_at_timeout_keeps_fault_and_stop_fallback(app):
    controller, clock = app
    controller.set_manual_valves([True, False, False, False, False, False])
    command = controller.driver.sent[-1]
    clock.now += 3
    telemetry(controller, clock, state="manual_valves", valves=command["valves"],
              uptime_ms=4000, manual_valves_receipt_id=command["id"])
    controller.tick()
    assert controller.stop_pending and controller.local_fault == "No acknowledgement for manual_valves"
    assert controller.driver.sent[-1]["cmd"] == "stop"
    assert '"event":"manual_valves_receipt"' not in controller.esp32_log_text()


def test_receipt_cannot_acknowledge_stop_or_bypass_controller_restart(app):
    controller, clock = app
    driver = controller.driver
    controller.set_manual_valves([True, False, False, False, False, False])
    valve_request = driver.sent[-1]
    controller.stop_run()
    stop = driver.sent[-1]
    for index, receipt_id in enumerate((valve_request["id"], stop["id"]), start=1):
        clock.now += 0.25
        telemetry(controller, clock, state="manual_valves", valves=valve_request["valves"],
                  uptime_ms=1000 + 250 * index, manual_valves_receipt_id=receipt_id)
        assert controller.stop_pending and stop["id"] in controller.pending
    controller._handle_packet({"v": 1, "type": "ack", "id": stop["id"], "ok": True}, clock())
    assert not controller.stop_pending and not any(controller.snapshot["valves"])
    controller.set_manual_valves([True, False, False, False, False, False])
    pending = driver.sent[-1]
    clock.now += 0.25
    telemetry(controller, clock, state="manual_valves", valves=pending["valves"],
              uptime_ms=20, manual_valves_receipt_id=pending["id"])
    assert controller.driver is None and driver.closed
    assert "restarted" in controller.local_fault
    assert '"event":"manual_valves_receipt"' not in controller.esp32_log_text()


def test_previous_connection_receipt_cannot_confirm_same_valves_on_reconnect(app, monkeypatch):
    controller, clock = app
    requested = [True, False, False, False, False, False]
    controller.set_manual_valves(requested)
    old_request = controller.driver.sent[-1]
    controller.disconnect_controller()
    new_driver = Driver()
    monkeypatch.setattr(controller_module, "SerialTransport", lambda _port: new_driver)
    controller.connect_controller(new_driver.port)
    identify(controller, clock)
    telemetry(controller, clock)
    controller.set_manual_valves(requested)
    new_request = new_driver.sent[-1]
    clock.now += 0.25
    telemetry(controller, clock, state="manual_valves", valves=new_request["valves"],
              uptime_ms=1250, manual_valves_receipt_id=old_request["id"])
    assert controller.manual_pending and new_request["id"] in controller.pending
    assert old_request["id"] not in controller.pending
    assert '"event":"manual_valves_receipt"' not in controller.esp32_log_text()


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


def test_valve_stop_ack_clears_prior_commands_before_the_next_toggle(app):
    controller, clock = app
    controller.set_manual_valves([True, False, False, False, False, False])
    acknowledge(controller, clock)
    controller.stop_run()
    stop = controller.driver.sent[-1]
    assert stop["cmd"] == "stop" and controller.snapshot["valves"][0]
    controller._handle_packet({"v": 1, "type": "ack", "id": stop["id"], "ok": True}, clock())
    # A second click can occur before the next hardware telemetry frame.
    assert controller.snapshot["valves"] == [False] * 7
    controller.set_manual_valves([False, True, False, False, False, False])
    assert controller.driver.sent[-1]["valves"] == [False, True, False, False, False, False, False]


def test_full_mode_stop_ack_waits_for_its_configured_safe_valve_telemetry(app):
    controller, clock = app
    prior_valves = [True, False, False, False, False, False, False]
    controller.snapshot.update(state="manual", valves=prior_valves)
    controller.stop_run()
    stop = controller.driver.sent[-1]
    controller._handle_packet({"v": 1, "type": "ack", "id": stop["id"], "ok": True}, clock())
    assert controller.snapshot["valves"] == prior_valves


def test_pending_valve_stop_withdraws_heartbeats_and_rejects_late_ack(app):
    controller, clock = app
    driver = controller.driver
    controller.set_manual_valves([True] * 6)
    acknowledge(controller, clock)
    controller.stop_run()
    stop = driver.sent[-1]
    sent = list(driver.sent)
    for index in range(1, 6):
        clock.now += 0.5
        telemetry(controller, clock, state="manual_valves", uptime_ms=1000 + index * 500,
                  valves=[True] * 5 + [False, True])
        controller.tick()
        assert controller.stop_pending and driver.sent == sent
    clock.now += 0.5
    driver.events.append({"v": 1, "type": "ack", "id": stop["id"], "ok": True})
    controller.tick()
    assert driver.closed and controller.driver is None and driver.sent == sent
    assert controller.local_fault == "No acknowledgement for stop"
    assert controller.snapshot["valves"][0]  # No all-off assertion without timely confirmation.


def test_unanswered_manual_valve_command_requests_stop_before_heartbeat(app):
    controller, clock = app
    driver = controller.driver
    controller.set_manual_valves([True] * 6)
    command = driver.sent[-1]
    clock.now += 3
    telemetry(controller, clock, state="manual_valves", uptime_ms=4000,
              valves=[True] * 5 + [False, True])
    driver.events.append({"v": 1, "type": "ack", "id": command["id"], "ok": True})
    controller.tick()
    assert controller.local_fault == "No acknowledgement for manual_valves"
    assert controller.stop_pending and driver.sent[-1]["cmd"] == "stop"
    assert [packet["cmd"] for packet in driver.sent[-2:]] == ["manual_valves", "stop"]


def test_idle_telemetry_while_waiting_for_valve_stop_ignores_balance_requirement(app):
    controller, clock = app
    controller.settings["require_balance"] = True
    controller.set_manual_valves([True] * 6)
    acknowledge(controller, clock)
    controller.stop_run()
    telemetry(controller, clock, state="idle")
    controller.tick()
    assert controller.stop_pending and controller.local_fault is None


@pytest.mark.parametrize("port_open", [False, True])
def test_unanswered_hello_closes_port_then_explicit_retry_starts_fresh(app, monkeypatch, port_open):
    controller, clock = app
    first, retry = Driver(), Driver()
    drivers = iter((first, retry))
    monkeypatch.setattr(controller_module, "SerialTransport", lambda _port: next(drivers))
    controller.connect_controller(first.port)
    if port_open:
        first.events.append({"type": "port_open"})
    for _ in range(8):
        controller.tick()
        clock.now += 1
    assert all(packet["cmd"] == "hello" for packet in first.sent)
    controller.tick()
    assert first.closed and controller.driver is None and controller.pending == {}
    reason = controller.snapshot["controller_status"]
    assert ("no supported controller HELLO" if port_open else "port did not open") in reason
    controller.connect_controller(retry.port)
    controller.tick()
    assert [packet["cmd"] for packet in retry.sent] == ["hello"]
    identify(controller, clock)
    telemetry(controller, clock)
    controller.tick()
    assert retry.sent[-1]["cmd"] == "heartbeat"
    assert controller.snapshot["controller_connected"]
    assert not any(controller.snapshot["valves"])


def test_reconnect_with_watchdog_fault_leaves_clear_fault_available(app, monkeypatch):
    controller, clock = app
    controller._stop_failed("No acknowledgement for stop")
    retry = Driver()
    monkeypatch.setattr(controller_module, "SerialTransport", lambda _port: retry)
    controller.connect_controller(retry.port)
    identify(controller, clock)
    for _ in range(3):
        telemetry(controller, clock, state="fault", fault="heartbeat_timeout")
        controller.tick()
        assert not controller.stop_pending
    assert controller.local_fault == "No acknowledgement for stop"
    assert [packet["cmd"] for packet in retry.sent] == ["hello"]
    controller.clear_fault()
    clear = retry.sent[-1]
    telemetry(controller, clock, state="fault", fault="heartbeat_timeout")
    assert clear["id"] in controller.pending and not controller.stop_pending
    controller._handle_packet({"v": 1, "type": "ack", "id": clear["id"], "ok": True}, clock())
    telemetry(controller, clock, state="idle")
    controller.tick()
    assert controller.local_fault is None and controller.snapshot["state"] == "idle"
    assert [packet["cmd"] for packet in retry.sent] == ["hello", "clear_fault", "heartbeat"]


def test_stale_valve_telemetry_and_unanswered_stop_release_each_failed_port(app, monkeypatch):
    controller, clock = app
    first = controller.driver
    controller.set_manual_valves([True] * 6)
    acknowledge(controller, clock)
    clock.now += 2.1
    controller.tick()
    assert controller.local_fault == "Controller telemetry is stale"
    assert controller.stop_pending and first.sent[-1]["cmd"] == "stop"
    clock.now += 3
    controller.tick()
    fault = "Controller telemetry is stale; No acknowledgement for stop"
    assert first.closed and controller.driver is None and controller.local_fault == fault
    assert not controller.stop_pending and controller.snapshot["valves"][0]
    retry, recovered = Driver(), Driver()
    drivers = iter((retry, recovered))
    monkeypatch.setattr(controller_module, "SerialTransport", lambda _port: next(drivers))
    controller.connect_controller(retry.port)
    retry.events.append({"type": "port_open"})
    controller.tick()
    assert controller.snapshot["valves"][0]  # Still unconfirmed until fresh telemetry arrives.
    clock.now += 8
    controller.tick()
    assert retry.closed and controller.driver is None and controller.local_fault == fault
    assert [packet["cmd"] for packet in retry.sent] == ["hello"]
    controller.connect_controller(recovered.port)
    identify(controller, clock)
    telemetry(controller, clock, state="fault", fault="heartbeat_timeout")
    controller.tick()
    assert controller.snapshot["controller_connected"] and not controller.stop_pending
    assert controller.local_fault == fault and not any(controller.snapshot["valves"])
    assert [packet["cmd"] for packet in recovered.sent] == ["hello"]


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

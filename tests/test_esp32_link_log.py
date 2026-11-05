import json

import pytest

import membrane_control.controller as controller_module
from membrane_control.controller import AppController
from membrane_control.esp32_link_log import Esp32LinkLog
from test_manual_valves_controller import Clock, Driver, acknowledge, identify, telemetry


def entries(source):
    return [json.loads(line) for line in source.splitlines()]


@pytest.fixture
def link(tmp_path, monkeypatch):
    clock = Clock()
    controller = AppController(tmp_path, clock)
    driver = Driver()
    driver.port = "COM5"
    monkeypatch.setattr(controller_module, "SerialTransport", lambda _port: driver)
    controller.set_simulation(False)
    controller.connect_controller("COM5")
    controller._handle_packet({"type": "port_open"}, clock())
    identify(controller, clock, reset_reason="power_on", sensor_test_available=True)
    telemetry(controller, clock, adc_pin_mv={"pressure": 0, "flow": 1500, "pump_feedback": 3300})
    yield controller, clock, driver
    controller.close()


def test_rotating_log_keeps_only_bounded_recent_complete_entries(tmp_path):
    path = tmp_path / "logs" / "esp32-link.jsonl"
    log = Esp32LinkLog(path, max_bytes=768, backups=2)
    try:
        for sequence in range(50):
            log.record("request_queued", sequence=sequence, detail="x" * 120)
        files = list(path.parent.iterdir())
        assert len(files) == 3 and all(item.stat().st_size <= 768 for item in files)
        recent = log.recent_text(max_bytes=700)
        records = entries(recent)
        sequences = [row["sequence"] for row in records]
        assert 0 < sequences[0] < sequences[-1] == 49 and sequences == sorted(sequences)
        assert len(recent.encode("utf-8")) <= 700
    finally:
        log.close()
    reopened = Esp32LinkLog(path)
    assert entries(reopened.recent_text())[-1]["sequence"] == 49
    reopened.close()


def test_three_accepted_v3_commands_followed_by_stale_telemetry_and_stop_timeout(link):
    controller, clock, driver = link
    assert controller.esp32_log_path.is_file()
    initial = entries(controller.esp32_log_text())
    assert [row["event"] for row in initial] == [
        "connect_requested", "port_opened", "request_queued", "request_acknowledged",
        "hello_identified", "telemetry_started"]
    assert initial[-2]["reset_reason"] == "power_on"
    requests = []
    for index, enabled in enumerate((True, False, True), start=1):
        controller.set_manual_valves([False, False, enabled, False, False, False])
        request = driver.sent[-1]
        requests.append(request["id"])
        clock.now += 0.2
        acknowledge(controller, clock)
        telemetry(controller, clock, state="manual_valves", valves=request["valves"], uptime_ms=1000 + 200 * index)
        controller.tick()
    clock.now += 2.2
    controller.tick()
    stop = driver.sent[-1]
    assert stop["cmd"] == "stop" and controller.stop_pending
    controller.tick()  # Repeated stale ticks must not flood the log.
    clock.now += 3
    controller.tick()
    assert controller.driver is None and driver.closed
    log = entries(controller.esp32_log_text())
    assert all(row["port"] == "COM5" and row["connection_id"] == 1 for row in log)
    queued = [row for row in log if row["event"] == "request_queued" and row["command"] == "manual_valves"]
    assert [row["request_id"] for row in queued] == requests
    assert [row["commanded_valves"]["V3"] for row in queued] == ["ON", "OFF", "ON"]
    assert set(queued[0]["commanded_valves"]) == {"V1", "V2", "V3", "V4", "V5", "V7"}
    for request_id in requests:
        ack = next(row for row in log if row["event"] == "request_acknowledged" and row["request_id"] == request_id)
        assert ack["request_age_ms"] == 200
    stale = [row for row in log if row["event"] == "telemetry_stale"]
    assert len(stale) == 1 and stale[0]["telemetry_age_ms"] == 2200 and stale[0]["controller_uptime_ms"] == 1600
    expiry = next(row for row in log if row["event"] == "request_timeout")
    assert expiry["command"] == "stop" and expiry["request_id"] == stop["id"]
    assert any(row["event"] == "stop_unconfirmed" for row in log)
    assert not any(row.get("command") == "heartbeat" or "adc_pin_mv" in row for row in log)


def test_ignored_and_rejected_replies_and_transport_error_keep_correlation(link):
    controller, clock, driver = link
    controller.set_manual_valves([False, False, True, False, False, False])
    request_id = driver.sent[-1]["id"]
    controller._handle_packet({"v": 1, "type": "ack", "ok": 1, "id": request_id}, clock())
    assert controller.manual_pending
    acknowledge(controller, clock, ok=False)
    driver.events.append({"type": "disconnected", "error": "ReadFile failed on fake port"})
    controller.tick()
    log = entries(controller.esp32_log_text())
    assert [row["event"] for row in log if row.get("request_id") == request_id] == [
        "request_queued", "reply_ignored", "request_rejected"]
    assert next(row for row in log if row["event"] == "request_rejected")["reason"] == "Rejected test command"
    assert next(row for row in log if row["event"] == "link_lost")["reason"] == "ReadFile failed on fake port"


def test_reset_event_records_both_uptimes_and_ignores_invalid_hello_reason(link):
    controller, clock, _ = link
    identify(controller, clock, reset_reason="line\nbreak", sensor_test_available=True)
    clock.now += 0.25
    telemetry(controller, clock, uptime_ms=1)
    log = entries(controller.esp32_log_text())
    hello = [row for row in log if row["event"] == "hello_identified"]
    assert hello[0]["reset_reason"] == "power_on" and "reset_reason" not in hello[-1]
    reset = next(row for row in log if row["event"] == "controller_reset_or_clock_jump")
    assert reset["controller_uptime_ms"] == 1000 and reset["observed_uptime_ms"] == 1
    assert controller.driver is None


def test_blocked_log_path_does_not_affect_valve_or_stop_ack(tmp_path, monkeypatch):
    clock = Clock()
    controller = AppController(tmp_path, clock)
    driver = Driver()
    monkeypatch.setattr(controller_module, "SerialTransport", lambda _port: driver)
    controller.esp32_log_path.parent.write_text("a file blocks the log directory", encoding="utf-8")
    try:
        controller.set_simulation(False)
        controller.connect_controller("COM5")
        identify(controller, clock)
        telemetry(controller, clock)
        controller.set_manual_valves([False, False, True, False, False, False])
        acknowledge(controller, clock)
        assert controller.snapshot["valves"][2]
        controller.stop_run()
        stop = driver.sent[-1]
        controller._handle_packet({"v": 1, "type": "ack", "ok": True, "id": stop["id"]}, clock())
        assert not any(controller.snapshot["valves"]) and controller.local_fault is None
        assert controller.esp32_log_text() == ""
    finally:
        controller.close()


def test_live_adc_mv_is_separate_from_calibration_and_one_shot_result(link):
    controller, clock, driver = link
    live = {"pressure": 0, "flow": 1500, "pump_feedback": 3300}
    one_shot = {"pressure": 4, "flow": 2210, "pump_feedback": 2000}
    assert controller.snapshot["live_sensor_voltages"] == live
    assert controller.snapshot["pressure_psi"] is controller.snapshot["flow_ml_min"] is None
    controller.read_sensor_inputs()
    controller._handle_packet({"v": 1, "type": "ack", "ok": True, "id": driver.sent[-1]["id"],
                               "adc_pin_mv": one_shot}, clock())
    assert controller.snapshot["sensor_test_voltages"] == one_shot
    assert controller.snapshot["live_sensor_voltages"] == live
    telemetry(controller, clock, adc_pin_mv={**live, "flow": True})
    assert controller.snapshot["live_sensor_voltages"] == {}
    telemetry(controller, clock, adc_pin_mv=live)
    telemetry(controller, clock)  # Earlier firmware has no continuous ADC field.
    assert controller.snapshot["live_sensor_voltages"] == {}
    telemetry(controller, clock, adc_pin_mv=live)
    clock.now += 2.1
    controller.tick()
    assert controller.snapshot["live_sensor_voltages"] == {} and controller.driver is None


def test_demo_has_no_esp32_link_log(tmp_path):
    controller = AppController(tmp_path, Clock())
    try:
        controller.tick()
        assert controller.esp32_log_text() == "" and not controller.esp32_log_path.exists()
    finally:
        controller.close()

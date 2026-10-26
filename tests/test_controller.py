import json
import serial
import pytest
from membrane_control.controller import AppController
from membrane_control.models import Recipe, Step
from membrane_control.transport import Simulator


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


@pytest.fixture
def app(tmp_path):
    clock = Clock()
    controller = AppController(tmp_path, clock)
    controller.tick()
    yield controller, clock
    controller.close()


def test_default_demo_no_real_ports_and_acknowledged_run(app, tmp_path):
    controller, clock = app
    assert isinstance(controller.driver, Simulator)
    assert controller.snapshot["controller_connected"]
    controller.load_recipe(Recipe(name="Short run", steps=[Step("Observe", 1)]))
    controller.start_run()
    assert controller.run_id is None  # loading acknowledgement must happen first
    controller.tick()
    controller.tick()
    assert controller.run_id is not None
    clock.advance(1.1)
    controller.tick()
    assert controller.snapshot["state"] == "idle"
    assert controller.list_runs()[0]["status"] == "completed"
    controller.export_csv(tmp_path / "test.csv")
    assert (tmp_path / "test.metadata.json").exists()


def test_stop_cancels_start_transaction(app):
    controller, _ = app
    controller.start_run()
    controller.stop_run()
    controller.tick()
    assert controller.run_id is None
    assert controller.snapshot["state"] == "idle"


def test_physical_start_cannot_be_unlocked_by_user_settings(app):
    controller, _ = app
    controller.snapshot.update(simulation=False, hardware_verified=False)
    controller.update_settings({"hardware_verified": True})
    controller.recipe.hardware_approved = True
    with pytest.raises(ValueError, match="verified firmware"):
        controller.start_run()


def test_heartbeat_timeout_stops_simulated_outputs(app):
    controller, clock = app
    controller.set_manual([True]*7, 50)
    controller.tick()
    clock.advance(4)
    packets = controller.driver.poll(clock())  # no desktop tick/heartbeat
    telemetry = packets[-1]
    assert telemetry["state"] == "fault"
    assert not any(telemetry["valves"]) and telemetry["pump_percent"] == 0


def test_required_balance_blocks_start_and_faults_on_loss(app):
    controller, clock = app
    controller.recipe.require_balance = True
    controller.snapshot["balance_connected"] = False
    with pytest.raises(ValueError, match="balance"):
        controller.start_run()


def test_invalid_telemetry_does_not_refresh_freshness(app):
    controller, clock = app
    old = controller.last_telemetry
    clock.advance(1)
    controller._handle_packet({"v": 1, "type": "telemetry", "valves": [1]*7,
        "pump_percent": 0, "state": "idle", "simulation": True, "hardware_verified": False}, clock())
    assert controller.last_telemetry == old


def test_controller_disconnect_clears_previous_analog_readings(app):
    controller, _ = app
    controller.snapshot.update(pressure_psi=12, flow_ml_min=30, pump_feedback_v=2.5)
    controller.disconnect_controller()
    assert not controller.snapshot["controller_connected"]
    assert all(controller.snapshot[key] is None for key in ("pressure_psi", "flow_ml_min", "pump_feedback_v"))


def test_idle_port_open_failure_detaches_and_preserves_original_error(app, monkeypatch):
    controller, clock = app
    reason = "Access denied: test COM port is already open in another program"

    class LockedSerial:
        def open(self):
            raise PermissionError(reason)
        def close(self):
            pass

    monkeypatch.setattr(serial, "Serial", lambda **kwargs: LockedSerial())
    controller.set_simulation(False)
    controller.connect_controller("LOCKED-TEST-PORT")
    failed = controller.driver
    failed._thread.join(timeout=1)
    assert not failed._thread.is_alive()
    for _ in range(100):
        clock.advance(0.5)
        controller.tick()
    assert controller.driver is None
    assert controller.pending == {} and controller.device == {}
    assert not controller.stop_pending
    assert controller.local_fault is None
    assert controller.snapshot["controller_status"] == reason
    assert not controller.snapshot["controller_connected"]
    assert failed.outgoing.empty()  # No queued heartbeat or futile STOP after failure.
    assert not any("queue is full" in line or "acknowledgement for stop" in line for line in controller.log)


def test_active_unplug_detaches_immediately_without_stop_transaction(app):
    controller, clock = app
    controller.start_run()
    controller.tick()
    controller.tick()
    assert controller.run_id is not None
    controller.driver.close()
    reason = "USB read failed: test cable removed"

    class UnpluggedController:
        def __init__(self):
            self.sent = []
            self.closed = False
        def send(self, packet):
            self.sent.append(packet)
        def poll(self, now):
            return [{"type": "disconnected", "error": reason}]
        def close(self):
            self.closed = True

    failed = UnpluggedController()
    controller.driver = failed
    controller.tick()
    assert controller.driver is None and failed.closed
    assert not controller.stop_pending and controller.pending == {}
    assert controller.snapshot["state"] == "fault"
    assert controller.snapshot["controller_status"] == reason
    assert reason in controller.local_fault
    assert controller.list_runs()[0]["status"] == "fault"
    sent_after_disconnect = list(failed.sent)
    for _ in range(100):
        clock.advance(0.5)
        controller.tick()
    assert failed.sent == sent_after_disconnect
    assert not any(packet["cmd"] == "stop" for packet in failed.sent)
    assert controller.snapshot["controller_status"] == reason


def test_settings_and_custom_recipe_persist(app, tmp_path):
    controller, _ = app
    controller.update_settings({"membrane_area_m2": 0.02})
    recipe = Recipe(name="My custom run")
    controller.save_recipe(tmp_path / "custom.json", recipe)
    assert "My custom run" in controller.list_presets()
    assert json.loads((tmp_path / "settings.json").read_text())["membrane_area_m2"] == 0.02


def test_local_pressure_limit_latches(app):
    controller, clock = app
    controller.update_settings({"max_pressure_psi": 1})
    controller.set_manual([True]*7, 50)
    controller.tick()
    assert controller.snapshot["fault"] == "Desktop pressure limit exceeded"
    controller.tick()
    assert controller.snapshot["state"] == "fault"
    controller.clear_fault()
    controller.tick()
    assert controller.snapshot["state"] == "idle"


class FaultyStopSimulator(Simulator):
    """A board that keeps responding to heartbeats but cannot confirm stop."""
    def __init__(self, clock, mode):
        super().__init__(clock)
        self.mode = mode
        self.closed = False
        self.heartbeats = 0

    def send(self, packet):
        if packet.get("cmd") == "heartbeat":
            self.heartbeats += 1
        if packet.get("cmd") == "stop":
            if self.mode == "write_error":
                raise OSError("Test stop write failure")
            if self.mode == "reject":
                self.events.append({"v": 1, "id": packet["id"], "type": "error",
                                    "ok": False, "error": "Test stop rejection"})
            return  # No stop execution and no ACK in drop mode.
        super().send(packet)

    def close(self):
        # Closing a USB link cannot itself turn off independent board outputs.
        self.closed = True


@pytest.mark.parametrize("mode", ["drop", "reject", "write_error"])
def test_unconfirmed_stop_disconnects_and_ceases_heartbeats(app, mode):
    controller, clock = app
    controller.driver.close()
    driver = FaultyStopSimulator(clock, mode)
    controller.driver = driver
    controller.load_recipe(Recipe(name="Stop confirmation", steps=[Step("Run", 60, (True,) * 7, 25)]))
    controller.start_run()
    controller.tick()
    controller.tick()
    assert controller.run_id is not None
    controller.stop_run()
    if mode != "write_error":
        assert controller.stop_pending
        assert controller.list_runs()[0]["status"] == "running"
    for _ in range(8):
        clock.advance(0.5)
        controller.tick()
    assert controller.driver is None
    assert driver.closed
    assert not controller.snapshot["controller_connected"]
    assert controller.snapshot["state"] == "fault"
    assert "stop" in controller.snapshot["fault"].lower()
    assert controller.list_runs()[0]["status"] == "fault"
    sent = driver.heartbeats
    clock.advance(4)
    controller.tick()
    assert driver.heartbeats == sent
    telemetry = driver.poll(clock())[-1]
    assert telemetry["state"] == "fault"
    assert telemetry["pump_percent"] == 0 and not any(telemetry["valves"])


def test_stop_pending_blocks_restart_until_ack_and_then_records_stopped(app):
    controller, _ = app
    controller.start_run()
    controller.tick()
    controller.tick()
    controller.stop_run()
    assert controller.stop_pending
    assert controller.run_id is not None
    with pytest.raises(ValueError, match="active"):
        controller.start_run()
    with pytest.raises(ValueError, match="Stop"):
        controller.set_manual([False] * 7, 0)
    original_deadline = next(deadline for command, deadline in controller.pending.values() if command == "stop")
    controller.stop_run()  # Repeated clicks do not postpone fault detection.
    assert next(deadline for command, deadline in controller.pending.values() if command == "stop") == original_deadline
    controller.tick()
    assert not controller.stop_pending
    assert controller.run_id is None
    assert controller.snapshot["state"] == "idle"
    assert controller.list_runs()[0]["status"] == "stopped"


def test_stop_failure_preserves_original_fault(app):
    controller, clock = app
    controller.driver.close()
    controller.driver = FaultyStopSimulator(clock, "reject")
    controller._abort("Original sensor fault")
    controller.tick()
    assert controller.local_fault.startswith("Original sensor fault;")
    assert "stop rejection" in controller.local_fault
    assert controller.driver is None


def test_multiple_faults_cannot_extend_unconfirmed_stop_deadline(app):
    controller, clock = app
    controller.driver.close()
    driver = FaultyStopSimulator(clock, "drop")
    controller.driver = driver
    controller._abort("First fault")
    original = dict(controller.pending)
    for index in range(8):
        clock.advance(0.5)
        controller._abort("Other fault " + str(index))
        if controller.driver is not None:
            assert controller.pending == original
        controller.tick()
    assert controller.driver is None
    assert controller.local_fault.startswith("First fault;")


@pytest.mark.parametrize("state", ["manual", "running", "idle"])
def test_physical_pressure_loss_aborts_active_or_starting_operation(app, state):
    controller, clock = app
    controller.device.update(simulation=False, hardware_verified=True)
    controller.snapshot.update(simulation=False, hardware_verified=True, state=state)
    if state == "idle":
        controller.start_phase = "loading"
    controller._handle_packet({"v": 1, "type": "telemetry", "uptime_ms": 0, "state": state,
        "simulation": False, "hardware_verified": True, "valves": [True] * 7,
        "pump_percent": 20, "pressure_psi": None, "flow_ml_min": 30,
        "step_index": -1, "cycle": 0, "remaining_s": 0, "fault": None}, clock())
    assert controller.snapshot["state"] == "fault"
    assert controller.local_fault == "Pressure reading unavailable during physical operation"
    assert controller.stop_pending
    assert any(command == "stop" for command, _ in controller.pending.values())


def test_idle_telemetry_does_not_finish_a_stop_without_ack(app):
    controller, clock = app
    controller.start_run()
    controller.tick()
    controller.tick()
    controller.driver.engine.state = "running"
    controller.stop_run()
    packet = {"v": 1, "type": "telemetry", "uptime_ms": 0, "state": "idle", "simulation": True,
              "hardware_verified": False, "valves": [False] * 7, "pump_percent": 0,
              "pressure_psi": 0, "flow_ml_min": 0, "step_index": -1,
              "cycle": 0, "remaining_s": 0, "fault": None}
    controller._handle_packet(packet, clock())
    assert controller.stop_pending
    assert controller.run_id is not None
    assert controller.list_runs()[0]["status"] == "running"
    controller.tick()
    assert controller.list_runs()[0]["status"] == "stopped"


def test_storage_failure_withdraws_heartbeat_and_closes_driver(app, monkeypatch):
    controller, clock = app
    controller.start_run()
    controller.tick()
    controller.tick()
    driver = controller.driver
    with monkeypatch.context() as patch:
        def failing_sample(*args):
            raise OSError("Test disk full")
        patch.setattr(controller.store, "sample", failing_sample)
        clock.advance(1.1)
        controller.tick()
        assert controller.driver is None
        assert not controller.snapshot["controller_connected"]
        assert controller.snapshot["state"] == "fault"
        assert "Test disk full" in controller.local_fault
        assert controller.snapshot["pump_feedback_v"] is None
        assert driver.engine.pump_percent == 0 and not any(driver.engine.valves)


def test_required_balance_stale_during_run_latches_fault_and_stops(app):
    controller, clock = app
    controller.recipe.require_balance = True
    # Exercise a connected dry-run board with an independent physical balance.
    # Retain the last valid balance reading, then stop supplying new weights.
    controller.simulation = False
    controller.start_run()
    controller.tick()
    controller.tick()
    assert controller.run_id is not None
    for _ in range(7):
        clock.advance(0.5)
        controller.tick()
    assert controller.local_fault == "Required balance reading is unavailable"
    assert controller.snapshot["mass_g"] is None
    assert controller.snapshot["balance_flow_ml_min"] is None
    assert controller.stop_pending
    controller.tick()
    assert controller.snapshot["state"] == "fault"
    assert not any(controller.snapshot["valves"])
    assert controller.snapshot["pump_percent"] == 0


def test_explicit_balance_disconnect_clears_readings_immediately(app):
    controller, _ = app

    class DisconnectedBalance:
        def poll(self, now):
            return [{"type": "disconnected", "error": "Test cable unplugged"}]
        def close(self):
            pass

    controller.simulation = False
    controller.balance = DisconnectedBalance()
    controller.snapshot.update(mass_g=123, balance_flow_ml_min=45, balance_connected=True)
    controller.tick()  # No freshness timeout needs to elapse.
    assert controller.snapshot["mass_g"] is None
    assert controller.snapshot["balance_flow_ml_min"] is None
    assert not controller.snapshot["balance_connected"]
    assert controller.last_mass is None


def test_close_still_closes_devices_and_database_after_persistent_storage_error(app, monkeypatch):
    controller, _ = app
    controller.start_run()
    controller.tick()
    controller.tick()
    closed = []
    original_close = controller.store.close

    def failing_sample(*args):
        raise OSError("Persistent disk full")

    def close_store():
        closed.append(True)
        original_close()

    monkeypatch.setattr(controller.store, "sample", failing_sample)
    monkeypatch.setattr(controller.store, "close", close_store)
    controller.close()
    assert closed == [True]
    assert controller.closed
    assert controller.driver is None and controller.balance is None
    controller.close()  # Shutdown remains idempotent despite the failed final record.
    assert closed == [True]


def telemetry_packet(**changes):
    packet = {"v": 1, "type": "telemetry", "uptime_ms": 0, "state": "idle", "simulation": True,
              "hardware_verified": False, "valves": [False] * 7, "pump_percent": 0,
              "pressure_psi": 0, "flow_ml_min": 0, "pump_feedback_v": 0,
              "step_index": -1, "cycle": 0, "remaining_s": 0, "fault": None}
    return {**packet, **changes}


def test_manual_waits_for_ack_and_ack_closes_idle_restart_window(app):
    controller, clock = app
    controller.set_manual([True] * 7, 20)
    assert controller.manual_pending and controller.snapshot["manual_pending"]
    with pytest.raises(ValueError, match="active"):
        controller.start_run()
    with pytest.raises(ValueError, match="Stop"):
        controller.set_simulation(False)
    with pytest.raises(ValueError, match="Stop"):
        controller.set_manual([False] * 7, 0)
    request_id = next(key for key, value in controller.pending.items() if value[0] == "manual")
    controller._handle_packet({"v": 1, "type": "ack", "id": request_id, "ok": True}, clock())
    assert not controller.manual_pending
    assert controller.snapshot["state"] == "manual"
    assert controller.snapshot["pump_percent"] == 20
    with pytest.raises(ValueError, match="active"):
        controller.start_run()  # Still blocked before the next telemetry frame.


def test_stop_cancels_unconfirmed_manual_command(app):
    controller, _ = app
    controller.set_manual([True] * 7, 20)
    controller.stop_run()
    controller.tick()
    assert not controller.manual_pending
    assert not controller.stop_pending
    assert controller.snapshot["state"] == "idle"
    assert not any(controller.snapshot["valves"])


@pytest.mark.parametrize("request_id", [True, "3", [], {}, None])
def test_malformed_ack_ids_do_not_consume_pending_commands_or_crash(app, request_id):
    controller, clock = app
    controller.set_manual([True] * 7, 20)
    before = dict(controller.pending)
    controller._handle_packet({"v": 1, "type": "ack", "id": request_id, "ok": True}, clock())
    assert controller.pending == before
    assert controller.manual_pending


def test_wrong_response_type_cannot_confirm_manual_action(app):
    controller, clock = app
    controller.set_manual([True] * 7, 20)
    request_id = next(key for key, value in controller.pending.items() if value[0] == "manual")
    controller._handle_packet({"v": 1, "type": "hello", "id": request_id, "ok": True}, clock())
    assert request_id in controller.pending and controller.manual_pending


def test_manual_control_rejects_stale_controller_readings(app):
    controller, clock = app
    clock.advance(2.1)
    with pytest.raises(ValueError, match="stale"):
        controller.set_manual([True] * 7, 20)
    assert controller.driver.engine.state == "idle"


@pytest.mark.parametrize("ack_delay", [0.2, 1.5])
def test_short_run_completes_even_without_a_running_telemetry_frame(app, ack_delay):
    controller, clock = app
    controller.load_recipe(Recipe(name="Very short", steps=[Step("Observe", 0.1)]))
    controller.start_run()
    controller.tick()  # load ACK causes start, but its ACK has not been read.
    clock.advance(ack_delay)
    controller.tick()  # start ACK followed immediately by already-idle telemetry.
    assert controller.run_id is None
    assert controller.list_runs()[0]["status"] == "completed"
    assert controller.snapshot["elapsed_s"] == pytest.approx(ack_delay)


def test_unexpected_early_idle_faults_even_if_uptime_does_not_move_backwards(app):
    controller, clock = app
    controller.load_recipe(Recipe(name="Full minute", steps=[Step("Observe", 60)]))
    controller.start_run()
    controller.tick()
    controller.tick()
    clock.advance(0.5)
    controller._handle_packet(telemetry_packet(uptime_ms=100), clock())
    assert controller.list_runs()[0]["status"] == "fault"
    assert "before the sequence could finish" in controller.local_fault
    assert controller.stop_pending


def test_controller_reset_is_faulted_instead_of_recorded_as_completed(app):
    controller, clock = app
    controller.start_run()
    controller.tick()
    controller.tick()
    clock.advance(1)
    controller.tick()
    assert controller.last_controller_uptime == 1000
    controller._handle_packet(telemetry_packet(uptime_ms=1), clock())
    assert controller.driver is None
    assert controller.snapshot["state"] == "fault"
    assert "restarted" in controller.local_fault
    assert controller.list_runs()[0]["status"] == "fault"


def test_normal_uint32_uptime_rollover_does_not_disconnect(app):
    controller, clock = app
    controller.last_controller_uptime = 0xfffffff0
    controller.last_telemetry = clock()
    clock.advance(0.05)
    controller._handle_packet(telemetry_packet(uptime_ms=34), clock())
    assert controller.last_controller_uptime == 34
    assert controller.driver is not None
    assert controller.local_fault is None


@pytest.mark.parametrize("uptime", [None, True, -1, 0x100000000])
def test_invalid_uptime_does_not_refresh_telemetry(app, uptime):
    controller, clock = app
    old = controller.last_telemetry
    clock.advance(0.5)
    controller._handle_packet(telemetry_packet(uptime_ms=uptime), clock())
    assert controller.last_telemetry == old


def test_runtime_hardware_verification_loss_immediately_disconnects(app):
    controller, clock = app
    controller.device.update(simulation=False, hardware_verified=True)
    controller.snapshot.update(simulation=False, hardware_verified=True, state="manual")
    controller._handle_packet(telemetry_packet(simulation=False, hardware_verified=False), clock())
    assert controller.driver is None
    assert not controller.snapshot["hardware_verified"]
    assert "verification changed" in controller.local_fault


def test_fault_without_description_has_an_actionable_message(app):
    controller, clock = app
    controller._handle_packet(telemetry_packet(state="fault", fault=None), clock())
    assert controller.local_fault == "Controller reported a fault without a description"
    assert controller.snapshot["fault"]

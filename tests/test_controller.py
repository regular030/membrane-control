import json
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
    controller._handle_packet({"v": 1, "type": "telemetry", "state": state,
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
    packet = {"v": 1, "type": "telemetry", "state": "idle", "simulation": True,
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
    clock.advance(3.1)
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

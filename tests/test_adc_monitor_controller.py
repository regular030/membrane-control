"""The extra sensor stream supplies observations without granting rig readiness."""
import copy
import csv
from types import SimpleNamespace

import pytest

from membrane_control.controller import AppController
from membrane_control.adc_display import adc_display_values


def board_snapshot():
    return {"connected": True, "opened": True, "identified": True, "port": "COM5",
            "status": "ADS1115 readings received", "fresh": True, "adc_ack": True,
            "uptime_ms": 300, "sequence": 1, "received_at": 100.0,
            "channels": {channel: {"signal": signal, "status": "reading_received",
                                    "raw": round(volts / .000125), "volts": volts,
                                    "sample_uptime_ms": 280, "received_at": 99.98}
                         for channel, signal, volts in (("A0", "pressure", .5),
                                                        ("A1", "flow", .25),
                                                        ("A2", "pump_feedback", 1.0))}}


class Monitor:
    def __init__(self, clock):
        self.state = {"port": "", "connected": False, "opened": False,
                      "fresh": False, "channels": {}, "status": "Disconnected"}
        self.transport = None
        self.fail = False
        self.closed = False

    def snapshot(self):
        return copy.deepcopy(self.state)

    def connect(self, port):
        self.transport = object()
        self.state = board_snapshot()
        self.state["port"] = port
        return True

    def disconnect(self):
        self.closed = True
        self.transport = None
        self.state.update(connected=False, opened=False, fresh=False, channels={})

    def clear_selection(self):
        self.disconnect()
        self.state["port"] = ""

    def tick(self):
        if self.fail:
            raise RuntimeError("Sensor worker test failure")


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setattr("membrane_control.controller.Ads1115Monitor", Monitor)
    app = AppController(tmp_path, clock=lambda: 100.0, simulation=False)
    yield app
    app.close()


def test_auxiliary_values_are_separate_from_controller_readiness(controller):
    controller.connect_adc_monitor("COM5")
    controller.tick()
    displayed = adc_display_values(controller.snapshot, .01)
    assert displayed["flow_ml_min"] == 25
    assert displayed["pump_feedback_v"] == 5
    assert displayed["pressure_psi"] == pytest.approx(50, abs=.1)
    assert controller.snapshot["pressure_psi"] is None
    assert controller.snapshot["flow_ml_min"] is None
    assert not controller.snapshot["hardware_verified"]
    controller.snapshot.update(controller_connected=True, hardware_verified=True)
    controller.recipe.hardware_approved = True
    controller.last_telemetry = 100.0
    with pytest.raises(ValueError, match="valid pressure"):
        controller.start_run()


def test_auxiliary_worker_failure_does_not_fault_the_rig(controller):
    controller.connect_adc_monitor()
    controller.adc_monitor.fail = True
    controller.tick()
    assert controller.local_fault is None
    assert controller.snapshot["state"] == "idle"
    assert controller.snapshot["adc_monitor"]["channels"] == {}
    assert "Sensor worker test failure" in "\n".join(controller.log)


def test_sensor_port_cannot_be_reused_by_scale(controller):
    controller.connect_adc_monitor()
    with pytest.raises(ValueError, match="different ports"):
        controller.connect_balance("COM5")
    controller.disconnect_adc_monitor()
    assert not controller._adc_port_matches("COM5")


@pytest.mark.parametrize("port", ["COM5", "COM10"])
def test_selecting_full_controller_releases_auxiliary_and_uses_controller_sensors(
        controller, monkeypatch, port):
    controller.connect_adc_monitor("COM5")
    controller.tick()
    old_monitor = controller.adc_monitor
    assert adc_display_values(controller.snapshot, .01)["flow_ml_min"] == 25
    opened = []

    class Driver:
        def __init__(self, selected):
            assert old_monitor.transport is None
            assert old_monitor.snapshot()["port"] == ""
            self.port = selected
            opened.append(selected)

        def send(self, message):
            pass

        def close(self):
            pass

        def poll(self, now):
            return []

    monkeypatch.setattr("membrane_control.controller.SerialTransport", Driver)
    controller.connect_controller(port)
    controller.snapshot.update(pressure_psi=22, flow_ml_min=40, pump_feedback_v=5)
    controller._poll_adc_monitor()
    assert opened == [port]
    assert not controller.snapshot["adc_monitor"]["port"]
    assert adc_display_values(controller.snapshot, .01) == {}
    assert controller.snapshot["flow_ml_min"] == 40


@pytest.mark.parametrize("owner", ["driver", "balance"])
def test_auxiliary_connect_rejects_an_existing_device_port(controller, owner):
    setattr(controller, owner, SimpleNamespace(port="COM6"))
    try:
        with pytest.raises(ValueError, match="own serial port"):
            controller.connect_adc_monitor("com6")
    finally:
        setattr(controller, owner, None)


def test_auxiliary_connection_closes_on_demo_switch_and_shutdown(controller):
    controller.connect_adc_monitor()
    controller.set_simulation(True)
    assert controller.adc_monitor.transport is None
    controller.set_simulation(False)
    controller.connect_adc_monitor()
    controller.close()
    assert controller.adc_monitor.transport is None and controller.adc_monitor.closed


def test_recording_and_csv_keep_raw_values_source_and_controller_readings(controller, tmp_path):
    controller.connect_adc_monitor()
    controller.tick()
    controller.run_id = controller.store.start(controller.recipe, controller.settings, {})
    controller._record_sample()
    sample = controller.recorded_samples_after(0)[0]
    assert sample["flow_ml_min"] == 25
    assert sample["sensor_source"] == "ads1115_usb" and sample["sensor_estimated"] is True
    assert sample["controller_readings"]["flow_ml_min"] is None
    assert sample["flow_adc_v"] == .25
    assert sample["adc_monitor"]["channels"]["A2"]["volts"] == 1.0
    assert controller.snapshot["flow_ml_min"] is None
    target = tmp_path / "adc.csv"
    controller.store.export(target, controller.run_id)
    with target.open(encoding="utf-8-sig", newline="") as stream:
        record = next(csv.DictReader(stream))
    assert record["flow_ml_min"] == "25.0"
    assert record["sensor_source"] == "ads1115_usb"
    assert record["pump_feedback_adc_v"] == "1.0"


def test_stale_auxiliary_records_do_not_inherit_controller_values(controller):
    controller.connect_adc_monitor()
    controller.adc_monitor.state.update(fresh=False, connected=False)
    controller.snapshot.update(pressure_psi=22, flow_ml_min=40, pump_feedback_v=5)
    controller.tick()
    controller.run_id = controller.store.start(controller.recipe, controller.settings, {})
    controller._record_sample()
    sample = controller.recorded_samples_after(0)[0]
    assert sample["flow_ml_min"] is None and sample["flow_adc_v"] is None
    assert sample["controller_readings"]["flow_ml_min"] == 40

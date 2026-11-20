"""External ADC readings stay visible without changing rig control permissions."""
import math

import pytest
from PySide6.QtWidgets import QApplication

from membrane_control.adc_display import adc_display_readings, adc_display_values
from membrane_control.controller import AppController
from membrane_control.device_status import device_statuses
from membrane_control.ui import MainWindow


def monitor(pressure=0.5004, flow=0.5, feedback=1.0, **changes):
    result = dict(port="COM5", connected=True, opened=True, identified=True,
                  fresh=True, adc_ack=True, status="Receiving ADS1115 readings on COM5",
                  channels={name: dict(signal=signal, status="reading_received", volts=volts)
                            for name, signal, volts in (("A0", "pressure", pressure),
                                                       ("A1", "flow", flow),
                                                       ("A2", "pump_feedback", feedback))})
    result.update(changes)
    return result


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def screen(qt_app, tmp_path):
    now = [100.0]
    controller = AppController(tmp_path, clock=lambda: now[0], simulation=False)
    controller.list_ports = lambda: []
    window = MainWindow(controller)
    window.timer.stop()
    yield window, controller, now
    window.close()


def test_certificate_and_nominal_divider_estimates_keep_channels_separate():
    snapshot = {"adc_monitor": monitor()}
    assert adc_display_values(snapshot, 0.01) == pytest.approx(
        dict(pressure_psi=50, flow_ml_min=50, pump_feedback_v=5, flux_lmh=300))
    for pin_volts, psi in ((0.001, 0), (0.5004, 50), (1.0008, 100)):
        snapshot["adc_monitor"] = monitor(pressure=pin_volts)
        assert adc_display_values(snapshot, 0.01)["pressure_psi"] == pytest.approx(psi)


def test_near_zero_noise_preserves_raw_voltage_and_large_negative_is_visible():
    snapshot = {"adc_monitor": monitor(pressure=0, flow=-0.000375, feedback=-0.104)}
    readings = adc_display_readings(snapshot)
    assert readings["flow"]["value"] == 0
    assert readings["flow"]["volts"] == -0.000375
    assert readings["pump_feedback"]["value"] is None
    assert readings["pump_feedback"]["volts"] == -0.104
    assert "below GND" in readings["pump_feedback"]["note"]


@pytest.mark.parametrize("change", [{"fresh": False}, {"adc_ack": False},
                                    {"connected": False}, {"identified": False}])
def test_stale_or_disconnected_selected_monitor_returns_explicit_missing_values(change):
    snapshot = {"pressure_psi": 99, "flow_ml_min": 99,
                "adc_monitor": monitor(**change)}
    values = adc_display_values(snapshot, 0.01)
    assert values and all(value is None for value in values.values())
    assert all(reading["volts"] is None for reading in adc_display_readings(snapshot).values())
    assert adc_display_values({}, 0.01) == {}


def test_external_metrics_show_without_rig_connection_or_readiness(screen):
    window, controller, _ = screen
    controller.snapshot["adc_monitor"] = monitor()
    window._update_view(dict(controller.snapshot))
    assert window._metric_labels["pressure_psi"].text() == "≈50.00"
    assert window._metric_labels["flow_ml_min"].text() == "≈50.0"
    assert window._metric_labels["pump_feedback_v"].text() == "≈5.00"
    assert "0.5004 V at ADS1115 A0" in window._metric_units["pressure_psi"].text()
    assert "A2 pump feedback 1.0000 V" in window.live_sensor_detail.text()
    assert not window.start_button.isEnabled()
    assert not window.manual_apply.isEnabled()
    assert not controller.snapshot["controller_connected"]
    assert controller.snapshot["pressure_psi"] is None
    statuses = {row["key"]: row for row in device_statuses(controller.snapshot, False)}
    assert statuses["pressure"]["status"] == "External ADC reading"
    assert statuses["controller"]["status"] == "Not connected"


def test_visible_estimates_cannot_satisfy_missing_controller_pressure(screen):
    window, controller, now = screen
    controller.recipe.hardware_approved = True
    window.recipe_approved.setChecked(True)
    controller.last_telemetry = now[0]
    controller.snapshot.update(controller_connected=True, hardware_verified=True,
                               pressure_psi=None, adc_monitor=monitor())
    window._update_view(dict(controller.snapshot))
    assert window._metric_labels["pressure_psi"].text() == "≈50.00"
    assert not window.start_button.isEnabled()
    assert not window.manual_apply.isEnabled()
    with pytest.raises(ValueError, match="pressure"):
        controller.start_run()


def test_stale_monitor_clears_display_and_graphs_without_old_controller_fallback(screen):
    window, controller, _ = screen
    controller.snapshot.update(pressure_psi=99, flow_ml_min=90, pump_feedback_v=9,
                               adc_monitor=monitor(fresh=False, status="Sensor readings stale"))
    window._last_plot = -100
    window._update_view(dict(controller.snapshot))
    for key in ("pressure_psi", "flow_ml_min", "pump_feedback_v", "flux_lmh"):
        assert window._metric_labels[key].text() == "Waiting"
    assert math.isnan(window._plot_data["pressure_psi"][-1])
    assert "Sensor readings stale" in window.adc_detail.text()


def test_negative_feedback_shows_actual_adc_voltage_instead_of_fabricated_zero(screen):
    window, controller, _ = screen
    controller.snapshot["adc_monitor"] = monitor(feedback=-0.104)
    window._update_view(dict(controller.snapshot))
    assert window._metric_labels["pump_feedback_v"].text() == "-0.1040"
    assert "below GND" in window._metric_units["pump_feedback_v"].text()


def test_startup_selects_and_connects_three_lab_ports(screen, monkeypatch):
    window, controller, _ = screen
    controller.preferred_controller_port = "COM9"
    controller.list_ports = lambda: [("COM5", "ADC USB"), ("COM6", "Scale"), ("COM9", "Rig Bluetooth")]
    calls = []
    monkeypatch.setattr(controller, "connect_controller", lambda port: calls.append(("rig", port)))
    monkeypatch.setattr(controller, "connect_balance", lambda port, *_args, **_kwargs: calls.append(("scale", port)))
    monkeypatch.setattr(controller, "connect_adc_monitor", lambda port: calls.append(("adc", port)))
    window._refresh_ports()
    assert window.adc_port.currentData() == "COM5"
    assert window.controller_port.currentData() == "COM9"
    assert window.balance_port.currentData() == "COM6"
    window.connect_lab_defaults()
    assert calls == [("rig", "COM9"), ("scale", "COM6"), ("adc", "COM5")]

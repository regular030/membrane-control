"""The measured drive-output level remains separate from the app command."""
import pytest
from PySide6.QtWidgets import QApplication

from membrane_control.controller import AppController
from membrane_control.ui import MainWindow, _drive_feedback_percent


def test_unbounded_numeric_input_cannot_overflow_the_percentage_conversion():
    assert _drive_feedback_percent(10 ** 1000) is None


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
    controller.last_telemetry = now[0]
    snapshot = dict(controller.snapshot, controller_connected=True, simulation=False,
                    hardware_verified=True, pump_percent=0, pump_feedback_v=9.78,
                    pump_feedback_adc_v=1.9564,
                    sensor_inputs={"pump_feedback": {"source": "ads1115", "channel": 2}})
    yield window, controller, now, snapshot
    window.close()


def test_reported_drive_level_is_visible_while_app_command_is_zero(screen):
    window, controller, _now, snapshot = screen
    window._update_view(snapshot)
    assert window.manual_pump_sent.text() == "Commanded 0.0%"
    assert window._metric_labels["pump_feedback_v"].text() == "9.78"
    assert window._metric_units["pump_feedback_v"].text() == (
        "V · 97.8% drive feedback · 1.9564 V at ADS1115 A2")
    assert "Drive command feedback 9.78 V · Reported drive level 97.8%" in window.manual_pump_feedback.text()
    assert "Motor tachometer unavailable" in window.manual_pump_feedback.text()
    assert controller.driver is None  # Rendering never opens or commands hardware.


@pytest.mark.parametrize("volts, percent", [(0, "0.0%"), (5, "50.0%"), (10.2, "102.0%")])
def test_feedback_percentage_uses_nominal_voltage_without_capping_overshoot(screen, volts, percent):
    window, _controller, _now, snapshot = screen
    window._update_view(dict(snapshot, pump_feedback_v=volts))
    assert percent + " drive feedback" in window._metric_units["pump_feedback_v"].text()
    assert "Reported drive level " + percent in window.manual_pump_feedback.text()


@pytest.mark.parametrize("volts", [None, -0.1, 10.6, float("nan"), float("inf"), True])
def test_invalid_feedback_does_not_create_a_reported_percentage(screen, volts):
    window, _controller, _now, snapshot = screen
    window._update_view(dict(snapshot, pump_feedback_v=volts))
    assert "% drive feedback" not in window._metric_units["pump_feedback_v"].text()
    assert "Reported drive level" not in window.manual_pump_feedback.text()


@pytest.mark.parametrize("changes", [{"controller_connected": False}, {"hardware_verified": False}, {"simulation": True}])
def test_unconfirmed_connection_or_hardware_cannot_show_a_reported_percentage(screen, changes):
    window, _controller, _now, snapshot = screen
    window._update_view(dict(snapshot, **changes))
    assert "% drive feedback" not in window._metric_units["pump_feedback_v"].text()
    assert "Reported drive level" not in window.manual_pump_feedback.text()


def test_stale_feedback_clears_reported_percentage(screen):
    window, _controller, now, snapshot = screen
    window._update_view(snapshot)
    assert "97.8% drive feedback" in window._metric_units["pump_feedback_v"].text()
    now[0] += 3
    window._update_view(snapshot)
    assert "% drive feedback" not in window._metric_units["pump_feedback_v"].text()
    assert window.manual_pump_feedback.text() == "Waiting for fresh pump feedback."

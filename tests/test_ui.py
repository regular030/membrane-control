"""Offscreen Qt integration checks for operator controls; no hardware required."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog

from membrane_control.controller import AppController
from membrane_control.ui import MainWindow


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def screen(qt_app, tmp_path):
    now = [100.0]
    controller = AppController(tmp_path, clock=lambda: now[0])
    window = MainWindow(controller)
    window.timer.stop()
    controller.tick()
    window._update_view(dict(controller.snapshot))
    yield window, controller, now
    window.close()


def test_manual_outputs_keep_stop_available_and_lock_mode(screen):
    window, controller, now = screen
    controller.set_manual([True, False, False, False, False, False, False], 20)
    now[0] += 0.1
    controller.tick()
    window._update_view(dict(controller.snapshot))
    assert controller.snapshot["state"] == "manual"
    assert window.stop_button.isEnabled()
    assert not window.start_button.isEnabled()
    assert not window.simulation_check.isEnabled()
    assert not window.steps_table.isEnabled()
    assert window.valve_buttons[0].isEnabled()
    assert window.manual_apply.isEnabled()


def test_start_pending_blocks_second_start_but_keeps_stop(screen):
    window, controller, _ = screen
    controller.start_run()
    assert controller.snapshot["start_pending"]
    window._update_view(dict(controller.snapshot))
    assert not window.start_button.isEnabled()
    assert window.stop_button.isEnabled()
    assert not window.simulation_check.isEnabled()
    assert not window.valve_buttons[0].isEnabled()
    assert not window.import_button.isEnabled()
    assert window.state_chip.text() == "STARTING"


def test_dry_run_firmware_does_not_change_desktop_connection_mode(screen):
    window, controller, now = screen
    controller.set_simulation(False)
    controller.snapshot.update(controller_connected=True, simulation=True,
                               hardware_verified=False, pressure_psi=0)
    controller.last_telemetry = now[0]
    window._update_view(dict(controller.snapshot))
    assert not window.simulation_check.isChecked()
    assert window.controller_disconnect.isEnabled()
    assert window.balance_connect.isEnabled()
    assert "DRY RUN FIRMWARE" in window.banner.text()
    assert window.stop_button.isEnabled()


def test_timer_failure_requests_stop_once_and_blocks_start(screen, monkeypatch):
    window, controller, _ = screen
    requests = []
    original_stop = controller.stop_run

    def stop():
        requests.append(True)
        original_stop()

    def failing_tick():
        raise RuntimeError("test acquisition failure")

    monkeypatch.setattr(controller, "stop_run", stop)
    monkeypatch.setattr(controller, "tick", failing_tick)
    window._on_tick()
    window._on_tick()
    assert len(requests) == 1
    assert "test acquisition failure" in window._timer_fault
    assert not window.start_button.isEnabled()
    assert any("test acquisition failure" in line for line in controller.log)


def test_editor_round_trip_and_reordering(screen):
    window, controller, _ = screen
    recipe = window._collect_recipe()
    assert recipe.to_dict() == controller.recipe.to_dict()
    window._add_step()
    row = window.steps_table.rowCount() - 1
    window.steps_table.selectRow(row)
    window._move_step(-1)
    assert window._step_data()[row - 1]["name"] == f"Step {row + 1}"
    window._remove_step()
    assert len(window._collect_recipe().steps) == len(recipe.steps)


def test_display_buffers_are_bounded(screen):
    window, controller, _ = screen
    for index in range(650):
        window._last_plot = 0
        window._update_view(dict(controller.snapshot))
    assert len(window._plot_time) == 600
    assert all(len(points) == 600 for points in window._plot_data.values())


def test_save_as_refreshes_custom_preset_dropdown(screen, monkeypatch):
    window, controller, _ = screen
    output = controller.data_dir / "saved-recipe.json"
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("My saved sequence", True))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(output), "Recipe JSON (*.json)"))
    window._save_as_recipe()
    assert output.exists()
    index = window.preset_combo.findData("My saved sequence")
    assert index >= 0
    assert "custom" in window.preset_combo.itemText(index)


def test_stop_pending_locks_start_and_mode(screen):
    window, controller, _ = screen
    controller.stop_run()
    window._update_view(dict(controller.snapshot))
    assert not window.start_button.isEnabled()
    assert window.stop_button.isEnabled()
    assert not window.simulation_check.isEnabled()
    assert not window.manual_apply.isEnabled()
    assert window.state_chip.text() == "STOPPING"

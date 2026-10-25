"""Offscreen Qt integration checks for operator controls; no hardware required."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog

from membrane_control.controller import AppController
from membrane_control.ui import MainWindow
from membrane_control.models import Recipe, Step


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
    assert controller.recipe.name == "My saved sequence"
    assert window.preset_combo.currentData() == "My saved sequence"


def test_stop_pending_locks_start_and_mode(screen):
    window, controller, _ = screen
    controller.stop_run()
    window._update_view(dict(controller.snapshot))
    assert not window.start_button.isEnabled()
    assert window.stop_button.isEnabled()
    assert not window.simulation_check.isEnabled()
    assert not window.manual_apply.isEnabled()
    assert window.state_chip.text() == "STOPPING"


def test_dashboard_device_panel_identifies_demo_as_simulated(screen):
    window, controller, _ = screen
    assert len(window.device_status_labels) == 6
    for label in window.device_status_labels.values():
        assert label.text() == "Simulated"
        assert label.property("statusLevel") == "warning"
        assert label.toolTip()
        assert "Simulated" in label.accessibleName()
    assert not window.device_panel.isHidden()


def test_dashboard_device_panel_hardware_disconnected(screen):
    window, controller, _ = screen
    controller.set_simulation(False)
    window._update_view(dict(controller.snapshot))
    labels = window.device_status_labels
    assert labels["controller"].text() == "Not connected"
    assert "ESP32 is not connected" in window.banner.text()
    assert labels["balance"].text() == "Not connected"
    assert all(labels[key].text() == "No reading" for key in ("pressure", "flow", "pump_feedback"))
    assert labels["outputs"].text() == "Not monitored"
    assert "physical" in labels["outputs"].accessibleDescription()


def test_dashboard_device_panel_distinguishes_received_readings_from_connections(screen):
    window, controller, _ = screen
    controller.set_simulation(False)
    controller.snapshot.update(controller_connected=True, simulation=False,
        hardware_verified=True, balance_connected=False, mass_g=None,
        pressure_psi=12, flow_ml_min=30, pump_feedback_v=2.5)
    window._update_view(dict(controller.snapshot))
    labels = window.device_status_labels
    assert labels["controller"].text() == "Connected"
    assert labels["balance"].text() == "Not connected"
    for key in ("pressure", "flow", "pump_feedback"):
        assert labels[key].text() == "Reading received"
        assert labels[key].property("statusLevel") == "success"
    assert labels["outputs"].text() == "Not monitored"


def test_dashboard_device_panel_dry_run_firmware_can_have_real_scale(screen):
    window, controller, _ = screen
    controller.set_simulation(False)
    controller.snapshot.update(controller_connected=True, simulation=True,
        balance_connected=True, mass_g=123, pressure_psi=1, flow_ml_min=2,
        pump_feedback_v=0.5)
    window._update_view(dict(controller.snapshot))
    labels = window.device_status_labels
    assert labels["controller"].text() == "Connected (dry run)"
    assert labels["controller"].property("statusLevel") == "warning"
    assert labels["balance"].text() == "Connected"
    assert labels["balance"].property("statusLevel") == "success"
    assert all(labels[key].text() == "Simulated" for key in ("pressure", "flow", "pump_feedback", "outputs"))
    assert not window.simulation_check.isChecked()


def test_compact_window_keeps_device_panel_visible_and_controls_unclipped(screen, qt_app):
    window, _, _ = screen
    window.resize(1080, 760)
    window.show()
    qt_app.processEvents()
    assert window.device_panel.isVisible()
    assert window.dashboard_scroll.verticalScrollBar().maximum() > 0
    window.dashboard_scroll.verticalScrollBar().setValue(window.dashboard_scroll.verticalScrollBar().maximum())
    qt_app.processEvents()
    for label in window.device_status_labels.values():
        assert label.fontMetrics().horizontalAdvance(label.text()) <= label.contentsRect().width()
    for button in window.valve_buttons:
        assert button.height() >= button.sizeHint().height()


def test_start_here_opens_beginner_guide(screen):
    window, _, _ = screen
    window.help_button.click()
    assert window.tabs.tabText(window.tabs.currentIndex()) == "Help"
    assert "cannot unlock" in window.recipe_approval_note.text()


def test_readiness_gives_connection_action_and_explains_hardware_gate(screen):
    window, controller, now = screen
    controller.set_simulation(False)
    window._update_view(dict(controller.snapshot))
    assert "ESP32 is not connected" in window.readiness_label.text()
    window.next_step_button.click()
    assert window.tabs.currentIndex() == 2
    controller.snapshot.update(controller_connected=True, simulation=False,
                               hardware_verified=False, pressure_psi=0)
    controller.last_telemetry = now[0]
    window.recipe_approved.setChecked(True)
    window._update_view(dict(controller.snapshot))
    assert "setup is unfinished" in window.readiness_label.text()
    assert "cannot unlock" in window.readiness_label.text()
    assert not window.start_button.isEnabled()
    window.next_step_button.click()
    assert window.tabs.currentIndex() == 4


def test_invalid_edited_sequence_has_visible_next_step(screen):
    window, controller, _ = screen
    window.recipe_name.setText("")
    window._update_view(dict(controller.snapshot))
    assert "Check the sequence" in window.readiness_label.text()
    assert not window.start_button.isEnabled()
    window.next_step_button.click()
    assert window.tabs.currentIndex() == 1


def test_completed_run_can_be_exported_from_dashboard_and_is_selected(screen):
    window, controller, now = screen
    recipe = Recipe(name="Short UI run", steps=[Step("Observe", 0.1)])
    controller.load_recipe(recipe)
    window._populate_recipe(recipe)
    controller.start_run()
    controller.tick()
    controller.tick()
    window._update_view(dict(controller.snapshot))
    now[0] += 0.2
    controller.tick()
    window._update_view(dict(controller.snapshot))
    assert controller.snapshot["run_id"] is None
    assert window.export_current_button.isEnabled()
    assert "most recent" in window.export_current_button.toolTip()
    assert window.history_table.currentRow() == 0


def test_valve_click_does_not_apply_an_unsent_pump_edit(screen):
    window, controller, _ = screen
    window.manual_pump.setValue(35)
    window.valve_buttons[0].click()
    assert controller.driver.engine.valves[0]
    assert controller.driver.engine.pump_percent == 0
    controller.tick()
    window._update_view(dict(controller.snapshot))
    assert window.manual_pump.value() == 35
    window.manual_apply.click()
    assert controller.driver.engine.pump_percent == 35


def test_manual_pending_locks_changes_but_keeps_stop(screen):
    window, controller, _ = screen
    controller.set_manual([True] + [False] * 6, 0)
    window._update_view(dict(controller.snapshot))
    assert controller.snapshot["manual_pending"]
    assert window.stop_button.isEnabled()
    assert not window.start_button.isEnabled()
    assert not window.manual_apply.isEnabled()
    assert not window.simulation_check.isEnabled()
    assert not window.steps_table.isEnabled()
    assert window.state_chip.text() == "APPLYING"


def test_loaded_file_name_is_visible_in_preset_dropdown(screen):
    window, controller, _ = screen
    recipe = Recipe(name="Imported lab sequence")
    controller.load_recipe(recipe)
    window._populate_recipe(recipe)
    assert "Imported lab sequence" in window.preset_combo.currentText()


def test_manual_controls_use_applied_review_not_an_unsaved_checkbox(screen):
    window, controller, now = screen
    controller.set_simulation(False)
    controller.snapshot.update(controller_connected=True, simulation=False,
                               hardware_verified=True, pressure_psi=0)
    controller.last_telemetry = now[0]
    window.recipe_approved.setChecked(True)
    window._update_view(dict(controller.snapshot))
    assert window.start_button.isEnabled()
    assert not window.manual_apply.isEnabled()
    assert "Apply the reviewed sequence first" in window.manual_apply.toolTip()
    window._apply_recipe()
    window._update_view(dict(controller.snapshot))
    assert window.manual_apply.isEnabled()


def test_csv_export_waits_until_operation_has_stopped(screen, monkeypatch):
    window, controller, _ = screen
    controller.start_run()

    def unexpected_dialog(*args, **kwargs):
        raise AssertionError("An export dialog must not open while a run is starting")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", unexpected_dialog)
    window._update_view(dict(controller.snapshot))
    assert not window.export_current_button.isEnabled()
    window._export_csv(None)
    assert "Stop run" in window.statusBar().currentMessage()

"""Comparison targets persist independently of measured flow and pump commands."""
import json
import math
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog

from membrane_control.controller import AppController
from membrane_control.ui import MainWindow


@pytest.fixture(scope='module')
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def screen(qt_app, tmp_path):
    now = [100.0]
    controller = AppController(tmp_path, clock=lambda: now[0])
    controller.list_ports = lambda: []
    window = MainWindow(controller)
    window.timer.stop()
    controller.tick()
    window._update_view(dict(controller.snapshot))
    yield window, controller, now
    window.close()


def test_dashboard_and_editor_target_edits_stay_in_sync(screen):
    window, controller, _ = screen
    assert window.desired_flow_spin.value() == window.recipe_desired_flow_spin.value() == 0
    window.desired_flow_spin.setValue(42.25)
    assert window.recipe_desired_flow_spin.value() == 42.25
    window.recipe_desired_flow_spin.setValue(73.5)
    assert window.desired_flow_spin.value() == 73.5
    assert window._collect_recipe().desired_flow_ml_min == 73.5
    assert controller.snapshot['desired_flow_ml_min'] == 0  # Edits are not yet applied.
    window._apply_recipe()
    assert controller.recipe.desired_flow_ml_min == controller.snapshot['desired_flow_ml_min'] == 73.5
    assert 'comparison' in window.desired_flow_note.text()
    assert 'pump output remains set in %' in window.desired_flow_note.text()


def test_apply_target_preserves_pending_sequence_edits_and_pump_output(screen, monkeypatch):
    window, controller, _ = screen
    applied_name = controller.recipe.steps[0].name
    applied_pump = controller.recipe.steps[0].pump_percent
    window.steps_table.item(0, 0).setText('Unsaved sequence edit')
    window.steps_table.cellWidget(0, 9).setValue(68.5)
    window.manual_pump.setValue(81)
    before_pump = controller.snapshot['pump_percent']
    before_flow = controller.snapshot['flow_ml_min']
    monkeypatch.setattr(controller, 'set_manual', lambda *_args: pytest.fail('Target must not send a pump command'))
    window.desired_flow_spin.setValue(90.25)
    window.apply_target_button.click()
    assert controller.recipe.desired_flow_ml_min == controller.snapshot['desired_flow_ml_min'] == 90.25
    assert controller.recipe.steps[0].name == applied_name
    assert controller.recipe.steps[0].pump_percent == applied_pump
    assert window.steps_table.item(0, 0).text() == 'Unsaved sequence edit'
    assert window.steps_table.cellWidget(0, 9).value() == 68.5
    assert controller.snapshot['pump_percent'] == before_pump
    assert controller.snapshot['flow_ml_min'] == before_flow


def test_target_save_and_import_round_trip(screen, monkeypatch):
    window, controller, _ = screen
    output = controller.data_dir / 'desired-flow-sequence.json'
    original_pumps = [step.pump_percent for step in controller.recipe.steps]
    window.recipe_desired_flow_spin.setValue(64.75)
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **kw: ('Desired flow comparison', True))
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(output), 'Recipe JSON (*.json)'))
    window._save_as_recipe()
    assert json.loads(output.read_text())['desired_flow_ml_min'] == 64.75
    window.desired_flow_spin.setValue(0)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(output), 'Recipe JSON (*.json)'))
    window._import_recipe()
    assert window.desired_flow_spin.value() == window.recipe_desired_flow_spin.value() == 64.75
    assert controller.snapshot['desired_flow_ml_min'] == 64.75
    assert [step.pump_percent for step in controller.recipe.steps] == original_pumps


def test_legacy_sequence_without_target_loads_zero(screen, monkeypatch):
    window, controller, _ = screen
    legacy = controller.recipe.to_dict()
    legacy.pop('desired_flow_ml_min')
    output = controller.data_dir / 'legacy-sequence.json'
    output.write_text(json.dumps(legacy))
    window.desired_flow_spin.setValue(200)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(output), 'Recipe JSON (*.json)'))
    window._import_recipe()
    assert window.desired_flow_spin.value() == window.recipe_desired_flow_spin.value() == 0


@pytest.mark.parametrize('state,flag', [
    ('running', None), ('manual', None), ('idle', 'start_pending'),
    ('idle', 'manual_pending'), ('idle', 'stop_pending'),
])
def test_desired_flow_controls_lock_during_operations(screen, state, flag):
    window, controller, _ = screen
    snapshot = dict(controller.snapshot, state=state)
    if flag:
        snapshot[flag] = True
    window._update_view(snapshot)
    assert not window.desired_flow_spin.isEnabled()
    assert not window.recipe_desired_flow_spin.isEnabled()
    assert not window.apply_target_button.isEnabled()
    window._update_view(dict(controller.snapshot, state='idle', start_pending=False,
                             manual_pending=False, stop_pending=False))
    assert window.desired_flow_spin.isEnabled()
    assert window.recipe_desired_flow_spin.isEnabled()
    assert window.apply_target_button.isEnabled()


def test_chart_displays_applied_target_as_distinct_dashed_comparison(screen):
    window, controller, _ = screen
    controller.set_simulation(False)
    window.desired_flow_spin.setValue(999)  # Unapplied edit must not become chart data.
    snapshot = dict(controller.snapshot, flow_ml_min=12.5, desired_flow_ml_min=75,
                    pump_percent=33)
    window._last_plot = 0
    window._update_view(snapshot)
    measured = window._curves['flow_ml_min']
    target = window._curves['desired_flow_ml_min']
    assert measured.name() == 'Measured flow' and target.name() == 'Desired flow'
    assert measured.opts['pen'].style() == Qt.PenStyle.SolidLine
    assert target.opts['pen'].style() == Qt.PenStyle.DashLine
    assert measured.getData()[1][-1] == 12.5
    assert target.getData()[1][-1] == 75
    assert window._metric_labels['flow_ml_min'].text() == '12.5'
    assert len(window.flow_legend.items) == 2
    snapshot['flow_ml_min'] = None
    window._last_plot = 0
    window._update_view(snapshot)
    assert math.isnan(measured.getData()[1][-1])
    assert target.getData()[1][-1] == 75
    assert window._metric_labels['flow_ml_min'].text() == 'Waiting'


def test_target_trace_is_bounded_cleared_and_keeps_dash_style_during_zoom(screen):
    window, controller, _ = screen
    snapshot = dict(controller.snapshot, desired_flow_ml_min=28)
    for _ in range(605):
        window._last_plot = 0
        window._update_view(snapshot)
    assert len(window._plot_data['desired_flow_ml_min']) == len(window._plot_time) == 600
    target = window._curves['desired_flow_ml_min']
    for percent in (60, 150, 100):
        window.set_zoom_percent(percent)
        assert target.opts['pen'].style() == Qt.PenStyle.DashLine
        assert target.opts['pen'].widthF() == pytest.approx(2 * percent / 100)
        assert target.getData()[1][-1] == 28
    window._clear_traces()
    assert len(window._plot_data['desired_flow_ml_min']) == 0
    assert target.getData()[0] is None


def test_compact_dashboard_preserves_full_target_and_valve_control_height(screen, qt_app):
    window, _, _ = screen
    window.resize(1080, 760)
    window.show()
    qt_app.processEvents()
    for percent in (100, 60, 150, 100):
        window.set_zoom_percent(percent)
        qt_app.processEvents()
    scroll = window.dashboard_scroll
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    qt_app.processEvents()
    assert scroll.verticalScrollBar().maximum() > 0
    for control in [*window.valve_buttons, window.manual_pump, window.manual_apply,
                    window.desired_flow_spin, window.apply_target_button]:
        assert control.height() >= control.sizeHint().height()

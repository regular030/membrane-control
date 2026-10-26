"""Live table displays committed samples without generating readings or history."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QAbstractItemView

from membrane_control.controller import AppController
from membrane_control.models import Recipe, Step
from membrane_control.ui import MainWindow, LIVE_TABLE_COLUMNS, LIVE_TABLE_MAX_ROWS


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


def column(key):
    return next(index for index, (field, _title, _width) in enumerate(LIVE_TABLE_COLUMNS) if field == key)


def cell(window, row, key):
    return window.live_table.item(row, column(key)).text()


def sample(sequence, run_id=1, **updates):
    return {'_sample_sequence': sequence, 'run_id': run_id,
        'time_utc': '2026-10-26T18:02:03.123+00:00', 'elapsed_s': sequence,
        'state': 'running', 'cycle': 1, 'step_index': 0, 'step_name': 'Record',
        'desired_flow_ml_min': 30, 'flow_ml_min': 21.5, 'balance_flow_ml_min': 20.5,
        'pressure_psi': 4.25, 'flux_lmh': 129, 'mass_g': 123.4, 'pump_percent': 25,
        'pump_feedback_v': 2.5, 'valves': [True, False, True, False, False, True, False],
        'fault': None, 'controller_status': 'Connected', 'balance_status': 'Connected',
        'simulation': False, **updates}


def test_idle_snapshots_create_no_rows_and_table_is_read_only(screen):
    window, controller, _ = screen
    for _ in range(4):
        window._update_view(dict(controller.snapshot, flow_ml_min=999))
    assert window.live_table.rowCount() == 0
    assert window.live_row_count.text() == '0 rows'
    assert window.live_table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert window.follow_latest_check.isChecked()
    assert 'mL/min' in window.live_table.horizontalHeaderItem(column('flow_ml_min')).text()
    assert 'command' in window.live_table.horizontalHeaderItem(column('valve_0')).text()


def test_committed_rows_contain_all_values_and_are_appended_once(screen, monkeypatch):
    window, controller, _ = screen
    event = sample(1)
    queries = []

    def after(sequence):
        queries.append(sequence)
        return [event] if sequence < 1 else []

    monkeypatch.setattr(controller, 'recorded_samples_after', after)
    window._update_view(dict(controller.snapshot, run_id=1))
    window._update_view(dict(controller.snapshot, run_id=1, flow_ml_min=999))
    assert queries == [0, 1]
    assert window.live_table.rowCount() == 1
    assert cell(window, 0, 'time_utc') == event['time_utc']
    assert cell(window, 0, 'flow_ml_min') == '21.5'
    assert cell(window, 0, 'desired_flow_ml_min') == '30'
    assert cell(window, 0, 'balance_flow_ml_min') == '20.5'
    assert cell(window, 0, 'pressure_psi') == '4.25'
    assert cell(window, 0, 'pump_percent') == '25'
    assert cell(window, 0, 'pump_feedback_v') == '2.5'
    assert cell(window, 0, 'valve_0') == 'ON' and cell(window, 0, 'valve_1') == 'OFF'
    assert cell(window, 0, 'simulation') == 'Hardware'
    assert not (window.live_table.item(0, 0).flags() & Qt.ItemFlag.ItemIsEditable)
    assert cell(window, 0, 'fault') == 'No fault'
    assert window.live_table.cellWidget(0, 0) is None


def test_missing_readings_are_unavailable_and_valid_zero_is_retained(screen, monkeypatch):
    window, controller, _ = screen
    event = sample(1, flow_ml_min=None, balance_flow_ml_min=None, pressure_psi=None,
                   mass_g=0, desired_flow_ml_min=0, pump_feedback_v=float('nan'),
                   valves=[False, None], simulation=True)
    monkeypatch.setattr(controller, 'recorded_samples_after', lambda seq: [event] if seq == 0 else [])
    window._update_view(dict(controller.snapshot))
    for key in ('flow_ml_min', 'balance_flow_ml_min', 'pressure_psi', 'pump_feedback_v', 'valve_1', 'valve_6'):
        assert cell(window, 0, key) == 'Unavailable'
    assert cell(window, 0, 'mass_g') == cell(window, 0, 'desired_flow_ml_min') == '0'
    assert cell(window, 0, 'valve_0') == 'OFF'
    assert cell(window, 0, 'simulation') == 'Simulation'


def test_recording_interval_and_final_sample_follow_actual_controller_events(screen):
    window, controller, now = screen
    controller.load_recipe(Recipe(name='Live sample test', sample_interval_s=1,
                                  steps=[Step('Observe', 10, pump_percent=0)]))
    controller.start_run()
    controller.tick()
    controller.tick()
    window._update_view(dict(controller.snapshot))
    first_count = window.live_table.rowCount()
    assert first_count >= 1
    first_time = cell(window, 0, 'time_utc')
    now[0] += 0.2
    controller.tick()
    window._update_view(dict(controller.snapshot))
    assert window.live_table.rowCount() == first_count
    controller.stop_run()
    controller.tick()
    window._update_view(dict(controller.snapshot))
    assert window.live_table.rowCount() == first_count + 1
    assert cell(window, 0, 'time_utc') == first_time
    assert controller.snapshot['run_id'] is None
    kept = window.live_table.rowCount()
    controller.tick()
    window._update_view(dict(controller.snapshot))
    assert window.live_table.rowCount() == kept


def test_new_run_clears_display_without_resetting_event_cursor(screen, monkeypatch):
    window, controller, _ = screen
    events = [sample(1, run_id=1)]
    monkeypatch.setattr(controller, 'recorded_samples_after',
                        lambda seq: [event for event in events if event['_sample_sequence'] > seq])
    window._update_view(dict(controller.snapshot, run_id=1))
    assert window.live_table.rowCount() == 1
    window._update_view(dict(controller.snapshot, run_id=None))
    assert window.live_table.rowCount() == 1  # Finished run remains visible.
    window._update_view(dict(controller.snapshot, run_id=2))
    assert window.live_table.rowCount() == 0
    assert window._live_sample_sequence == 1
    events.append(sample(2, run_id=2))
    window._update_view(dict(controller.snapshot, run_id=2))
    assert window.live_table.rowCount() == 1
    assert cell(window, 0, 'run_id') == '2'
    assert window.live_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == 2


def test_starting_new_window_does_not_show_older_run_while_waiting_for_first_sample(screen, monkeypatch):
    window, controller, _ = screen
    monkeypatch.setattr(controller, 'recorded_samples_after', lambda seq: [sample(1, run_id=1)] if seq == 0 else [])
    window._update_view(dict(controller.snapshot, run_id=2))
    assert window.live_table.rowCount() == 0
    assert window._live_sample_sequence == 1


def test_table_is_bounded_and_follow_latest_can_be_paused(screen, qt_app, monkeypatch):
    window, controller, _ = screen
    events = [sample(seq) for seq in range(1, LIVE_TABLE_MAX_ROWS + 1)]
    monkeypatch.setattr(controller, 'recorded_samples_after',
                        lambda seq: [event for event in events if event['_sample_sequence'] > seq])
    window.show()
    qt_app.processEvents()
    window._update_view(dict(controller.snapshot, run_id=1))
    qt_app.processEvents()
    table = window.live_table
    assert table.rowCount() == LIVE_TABLE_MAX_ROWS
    assert table.horizontalScrollBar().maximum() > 0
    bar = table.verticalScrollBar()
    assert bar.value() == bar.maximum()
    window.follow_latest_check.setChecked(False)
    bar.setValue(50)
    anchor = table.item(bar.value(), 0).data(Qt.ItemDataRole.UserRole)
    events.append(sample(LIVE_TABLE_MAX_ROWS + 1))
    window._update_view(dict(controller.snapshot, run_id=1))
    qt_app.processEvents()
    assert table.rowCount() == LIVE_TABLE_MAX_ROWS
    assert table.item(0, 0).data(Qt.ItemDataRole.UserRole) == 2
    assert table.item(bar.value(), 0).data(Qt.ItemDataRole.UserRole) == anchor
    assert bar.value() < bar.maximum()
    assert window.live_row_count.text() == '1,000 rows'
    window.follow_latest_check.setChecked(True)
    qt_app.processEvents()
    assert bar.value() == bar.maximum()


def test_clear_traces_keeps_recorded_table_and_zoom_keeps_rows_readable(screen, qt_app, monkeypatch):
    window, controller, _ = screen
    monkeypatch.setattr(controller, 'recorded_samples_after', lambda seq: [sample(1)] if seq == 0 else [])
    window._update_view(dict(controller.snapshot))
    window._clear_traces()
    assert window.live_table.rowCount() == 1
    before = cell(window, 0, 'flow_ml_min')
    for percent in (60, 150, 100):
        window.set_zoom_percent(percent)
        qt_app.processEvents()
    assert cell(window, 0, 'flow_ml_min') == before
    assert window.live_table.rowHeight(0) == window.live_table.verticalHeader().defaultSectionSize()

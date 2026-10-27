"""Six normal-firmware toggles and balance tools use simulated/fake transports."""
import pytest
from PySide6.QtWidgets import QCheckBox

from test_ui import qt_app, screen
from test_manual_valves_controller import Driver, identify, telemetry, acknowledge


def physical_valves(controller, now):
    controller.set_simulation(False)
    controller.driver = Driver()
    identify(controller, lambda: now[0])
    telemetry(controller, lambda: now[0])


def test_six_controls_live_on_dashboard_without_sensor_or_review_boxes(screen, qt_app):
    window, controller, now = screen
    physical_valves(controller, now)
    controller.recipe.require_balance = True
    controller.settings['require_balance'] = True
    controller.recipe.hardware_approved = False
    window._update_view(dict(controller.snapshot))
    window.show()
    qt_app.processEvents()
    assert len(window.valve_buttons) == 6
    assert [button.text().splitlines()[0] for button in window.valve_buttons] == ['V1', 'V2', 'V3', 'V4', 'V5', 'V7']
    assert all(button.isEnabled() for button in window.valve_buttons)
    assert not window.valve_controls.findChildren(QCheckBox)
    assert not window.manual_apply.isEnabled() and not window.start_button.isEnabled()
    assert 'VALVE CONTROLS READY' in window.banner.text()
    assert 'without sensors' in window.readiness_label.text()
    assert window.steps_table.isColumnHidden(7)
    assert not window.steps_table.isColumnHidden(8)
    assert controller.snapshot['pressure_psi'] is None and controller.snapshot['flow_ml_min'] is None


def test_normal_toggle_routes_new_command_and_all_off_slot7(screen):
    window, controller, now = screen
    physical_valves(controller, now)
    window._update_view(dict(controller.snapshot))
    window.valve_buttons[5].click()
    command = controller.driver.sent[-1]
    assert command['cmd'] == 'manual_valves'
    assert command['valves'] == [False] * 6 + [True]
    assert 'pump_percent' not in command
    assert not any(button.isEnabled() for button in window.valve_buttons)
    acknowledge(controller, lambda: now[0])
    window._update_view(dict(controller.snapshot))
    assert all(button.isEnabled() for button in window.valve_buttons)
    assert window.valve_buttons[5].isChecked()
    assert window.stop_button.text() == 'Stop valves'
    assert not window.manual_apply.isEnabled()
    window.stop_button.click()
    assert controller.driver.sent[-1]['cmd'] == 'stop'


def test_v5_label_uses_physical_wire_slot_and_bit5_tooltip(screen):
    window, controller, now = screen
    physical_valves(controller, now)
    window._update_view(dict(controller.snapshot))
    window.valve_buttons[4].click()
    assert controller.driver.sent[-1]['valves'] == [False] * 4 + [True, False, False]
    assert 'bit 5' in window.valve_buttons[4].toolTip()
    assert 'bit 6' in window.valve_buttons[5].toolTip()


def test_builtin_demos_do_not_command_absent_v6(screen):
    window, controller, _ = screen
    for recipe in controller.presets.values():
        assert all(not step.valves[5] for step in recipe.steps)
        window._populate_recipe(recipe)
        assert window._collect_recipe().to_dict() == recipe.to_dict()


def test_old_firmware_does_not_offer_unknown_new_commands(screen):
    window, controller, now = screen
    physical_valves(controller, now)
    controller.snapshot['valve_control_ready'] = False
    window._update_view(dict(controller.snapshot))
    assert not any(button.isEnabled() for button in window.valve_buttons)


def test_balance_serial_choices_and_connection_arguments(screen, monkeypatch):
    window, controller, _ = screen
    controller.set_simulation(False)
    window.balance_port.addItem('COM6 · test only', 'COM6')
    window.balance_port.setCurrentIndex(window.balance_port.findData('COM6'))
    window.balance_baud.setCurrentText('9600')
    window.balance_format.setCurrentIndex(window.balance_format.findData('7E1'))
    calls = []
    monkeypatch.setattr(controller, 'connect_balance', lambda *args, **kwargs: calls.append((args, kwargs)))
    window._connect_balance()
    assert calls == [(('COM6', 9600), {'serial_format': '7E1', 'polling': True})]
    assert window.balance_baud.findText('4800') >= 0


def test_main_window_shutdown_also_closes_owned_scale_diagnostics(screen):
    window, _, _ = screen
    calls = []
    class Diagnostics:
        def shutdown(self): calls.append('shutdown')
        def reject(self): calls.append('reject')
    window._balance_diagnostics_dialog = Diagnostics()
    window.shutdown()
    assert calls == ['shutdown', 'reject']
    assert window._balance_diagnostics_dialog is None


def test_raw_scale_test_releases_main_port_and_preserves_selected_settings(screen, monkeypatch):
    window, controller, now = screen
    physical_valves(controller, now)
    closed = []
    class Balance:
        port = 'COM6'
        def close(self): closed.append(True)
    controller.balance = Balance()
    controller.snapshot.update(balance_connected=True, mass_g=12)
    window.balance_port.addItem('COM6 test scale', 'COM6')
    window.balance_port.setCurrentIndex(window.balance_port.findData('COM6'))
    window.balance_format.setCurrentIndex(window.balance_format.findData('7E1'))
    called = []
    class Dialog:
        def __init__(self, _parent, **kwargs): called.append(kwargs)
        def exec(self): return 0
        def shutdown(self): called.append('closed')
        def deleteLater(self): pass
    monkeypatch.setattr('membrane_control.balance_diagnostics.BalanceDiagnosticsDialog', Dialog)
    window._open_balance_diagnostics()
    assert closed and controller.balance is None
    assert called[0]['selected_port'] == 'COM6'
    assert called[0]['selected_baud'] == 9600 and called[0]['selected_format'] == '7E1'
    assert called[0]['excluded_ports'] == {'FAKE-VALVES'}
    assert called[-1] == 'closed' and window._balance_diagnostics_dialog is None
    assert controller.snapshot['mass_g'] is None and not controller.snapshot['balance_connected']

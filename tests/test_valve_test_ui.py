"""Valve commissioning window, using fake transports only."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea

from membrane_control.valve_test import ValveTestDialog
from membrane_control.ui import STYLE
from membrane_control.zoom import NativeZoom
from test_valve_test import FakeTransport, ack, arm, connect_verified, identity, status


@pytest.fixture(scope='module')
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(qt_app):
    now = [100.0]
    transport = FakeTransport()
    widget = ValveTestDialog(selected_port='FAKE-ONLY',
        port_lister=lambda: [('FAKE-ONLY', 'Test double')],
        transport_factory=lambda *_args: transport, clock=lambda: now[0])
    widget.timer.stop()
    yield widget, transport, now
    widget.close()


def test_opens_disconnected_with_clear_sensorless_notice_and_seven_named_commands(dialog):
    widget, transport, _ = dialog
    assert widget.session.transport is None and not transport.sent
    assert [button.text() for button in widget.pulse_buttons] == [f'V{i}: Energize 500 ms' for i in range(1, 8)]
    assert not widget.arm_button.isEnabled()
    assert all(not button.isEnabled() for button in widget.pulse_buttons)
    labels = ' '.join(label.text() for label in widget.findChildren(QLabel))
    assert 'Pressure, flow and scale readings are unavailable' in labels
    assert 'pump must be physically isolated' in labels
    assert "Dr. Onita Basu's lab" in labels
    assert all(not checkbox.isChecked() for checkbox in widget.attestation_checkboxes.values())


def test_locked_profile_explains_mapping_review_without_offer_to_bypass(dialog):
    widget, transport, _ = dialog
    connect_verified(widget.session, transport, locked=True)
    widget._render()
    assert 'LOCKED' in widget.profile_label.text()
    assert 'bare-board mapping' in widget.status_label.text()
    assert 'not approved' in widget.mapping_label.text()
    assert 'https://github.com/regular030/membrane-control/blob/main/docs/valve-test.md' in widget.setup_guide.text()
    assert widget.setup_guide.openExternalLinks()
    assert widget.stop_button.isEnabled()
    assert all(not checkbox.isEnabled() for checkbox in widget.attestation_checkboxes.values())
    assert all(not button.isEnabled() for button in widget.pulse_buttons)


def test_explicit_connect_checks_and_arm_before_one_valve_pulse(dialog):
    widget, transport, _ = dialog
    widget.connect_button.click()
    transport.events.append(identity(transport.last('hello')['id']))
    widget._tick()
    transport.events.extend([ack(transport.last('heartbeat')['id']), status()])
    widget._tick()
    for checkbox in widget.attestation_checkboxes.values():
        checkbox.click()
    assert widget.arm_button.isEnabled()
    widget.arm_button.click()
    assert not any(button.isEnabled() for button in widget.pulse_buttons)
    transport.events.extend([ack(transport.last('valve_arm')['id']), status(state='ready')])
    widget._tick()
    assert all(button.isEnabled() for button in widget.pulse_buttons)
    widget.pulse_buttons[4].click()
    widget.pulse_buttons[0].click()
    assert transport.last('valve_pulse')['valve'] == 5
    assert len([packet for packet in transport.sent if packet['cmd'] == 'valve_pulse']) == 1
    assert not any(button.isEnabled() for button in widget.pulse_buttons)
    assert 'not monitored' in widget.output_label.text()


@pytest.mark.parametrize('ending', ['stop', 'close', 'reject', 'accept', 'done', 'quit'])
def test_every_close_path_releases_port_and_withdraws_heartbeats(dialog, ending):
    widget, transport, now = dialog
    connect_verified(widget.session, transport)
    arm(widget.session, transport)
    widget._render()
    if ending == 'stop':
        widget.stop_button.click()
    elif ending == 'quit':
        widget._quit_application.aboutToQuit.emit()
    elif ending == 'done':
        widget.done(0)
    else:
        getattr(widget, ending)()
    assert transport.closed and transport.close_count == 1
    assert widget.session.transport is None and not widget.session.armed
    assert all(not checkbox.isChecked() for checkbox in widget.attestation_checkboxes.values())
    if ending != 'stop':
        assert not widget.timer.isActive()
    count = len(transport.sent)
    now[0] += 10
    widget._tick()
    assert len(transport.sent) == count


def test_withdrawing_a_checked_attestation_stops_an_armed_session(dialog):
    widget, transport, _ = dialog
    connect_verified(widget.session, transport)
    arm(widget.session, transport)
    widget._render()
    widget.attestation_checkboxes['pump_isolated'].click()
    assert transport.closed and not widget.session.armed
    assert not any(button.isEnabled() for button in widget.pulse_buttons)


def test_connected_scale_port_is_excluded_and_refresh_preserves_selection(qt_app):
    widget = ValveTestDialog(selected_port='FAKE-ONLY', excluded_ports={'FAKE-SCALE'},
        port_lister=lambda: [('FAKE-SCALE', 'Scale'), ('FAKE-ONLY', 'Board')],
        transport_factory=lambda *_args: pytest.fail('No user connect requested'))
    widget.timer.stop()
    assert widget.port_combo.findData('FAKE-SCALE') == -1
    widget.refresh_ports()
    assert widget.port_combo.currentData() == 'FAKE-ONLY'
    widget.close()


def test_compact_dialog_scrolls_content_while_stop_remains_visible(dialog, qt_app):
    widget, _, _ = dialog
    widget.resize(700, 650)
    widget.show()
    qt_app.processEvents()
    assert widget.stop_button.height() >= 46
    assert widget.stop_button.isVisible()
    scroll = widget.findChild(QScrollArea)
    assert scroll.widgetResizable()
    assert scroll.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert all(button.height() >= 40 for button in widget.pulse_buttons)


def test_larger_text_keeps_stop_visible_and_pulse_controls_unclipped(dialog, qt_app):
    widget, _, _ = dialog
    widget.setStyleSheet(STYLE)
    widget.resize(700, 650)
    zoom = NativeZoom(widget)
    zoom.set_percent(150)
    widget.show()
    qt_app.processEvents()
    assert widget.stop_button.isVisible()
    assert widget.stop_button.height() >= widget.stop_button.sizeHint().height()
    assert all(button.height() >= button.sizeHint().height() for button in widget.pulse_buttons)

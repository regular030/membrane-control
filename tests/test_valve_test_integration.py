"""Main-window ownership and gates for valve testing; every port is a double."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from membrane_control.controller import AppController
from membrane_control.relay_bench import RelayBenchDialog
from membrane_control.ui import MainWindow
from membrane_control.valve_test import ValveTestDialog


class Wire:
    def __init__(self, port, *, fail_close=False):
        self.port = port
        self.closed = False
        self.close_count = 0
        self.sent = []
        self.fail_close = fail_close

    def send(self, packet):
        assert not self.closed
        self.sent.append(dict(packet))

    def poll(self, _now=None):
        return []

    def close(self):
        self.closed = True
        self.close_count += 1
        if self.fail_close:
            raise RuntimeError('Fake port close failure: ' + self.port)


@pytest.fixture(scope='module')
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def screen(qt_app, tmp_path, monkeypatch):
    def no_real_port(*_args, **_kwargs):
        pytest.fail('An integration test must never open a real serial port')

    for module in ('controller', 'relay_bench', 'valve_test'):
        monkeypatch.setattr(f'membrane_control.{module}.SerialTransport', no_real_port)
    controller = AppController(tmp_path)
    controller.list_ports = lambda: [('FAKE-CONTROLLER', 'Controller double'),
                                      ('FAKE-SCALE', 'Scale double')]
    window = MainWindow(controller)
    window.timer.stop()
    yield window, controller
    window.shutdown()
    window.close()


def hardware_mode(window, controller):
    controller.set_simulation(False)
    window._update_view(dict(controller.snapshot))


def connected_dialog(kind, parent, wire):
    dialog = kind(parent, selected_port=wire.port,
        port_lister=lambda: [(wire.port, 'Device double')],
        transport_factory=lambda *_args: wire)
    dialog.connect_board()
    assert dialog.session.transport is wire
    return dialog


def test_valve_entry_is_discoverable_but_cannot_open_in_simulation(screen, monkeypatch):
    window, controller = screen
    monkeypatch.setattr('membrane_control.ui.ValveTestDialog',
                        lambda *_args, **_kwargs: pytest.fail('Simulation must not open the tool'))
    window.tabs.setCurrentIndex(window.connections_tab_index)
    buttons = [button for button in window.findChildren(QPushButton)
               if 'Legacy valve pulse test' in button.text()]
    assert buttons == [window.valve_test_button]
    assert not window.valve_test_button.isEnabled()
    driver = controller.driver
    window.valve_test_button.click()
    window._open_valve_test()  # The programmatic entry must enforce the same gate.
    assert controller.simulation and controller.driver is driver
    assert window._valve_test_dialog is None
    assert 'Simulation mode off' in window.statusBar().currentMessage()


@pytest.mark.parametrize('operation', ['running', 'manual', 'starting', 'manual_pending', 'stopping'])
def test_active_operation_cannot_transfer_controller_ownership(screen, monkeypatch, operation):
    window, controller = screen
    hardware_mode(window, controller)
    wire = Wire('FAKE-CONTROLLER')
    controller.driver = wire
    if operation in ('running', 'manual'):
        controller.snapshot['state'] = operation
    elif operation == 'starting':
        controller.start_phase = 'loading'
        controller.snapshot['start_pending'] = True
    elif operation == 'manual_pending':
        controller.manual_pending = True
        controller.snapshot['manual_pending'] = True
    else:
        controller.stop_pending = True
        controller.snapshot['stop_pending'] = True
    window._update_view(dict(controller.snapshot))
    monkeypatch.setattr('membrane_control.ui.ValveTestDialog',
                        lambda *_args, **_kwargs: pytest.fail('Active operation must block the tool'))
    assert not window.valve_test_button.isEnabled()
    window._open_valve_test()
    assert controller.driver is wire and not wire.closed and wire.sent == []
    assert window._valve_test_dialog is None
    assert 'Stop the current operation' in window.statusBar().currentMessage()


def test_open_releases_normal_controller_and_excludes_the_connected_scale(screen, monkeypatch):
    window, controller = screen
    hardware_mode(window, controller)
    previous, scale = Wire('FAKE-CONTROLLER'), Wire('FAKE-SCALE')
    controller.driver, controller.balance = previous, scale
    captures = []

    class OwnedModal(ValveTestDialog):
        def __init__(self, parent, **kwargs):
            assert controller.driver is None and previous.closed
            self.wire = Wire('FAKE-CONTROLLER')
            super().__init__(parent, transport_factory=lambda *_args: self.wire, **kwargs)
            captures.append(self)

        def exec(self):
            assert self.port_combo.currentData() == 'FAKE-CONTROLLER'
            assert self.port_combo.findData('FAKE-SCALE') == -1
            assert self.excluded_ports == {'FAKE-SCALE'}
            assert controller.balance is scale and not scale.closed
            assert self.session.transport is None  # Opening never auto-connects or energizes.
            self.connect_board()
            assert [packet['cmd'] for packet in self.wire.sent] == ['hello']
            return 0

    monkeypatch.setattr('membrane_control.ui.ValveTestDialog', OwnedModal)
    window.valve_test_button.click()
    dialog = captures[0]
    assert previous.close_count == 1 and previous.sent[-1]['cmd'] == 'stop'
    assert dialog.wire.closed and dialog.wire.close_count == 1
    assert not dialog.timer.isActive() and window._valve_test_dialog is None
    assert controller.driver is None and controller.balance is scale and not scale.closed
    assert not controller.snapshot['hardware_verified'] and controller.simulation is False
    assert {packet['cmd'] for packet in dialog.wire.sent} <= {'hello', 'stop'}


def test_selected_balance_port_is_rejected_before_normal_controller_disconnect(screen, monkeypatch):
    window, controller = screen
    hardware_mode(window, controller)
    previous, scale = Wire('FAKE-CONTROLLER'), Wire('FAKE-SCALE')
    controller.driver, controller.balance = previous, scale
    window.controller_port.setCurrentIndex(window.controller_port.findData(scale.port))
    monkeypatch.setattr('membrane_control.ui.ValveTestDialog',
                        lambda *_args, **_kwargs: pytest.fail('The balance port must be excluded'))
    window._open_valve_test()
    assert controller.driver is previous and not previous.closed and not scale.closed
    assert window._valve_test_dialog is None
    assert "not the connected scale's port" in window.statusBar().currentMessage()


def test_failed_controller_release_does_not_open_a_second_owner(screen, monkeypatch):
    window, controller = screen
    hardware_mode(window, controller)
    previous = Wire('FAKE-CONTROLLER', fail_close=True)
    controller.driver = previous
    monkeypatch.setattr('membrane_control.ui.ValveTestDialog',
                        lambda *_args, **_kwargs: pytest.fail('A failed release must abort opening'))
    window._open_valve_test()
    assert previous.closed and previous.close_count == 1
    assert controller.driver is None and window._valve_test_dialog is None
    assert 'Could not release the controller port' in window.statusBar().currentMessage()
    assert 'Fake port close failure' in window.statusBar().currentMessage()


@pytest.mark.parametrize('raises', [False, True])
def test_modal_exec_unwind_closes_port_without_relying_on_close_event(screen, monkeypatch, raises):
    window, controller = screen
    hardware_mode(window, controller)
    captures = []

    class UnwindingModal(ValveTestDialog):
        def __init__(self, parent, **kwargs):
            self.wire = Wire('FAKE-CONTROLLER')
            super().__init__(parent, transport_factory=lambda *_args: self.wire, **kwargs)
            self.connect_board()
            captures.append(self)

        def exec(self):
            assert self.timer.isActive() and not self.wire.closed
            if raises:
                raise RuntimeError('Fake modal event-loop failure')
            return 0

    monkeypatch.setattr('membrane_control.ui.ValveTestDialog', UnwindingModal)
    if raises:
        with pytest.raises(RuntimeError, match='modal event-loop failure'):
            window._open_valve_test()
    else:
        window._open_valve_test()
    dialog = captures[0]
    assert dialog.wire.closed and dialog.wire.close_count == 1
    assert dialog.session.transport is None and not dialog.timer.isActive()
    assert window._valve_test_dialog is None
    count = len(dialog.wire.sent)
    dialog._tick()
    dialog.connect_board()
    assert len(dialog.wire.sent) == count


@pytest.mark.parametrize(('existing', 'requested'), [('relay', 'valve'), ('valve', 'valve'), ('valve', 'relay')])
def test_equipment_tools_are_mutually_exclusive(screen, monkeypatch, existing, requested):
    window, controller = screen
    hardware_mode(window, controller)
    wire = Wire('FAKE-CONTROLLER')
    kind = RelayBenchDialog if existing == 'relay' else ValveTestDialog
    dialog = connected_dialog(kind, window, wire)
    attribute = '_relay_bench_dialog' if existing == 'relay' else '_valve_test_dialog'
    setattr(window, attribute, dialog)
    monkeypatch.setattr('membrane_control.ui.ValveTestDialog',
                        lambda *_args, **_kwargs: pytest.fail('An equipment test is already open'))
    monkeypatch.setattr('membrane_control.ui.RelayBenchDialog',
                        lambda *_args, **_kwargs: pytest.fail('An equipment test is already open'))
    action = window._open_valve_test if requested == 'valve' else window._open_relay_bench
    action()
    assert getattr(window, attribute) is dialog and not wire.closed
    assert 'Close' in window.statusBar().currentMessage()


@pytest.mark.parametrize('failure', [None, 'relay_wire', 'valve_wire', 'relay_dialog', 'valve_dialog'])
def test_window_shutdown_releases_both_tools_controller_and_scale_even_after_close_failure(
        screen, monkeypatch, failure):
    window, controller = screen
    hardware_mode(window, controller)
    normal, scale = Wire('FAKE-CONTROLLER'), Wire('FAKE-SCALE')
    relay_wire = Wire('FAKE-RELAY', fail_close=failure == 'relay_wire')
    valve_wire = Wire('FAKE-VALVE', fail_close=failure == 'valve_wire')
    controller.driver, controller.balance = normal, scale
    relay = connected_dialog(RelayBenchDialog, window, relay_wire)
    valve = connected_dialog(ValveTestDialog, window, valve_wire)
    window._relay_bench_dialog, window._valve_test_dialog = relay, valve
    # Both references are deliberate fault injection. Normal UI entry forbids this.
    if failure in ('relay_dialog', 'valve_dialog'):
        failing_dialog = relay if failure == 'relay_dialog' else valve
        original = failing_dialog.shutdown

        def close_then_raise():
            original()
            raise RuntimeError('Fake Qt teardown error')

        # Keep the fake teardown hook consistent with Qt's registered quit slot.
        # Merely replacing the method would leave a different bound slot connected.
        application = failing_dialog._quit_application
        application.aboutToQuit.disconnect(original)
        monkeypatch.setattr(failing_dialog, 'shutdown', close_then_raise)
        application.aboutToQuit.connect(failing_dialog.shutdown)
    window.shutdown()
    wires = (normal, scale, relay_wire, valve_wire)
    assert all(wire.closed and wire.close_count == 1 for wire in wires)
    assert controller.closed and controller.driver is None and controller.balance is None
    assert window._relay_bench_dialog is None and window._valve_test_dialog is None
    assert relay.session.transport is None and valve.session.transport is None
    assert not window.timer.isActive() and not relay.timer.isActive() and not valve.timer.isActive()
    if failure == 'valve_wire':
        assert 'Fake port close failure' in valve.session.error
    if failure == 'relay_wire':
        assert 'Fake port close failure' in relay.session.error
    window.shutdown()
    assert all(wire.close_count == 1 for wire in wires)


def test_a_closed_window_cannot_reopen_the_valve_port(screen, monkeypatch):
    window, controller = screen
    hardware_mode(window, controller)
    window.shutdown()
    monkeypatch.setattr('membrane_control.ui.ValveTestDialog',
                        lambda *_args, **_kwargs: pytest.fail('Shutdown must block a new tool'))
    window._open_valve_test()
    assert controller.closed and window._valve_test_dialog is None

"""Port-list discovery updates never connect to a device or invent a scale port."""
import os
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from membrane_control.controller import AppController
from membrane_control.ui import MainWindow


@pytest.fixture(scope='module')
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def ports_screen(qt_app, tmp_path, monkeypatch):
    ports = [('COM4', 'ESP32 CP2102')]
    enumerations = []

    def comports():
        enumerations.append(True)
        return [SimpleNamespace(device=device, description=description,
                                hwid=hardware_id[0] if hardware_id else 'n/a')
                for device, description, *hardware_id in ports]

    monkeypatch.setattr('serial.tools.list_ports.comports', comports)
    monkeypatch.setattr('membrane_control.controller.SerialTransport',
                        lambda *_args, **_kwargs: pytest.fail('Refreshing ports must not open a device'))
    controller = AppController(tmp_path)
    window = MainWindow(controller)
    window.timer.stop()
    yield window, controller, ports, enumerations
    window.close()


def items(combo):
    return [combo.itemData(index) for index in range(combo.count())]


def test_newly_plugged_scale_port_appears_when_connections_tab_opens(ports_screen):
    window, controller, ports, enumerations = ports_screen
    assert items(window.controller_port) == items(window.balance_port) == [None, 'COM4']
    ports.append(('COM11', 'USB Serial Port'))
    before = len(enumerations)
    window.tabs.setCurrentIndex(window.connections_tab_index)
    assert len(enumerations) == before + 1
    assert items(window.controller_port) == items(window.balance_port) == [None, 'COM4', 'COM11']
    assert window.controller_port.currentData() is None
    assert window.balance_port.currentData() is None
    assert controller.balance is None
    assert 'USB Serial Port' in window.balance_port_hint.text()
    assert 'own COM port' in window.balance_port_hint.text()
    assert window.balance_port_hint.wordWrap()


def test_refresh_preserves_selected_controller_and_scale_when_list_order_changes(ports_screen):
    window, controller, ports, _ = ports_screen
    ports.append(('COM11', 'Scale adapter'))
    window._refresh_ports()
    window.controller_port.setCurrentIndex(window.controller_port.findData('COM4'))
    window.balance_port.setCurrentIndex(window.balance_port.findData('COM11'))
    ports[:] = [('COM11', 'Updated adapter description'), ('COM12', 'Other USB device'),
                ('COM4', 'Silicon Labs CP210x')]
    driver_before = controller.driver
    window.tabs.setCurrentIndex(window.connections_tab_index)
    assert window.controller_port.currentData() == 'COM4'
    assert window.balance_port.currentData() == 'COM11'
    assert controller.driver is driver_before and controller.balance is None


def test_missing_windows_scale_port_remains_missing(ports_screen):
    window, controller, ports, _ = ports_screen
    window.tabs.setCurrentIndex(window.connections_tab_index)
    assert items(window.balance_port) == [None, 'COM4']
    assert window.balance_port.currentData() is None
    assert controller.balance is None and not controller.snapshot['balance_connected']
    ports.clear()
    window.tabs.setCurrentIndex(0)
    window.tabs.setCurrentIndex(window.connections_tab_index)
    assert items(window.balance_port) == items(window.controller_port) == [None]
    assert window.balance_port.itemText(0) == 'No serial ports found'
    assert controller.balance is None


def test_refresh_is_only_on_tab_entry_or_explicit_button_not_a_timer(ports_screen, qt_app):
    window, _, _, enumerations = ports_screen
    before = len(enumerations)
    qt_app.processEvents()
    assert len(enumerations) == before
    window.tabs.setCurrentIndex(window.connections_tab_index)
    assert len(enumerations) == before + 1
    window.tabs.setCurrentIndex(window.connections_tab_index)
    qt_app.processEvents()
    assert len(enumerations) == before + 1
    window.tabs.setCurrentIndex(1)
    window.tabs.setCurrentIndex(window.connections_tab_index)
    assert len(enumerations) == before + 2


def test_startup_connects_the_detected_controller_but_keeps_scale_closed(ports_screen, monkeypatch):
    window, controller, ports, _ = ports_screen
    calls = []
    monkeypatch.setattr(controller, 'connect_controller', lambda port: calls.append(('ESP32', port)))
    monkeypatch.setattr(controller, 'connect_balance',
                        lambda port, baud, **options: calls.append(('scale', port, baud, options)))
    ports.extend([('COM6', 'Scale adapter'), ('COM9', 'ESP32 Bluetooth')])
    window._refresh_ports()
    window.connect_lab_defaults()
    assert calls == []  # Demo never opens hardware ports.

    controller.set_simulation(False)
    window.connect_lab_defaults()
    assert calls == [('ESP32', 'COM9')]
    assert window.balance_port.currentData() == 'COM6'
    assert controller.balance is None

    calls.clear()
    ports.remove(('COM6', 'Scale adapter'))
    window._refresh_ports()
    window.connect_lab_defaults()
    assert calls == [('ESP32', 'COM9')]


@pytest.mark.parametrize('port_open', [False, True])
def test_balance_can_disconnect_without_a_weight_reading(ports_screen, monkeypatch, port_open):
    window, controller, ports, _ = ports_screen
    controller.set_simulation(False)
    ports.append(('COM6', 'Scale adapter'))
    window._refresh_ports()
    window._update_view(dict(controller.snapshot))
    closed = []
    events = [{'type': 'port_open'}] if port_open else []
    transport = SimpleNamespace(
        poll=lambda now: events,
        close=lambda: closed.append(True),
    )
    monkeypatch.setattr('membrane_control.controller.SerialTransport',
                        lambda *args, **options: transport)

    window.balance_connect.click()
    controller.tick()
    window._update_view(dict(controller.snapshot))
    assert controller.balance is transport
    assert controller.balance_port_open is port_open
    assert not controller.snapshot['balance_connected']
    assert not window.balance_connect.isEnabled()
    assert window.balance_disconnect.isEnabled()

    window.balance_disconnect.click()
    controller.tick()
    window._update_view(dict(controller.snapshot))
    assert closed == [True]
    assert controller.balance is None
    assert window.balance_connect.isEnabled()
    assert not window.balance_disconnect.isEnabled()


@pytest.mark.parametrize('peer', ['8C94DF4F8AEA', '8C94DF50204E'])
def test_startup_follows_outgoing_membrane_controller_after_windows_renumbers_ports(
        ports_screen, monkeypatch, peer):
    window, controller, ports, _ = ports_screen
    calls = []
    monkeypatch.setattr(controller, 'connect_controller', calls.append)
    controller.set_simulation(False)
    outgoing = (r'BTHENUM\{00001101-0000-1000-8000-00805f9b34fb}_LOCALMFG&0002'
                rf'\7&33c6b4b6&0&{peer}_C00000000')
    incoming = (r'BTHENUM\{00001101-0000-1000-8000-00805f9b34fb}_LOCALMFG&0000'
                r'\7&33c6b4b6&0&000000000000_0000000A')
    ports.append(('COM8', 'Standard Serial over Bluetooth link', outgoing))
    window._refresh_ports()
    assert window.controller_port.currentData() == 'COM8'

    ports[-1:] = [('COM7', 'Standard Serial over Bluetooth link', outgoing),
                  ('COM8', 'Standard Serial over Bluetooth link', incoming)]
    window._refresh_ports()
    assert window.controller_port.currentData() == 'COM7'
    window.connect_lab_defaults()
    assert calls == ['COM7']


def test_new_full_rig_board_is_preferred_over_cached_old_controller(ports_screen, monkeypatch):
    window, controller, ports, _ = ports_screen
    calls = []
    monkeypatch.setattr(controller, 'connect_controller', calls.append)
    controller.set_simulation(False)
    prefix = (r'BTHENUM\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0002'
              r'\7&33c6b4b6&0&')
    ports.extend([('COM9', 'MembraneControl-Bench', prefix + '8C94DF50204E_C00000000'),
                  ('COM10', 'Renamed full rig', prefix + '8C94DF4F8AEA_C00000000')])
    window._refresh_ports()
    assert controller.preferred_controller_port == 'COM10'
    assert window.controller_port.currentData() == 'COM10'
    window.connect_lab_defaults()
    assert calls == ['COM10']


def test_ambiguous_new_controller_ports_do_not_fall_back_to_old_board(ports_screen, monkeypatch):
    window, controller, ports, _ = ports_screen
    calls = []
    monkeypatch.setattr(controller, 'connect_controller', calls.append)
    controller.set_simulation(False)
    prefix = (r'BTHENUM\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0002'
              r'\7&33c6b4b6&0&')
    ports.extend([('COM9', 'Old controller', prefix + '8C94DF50204E_C00000000'),
                  ('COM10', 'New controller', prefix + '8C94DF4F8AEA_C00000000'),
                  ('COM11', 'Duplicate outgoing port', prefix + '8C94DF4F8AEA_C00000000')])
    window._refresh_ports()
    assert controller.preferred_controller_port is None
    window.connect_lab_defaults()
    assert calls == []


@pytest.mark.parametrize('peer', ['000000000000', 'AABBCCDDEEFF'])
def test_startup_does_not_open_unmatched_bluetooth_com8(ports_screen, monkeypatch, peer):
    window, controller, ports, _ = ports_screen
    calls = []
    monkeypatch.setattr(controller, 'connect_controller', calls.append)
    controller.set_simulation(False)
    ports.append(('COM8', 'Standard Serial over Bluetooth link',
                  r'BTHENUM\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0002'
                  rf'\7&33c6b4b6&0&{peer}_C00000000'))
    window._refresh_ports()
    assert window.controller_port.currentData() is None
    window.connect_lab_defaults()
    assert calls == []
    assert 'COM8' in items(window.controller_port)

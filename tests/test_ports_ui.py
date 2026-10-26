"""Port-list discovery updates never connect to a device or invent a scale port."""
import os

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

    def list_ports():
        enumerations.append(True)
        return list(ports)

    monkeypatch.setattr('membrane_control.controller.SerialTransport',
                        lambda *_args, **_kwargs: pytest.fail('Refreshing ports must not open a device'))
    controller = AppController(tmp_path)
    controller.list_ports = list_ports
    window = MainWindow(controller)
    window.timer.stop()
    yield window, controller, ports, enumerations
    window.close()


def items(combo):
    return [combo.itemData(index) for index in range(combo.count())]


def test_newly_plugged_scale_port_appears_when_connections_tab_opens(ports_screen):
    window, controller, ports, enumerations = ports_screen
    assert items(window.controller_port) == items(window.balance_port) == ['COM4']
    ports.append(('COM11', 'USB Serial Port'))
    before = len(enumerations)
    window.tabs.setCurrentIndex(window.connections_tab_index)
    assert len(enumerations) == before + 1
    assert items(window.controller_port) == items(window.balance_port) == ['COM4', 'COM11']
    assert window.controller_port.currentData() == 'COM4'
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
    assert items(window.balance_port) == ['COM4']
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

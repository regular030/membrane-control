"""The USB voltage test only commands the converter after explicit confirmation."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from membrane_control.pump_voltage_test import PumpVoltageTestWindow


class FakePort:
    def __init__(self):
        self.reply = b""
        self.writes = []
        self.closed = False

    def read(self, size):
        data, self.reply = self.reply[:size], self.reply[size:]
        return data

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def close(self):
        self.closed = True


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def screen(qt_app):
    port = FakePort()
    now = [0.0]
    window = PumpVoltageTestWindow("COM5", open_port=lambda _: port, clock=lambda: now[0])
    window.timer.stop()
    yield window, port, now
    window.close()


def test_requires_open_run_and_fresh_zero_then_displays_command_and_feedback(screen):
    window, port, _ = screen
    port.reply = b"PUMP_TEST 0 0 "
    window._poll()
    assert port.writes == [b"PING\n"]
    assert not window.test.isEnabled()
    port.reply = b"78\r\n"
    window._poll()
    assert not window.test.isEnabled()
    assert "Outside the ADC range" in window.feedback.text()
    window.interlock.setChecked(True)
    assert window.test.isEnabled()
    window.test.click()
    window.test.click()
    assert port.writes.count(b"TEST50\n") == 1
    assert not window.test.isEnabled()

    port.reply = b"PUMP_TEST 50 29950 1000\n"
    window._poll()
    assert "50%" in window.command.text()
    assert "5.00 V" in window.feedback.text()
    window.stop.click()
    assert port.writes[-1] == b"STOP\n"
    port.reply = b"PUMP_TEST 0 0 78\n"
    window._poll()
    assert window.test.isEnabled()


def test_unacknowledged_start_disarms_without_resending_test(screen):
    window, port, now = screen
    window.interlock.setChecked(True)
    port.reply = b"PUMP_TEST 0 0 78\n"
    window._poll()
    window.test.click()
    now[0] = 1.5
    port.reply = b"PUMP_TEST 0 0 78\n"
    window._poll()
    assert not window.test.isEnabled()
    assert port.writes[-2:] == [b"TEST50\n", b"STOP\n"]
    assert port.closed


def test_stale_reading_shuts_down_port(screen):
    window, port, now = screen
    window.interlock.setChecked(True)
    port.reply = b"PUMP_TEST 0 0 78\n"
    window._poll()
    assert window.test.isEnabled()
    now[0] = 1.5
    window._poll()
    assert not window.test.isEnabled()
    assert not window.stop.isEnabled()
    assert port.writes[-1] == b"STOP\n"
    assert port.closed

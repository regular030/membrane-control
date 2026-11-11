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


@pytest.fixture
def bucket_screen(qt_app):
    port = FakePort()
    now = [0.0]
    window = PumpVoltageTestWindow("COM5", open_bucket=True, open_port=lambda _: port, clock=lambda: now[0])
    window.timer.stop()
    yield window, port, now
    window.close()


def reply(window, port, data):
    port.reply = data
    window._poll()


def stage_bucket(window, port, now):
    for box in window._confirmations:
        box.setChecked(True)
    reply(window, port, b"PUMP_BENCH 0 0 460 0 0\n")
    window.test.click()
    now[0] = 0.1
    reply(window, port, b"PUMP_BENCH 50 29900 460 0 0\n")


def test_requires_open_run_and_fresh_zero_then_displays_command_and_feedback(screen):
    window, port, _ = screen
    port.reply = b"PUMP_TEST 0 0 "
    window._poll()
    assert port.writes == [b"PING\n"]
    assert not window.test.isEnabled()
    assert not window.stop.isEnabled()
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


def test_reconnect_requires_new_feedback_and_confirmation(screen):
    window, port, now = screen
    window.interlock.setChecked(True)
    port.reply = b"PUMP_TEST 0 0 78\n"
    window._poll()
    now[0] = 1.5
    window._poll()

    reopened = FakePort()
    window._open_port = lambda _: reopened
    window.reconnect.click()
    window.timer.stop()
    assert not window.interlock.isChecked()
    assert not window.test.isEnabled()
    assert not reopened.writes

    reopened.reply = b"PUMP_TEST 0 0 78\n"
    window._poll()
    assert reopened.writes == [b"PING\n"]
    assert not window.test.isEnabled()


def test_open_bucket_requires_all_checks_new_stage_and_explicit_run(bucket_screen):
    window, port, now = bucket_screen
    for box in window._confirmations[:-1]:
        box.setChecked(True)
    reply(window, port, b"PUMP_BENCH 0 0 460 0 0\n")
    assert not window.test.isEnabled()
    assert not window.run.isEnabled()
    assert not window.voltage_confirmed.isEnabled()
    assert port.writes == [b"PING\n"]

    stage_bucket(window, port, now)
    assert port.writes.count(b"TEST50\n") == 1
    assert not window.voltage_confirmed.isEnabled()
    assert "GPIO34 / IO34 460 mV" in window.feedback.text()
    assert "2.30 V" in window.feedback.text()
    now[0] = 1.65
    reply(window, port, b"PUMP_BENCH 50 28350 460 0 0\n")
    assert window.voltage_confirmed.isEnabled()
    assert not window.run.isEnabled()
    window.voltage_confirmed.click()
    assert window.run.isEnabled()
    assert b"RUN50\n" not in port.writes
    window.run.click()
    window.run.click()
    assert port.writes.count(b"RUN50\n") == 1
    reply(window, port, b"PUMP_BENCH 50 28000 460 1 9900\n")
    assert "closed" in window.motor.text()
    assert "9.9 seconds" in window.motor.text()
    assert window.stop.isEnabled()

    reply(window, port, b"PUMP_BENCH 0 0 460 0 0\n")
    assert "open" in window.motor.text()
    assert window.test.isEnabled()
    assert not window.voltage_confirmed.isChecked()
    assert not window.run.isEnabled()


def test_open_bucket_ignores_voltage_only_status_and_rejects_late_run(bucket_screen):
    window, port, now = bucket_screen
    for box in window._confirmations:
        box.setChecked(True)
    reply(window, port, b"PUMP_TEST 0 0 460\n")
    assert not window.test.isEnabled()
    stage_bucket(window, port, now)
    now[0] = 21.0
    reply(window, port, b"PUMP_BENCH 50 9000 460 0 0\n")
    assert not window.voltage_confirmed.isEnabled()
    window.voltage_confirmed.setChecked(True)
    window._run_test()
    assert b"RUN50\n" not in port.writes


def test_open_bucket_rejects_unrequested_run_and_clears_confirmations_on_reconnect(bucket_screen):
    window, port, now = bucket_screen
    stage_bucket(window, port, now)
    reply(window, port, b"PUMP_BENCH 50 28000 460 1 9900\n")
    assert b"RUN50\n" not in port.writes
    assert b"STOP\n" in port.writes
    reply(window, port, b"PUMP_BENCH_FAULT\n")
    assert port.closed
    assert "fault" in window.connection.text()
    reopened = FakePort()
    window._open_port = lambda _: reopened
    window.reconnect.click()
    window.timer.stop()
    assert not any(box.isChecked() for box in window._confirmations)
    assert not window.voltage_confirmed.isChecked()
    assert not window.run.isEnabled()


def test_open_bucket_withdrawn_check_stops_run(bucket_screen):
    window, port, now = bucket_screen
    stage_bucket(window, port, now)
    now[0] = 1.65
    reply(window, port, b"PUMP_BENCH 50 28350 460 0 0\n")
    window.voltage_confirmed.click()
    window.run.click()
    reply(window, port, b"PUMP_BENCH 50 28000 460 1 9900\n")
    window._confirmations[0].setChecked(False)
    assert port.writes[-1] == b"STOP\n"
    assert not window.voltage_confirmed.isChecked()
    assert not window.run.isEnabled()

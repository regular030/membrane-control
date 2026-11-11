"""Operator UI for the USB pump voltage commissioning image."""
import re
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


STATUS = re.compile(rb"PUMP_TEST (0|50) ([0-9]{1,5}) ([0-9]{1,4})")
REPLY_TIMEOUT_S = 1.25
WAITING_TEXT = "Waiting for the pump-test firmware. If you just flashed it, release BOOT and press EN once."


def _open_port(name):
    import serial

    port = serial.Serial(baudrate=115200, timeout=0, write_timeout=0.2)
    port.port = name
    port.dtr = False
    port.rts = False
    port.open()
    return port


class PumpVoltageTestWindow(QWidget):
    def __init__(self, port_name, *, open_port=_open_port, clock=time.monotonic):
        super().__init__()
        self._port_name = port_name
        self._open_port = open_port
        self._clock = clock
        self._port = None
        self._buffer = b""
        self._status = None
        self._last_reply = None
        self._pending = None
        self._pending_since = None
        self.setWindowTitle("Membrane Control — Pump voltage test")
        self.resize(540, 300)

        layout = QVBoxLayout(self)
        heading = QLabel(f"<b>Pump voltage test · {port_name}</b>")
        layout.addWidget(heading)
        instructions = QLabel(
            "Set the drive to Voltage Input and Continuous Pump Mode. Set START/STOP required to ON "
            "and keep the 15/17 RUN contact open so the motor remains stopped."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.interlock = QCheckBox("START/STOP required is ON and the RUN contact is open")
        self.interlock.toggled.connect(self._interlock_changed)
        layout.addWidget(self.interlock)

        self.connection = QLabel(WAITING_TEXT)
        self.connection.setWordWrap(True)
        self.command = QLabel("Converter command unavailable")
        self.feedback = QLabel("Drive feedback unavailable")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.connection)
        layout.addWidget(self.command)
        layout.addWidget(self.feedback)

        instructions = QLabel(
            "At 50%, measure DC voltage across pins 1 and 3. Watch the pump's own display "
            "and compare the app's feedback with a meter across pins 14 and 5. Zero feedback "
            "while stopped may be normal."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        buttons = QHBoxLayout()
        self.test = QPushButton("Set 50% for up to 30 seconds")
        self.test.clicked.connect(self._start_test)
        self.stop = QPushButton("Return to 0%")
        self.stop.clicked.connect(self._stop_test)
        buttons.addWidget(self.test)
        buttons.addWidget(self.stop)
        self.reconnect = QPushButton("Reconnect USB")
        self.reconnect.clicked.connect(self._connect)
        buttons.addWidget(self.reconnect)
        layout.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._poll)
        self._connect()

    def _connect(self):
        if self._port is not None:
            return
        self._buffer = b""
        self._status = self._last_reply = self._pending = self._pending_since = None
        self.interlock.setChecked(False)
        self.connection.setText(WAITING_TEXT)
        try:
            self._port = self._open_port(self._port_name)
        except (OSError, ValueError) as error:
            self.connection.setText(f"Could not open {self._port_name}. {error}")
        else:
            self.timer.start()
        self._update_buttons()

    def _write(self, command):
        if self._port.write(command) != len(command):
            raise OSError("USB write was incomplete")

    def _send(self, command, pending):
        if self._port is None:
            return
        try:
            self._write(command)
        except OSError as error:
            self._disconnect(f"USB command failed. {error}")
            return
        self._pending = pending
        self._pending_since = self._clock()
        self._update_buttons()

    def _start_test(self):
        if self._can_start():
            self._send(b"TEST50\n", 50)

    def _stop_test(self):
        self._send(b"STOP\n", 0)

    def _interlock_changed(self, checked):
        if not checked and (self._pending == 50 or self._status == 50):
            self._stop_test()
        self._update_buttons()

    def _can_start(self):
        return (self._port is not None and self.interlock.isChecked() and self._status == 0
                and self._pending is None and self._last_reply is not None
                and self._clock() - self._last_reply <= REPLY_TIMEOUT_S)

    def _update_buttons(self):
        self.test.setEnabled(self._can_start())
        self.stop.setEnabled(self._port is not None and (self._status == 50 or self._pending == 50))
        self.reconnect.setVisible(self._port is None)

    def _poll(self):
        if self._port is None:
            return
        try:
            self._buffer += self._port.read(4096)
            *lines, self._buffer = self._buffer.split(b"\n")
            if len(self._buffer) > 256:
                self._buffer = b""
            for line in lines:
                self._receive(line.rstrip(b"\r"))
                if self._port is None:
                    return
            now = self._clock()
            if self._pending_since is not None and now - self._pending_since > REPLY_TIMEOUT_S:
                self._disconnect("The firmware did not confirm the command. Reconnect USB to retry.")
                return
            if self._last_reply is not None and now - self._last_reply > REPLY_TIMEOUT_S:
                self._disconnect("Pump-test status timed out. Reconnect USB to retry.")
                return
            self._write(b"PING\n")
        except OSError as error:
            self._disconnect(f"The USB connection failed. {error}")

    def _receive(self, line):
        if line == b"PUMP_TEST_FAULT":
            self._disconnect("Pump-test firmware reported a fault. Check the controller, then reconnect USB.")
            return
        match = STATUS.fullmatch(line)
        if match is None:
            return
        percent, remaining_ms, pin_mv = map(int, match.groups())
        if pin_mv > 3300 or not (0 <= remaining_ms <= 30000) or (percent == 0) != (remaining_ms == 0):
            return
        self._last_reply = self._clock()
        self._status = percent
        if self._pending == percent:
            self._pending = None
            self._pending_since = None
        if percent == 50 and not self.interlock.isChecked():
            if self._pending != 0:
                self._stop_test()
            if self._port is None:
                return
        self.connection.setText("USB pump-test firmware connected.")
        countdown = f" · {remaining_ms / 1000:.1f} seconds left" if percent else ""
        self.command.setText(f"Converter command {percent}%{countdown}")
        if 150 <= pin_mv <= 2450:
            self.feedback.setText(f"GPIO39 {pin_mv} mV · DB25 14/5 estimate {pin_mv * 0.005:.2f} V (5:1 divider)")
        else:
            self.feedback.setText(f"GPIO39 {pin_mv} mV · Outside the ADC range for a DB25 14/5 estimate")
        self._update_buttons()

    def _disconnect(self, message):
        self.shutdown()
        self.connection.setText(message)
        self.command.setText("Converter command unavailable")
        self.feedback.setText("Drive feedback unavailable")

    def shutdown(self):
        self.timer.stop()
        if self._port is not None:
            try:
                self._write(b"STOP\n")
            except OSError:
                pass
            try:
                self._port.close()
            except OSError:
                pass
            self._port = None
        self._update_buttons()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

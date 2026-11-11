"""Operator UI for the USB pump voltage commissioning image."""
import re
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


STATUS = re.compile(rb"PUMP_TEST (0|50) ([0-9]{1,5}) ([0-9]{1,4})")
BENCH_STATUS = re.compile(rb"PUMP_BENCH (0|50) ([0-9]{1,5}) ([0-9]{1,4}) (0|1) ([0-9]{1,5})")
REPLY_TIMEOUT_S = 1.25
STOPPED = (0, False)
STAGED = (50, False)
RUNNING = (50, True)


def _open_port(name):
    import serial

    port = serial.Serial(baudrate=115200, timeout=0, write_timeout=0.2)
    port.port = name
    port.dtr = False
    port.rts = False
    port.open()
    return port


class PumpVoltageTestWindow(QWidget):
    def __init__(self, port_name, *, open_bucket=False, open_port=_open_port, clock=time.monotonic):
        super().__init__()
        self._port_name = port_name
        self._open_port = open_port
        self._open_bucket = open_bucket
        self._status_pattern = BENCH_STATUS if open_bucket else STATUS
        self._fault_message = b"PUMP_BENCH_FAULT" if open_bucket else b"PUMP_TEST_FAULT"
        self._feedback_pin = "GPIO34 / IO34" if open_bucket else "GPIO39"
        self._clock = clock
        self._port = None
        self._buffer = b""
        self._status = None
        self._last_reply = None
        self._pending = None
        self._pending_since = None
        self._stage_started = None
        self._stage_remaining_ms = 0
        self._stage_ping_sent = False
        self._stage_ping_received = False
        self._run_requested = False
        self._run_acknowledged = False
        self._stop_reason = None
        title = "Open-bucket pump test" if open_bucket else "Pump voltage test"
        self._waiting = f"Waiting for the {title.lower()} firmware. If you just flashed it, release BOOT and press EN once."
        self.setWindowTitle(f"Membrane Control — {title}")
        width, height = (670, 400) if open_bucket else (540, 300)
        self.resize(width, height)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>{title} · {port_name}</b>"))
        if open_bucket:
            layout.addWidget(QLabel("Confirm the setup before starting the test."))
            self._confirmations = [QCheckBox(text) for text in (
                "The pump head is primed and the inlet is supplied with water.",
                "The unrestricted discharge goes to an open bucket, isolated from rig valves.",
                "Drive is in Voltage Input and Continuous Mode with START/STOP required ON and Auto Start OFF.",
                "The RUN contact is open and the drive’s power switch is within reach.",
                "The 50% command was verified at about 5 V across DB25 1/3.",
            )]
        else:
            instructions = QLabel(
                "Set the drive to Voltage Input and Continuous Pump Mode. Set START/STOP required to ON "
                "and keep the 15/17 RUN contact open so the motor remains stopped."
            )
            instructions.setWordWrap(True)
            layout.addWidget(instructions)
            self.interlock = QCheckBox("START/STOP required is ON and the RUN contact is open")
            self._confirmations = [self.interlock]
        for box in self._confirmations:
            box.toggled.connect(self._interlock_changed)
            layout.addWidget(box)

        self.connection = QLabel(self._waiting)
        self.connection.setWordWrap(True)
        self.command = QLabel("Converter command unavailable")
        self.feedback = QLabel("Drive feedback unavailable")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.connection)
        layout.addWidget(self.command)
        layout.addWidget(self.feedback)

        if open_bucket:
            self.motor = QLabel("RUN contact command unavailable")
            layout.addWidget(self.motor)
            self.outcome = QLabel("No run requested.")
            self.outcome.setWordWrap(True)
            layout.addWidget(self.outcome)
            instructions = QLabel(
                "The test stages 50%, waits for the converter to settle, and commands RUN for up to 10 seconds. "
                "Watch the pump display and the returned voltage on DB25 14/5."
            )
        else:
            instructions = QLabel(
                "At 50%, measure DC voltage across pins 1 and 3. Watch the pump's own display "
                "and compare the app's feedback with a meter across pins 14 and 5. Zero feedback "
                "while stopped may be normal."
            )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        buttons = QHBoxLayout()
        self.test = QPushButton("Run pump at 50%" if open_bucket else "Set 50% for up to 30 seconds")
        self.test.clicked.connect(self._start_test)
        buttons.addWidget(self.test)
        self.stop = QPushButton("Stop pump and return to 0%" if open_bucket else "Return to 0%")
        self.stop.clicked.connect(self._stop_test)
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
        self._reset_stage()
        self._run_acknowledged = False
        self._stop_reason = None
        for box in self._confirmations:
            box.setChecked(False)
        self.connection.setText(self._waiting)
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
            return False
        self._pending = pending
        self._pending_since = self._clock()
        try:
            self._write(command)
        except OSError as error:
            self._disconnect(f"USB command failed. {error}")
            return False
        self._update_buttons()
        return True

    def _start_test(self):
        if self._can_start():
            self._reset_stage()
            if self._open_bucket:
                self._run_acknowledged = False
                self._stop_reason = None
                self.outcome.setText("Preparing 50% · waiting for firmware confirmation.")
            self._send(b"TEST50\n", STAGED)

    def _stop_test(self):
        self._cancel_test("Stopped by operator")

    def _cancel_test(self, reason):
        self._stop_reason = reason
        self._reset_stage()
        self._send(b"STOP\n", STOPPED)

    def _reset_stage(self):
        self._stage_started = None
        self._stage_ping_sent = False
        self._stage_ping_received = False
        self._run_requested = False

    def _interlock_changed(self, checked):
        if not checked and self._test_active() and self._pending != STOPPED:
            self._cancel_test("Setup confirmation withdrawn")
        self._update_buttons()

    def _test_active(self):
        return self._status in (STAGED, RUNNING) or self._pending in (STAGED, RUNNING)

    def _confirmed(self):
        return all(box.isChecked() for box in self._confirmations)

    def _fresh(self):
        return (self._port is not None and self._last_reply is not None
                and self._clock() - self._last_reply <= REPLY_TIMEOUT_S)

    def _can_start(self):
        return self._fresh() and self._status == STOPPED and self._pending is None and self._confirmed()

    def _advance_run(self):
        if (self._status != STAGED or self._stage_started is None or self._run_requested
                or self._pending is not None or not self._confirmed() or not self._fresh()):
            return
        now = self._clock()
        remaining_ms = self._stage_remaining_ms - (now - self._last_reply) * 1000
        if remaining_ms < 10000:
            self._cancel_test("Preparation timed out")
        elif now - self._stage_started >= 1.5 and self._stage_ping_received:
            self.outcome.setText("RUN requested · waiting for firmware acknowledgment.")
            self._run_requested = self._send(b"RUN50\n", RUNNING)

    def _update_buttons(self):
        self.test.setEnabled(self._can_start())
        self.stop.setEnabled(self._port is not None and self._test_active())
        self.reconnect.setVisible(self._port is None)

    def _poll(self):
        if self._port is None:
            return
        if self._open_bucket and self._test_active() and not self._fresh():
            self._disconnect("Pump-test status timed out. Reconnect USB to retry.")
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
            if self._open_bucket and self._stage_started is not None:
                self._stage_ping_sent = True
                self._advance_run()
            self._update_buttons()
        except OSError as error:
            self._disconnect(f"The USB connection failed. {error}")

    def _receive(self, line):
        if line == self._fault_message:
            self._disconnect("Pump-test firmware reported a fault. Check the controller, then reconnect USB.")
            return
        match = self._status_pattern.fullmatch(line)
        if match is None:
            return
        percent, remaining_ms, pin_mv, *run_status = map(int, match.groups())
        running, run_remaining_ms = run_status or (0, 0)
        if (pin_mv > 3300 or remaining_ms > 30000 or (percent == 0) != (remaining_ms == 0)
                or run_remaining_ms > min(10000, remaining_ms) or bool(running) != bool(run_remaining_ms)):
            return
        self._last_reply = self._clock()
        previous = self._status
        self._status = (percent, bool(running))
        self._stage_remaining_ms = remaining_ms
        if self._pending == self._status:
            self._pending = None
            self._pending_since = None
            if self._open_bucket and self._status == STAGED:
                self._stage_started = self._last_reply
                self.outcome.setText("Preparing 50% · waiting for the converter to settle.")
            if self._open_bucket and self._status == RUNNING and self._run_requested:
                self._run_acknowledged = True
                self.outcome.setText("RUN acknowledged · controller commanded the contact closed.")
        if self._status == STAGED and self._stage_ping_sent:
            self._stage_ping_received = True
        if self._status == STOPPED:
            if self._open_bucket and previous in (STAGED, RUNNING):
                if self._pending == RUNNING:
                    self._pending = self._pending_since = None
                reason = self._stop_reason or ("Run ended" if self._run_acknowledged else "Test ended")
                result = "RUN acknowledged" if self._run_acknowledged else "RUN was not acknowledged"
                self.outcome.setText(f"{reason} · {result} · controller commands the contact open.")
            self._reset_stage()
        unauthorized = not self._confirmed() or (self._open_bucket and (
            self._stage_started is None or (running and not self._run_requested)
        ))
        if percent == 50 and unauthorized and self._pending != STOPPED:
            self._cancel_test("Unexpected pump-test status")
            if self._port is None:
                return
        self.connection.setText("USB pump-test firmware connected.")
        countdown = f" · {remaining_ms / 1000:.1f} seconds left" if percent else ""
        self.command.setText(f"Converter command {percent}%{countdown}")
        if self._open_bucket:
            self.motor.setText(f"RUN contact commanded closed · {run_remaining_ms / 1000:.1f} seconds left"
                               if running else "RUN contact commanded open")
        if 150 <= pin_mv <= 2450:
            self.feedback.setText(f"{self._feedback_pin} {pin_mv} mV · DB25 14/5 estimate {pin_mv * 0.005:.2f} V (5:1 divider)")
        else:
            self.feedback.setText(f"{self._feedback_pin} {pin_mv} mV · Outside the ADC range for a DB25 14/5 estimate")
        self._update_buttons()

    def _disconnect(self, message):
        if self._open_bucket and self._test_active():
            result = "RUN was acknowledged before the connection ended" if self._run_acknowledged else "RUN was not acknowledged"
            self.outcome.setText(f"Test interrupted · {result}.")
        self.shutdown()
        self.connection.setText(message)
        self.command.setText("Converter command unavailable")
        self.feedback.setText("Drive feedback unavailable")
        if self._open_bucket:
            self.motor.setText("RUN contact command unavailable")

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

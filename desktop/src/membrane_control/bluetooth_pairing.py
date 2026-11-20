"""Local USB pairing window: the operator confirms the actual Bluetooth code."""
from __future__ import annotations

import argparse
from collections import deque
import re
import sys
import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from .transport import SerialTransport, close_transport

_CODE = re.compile(r"^Bluetooth pairing code: ([0-9]{6})$")


class _PairingTransport(SerialTransport):
    def pairing_command(self, text):
        if text != "PAIR" and not re.fullmatch(r"CONFIRM [0-9]{6}", text):
            raise ValueError("Unsupported pairing command")
        self._enqueue((text + "\n").encode("ascii"))


class BluetoothPairingSession:
    def __init__(self, port="COM5", transport_factory=None, clock=time.monotonic):
        self.port = port
        self.clock = clock
        self.transport_factory = transport_factory or _PairingTransport
        self.transport = None
        self.opened = False
        self.code = None
        self.code_at = None
        self.confirmed = False
        self.saved = False
        self.status = "Opening the rig's wired USB port…"
        self.logs = deque(maxlen=200)
        self._pair_until = None
        self._last_pair = None

    @property
    def can_confirm(self):
        return (self.transport is not None and self.opened and self.code is not None
                and self.code_at is not None and not self.confirmed
                and self.clock() - self.code_at < 25)

    def connect(self):
        try:
            self.transport = self.transport_factory(self.port, 115200, raw=True, dtr=False)
        except Exception as error:
            self.status = "USB connection failed: " + str(error)

    def _clear_code(self):
        self.code = self.code_at = None
        self.confirmed = False

    def retry(self):
        if self.saved:
            return
        self._clear_code()
        if self.transport is None:
            self.opened = False
            self.connect()
        self._pair_until = self.clock() + 15
        self._last_pair = None
        self.status = "Cancel the old Windows attempt, then select MembraneControl-Rig again."

    def confirm(self):
        # Only a direct operator action may call this. Never auto-accept a code.
        if not self.can_confirm:
            self.status = "This code expired. Cancel the Windows attempt and try pairing again."
            return False
        self.transport.pairing_command("CONFIRM " + self.code)
        self.confirmed = True
        self.status = "Code confirmed on the ESP32. Accept the same code in Windows."
        return True

    def _line(self, line):
        self.logs.append(str(line)[:1000])
        match = _CODE.fullmatch(line.strip())
        if match:
            self.code = match.group(1)
            self.code_at = self.clock()
            self.confirmed = False
            self._pair_until = None
            self.status = "Compare this code with Windows. If they match, accept in both windows now."
        elif "pairing ready" in line:
            self._clear_code()
            self._pair_until = None
            self.status = "Windows: Add device → Bluetooth → MembraneControl-Rig."
        elif "pairing command accepted" in line:
            self._clear_code()
            self._pair_until = None
            self.status = "Starting pairing mode. In Windows, add MembraneControl-Rig."
        elif "pairing saved" in line:
            self.saved = True
            self._clear_code()
            self._pair_until = None
            self.status = "Paired successfully. USB released. Connect Membrane Control to the rig's outgoing Bluetooth port."
            self.close()
        elif "pairing confirmation accepted" in line:
            self.confirmed = True
            self.status = "ESP32 accepted your confirmation. Waiting for Windows to finish."
        elif any(text in line for text in ("pairing failed", "pairing timed out", "confirmation rejected")):
            self._clear_code()
            self.status = "Pairing did not finish. Cancel the Windows attempt, then click Try pairing again."
        elif "stop the controller before USB pairing" in line:
            self._clear_code()
            self._pair_until = None
            self.status = "Stop the rig in Membrane Control before pairing."

    def tick(self):
        if self.transport is not None:
            transport = self.transport
            for packet in transport.poll(self.clock()):
                if self.transport is not transport:
                    break
                kind = packet.get("type")
                if kind == "port_open":
                    self.opened = True
                    self.retry()
                elif kind == "mass_line":
                    self._line(packet.get("line", ""))
                elif kind == "disconnected":
                    self.status = "USB disconnected: " + str(packet.get("error") or "connection closed")
                    self._clear_code()
                    self.close()
            now = self.clock()
            if (self.transport is not None and self.opened and self._pair_until is not None
                    and now < self._pair_until and (self._last_pair is None or now - self._last_pair >= 1)):
                self.transport.pairing_command("PAIR")
                self._last_pair = now
        if self.code is not None and not self.confirmed and not self.can_confirm:
            self._clear_code()
            self.status = "Code expired. Cancel the Windows attempt, then click Try pairing again."

    def close(self):
        transport, self.transport = self.transport, None
        self.opened = False
        self._pair_until = None
        if transport is not None:
            # Serial cleanup is allowed to wait for its I/O worker, off the UI thread.
            threading.Thread(target=close_transport, args=(transport,), daemon=True,
                             name="bluetooth-pairing-close").start()


class BluetoothPairingWindow(QWidget):
    def __init__(self, port="COM5", parent=None, session=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.session = session or BluetoothPairingSession(port)
        self.setWindowTitle("Pair MembraneControl-Rig")
        self.resize(620, 550)
        layout = QVBoxLayout(self)
        title = QLabel("Pair MembraneControl-Rig")
        title.setStyleSheet("font-size:22px;font-weight:600")
        layout.addWidget(title)
        instructions = QLabel(
            f"Wired USB: {port}\n"
            "1. Cancel any stalled Windows pairing attempt.\n"
            "2. Windows Settings → Bluetooth & devices → Add device → Bluetooth.\n"
            "3. Select MembraneControl-Rig. Compare the code below with Windows.\n"
            "4. If they match, click Yes in Windows AND confirm here promptly.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.code_label = QLabel("Waiting for code")
        self.code_label.setAccessibleName("Bluetooth pairing code")
        self.code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_label.setStyleSheet("font-size:38px;font-weight:700;padding:16px")
        self.code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.code_label)
        self.confirm_button = QPushButton("Codes match — confirm")
        self.confirm_button.setAccessibleName("Confirm matching Bluetooth code")
        self.confirm_button.setEnabled(False)
        self.confirm_button.setMinimumHeight(46)
        self.confirm_button.clicked.connect(self._confirm)
        layout.addWidget(self.confirm_button)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.retry_button = QPushButton("Try pairing again")
        self.retry_button.clicked.connect(self._retry)
        layout.addWidget(self.retry_button)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(200)
        layout.addWidget(self.log)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self.session.connect()
        self._render()

    def _confirm(self):
        try:
            self.session.confirm()
        except Exception as error:
            self.session.status = str(error)
        self._render()

    def _retry(self):
        self.session.retry()
        self._render()

    def _tick(self):
        try:
            self.session.tick()
        except Exception as error:
            self.session.status = "Pairing connection error: " + str(error)
            self.session._clear_code()
            self.session.close()
        self._render()

    def _render(self):
        self.code_label.setText(self.session.code or ("Paired" if self.session.saved else "Waiting for code"))
        self.confirm_button.setEnabled(self.session.can_confirm)
        self.retry_button.setEnabled(not self.session.saved)
        self.status_label.setText(self.session.status)
        text = "\n".join(self.session.logs)
        if self.log.toPlainText() != text:
            self.log.setPlainText(text)
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def closeEvent(self, event):
        self.timer.stop()
        self.session.close()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM5")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    window = BluetoothPairingWindow(args.port)
    window.show()
    app.aboutToQuit.connect(window.session.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

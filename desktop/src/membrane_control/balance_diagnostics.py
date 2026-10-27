"""Explicit Nimbus serial diagnostics; no tare, reset or settings commands."""
from __future__ import annotations

from collections import deque
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .balance import parse_mass
from .transport import SerialTransport, close_transport

NIMBUS_BAUDS = (4800, 9600, 19200, 38400)
SERIAL_FORMATS = ('8N1', '7E1', '7O1')
MANUAL_URL = 'https://adamequipment.com.cn/media/docs/manuals/NBLe_i_UM_EN.pdf'


class BalanceDiagnosticsSession:
    """Counts actual received bytes and parsed masses without generating data."""

    def __init__(self, transport_factory=None, clock=time.monotonic):
        self.transport_factory = transport_factory or SerialTransport
        self.clock = clock
        self.transport = None
        self.opened = False
        self.port, self.baud, self.serial_format = '', 9600, '8N1'
        self.bytes_received = self.lines_received = self.mass_readings = self.decode_errors = 0
        self.last_mass_g = self.last_mass_at = self.last_request_at = None
        self.error = ''
        self.pending_log = deque(maxlen=600)

    def log(self, message):
        self.pending_log.append(str(message)[:7000])

    def drain_log(self):
        lines = list(self.pending_log)
        self.pending_log.clear()
        return lines

    @property
    def fresh(self):
        return bool(self.transport is not None and self.opened and self.last_mass_at is not None
                    and self.clock() - self.last_mass_at <= 3.0)

    @property
    def can_request(self):
        return bool(self.transport is not None and self.opened and
                    (self.last_request_at is None or self.clock() - self.last_request_at >= 1.0))

    @property
    def status(self):
        if self.error:
            return 'Serial error: ' + self.error
        if self.transport is None:
            return 'Disconnected. Select the scale port and matching baud/parity, then Connect.'
        if not self.opened:
            return 'Opening the selected port. No balance response has been established.'
        if not self.bytes_received:
            return ('Port opened; NO BYTES RECEIVED. Press Print on the balance or Request reading here. '
                    'If still empty, check SERIAL ENABLE and matching baud/parity on the balance.')
        if self.decode_errors and not self.lines_received:
            return 'Bytes received but text/framing is invalid. Inspect the raw log and match the balance baud/parity.'
        if not self.lines_received:
            return 'Bytes received, but no complete decoded line yet. Inspect the raw log and serial settings.'
        if not self.mass_readings:
            return ('Text received, but no usable net mass. Inspect the raw log; use normal weighing with g/kg/mg units. '
                    'Gross, tare and report identifiers are not accepted as net mass.')
        if self.fresh:
            return 'Valid mass readings received. Compare them with the balance display.'
        return 'Last valid mass is stale. Manual Print gives one result; continuous output is needed for ongoing acquisition.'

    def connect(self, port, baud=9600, serial_format='8N1', dtr=True):
        if self.transport is not None:
            raise ValueError('Disconnect before changing the serial settings.')
        if not isinstance(port, str) or not port.strip():
            raise ValueError('Select the scale serial port.')
        if (type(baud) is not int or baud not in NIMBUS_BAUDS
            or serial_format not in SERIAL_FORMATS or type(dtr) is not bool):
            raise ValueError('Nimbus settings are 4800/9600/19200/38400 baud and NONE 8N1, EVEN 7E1 or ODD 7O1.')
        self.port, self.baud, self.serial_format = port, baud, serial_format
        self.bytes_received = self.lines_received = self.mass_readings = self.decode_errors = 0
        self.last_mass_g = self.last_mass_at = self.last_request_at = None
        self.error = ''
        self.opened = False
        self.log(f'CONNECT requested: {port}, {baud}, {serial_format}, DTR={dtr}. Weighing settings are not changed.')
        try:
            self.transport = self.transport_factory(port, baud, raw=True,
                serial_format=serial_format, diagnostics=True, dtr=dtr)
        except Exception as error:
            self.fail(str(error))

    def disconnect(self):
        transport, self.transport = self.transport, None
        self.opened = False
        if transport is not None:
            try:
                close_transport(transport)  # Never send a controller JSON STOP to a balance.
            except Exception as error:
                if not self.error:
                    self.error = str(error)[:500]
            self.log('DISCONNECTED. No polling or commands continue.')

    def fail(self, error):
        if not self.error:
            self.error = str(error)[:500]
        self.log('ERROR: ' + self.error)
        self.disconnect()

    def request_reading(self):
        if not self.can_request:
            raise ValueError('Wait for the port to open and one second between Print requests.')
        try:
            self.transport.request_reading()
            self.last_request_at = self.clock()
            self.log(r'TX explicit Print request: !KP\r (hex 21 4b 50 0d). No tare or configuration command.')
        except Exception as error:
            self.fail(str(error))

    def tick(self):
        if self.transport is None:
            return
        try:
            for packet in self.transport.poll(self.clock()):
                if not isinstance(packet, dict):
                    raise ValueError('Invalid diagnostic transport event.')
                kind = packet.get('type')
                if kind == 'port_open':
                    self.opened = True
                    self.log('PORT OPEN. This alone does not confirm the scale is sending data.')
                elif kind == 'serial_raw':
                    data = packet.get('data')
                    if not isinstance(data, bytes):
                        raise ValueError('Invalid raw serial event.')
                    self.bytes_received += len(data)
                    shown = data[:1024]
                    self.log(f'RX {len(data)} bytes | escaped={shown!r} | hex={shown.hex(" ")}')
                elif kind == 'mass_line':
                    line = packet.get('line')
                    if not isinstance(line, str):
                        raise ValueError('Invalid decoded balance line.')
                    self.lines_received += 1
                    try:
                        mass = parse_mass(line)
                    except ValueError:
                        self.log(f'NOT A NET MASS: {line[:256]!r}')
                    else:
                        self.mass_readings += 1
                        self.last_mass_g, self.last_mass_at = mass, self.clock()
                        self.log(f'PARSED NET MASS: {mass:g} g from {line[:256]!r}')
                elif kind == 'parse_error':
                    self.decode_errors += 1
                    self.log('DECODE/FRAMING ERROR: ' + str(packet.get('error', 'unknown'))[:500])
                elif kind == 'disconnected':
                    self.fail(packet.get('error') or 'Balance port disconnected.')
                    return
        except Exception as error:
            self.fail(error)


class BalanceDiagnosticsDialog(QDialog):
    def __init__(self, parent=None, *, selected_port='', selected_baud=9600,
                 selected_format='8N1', excluded_ports=(), port_lister=None,
                 transport_factory=None, clock=time.monotonic, selected_dtr=True):
        super().__init__(parent)
        self._shutdown_done = False
        self.setWindowTitle('Scale diagnostics (Adam Nimbus)')
        self.setModal(True)
        self.resize(850, 690)
        self.session = BalanceDiagnosticsSession(transport_factory, clock)
        self.excluded_ports = set(excluded_ports)
        self.port_lister = port_lister or self._list_ports
        self._selected_port = selected_port
        layout = QVBoxLayout(self)
        notice = QLabel('Use the balance USB-B I/O port and its own COM port. '
                        'Connect only when the normal scale connection has been released. '
                        'This tool listens and can send one Print request; it does not tare, reset or change the balance settings.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        form = QFormLayout()
        self.port_combo = QComboBox()
        self.port_combo.setAccessibleName('Scale diagnostic serial port')
        self.baud_combo = QComboBox()
        for baud in NIMBUS_BAUDS:
            self.baud_combo.addItem(str(baud), baud)
        baud_index = self.baud_combo.findData(selected_baud)
        self.baud_combo.setCurrentIndex(baud_index if baud_index >= 0 else self.baud_combo.findData(9600))
        self.format_combo = QComboBox()
        for label, value in (('NONE (8N1)', '8N1'), ('EVEN (7E1)', '7E1'), ('ODD (7O1)', '7O1')):
            self.format_combo.addItem(label, value)
        index = self.format_combo.findData(selected_format)
        self.format_combo.setCurrentIndex(max(0, index))
        form.addRow('Scale port', self.port_combo)
        form.addRow('Baud rate on balance', self.baud_combo)
        form.addRow('Parity on balance', self.format_combo)
        self.dtr_checkbox = QCheckBox('USB ready signal (DTR)')
        self.dtr_checkbox.setChecked(bool(selected_dtr))
        self.dtr_checkbox.setToolTip('Normal USB serial readiness. Disconnect before changing it; no tare, reset or settings command is sent.')
        form.addRow(self.dtr_checkbox)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.refresh_button = QPushButton('Refresh ports')
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button = QPushButton('Connect')
        self.connect_button.clicked.connect(self.connect_balance)
        self.disconnect_button = QPushButton('Disconnect')
        self.disconnect_button.clicked.connect(self.disconnect_balance)
        self.request_button = QPushButton('Request reading')
        self.request_button.clicked.connect(self.request_reading)
        for button in (self.refresh_button, self.connect_button, self.disconnect_button, self.request_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.status_label = QLabel()
        self.count_label = QLabel()
        self.mass_label = QLabel()
        for label in (self.status_label, self.count_label, self.mass_label):
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(label)
        self.raw_log = QPlainTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumBlockCount(600)
        self.raw_log.setAccessibleName('Actual scale serial bytes, decoded lines and parser results')
        layout.addWidget(self.raw_log, 1)
        hint = QLabel('If no bytes arrive, check SERIAL ENABLE, baud and parity on the scale, '
                      'then power-cycle it after any serial setting change. For continuous weights use '
                      'CONTIN ON, STABLE OFF, PERIOD OFF and SINGLE output. '
                      f'<a href="{MANUAL_URL}">Nimbus manual, sections 11 and 13.3</a>. '
                      "Dr. Onita Basu's lab · Carleton University.")
        hint.setWordWrap(True)
        hint.setOpenExternalLinks(True)
        layout.addWidget(hint)
        bottom = QHBoxLayout()
        clear = QPushButton('Clear log')
        clear.clicked.connect(self.raw_log.clear)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        bottom.addWidget(clear)
        bottom.addStretch()
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self.refresh_ports()
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._quit_application = QApplication.instance()
        if self._quit_application is not None:
            self._quit_application.aboutToQuit.connect(self.shutdown)
        self._render()

    @staticmethod
    def _list_ports():
        from serial.tools import list_ports
        return [(port.device, port.description) for port in list_ports.comports()]

    def refresh_ports(self):
        if self._shutdown_done or self.session.transport is not None:
            return
        previous = self.port_combo.currentData() or self._selected_port
        self.port_combo.clear()
        try:
            for port, description in self.port_lister():
                if port not in self.excluded_ports:
                    self.port_combo.addItem(f'{port}  {description}', port)
            if previous and previous not in self.excluded_ports and self.port_combo.findData(previous) < 0:
                self.port_combo.addItem(f'{previous}  (not currently listed)', previous)
            index = self.port_combo.findData(previous)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        except Exception as error:
            self.session.log(f'Could not list ports: {error}')
        self._render()

    def _act(self, action):
        if self._shutdown_done:
            return
        try:
            action()
        except Exception as error:
            self.session.log(str(error))
        self._render()

    def connect_balance(self):
        port = self.port_combo.currentData()
        if port in self.excluded_ports:
            self.session.log('Select the scale port, not the controller port.')
            self._render()
            return
        self._act(lambda: self.session.connect(port, self.baud_combo.currentData(),
                                               self.format_combo.currentData(), self.dtr_checkbox.isChecked()))

    def disconnect_balance(self):
        self.session.disconnect()
        self._render()

    def request_reading(self):
        self._act(self.session.request_reading)

    def _tick(self):
        if not self._shutdown_done:
            self.session.tick()
            self._render()

    def _render(self):
        session = self.session
        connected = session.transport is not None
        live = not self._shutdown_done
        self.connect_button.setEnabled(live and not connected and bool(self.port_combo.currentData()))
        self.disconnect_button.setEnabled(live and connected)
        self.request_button.setEnabled(live and session.can_request)
        for widget in (self.port_combo, self.baud_combo, self.format_combo, self.dtr_checkbox, self.refresh_button):
            widget.setEnabled(live and not connected)
        self.status_label.setText(session.status)
        self.count_label.setText(f'Actual bytes: {session.bytes_received}   Decoded lines: {session.lines_received}   '
                                f'Valid masses: {session.mass_readings}   Decode errors: {session.decode_errors}')
        mass = 'Unavailable' if session.last_mass_g is None else f'{session.last_mass_g:g} g'
        suffix = '' if session.last_mass_g is None else (' (fresh)' if session.fresh else ' (stale or disconnected)')
        self.mass_label.setText('Last parsed net mass: ' + mass + suffix)
        lines = session.drain_log()
        if lines:
            self.raw_log.appendPlainText('\n'.join(lines))

    def shutdown(self):
        if self._shutdown_done:
            return
        self._shutdown_done = True
        try:
            self.timer.stop()
        except RuntimeError:
            pass
        self.session.disconnect()
        try:
            self._render()
        except RuntimeError:
            pass
        if self._quit_application is not None:
            try:
                self._quit_application.aboutToQuit.disconnect(self.shutdown)
            except (RuntimeError, TypeError):
                pass
            self._quit_application = None

    def done(self, result):
        self.shutdown()
        super().done(result)

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

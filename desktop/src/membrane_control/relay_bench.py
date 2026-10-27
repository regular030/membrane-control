"""Explicit bare-board relay testing, isolated from production control and recipes."""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .transport import SerialTransport, close_transport


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


class RelayBenchSession:
    """One explicit connection; no automatic rearming or queued relay operations."""

    STATUS_TIMEOUT = 1.2
    ACK_TIMEOUT = 1.5
    OPERATION_TIMEOUT = 2.5
    HEARTBEAT_INTERVAL = 0.5
    HELLO_INTERVAL = 1.0
    HELLO_TIMEOUT = 8.0
    PULSE_MS = 500

    def __init__(self, transport_factory=None, clock=time.monotonic):
        self.transport_factory = transport_factory or SerialTransport
        self.clock = clock
        self.transport = None
        self._cleanup_transport = None
        self.next_id = 0
        self.pending = {}
        self.operation = None
        self.verified = False
        self.loads_disconnected = False
        self.observed = False
        self.confirmed = False
        self.probe_id = None
        self.probe_acked = False
        self.baseline_word = 0
        self.status = None
        self.last_status = None
        self.last_uptime = None
        self.hello_at = None
        self.connect_started = None
        self.last_hello_sent = -100.0
        self.retired_hello_ids = set()
        self.last_heartbeat_sent = -100.0
        self.last_heartbeat_ack = None
        self.error = ''
        self.message = 'Not connected. Select the bare relay board port, then Connect.'

    @property
    def cleanup_pending(self):
        return self._cleanup_transport is not None

    @property
    def fresh(self):
        return (self.verified and self.last_status is not None
                and self.clock() - self.last_status <= self.STATUS_TIMEOUT)

    @property
    def heartbeat_fresh(self):
        return (self.last_heartbeat_ack is not None
                and self.clock() - self.last_heartbeat_ack < 1.0)

    @property
    def busy(self):
        return self.operation is not None or any(command != 'heartbeat' for command, _ in self.pending.values())

    @property
    def can_probe(self):
        return bool(self.fresh and self.heartbeat_fresh and self.loads_disconnected
                    and not self.busy and self.status['state'] in ('disarmed', 'ready'))

    @property
    def can_confirm(self):
        return bool(self.fresh and self.heartbeat_fresh and self.loads_disconnected
                    and not self.busy and self.probe_acked and self.probe_id is not None
                    and self.status['probe_id'] == self.probe_id
                    and self.status['probe_completed'] and self.status['state'] == 'disarmed'
                    and self.status['baseline_word'] == self.baseline_word)

    @property
    def can_pulse(self):
        return bool(self.fresh and self.heartbeat_fresh and self.loads_disconnected
                    and self.observed and self.confirmed and not self.busy
                    and self.status['state'] == 'ready' and self.status['baseline_confirmed']
                    and self.status['probe_id'] == self.probe_id
                    and self.status['baseline_word'] == self.baseline_word)

    def _request(self, command, **values):
        if self.transport is None:
            raise ValueError('Connect the relay board first.')
        if not self.verified and command not in ('hello', 'heartbeat', 'stop'):
            raise ValueError('The relay test firmware has not been identified.')
        if command == 'hello' and self.verified:
            raise ValueError('Reconnect explicitly to identify the board again; HELLO would disarm it.')
        self.next_id = self.next_id % 0x7ffffffe + 1
        request_id = self.next_id
        deadline = (self.connect_started + self.HELLO_TIMEOUT if command == 'hello'
                    else self.clock() + self.ACK_TIMEOUT)
        self.pending[request_id] = (command, deadline)
        try:
            self.transport.send({'v': 1, 'id': request_id, 'cmd': command, **values})
        except Exception:
            self.pending.pop(request_id, None)
            raise
        if command == 'heartbeat':
            self.last_heartbeat_sent = self.clock()
        elif command == 'hello':
            self.last_hello_sent = self.clock()
        return request_id

    def connect(self, port):
        if self.transport is not None:
            raise ValueError('Disconnect before choosing another board.')
        if self.cleanup_pending:
            raise ValueError('Previous serial connection still needs cleanup. Choose Recover connection before reconnecting.')
        if not isinstance(port, str) or not port.strip():
            raise ValueError('Select the relay board serial port.')
        self._clear_attestations()
        self.error = ''
        self.status = None
        self.last_status = self.last_uptime = self.hello_at = None
        self.connect_started = self.clock()
        self.last_hello_sent = -100.0
        self.retired_hello_ids.clear()
        self.last_heartbeat_ack = None
        self.last_heartbeat_sent = -100.0
        self.verified = False
        try:
            self.transport = self.transport_factory(port, 115200)
            self._request('hello')
            self.message = ('Waiting for relay test firmware (up to 8 s). If just flashed using the '
                            'three-wire UART adapter, release IO0/BOOT and briefly press EN/RESET.')
        except Exception as exc:
            self.fail(f'Could not connect: {exc}')

    def _clear_attestations(self):
        self.loads_disconnected = self.observed = self.confirmed = False
        self.probe_id = None
        self.probe_acked = False
        self.operation = None

    def detach(self, message='Disconnected. Reconnect and repeat the bare-board checks.'):
        transport, self.transport = self.transport, None
        retry = transport is None
        if retry:
            transport = self._cleanup_transport
        self._cleanup_transport = None
        self.pending.clear()
        self._clear_attestations()
        self.verified = False
        self.status = None
        self.last_status = self.last_uptime = self.hello_at = None
        self.connect_started = None
        self.retired_hello_ids.clear()
        self.last_heartbeat_ack = None
        if transport is not None:
            # The real transport makes one bounded STOP write, then cancels I/O
            # and closes its handle. Duck transports retain zero-argument close.
            self.next_id = self.next_id % 0x7ffffffe + 1
            try:
                stop = None if retry else {'v': 1, 'id': self.next_id, 'cmd': 'stop'}
                close_transport(transport, stop_message=stop)
            except Exception as exc:
                logging.exception('Could not close relay test serial connection')
                if getattr(transport, 'cleanup_pending', True):
                    self._cleanup_transport = transport
                if not self.error:
                    self.error = f'Could not close the serial connection: {exc}'[:500]
                if self.cleanup_pending and 'Recover connection' not in self.error:
                    self.error = (self.error[:330] + ' Port cleanup is pending; choose Recover connection to retry.')[:500]
        self.message = self.error or message

    def recover(self, port):
        """Release this session first; a new HELLO never restores relay checks."""
        self.detach('Releasing the previous connection before a fresh handshake.')
        if self.cleanup_pending:
            return
        # SerialTransport also retries retired cleanup owners from deleted
        # dialogs. It refuses to open a replacement while their handle remains.
        self.connect(port)

    def fail(self, message):
        if not self.error:
            self.error = str(message)[:500]
        self.detach()

    def attest_loads(self, disconnected):
        if type(disconnected) is not bool:
            raise ValueError('Confirm that all relay contacts are disconnected from loads.')
        if not disconnected:
            if self.probe_id is not None or self.operation is not None:
                self.detach('Load-disconnection confirmation withdrawn; port disconnected.')
            self.loads_disconnected = False
        elif self.fresh:
            self.loads_disconnected = True
        else:
            raise ValueError('Wait for fresh relay test firmware status first.')

    def invalidate_observation(self):
        if self.busy:
            raise ValueError('Wait for the current relay test to finish.')
        self.probe_id = None
        self.probe_acked = self.observed = self.confirmed = False

    def _begin_operation(self, command, **values):
        request_id = self._request(command, **values)
        self.operation = {'command': command, 'id': request_id, 'acked': False,
                          'seen_active': False, 'deadline': self.clock() + self.OPERATION_TIMEOUT,
                          **values}
        return request_id

    def probe(self, baseline_word):
        if not self.can_probe or type(baseline_word) is not int or baseline_word not in (0, 65535):
            raise ValueError('Connect, verify status and disconnect every load before testing a rest pattern.')
        self.baseline_word = baseline_word
        self.probe_acked = self.observed = self.confirmed = False
        self.probe_id = self._begin_operation('bench_probe', baseline_word=baseline_word,
            duration_ms=self.PULSE_MS, loads_disconnected=True)
        self.message = 'Testing the rest pattern for 500 ms. Observe the bare relays.'

    def confirm_observation(self):
        if not self.can_confirm:
            raise ValueError('Wait for this rest-pattern test to complete and be acknowledged before confirming it.')
        self._begin_operation('bench_confirm', baseline_word=self.baseline_word,
            probe_id=self.probe_id, loads_disconnected=True, all_relays_off=True)
        self.observed = True
        self.message = 'Sending your all-relays-off observation; waiting for the board.'

    def pulse(self, bit):
        if not self.can_pulse or not _integer(bit, 0, 15):
            raise ValueError('Complete and confirm the rest-pattern test before pulsing one raw bit.')
        self._begin_operation('bench_pulse', bit=bit, duration_ms=self.PULSE_MS)
        self.message = f'Requested Bit {bit} for 500 ms. This is a command, not contact feedback.'

    @staticmethod
    def _checked_status(packet):
        required = ('simulation', 'hardware_verified', 'uptime_ms', 'state', 'outputs_enabled',
                    'baseline_confirmed', 'probe_completed', 'probe_id', 'baseline_word',
                    'remaining_ms', 'pulse_bit', 'fault')
        if (not all(key in packet for key in required)
            or packet.get('simulation') is not False or packet.get('hardware_verified') is not False
            or not _integer(packet.get('uptime_ms'), 0, 0xffffffff)
            or packet.get('state') not in ('disarmed', 'probing', 'ready', 'pulsing', 'fault')
            or type(packet.get('outputs_enabled')) is not bool
            or type(packet.get('baseline_confirmed')) is not bool
            or type(packet.get('probe_completed')) is not bool
            or not _integer(packet.get('probe_id'), 0, 0xffffffff)
            or type(packet.get('baseline_word')) is not int or packet['baseline_word'] not in (0, 65535)
            or not _integer(packet.get('remaining_ms'), 0, 2000)
            or not (packet.get('fault') is None or isinstance(packet.get('fault'), str))):
            raise ValueError('Invalid relay test status or unexpected firmware mode.')
        state = packet['state']
        active = state in ('probing', 'pulsing')
        if (packet['outputs_enabled'] is not active
            or (state == 'pulsing' and not _integer(packet.get('pulse_bit'), 0, 15))
            or (state != 'pulsing' and packet.get('pulse_bit') is not None)
            or (not active and packet['remaining_ms'] != 0)
            or (packet['probe_completed'] and packet['probe_id'] == 0)
            or (packet['baseline_confirmed'] and (not packet['probe_completed'] or state not in ('ready', 'pulsing')))
            or (state in ('ready', 'pulsing') and not packet['baseline_confirmed'])):
            raise ValueError('Inconsistent relay test status; connection stopped.')
        return dict(packet)

    def _finish_operation(self):
        op, status = self.operation, self.status
        if op is None or not op['acked'] or not self.fresh:
            return
        same_probe = status['probe_id'] == self.probe_id and status['baseline_word'] == self.baseline_word
        if op['command'] == 'bench_probe':
            complete = same_probe and status['probe_completed'] and status['state'] == 'disarmed'
        elif op['command'] == 'bench_confirm':
            complete = same_probe and status['baseline_confirmed'] and status['state'] == 'ready'
            if complete:
                self.confirmed = True
        else:
            complete = same_probe and op['seen_active'] and status['state'] == 'ready'
        if complete:
            self.operation = None
            self.message = ('Rest-pattern test completed. Only confirm if all relays stayed off.'
                            if op['command'] == 'bench_probe' else
                            'Ready for one 500 ms raw-bit pulse. Relay contacts are not monitored.')

    def _handle_packet(self, packet, now):
        if not isinstance(packet, dict):
            raise ValueError('Invalid relay test message.')
        kind = packet.get('type')
        if kind == 'port_open':
            return
        if kind == 'parse_error' and not self.verified:
            return  # Boot text cannot authorize anything; HELLO still has a deadline.
        if kind == 'disconnected':
            raise ValueError(packet.get('error') or 'Relay board disconnected.')
        if kind == 'bench_status' and not self.verified:
            # Serial data from a previous session may precede our HELLO reply.
            # Even a stale fault/active state cannot authorize this new session.
            # Matching HELLO disarms the board; require new status afterwards.
            return
        if type(packet.get('v')) is not int or packet['v'] != 1:
            raise ValueError('Invalid relay test protocol version.')
        if kind in ('hello', 'ack', 'error'):
            request_id = packet.get('id')
            if (not self.verified and kind == 'error' and packet.get('ok') is False
                and type(request_id) is int and request_id == 0
                and isinstance(packet.get('error'), str)):
                return  # Firmware can report a partial boot-time JSON frame with id 0.
            retired_hello = _integer(request_id, 1, 0xffffffff) and request_id in self.retired_hello_ids
            if retired_hello and kind == 'hello':
                self._check_identity(packet)
                return  # An older retry cannot identify/disarm the current UI session.
            if not _integer(request_id, 1, 0xffffffff) or request_id not in self.pending:
                raise ValueError('Unexpected relay test acknowledgement; reconnect the board.')
            command, _ = self.pending[request_id]
            expected = 'hello' if command == 'hello' else 'ack'
            if kind == 'error' and packet.get('ok') is False:
                raise ValueError(f"Board rejected {command}: {str(packet.get('error', 'unknown error'))[:300]}")
            if kind != expected or packet.get('ok') is not True:
                raise ValueError('Malformed relay test acknowledgement.')
            if command == 'hello':
                self._check_identity(packet)
                self.verified = True
                self.hello_at = now
                self.status = self.last_status = self.last_uptime = None
                self.message = 'Relay test firmware identified; waiting for fresh status and heartbeat acknowledgement.'
            self.pending.pop(request_id)
            if command == 'hello':
                self._request('heartbeat')
            elif command == 'heartbeat':
                self.last_heartbeat_ack = now
            elif self.operation is not None and request_id == self.operation['id']:
                self.operation['acked'] = True
                if command == 'bench_probe':
                    self.probe_acked = True
            self._finish_operation()
            return
        if kind != 'bench_status':
            raise ValueError('Unexpected firmware telemetry. This dialog only accepts relay test firmware.')
        status = self._checked_status(packet)
        if self.last_uptime is not None and ((status['uptime_ms'] - self.last_uptime) & 0xffffffff) > 0x7fffffff:
            raise ValueError('Relay board restarted; reconnect and repeat the checks.')
        if status['fault'] or status['state'] == 'fault':
            raise ValueError(status['fault'] or 'Relay test firmware fault.')
        if status['outputs_enabled']:
            op = self.operation
            if op is None:
                raise ValueError('Unexpected active relay output; connection stopped.')
            if status['state'] == 'probing':
                if op['command'] != 'bench_probe' or status['probe_id'] != op['id']:
                    raise ValueError('Unexpected rest-pattern operation.')
            elif (op['command'] != 'bench_pulse' or status['pulse_bit'] != op['bit']
                  or status['probe_id'] != self.probe_id):
                raise ValueError('Unexpected raw relay bit operation.')
            if status['baseline_word'] != self.baseline_word:
                raise ValueError('Relay test baseline changed unexpectedly.')
            op['seen_active'] = True
        self.status, self.last_status, self.last_uptime = status, now, status['uptime_ms']
        self._finish_operation()

    @staticmethod
    def _check_identity(packet):
        if (packet.get('ok') is not True or packet.get('device') != 'membrane-relay-bench'
            or type(packet.get('protocol_version')) is not int or packet['protocol_version'] != 1
            or type(packet.get('relay_count')) is not int or packet['relay_count'] != 16
            or packet.get('simulation') is not False or packet.get('hardware_verified') is not False):
            raise ValueError('Not the 16-channel real relay test firmware. Flash the separate relay board test target.')

    def tick(self):
        if self.transport is None:
            return
        now = self.clock()
        try:
            for packet in self.transport.poll(now):
                self._handle_packet(packet, now)
                if self.transport is None:
                    return
            if not self.verified:
                if now - self.connect_started >= self.HELLO_TIMEOUT:
                    raise ValueError('Relay test HELLO timed out after 8 s. Check the COM port. '
                        'With the three-wire UART adapter, release IO0/BOOT, briefly press EN/RESET, '
                        'then reconnect. The app does not toggle those pins.')
                if now - self.last_hello_sent >= self.HELLO_INTERVAL:
                    for request_id, (command, _deadline) in list(self.pending.items()):
                        if command == 'hello':
                            self.retired_hello_ids.add(request_id)
                            self.pending.pop(request_id)
                    self._request('hello')
            for command, deadline in self.pending.values():
                if now >= deadline:
                    raise ValueError(f'{command} acknowledgement timed out; disconnected and stopped sending heartbeats.')
            if self.verified:
                since_status = self.last_status if self.last_status is not None else self.hello_at
                if now - since_status > self.STATUS_TIMEOUT:
                    raise ValueError('Relay test status is stale; disconnected and stopped sending heartbeats.')
                if self.operation is not None and now >= self.operation['deadline']:
                    raise ValueError('Relay test completion timed out; reconnect and repeat the checks.')
                heartbeat_pending = any(cmd == 'heartbeat' for cmd, _ in self.pending.values())
                if now - self.last_heartbeat_sent >= self.HEARTBEAT_INTERVAL and not heartbeat_pending:
                    self._request('heartbeat')
        except Exception as exc:
            self.fail(exc)


class RelayBenchDialog(QDialog):
    """A separate modal tool that can drive real relays on an unloaded board."""

    def __init__(self, parent=None, *, selected_port=None, port_lister=None,
                 excluded_ports=(), transport_factory=None, clock=time.monotonic):
        super().__init__(parent)
        self._shutdown_done = False
        self.setWindowTitle('Relay board test (real relays)')
        self.setModal(True)
        self.resize(640, 680)
        self.session = RelayBenchSession(transport_factory, clock)
        self.port_lister = port_lister or self._list_ports
        self.excluded_ports = set(excluded_ports)
        self._selected_port = selected_port
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        notice = QLabel('REAL RELAYS. Only bare board. No pump, sensor or recipe controls. Raw bits need mapping. '
                        'Disconnect every COM / NO / NC contact wire from all loads before testing. '
                        'Pressure and flow are unavailable here; no measurements are generated.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        row = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setAccessibleName('Relay test serial port')
        self.refresh_button = QPushButton('Refresh ports')
        self.refresh_button.clicked.connect(self.refresh_ports)
        row.addWidget(self.port_combo, 1)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.connect_button = QPushButton('Connect')
        self.connect_button.clicked.connect(self.connect_board)
        self.disconnect_button = QPushButton('Disconnect')
        self.disconnect_button.clicked.connect(self.disconnect_board)
        self.recover_button = QPushButton('Recover connection')
        self.recover_button.setToolTip('Release the previous serial connection, then identify the board again. '
                                       'No relay test resumes; repeat all bare-board checks.')
        self.recover_button.clicked.connect(self.recover_board)
        row.addWidget(self.connect_button)
        row.addWidget(self.disconnect_button)
        row.addWidget(self.recover_button)
        layout.addLayout(row)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.output_label = QLabel()
        self.output_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addWidget(self.output_label)
        self.loads_checkbox = QCheckBox('All relay contact terminals are disconnected from loads')
        self.loads_checkbox.toggled.connect(self._loads_changed)
        layout.addWidget(self.loads_checkbox)
        row = QHBoxLayout()
        self.baseline_combo = QComboBox()
        self.baseline_combo.addItem('All LOW (0)', 0)
        self.baseline_combo.addItem('All HIGH (65535)', 65535)
        self.baseline_combo.currentIndexChanged.connect(self._baseline_changed)
        self.probe_button = QPushButton('Test rest pattern (500 ms)')
        self.probe_button.clicked.connect(self.probe_baseline)
        row.addWidget(self.baseline_combo)
        row.addWidget(self.probe_button)
        layout.addLayout(row)
        warning = QLabel('A rest-pattern test may energize multiple BARE relays. '
                         'Watch and listen. If any relay energizes, do not confirm this pattern; try the other pattern.')
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.observation_checkbox = QCheckBox('All relays stayed off during the rest-pattern test')
        self.observation_checkbox.clicked.connect(self._observation_clicked)
        layout.addWidget(self.observation_checkbox)
        grid = QGridLayout()
        self.pulse_buttons = []
        for bit in range(16):
            button = QPushButton(f'Bit {bit}')
            button.setToolTip('Request one raw-bit pulse for 500 ms. Physical channel and contact polarity need mapping.')
            button.clicked.connect(lambda _checked=False, bit=bit: self.pulse(bit))
            grid.addWidget(button, bit // 4, bit % 4)
            self.pulse_buttons.append(button)
        layout.addLayout(grid)
        footer = QLabel('Board status describes commanded outputs, not relay contact feedback. '
                        'Stop, disconnect or close withdraws heartbeats and clears these confirmations. '
                        "Firmware also limits pulse duration and stops after a heartbeat timeout. "
                        "Dr. Onita Basu's lab · Carleton University.")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        row = QHBoxLayout()
        self.stop_button = QPushButton('Stop and disconnect')
        self.stop_button.setObjectName('stopButton')
        self.stop_button.clicked.connect(self.stop)
        close_button = QPushButton('Close')
        close_button.clicked.connect(self.reject)
        row.addWidget(self.stop_button, 1)
        row.addWidget(close_button)
        outer.addLayout(row)
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
        except Exception as exc:
            self.session.message = f'Could not list ports: {exc}'[:500]
        self._render()

    def _act(self, action):
        if self._shutdown_done:
            return
        try:
            action()
        except Exception as exc:
            # A failed write may have reached the board; never keep heartbeats alive.
            self.session.fail(exc)
        self._render()

    def connect_board(self):
        port = self.port_combo.currentData()
        if port in self.excluded_ports:
            self.session.message = 'This port is already used by another instrument.'
            self._render()
            return
        self._act(lambda: self.session.connect(port))

    def disconnect_board(self):
        self.session.detach()
        self._render()

    def recover_board(self):
        port = self.port_combo.currentData()
        if port in self.excluded_ports:
            self.session.message = 'This port is already used by another instrument.'
            self._render()
            return
        self._act(lambda: self.session.recover(port))

    def stop(self):
        self.session.detach('Stop requested; disconnected and stopped sending heartbeats. Reconnect to test again.')
        self._render()

    def _loads_changed(self, checked):
        self._act(lambda: self.session.attest_loads(checked))

    def _baseline_changed(self, _index):
        self._act(self.session.invalidate_observation)

    def probe_baseline(self):
        self._act(lambda: self.session.probe(self.baseline_combo.currentData()))

    def _observation_clicked(self, checked):
        if checked:
            self._act(self.session.confirm_observation)
        else:
            self.session.detach('Rest-pattern observation withdrawn; port disconnected.')
            self._render()

    def pulse(self, bit):
        self._act(lambda: self.session.pulse(bit))

    def _tick(self):
        if self._shutdown_done:
            return
        self.session.tick()
        self._render()

    def _render(self):
        session = self.session
        connected = session.transport is not None
        live = not self._shutdown_done
        self.connect_button.setEnabled(live and not connected and not session.cleanup_pending
                                       and bool(self.port_combo.currentData()))
        self.disconnect_button.setEnabled(live and (connected or session.cleanup_pending))
        self.recover_button.setEnabled(live and bool(self.port_combo.currentData()))
        self.stop_button.setEnabled(live and connected)
        self.refresh_button.setEnabled(live and not connected)
        self.port_combo.setEnabled(live and not connected)
        self.loads_checkbox.setEnabled(live and session.fresh)
        self.baseline_combo.setEnabled(live and session.fresh and not session.busy and not session.confirmed)
        self.probe_button.setEnabled(live and session.can_probe)
        self.observation_checkbox.setEnabled(live and session.can_confirm)
        for checkbox, value in ((self.loads_checkbox, session.loads_disconnected),
                                (self.observation_checkbox, session.observed)):
            with QSignalBlocker(checkbox):
                checkbox.setChecked(value)
        for button in self.pulse_buttons:
            button.setEnabled(live and session.can_pulse)
        self.status_label.setText(session.error or session.message)
        if session.fresh:
            status = session.status
            if status['outputs_enabled']:
                detail = f"{status['state'].upper()}, {status['remaining_ms']} ms remaining"
                if status['pulse_bit'] is not None:
                    detail += f", Bit {status['pulse_bit']}"
            else:
                detail = 'output enable disabled'
            self.output_label.setText(f'Board reports {detail}. Relay contacts are not monitored.')
        else:
            self.output_label.setText('Output status unavailable. Relay contacts are not monitored.')

    def shutdown(self):
        """Release the session even when Qt exits without a dialog close event."""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        try:
            self.timer.stop()
        except RuntimeError:
            pass  # Python cleanup can outlive its Qt wrapper during final teardown.
        self.session.detach('Relay test closed; disconnected and stopped sending heartbeats.')
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

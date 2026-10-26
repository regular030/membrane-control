"""Bounded, sensorless valve commissioning with a separately reviewed profile."""
from __future__ import annotations

import logging
import re
import time

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .transport import SerialTransport, close_transport


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


class ValveTestSession:
    """Never queues outputs, changes a profile, or authorizes production control."""

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
        self.next_id = 0
        self.pending = {}
        self.operation = None
        self.verified = False
        self.valve_profile_verified = False
        self.profile_id = ''
        self.firmware_version = ''
        self.attestations = dict(wiring_checked=False, pump_isolated=False, test_area_ready=False)
        self.armed = False
        self.status = self.last_status = self.last_uptime = None
        self.status_sequence = 0
        self.hello_at = self.connect_started = None
        self.last_hello_sent = self.last_heartbeat_sent = -100.0
        self.last_heartbeat_ack = None
        self.retired_hello_ids = set()
        self.error = ''
        self.message = 'Not connected. Select the valve-test board port, then Connect.'

    @property
    def fresh(self):
        return bool(self.verified and self.last_status is not None
                    and self.clock() - self.last_status <= self.STATUS_TIMEOUT)

    @property
    def heartbeat_fresh(self):
        return self.last_heartbeat_ack is not None and self.clock() - self.last_heartbeat_ack < 1.0

    @property
    def busy(self):
        return self.operation is not None or any(cmd != 'heartbeat' for cmd, _ in self.pending.values())

    @property
    def can_arm(self):
        return bool(self.fresh and self.heartbeat_fresh and self.valve_profile_verified
                    and all(self.attestations.values()) and not self.busy
                    and not self.armed and self.status['state'] == 'disarmed')

    @property
    def can_pulse(self):
        return bool(self.fresh and self.heartbeat_fresh and self.valve_profile_verified
                    and all(self.attestations.values()) and self.armed
                    and not self.busy and self.status['state'] == 'ready')

    def _request(self, command, **values):
        if self.transport is None:
            raise ValueError('Connect the valve-test board first.')
        if not self.verified and command not in ('hello', 'heartbeat', 'stop'):
            raise ValueError('The valve-test firmware has not been identified.')
        if command == 'hello' and self.verified:
            raise ValueError('Reconnect explicitly; HELLO disarms the valve-test session.')
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
        if command == 'hello':
            self.last_hello_sent = self.clock()
        elif command == 'heartbeat':
            self.last_heartbeat_sent = self.clock()
        return request_id

    def connect(self, port):
        if self.transport is not None:
            raise ValueError('Disconnect before choosing another board.')
        if not isinstance(port, str) or not port.strip():
            raise ValueError('Select the valve-test serial port.')
        self._clear_attestations()
        self.error = ''
        self.verified = self.valve_profile_verified = False
        self.profile_id = self.firmware_version = ''
        self.status = self.last_status = self.last_uptime = self.hello_at = None
        self.connect_started = self.clock()
        self.last_hello_sent = self.last_heartbeat_sent = -100.0
        self.last_heartbeat_ack = None
        self.retired_hello_ids.clear()
        try:
            self.transport = self.transport_factory(port, 115200)
            self._request('hello')
            self.message = ('Waiting for valve-test firmware (up to 8 s). After a three-wire UART '
                            'upload, release IO0/BOOT and briefly press EN/RESET.')
        except Exception as exc:
            self.fail(f'Could not connect: {exc}')

    def _clear_attestations(self):
        self.attestations = dict.fromkeys(self.attestations, False)
        self.armed = False
        self.operation = None

    def detach(self, message='Disconnected. Reconnect and repeat the checks before testing.'):
        transport, self.transport = self.transport, None
        self.pending.clear()
        self._clear_attestations()
        self.verified = self.valve_profile_verified = False
        self.profile_id = self.firmware_version = ''
        self.status = self.last_status = self.last_uptime = self.hello_at = None
        self.connect_started = self.last_heartbeat_ack = None
        self.retired_hello_ids.clear()
        if transport is not None:
            self.next_id = self.next_id % 0x7ffffffe + 1
            try:
                close_transport(transport, stop_message={'v': 1, 'id': self.next_id, 'cmd': 'stop'})
            except Exception as exc:
                logging.exception('Could not close valve-test serial connection')
                if not self.error:
                    self.error = f'Could not close serial connection: {exc}'[:500]
        self.message = self.error or message

    def fail(self, message):
        if not self.error:
            self.error = str(message)[:500]
        self.detach()

    def attest(self, name, checked):
        if name not in self.attestations or type(checked) is not bool:
            raise ValueError('Invalid valve-test confirmation.')
        if not checked and (self.armed or self.operation is not None):
            self.detach('Test confirmation withdrawn; stopped sending heartbeats and disconnected.')
        elif checked and not (self.fresh and self.valve_profile_verified):
            raise ValueError('Wait for a reviewed valve-test profile and fresh status first.')
        else:
            self.attestations[name] = checked

    def _begin_operation(self, command, **values):
        request_id = self._request(command, **values)
        self.operation = dict(command=command, id=request_id, acked=False, seen_active=False,
                              status_at_request=self.status_sequence,
                              deadline=self.clock() + self.OPERATION_TIMEOUT, **values)

    def arm(self):
        if not self.can_arm:
            raise ValueError('A reviewed valve profile and all three checks are required before arming.')
        self._begin_operation('valve_arm', profile_id=self.profile_id, **self.attestations)
        self.message = 'Arming valve tests; waiting for acknowledgement and fresh ready status.'

    def pulse(self, valve):
        if not self.can_pulse or not _integer(valve, 1, 7):
            raise ValueError('Arm this session before requesting one valve pulse.')
        self._begin_operation('valve_pulse', valve=valve, duration_ms=self.PULSE_MS)
        self.message = f'Requested V{valve} energize for 500 ms. Actual valve motion is not monitored.'

    @staticmethod
    def _check_identity(packet):
        profile = packet.get('profile_id')
        verified = packet.get('valve_profile_verified')
        if (packet.get('ok') is not True or packet.get('device') != 'membrane-valve-test'
            or packet.get('mode') != 'valve_test'
            or type(packet.get('protocol_version')) is not int or packet['protocol_version'] != 1
            or type(packet.get('valve_count')) is not int or packet['valve_count'] != 7
            or packet.get('simulation') is not False or packet.get('hardware_verified') is not False
            or type(verified) is not bool or not isinstance(profile, str) or len(profile) > 128
            or (verified and (not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', profile) or profile == 'UNVERIFIED'))
            or not isinstance(packet.get('firmware_version'), str)
            or not 1 <= len(packet['firmware_version']) <= 64):
            raise ValueError('Not the dedicated seven-valve test firmware. Flash the valve-test target.')

    def _checked_status(self, packet):
        required = ('profile_id', 'valve_profile_verified', 'outputs_enabled', 'active_valve',
                    'remaining_ms', 'fault', 'simulation', 'hardware_verified')
        if (not all(key in packet for key in required)
            or packet.get('simulation') is not False or packet.get('hardware_verified') is not False
            or not _integer(packet.get('uptime_ms'), 0, 0xffffffff)
            or packet.get('state') not in ('locked', 'disarmed', 'ready', 'pulsing', 'fault')
            or type(packet.get('outputs_enabled')) is not bool
            or type(packet.get('valve_profile_verified')) is not bool
            or packet['valve_profile_verified'] is not self.valve_profile_verified
            or packet['profile_id'] != self.profile_id
            or not _integer(packet.get('active_valve'), 0, 7)
            or not _integer(packet.get('remaining_ms'), 0, 2000)
            or not (packet.get('fault') is None or isinstance(packet.get('fault'), str))):
            raise ValueError('Invalid valve-test status or changed firmware profile.')
        active = packet['state'] == 'pulsing'
        if (packet['outputs_enabled'] is not active
            or (active and packet['active_valve'] == 0)
            or (not active and (packet['active_valve'] != 0 or packet['remaining_ms'] != 0))
            or (not self.valve_profile_verified and packet['state'] not in ('locked', 'fault'))
            or (self.valve_profile_verified and packet['state'] == 'locked')):
            raise ValueError('Inconsistent valve-test status; connection stopped.')
        return dict(packet)

    def _finish_operation(self):
        op = self.operation
        if (op is None or not op['acked'] or not self.fresh
            or self.status_sequence <= op['status_at_request']):
            return
        if op['command'] == 'valve_arm':
            complete = self.status['state'] == 'ready'
            if complete:
                self.armed = True
        else:
            complete = op['seen_active'] and self.status['state'] == 'ready'
        if complete:
            self.operation = None
            self.message = 'Ready for one 500 ms valve pulse. These are commands; valve motion is not monitored.'

    def _handle_packet(self, packet, now):
        if not isinstance(packet, dict):
            raise ValueError('Invalid valve-test message.')
        kind = packet.get('type')
        if kind == 'port_open' or (not self.verified and kind in ('parse_error', 'valve_test_status')):
            return
        if kind == 'disconnected':
            raise ValueError(packet.get('error') or 'Valve-test board disconnected.')
        if type(packet.get('v')) is not int or packet['v'] != 1:
            raise ValueError('Invalid valve-test protocol version.')
        if kind in ('hello', 'ack', 'error'):
            request_id = packet.get('id')
            if (not self.verified and kind == 'error' and packet.get('ok') is False
                and type(request_id) is int and request_id == 0 and isinstance(packet.get('error'), str)):
                return
            if kind == 'hello' and _integer(request_id, 1, 0xffffffff) and request_id in self.retired_hello_ids:
                self._check_identity(packet)
                if self.verified and (packet['profile_id'] != self.profile_id
                    or packet['valve_profile_verified'] is not self.valve_profile_verified):
                    raise ValueError('Valve-test profile changed unexpectedly.')
                return
            if not _integer(request_id, 1, 0xffffffff) or request_id not in self.pending:
                raise ValueError('Unexpected valve-test acknowledgement; reconnect.')
            command, _ = self.pending[request_id]
            if kind == 'error' and packet.get('ok') is False:
                raise ValueError(f"Board rejected {command}: {str(packet.get('error', 'unknown error'))[:300]}")
            if kind != ('hello' if command == 'hello' else 'ack') or packet.get('ok') is not True:
                raise ValueError('Malformed valve-test acknowledgement.')
            if command == 'hello':
                self._check_identity(packet)
                self.verified = True
                self.profile_id = packet['profile_id']
                self.valve_profile_verified = packet['valve_profile_verified']
                self.firmware_version = packet['firmware_version']
                self.hello_at = now
                self.status = self.last_status = self.last_uptime = None
                self.message = 'Valve-test firmware identified; waiting for fresh status and heartbeat acknowledgement.'
            self.pending.pop(request_id)
            if command == 'hello':
                self._request('heartbeat')
            elif command == 'heartbeat':
                self.last_heartbeat_ack = now
            elif self.operation is not None and request_id == self.operation['id']:
                self.operation['acked'] = True
            self._finish_operation()
            return
        if kind != 'valve_test_status' or not self.verified:
            raise ValueError('Unexpected firmware telemetry. Only dedicated valve-test firmware is accepted.')
        status = self._checked_status(packet)
        if self.last_uptime is not None and ((status['uptime_ms'] - self.last_uptime) & 0xffffffff) > 0x7fffffff:
            raise ValueError('Valve-test board restarted; reconnect and repeat the checks.')
        if (status['fault'] and status['state'] != 'locked') or status['state'] == 'fault':
            raise ValueError(status['fault'] or 'Valve-test firmware fault.')
        op = self.operation
        if status['state'] in ('ready', 'pulsing') and not (self.armed or (op and op['command'] == 'valve_arm')):
            raise ValueError('Unexpected armed valve-test session; connection stopped.')
        if status['outputs_enabled']:
            if op is None or op['command'] != 'valve_pulse' or status['active_valve'] != op['valve']:
                raise ValueError('Unexpected energized valve command; connection stopped.')
            op['seen_active'] = True
        if self.armed and status['state'] == 'disarmed':
            raise ValueError('Valve-test session disarmed unexpectedly; repeat the checks.')
        self.status_sequence += 1
        self.status, self.last_status, self.last_uptime = status, now, status['uptime_ms']
        self._finish_operation()
        if status['state'] == 'locked':
            self.message = ('Locked: no reviewed valve-test profile. Complete bare-board mapping, then '
                            'have the mapping, polarity, safe states and wiring reviewed and compiled into valve-test firmware.')
            if status['fault']:
                self.message += ' Board reports: ' + status['fault'][:300]

    def tick(self):
        if self.transport is None:
            return
        now = self.clock()
        try:
            for packet in self.transport.poll(now):
                self._handle_packet(packet, now)
            if not self.verified:
                if now - self.connect_started >= self.HELLO_TIMEOUT:
                    raise ValueError('Valve-test HELLO timed out after 8 s. Check the COM port; release '
                                     'IO0/BOOT, briefly press EN/RESET after a three-wire upload, then reconnect.')
                if now - self.last_hello_sent >= self.HELLO_INTERVAL:
                    for request_id, (command, _) in list(self.pending.items()):
                        if command == 'hello':
                            self.retired_hello_ids.add(request_id)
                            self.pending.pop(request_id)
                    self._request('hello')
            for command, deadline in self.pending.values():
                if now >= deadline:
                    raise ValueError(f'{command} acknowledgement timed out; disconnected and stopped sending heartbeats.')
            if self.verified:
                since = self.last_status if self.last_status is not None else self.hello_at
                if now - since > self.STATUS_TIMEOUT:
                    raise ValueError('Valve-test status is stale; disconnected and stopped sending heartbeats.')
                if self.operation is not None and now >= self.operation['deadline']:
                    raise ValueError('Valve-test completion timed out; reconnect and repeat the checks.')
                if (now - self.last_heartbeat_sent >= self.HEARTBEAT_INTERVAL
                    and not any(cmd == 'heartbeat' for cmd, _ in self.pending.values())):
                    self._request('heartbeat')
        except Exception as exc:
            self.fail(exc)


class ValveTestDialog(QDialog):
    """A separate operator window for a commissioned seven-valve profile."""

    def __init__(self, parent=None, *, selected_port='', port_lister=None,
                 excluded_ports=(), transport_factory=None, clock=time.monotonic):
        super().__init__(parent)
        self._shutdown_done = False
        self.setWindowTitle('Valve test (real solenoid valves)')
        self.setModal(True)
        self.resize(700, 700)
        self.session = ValveTestSession(transport_factory, clock)
        self.port_lister = port_lister or self._list_ports
        self.excluded_ports = set(excluded_ports)
        self._selected_port = selected_port
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        notice = QLabel('REAL SOLENOID VALVES. One 500 ms energize command at a time. '
                        'For a reviewed valve-test profile only. Pump control is unavailable; '
                        'the pump must be physically isolated. Pressure, flow and scale readings '
                        'are unavailable here; sensor protection is not provided in this test.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        ports = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setAccessibleName('Valve-test serial port')
        self.refresh_button = QPushButton('Refresh ports')
        self.refresh_button.clicked.connect(self.refresh_ports)
        ports.addWidget(self.port_combo, 1)
        ports.addWidget(self.refresh_button)
        layout.addLayout(ports)
        row = QHBoxLayout()
        self.connect_button = QPushButton('Connect')
        self.connect_button.clicked.connect(self.connect_board)
        self.disconnect_button = QPushButton('Disconnect')
        self.disconnect_button.clicked.connect(self.disconnect_board)
        row.addWidget(self.connect_button)
        row.addWidget(self.disconnect_button)
        layout.addLayout(row)
        self.profile_label = QLabel('Profile: not connected')
        self.mapping_label = QLabel()
        self.status_label = QLabel()
        self.output_label = QLabel()
        for label in (self.profile_label, self.mapping_label, self.status_label, self.output_label):
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(label)
        self.setup_guide = QLabel('<a href="https://github.com/regular030/membrane-control/blob/main/docs/valve-test.md">Valve test setup guide</a>')
        self.setup_guide.setOpenExternalLinks(True)
        self.setup_guide.setWordWrap(True)
        layout.addWidget(self.setup_guide)
        self.attestation_checkboxes = {}
        for name, text in (
            ('wiring_checked', 'The valve mapping, polarity, safe states and mains wiring have been checked'),
            ('pump_isolated', 'The pump is physically isolated and cannot run during this test'),
            ('test_area_ready', 'The test area and fluid paths are approved for this valve test'),
        ):
            checkbox = QCheckBox(text)
            checkbox.toggled.connect(lambda checked, name=name: self._act(lambda: self.session.attest(name, checked)))
            self.attestation_checkboxes[name] = checkbox
            layout.addWidget(checkbox)
        self.arm_button = QPushButton('Arm valve tests')
        self.arm_button.clicked.connect(lambda: self._act(self.session.arm))
        layout.addWidget(self.arm_button)
        grid = QGridLayout()
        self.pulse_buttons = []
        for valve in range(1, 8):
            button = QPushButton(f'V{valve}: Energize 500 ms')
            button.setMinimumHeight(40)
            button.setToolTip('Request a brief coil energize command. Actual valve position is not monitored.')
            button.clicked.connect(lambda _checked=False, valve=valve: self._act(lambda: self.session.pulse(valve)))
            grid.addWidget(button, (valve - 1) // 2, (valve - 1) % 2)
            self.pulse_buttons.append(button)
        layout.addLayout(grid)
        footer = QLabel('Commands do not confirm valve motion or contact state. '
                        'The firmware limits each pulse and withdraws arming after heartbeat loss. '
                        'Stop, close or disconnect clears all confirmations. '
                        "Dr. Onita Basu's lab · Carleton University.")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        row = QHBoxLayout()
        self.stop_button = QPushButton('STOP and disconnect')
        self.stop_button.setObjectName('stopButton')
        self.stop_button.setMinimumHeight(46)
        self.stop_button.clicked.connect(self.disconnect_board)
        self.close_button = QPushButton('Close')
        self.close_button.clicked.connect(self.reject)
        row.addWidget(self.stop_button, 1)
        row.addWidget(self.close_button)
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
        self.session.detach('Stop requested; disconnected and stopped sending heartbeats. Repeat the checks to test again.')
        self._render()

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
        self.stop_button.setEnabled(live and connected)
        self.refresh_button.setEnabled(live and not connected)
        self.port_combo.setEnabled(live and not connected)
        self.status_label.setText(session.error or session.message)
        if session.verified:
            label = 'Reviewed valve profile' if session.valve_profile_verified else 'LOCKED: no reviewed valve profile'
            self.profile_label.setText(f'{label}: {session.profile_id or "not assigned"} | Firmware {session.firmware_version}')
            self.mapping_label.setText('Valve mapping: supplied by the reviewed firmware profile.'
                if session.valve_profile_verified else
                'Valve mapping: not approved for valve testing. Record the bare-board mapping, then review the compiled profile.')
        else:
            self.profile_label.setText('Profile: not connected or not identified')
            self.mapping_label.setText('Valve mapping: not identified. A reviewed compiled profile is required.')
        if session.status and session.status['state'] == 'pulsing':
            self.output_label.setText(f"Command: V{session.status['active_valve']} energized, "
                                      f"{session.status['remaining_ms']} ms remaining. Valve motion is not monitored.")
        else:
            self.output_label.setText('Command: no pulse active. Actual valve and contact states are not monitored.')
        for name, checkbox in self.attestation_checkboxes.items():
            with QSignalBlocker(checkbox):
                checkbox.setChecked(session.attestations[name])
            checkbox.setEnabled(live and session.fresh and session.valve_profile_verified)
        self.arm_button.setEnabled(live and session.can_arm)
        for button in self.pulse_buttons:
            button.setEnabled(live and session.can_pulse)

    def shutdown(self):
        if self._shutdown_done:
            return
        self._shutdown_done = True
        try:
            self.timer.stop()
        except RuntimeError:
            pass
        self.session.detach('Valve test closed; disconnected and stopped sending heartbeats.')
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

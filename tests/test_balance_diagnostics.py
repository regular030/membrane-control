"""Nimbus formats and raw diagnostic I/O, using fake ports only."""
import os
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
import serial
from PySide6.QtWidgets import QApplication

from membrane_control.balance import parse_mass
from membrane_control.balance_diagnostics import BalanceDiagnosticsDialog, BalanceDiagnosticsSession
from membrane_control.transport import SerialTransport
from test_transport import BlockingInstrument, Instrument, wait_for


@pytest.mark.parametrize('line, grams', [
    ('Net: 123.4 g', 123.4), ('\x01Net: + 12,34 g\x04', 12.34),
    ('12,345 g', 12.345), ('Net: - 0,5 kg', -500), ('Net: 10 mg', .01),
    ('\x01 0.0 g\r\n\x04', 0), ('ST, Net: 1.5 g', 1.5),
    ('+\t12.3 g', 12.3),
])
def test_documented_net_decimal_and_report_boundaries(line, grams):
    assert parse_mass(line) == pytest.approx(grams)


@pytest.mark.parametrize('line', [
    'Gross: 123 g', 'Tare: 1 g', 'Ref. wt: 1 g', 'Unit wt: 1 g',
    'ID No: 123456', 'DATE 23/09/04', '12.3 %', '123 pcs', '1 g/cc',
    '1,234.56 g', '1,2,3 g', 'Net: nan g', 'Net: 5 g garbage', 'Nett: 5 g',
])
def test_other_report_fields_and_ambiguous_numbers_remain_rejected(line):
    with pytest.raises(ValueError):
        parse_mass(line)


@pytest.fixture
def raw_instrument(monkeypatch):
    device = Instrument()
    settings = {}
    def create(**kwargs):
        settings.update(kwargs)
        return device
    monkeypatch.setattr(serial, 'Serial', create)
    return device, settings


@pytest.mark.parametrize('serial_format,bits,parity', [('8N1', 8, 'N'), ('7E1', 7, 'E'), ('7O1', 7, 'O')])
def test_balance_serial_settings_match_nimbus_without_reset_toggles(raw_instrument, serial_format, bits, parity):
    device, settings = raw_instrument
    worker = SerialTransport('FAKE-SCALE', 9600, raw=True, serial_format=serial_format)
    try:
        wait_for(worker, lambda packets: any(p['type'] == 'port_open' for p in packets))
        assert settings['bytesize'] == bits and settings['parity'] == parity
        assert settings['stopbits'] == 1 and settings['baudrate'] == 9600
        assert device.opened_lines == (True, False)
        assert settings['rtscts'] is settings['dsrdtr'] is settings['xonxoff'] is False
    finally:
        worker.close()


def test_raw_cr_lf_and_split_crlf_each_produce_one_line(raw_instrument):
    device, _ = raw_instrument
    worker = SerialTransport('FAKE-SCALE', raw=True)
    try:
        device.input.put(b'+1 g\r')
        device.input.put(b'\n+2 g\n+3 g\r+4 g\r\n')
        packets = wait_for(worker, lambda events: sum(p['type'] == 'mass_line' for p in events) >= 4)
        assert [p['line'] for p in packets if p['type'] == 'mass_line'] == ['+1 g', '+2 g', '+3 g', '+4 g']
    finally:
        worker.close()


def test_raw_dtr_override_is_applied_before_open_and_closed_normally(raw_instrument):
    device, _ = raw_instrument
    worker = SerialTransport('FAKE-SCALE', raw=True, dtr=False)
    try:
        wait_for(worker, lambda packets: any(p['type'] == 'port_open' for p in packets))
        assert device.opened_lines == (False, False)
    finally:
        worker.close()
    assert device.closed


def test_partial_or_undecodable_bytes_are_visible_before_a_complete_mass(raw_instrument):
    device, _ = raw_instrument
    worker = SerialTransport('FAKE-SCALE', raw=True, diagnostics=True)
    try:
        device.input.put(b'\xff\x00')
        packets = wait_for(worker, lambda events: any(p['type'] == 'serial_raw' for p in events))
        assert {'type': 'serial_raw', 'data': b'\xff\x00'} in packets
        assert not any(p['type'] == 'mass_line' for p in packets)
        device.input.put(b'\rNet: 2,5 g\r\n')
        packets = wait_for(worker, lambda events: any(p['type'] == 'mass_line' for p in events))
        assert any(p['type'] == 'parse_error' for p in packets)
        assert [p['line'] for p in packets if p['type'] == 'mass_line'] == ['Net: 2,5 g']
    finally:
        worker.close()


def test_request_writes_only_documented_print_bytes_and_closed_transport_rejects(raw_instrument):
    device, _ = raw_instrument
    worker = SerialTransport('FAKE-SCALE', raw=True)
    try:
        wait_for(worker, lambda packets: any(p['type'] == 'port_open' for p in packets))
        assert device.writes == []
        worker.request_reading()
        deadline = time.monotonic() + 2
        while not device.writes and time.monotonic() < deadline:
            time.sleep(.005)
        assert device.writes == [b'!KP\r']
    finally:
        worker.close()
    with pytest.raises(RuntimeError):
        worker.request_reading()
    assert device.writes == [b'!KP\r']  # Closing never sends a JSON STOP to the scale.


def test_request_cannot_queue_while_the_driver_is_still_opening(monkeypatch):
    device = BlockingInstrument('open')
    monkeypatch.setattr(serial, 'Serial', lambda **_kwargs: device)
    worker = SerialTransport('FAKE-SCALE', raw=True)
    try:
        assert device.open_entered.wait(1)
        with pytest.raises(RuntimeError, match='not open'):
            worker.request_reading()
        assert device.writes == []
    finally:
        device.release_open.set()
        worker.close()


def test_failed_balance_request_preserves_the_original_port_error(monkeypatch):
    class FailingInstrument(Instrument):
        def read(self, _count):
            raise OSError('FAKE cable failure')
    device = FailingInstrument()
    monkeypatch.setattr(serial, 'Serial', lambda **_kwargs: device)
    worker = SerialTransport('FAKE-SCALE', raw=True)
    try:
        wait_for(worker, lambda events: any(p['type'] == 'disconnected' for p in events))
        with pytest.raises(RuntimeError, match='FAKE cable failure'):
            worker.request_reading()
    finally:
        worker.close()


def test_json_controller_framing_and_command_queue_remain_separate(raw_instrument):
    device, _ = raw_instrument
    worker = SerialTransport('FAKE-CONTROLLER')
    try:
        with pytest.raises(ValueError, match='balance'):
            worker.request_reading()
        device.input.put(b'{"type":"one"}\r{"type":"two"}\n{"type":"recovered"}\n')
        events = wait_for(worker, lambda packets: any(p.get('type') == 'recovered' for p in packets))
        assert any(p['type'] == 'parse_error' for p in events)
        assert not any(p['type'] in ('one', 'two', 'serial_raw') for p in events)
    finally:
        worker.close()
    with pytest.raises(ValueError):
        SerialTransport('DO-NOT-OPEN', serial_format='7E1')
    with pytest.raises(ValueError):
        SerialTransport('DO-NOT-OPEN', diagnostics=True)
    with pytest.raises(ValueError):
        SerialTransport('DO-NOT-OPEN', dtr=True)


class FakeTransport:
    def __init__(self, port='FAKE-SCALE', baud=9600, **kwargs):
        self.port, self.baud, self.kwargs = port, baud, kwargs
        self.events = []
        self.requests = self.close_count = 0

    def poll(self, _now=None):
        events, self.events = self.events, []
        return events

    def request_reading(self):
        self.requests += 1

    def close(self):
        self.close_count += 1

    def send(self, _message):
        pytest.fail('A scale must never receive controller JSON or other commands')


@pytest.fixture
def session():
    now = [100.0]
    transport = FakeTransport()
    tracker = []
    def create(port, baud, **kwargs):
        tracker.append((port, baud, kwargs))
        return transport
    active = BalanceDiagnosticsSession(create, lambda: now[0])
    yield active, transport, now, tracker
    active.disconnect()


def test_session_never_auto_connects_or_requests_and_needs_open_event(session):
    active, transport, _, tracker = session
    active.tick()
    assert not tracker and transport.requests == 0
    active.connect('COM6', 9600, '7E1')
    assert tracker == [('COM6', 9600, dict(raw=True, serial_format='7E1', diagnostics=True, dtr=True))]
    assert not active.can_request and not active.fresh
    with pytest.raises(ValueError):
        active.request_reading()
    transport.events.append({'type': 'port_open'})
    active.tick()
    assert active.can_request and 'NO BYTES' in active.status
    active.request_reading()
    assert transport.requests == 1 and not active.can_request


def test_raw_line_and_mass_counts_distinguish_no_data_from_rejected_data(session):
    active, transport, now, _ = session
    active.connect('COM6')
    transport.events.extend([{'type': 'port_open'}, {'type': 'serial_raw', 'data': b'Gross: 12 g\r'},
                             {'type': 'mass_line', 'line': 'Gross: 12 g'}])
    active.tick()
    assert active.bytes_received == 12 and active.lines_received == 1 and active.mass_readings == 0
    assert 'no usable net mass' in active.status and active.last_mass_g is None
    transport.events.extend([{'type': 'serial_raw', 'data': b'Net: 0,0 g\r'},
                             {'type': 'mass_line', 'line': 'Net: 0,0 g'}])
    active.tick()
    assert active.lines_received == 2 and active.mass_readings == 1 and active.last_mass_g == 0
    assert active.fresh and 'Valid mass' in active.status
    now[0] += 3.01
    active.tick()
    assert not active.fresh and 'stale' in active.status
    assert transport.requests == 0


def test_raw_errors_and_bounded_logs_retain_evidence_without_fabricated_mass(session):
    active, transport, _, _ = session
    active.connect('COM6')
    transport.events.extend([{'type': 'port_open'}, {'type': 'serial_raw', 'data': b'\xff\x00'},
                             {'type': 'parse_error', 'error': 'Malformed serial data'}])
    active.tick()
    assert active.bytes_received == 2 and active.lines_received == active.mass_readings == 0
    assert 'invalid' in active.status and active.decode_errors == 1
    log = '\n'.join(active.drain_log())
    assert 'ff 00' in log and r'\xff\x00' in log
    for i in range(1000):
        active.log(f'{i} ' + 'x' * 10000)
    assert len(active.pending_log) == 600
    assert all(len(line) <= 7000 for line in active.pending_log)
    assert active.last_mass_g is None


def test_disconnect_and_failure_stop_requests_and_close_once(session):
    active, transport, now, _ = session
    active.connect('COM6')
    transport.events.append({'type': 'port_open'})
    active.tick()
    active.request_reading()
    transport.events.append({'type': 'disconnected', 'error': 'FAKE unplug'})
    active.tick()
    assert active.transport is None and 'FAKE unplug' in active.status
    assert transport.close_count == 1
    now[0] += 10
    active.tick()
    active.disconnect()
    assert transport.requests == 1 and transport.close_count == 1


@pytest.fixture(scope='module')
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(qt_app):
    now = [100.0]
    transport = FakeTransport()
    widget = BalanceDiagnosticsDialog(selected_port='COM6', selected_baud=9600,
        selected_format='8N1', excluded_ports={'COM4'},
        port_lister=lambda: [('COM4', 'ESP32'), ('COM6', 'Scale')],
        transport_factory=lambda *_a, **_k: transport, clock=lambda: now[0])
    widget.timer.stop()
    yield widget, transport, now
    widget.close()


def test_dialog_preserves_com6_settings_and_shows_actual_raw_and_mass_counts(dialog):
    widget, transport, _ = dialog
    assert widget.session.transport is None and transport.requests == 0
    assert widget.port_combo.currentData() == 'COM6' and widget.port_combo.findData('COM4') == -1
    assert widget.baud_combo.currentData() == 9600 and widget.format_combo.currentData() == '8N1'
    assert widget.dtr_checkbox.isChecked()
    assert widget.baud_combo.findData(4800) >= 0
    widget.connect_button.click()
    assert not widget.request_button.isEnabled()
    transport.events.append({'type': 'port_open'})
    widget._tick()
    widget.request_button.click()
    assert transport.requests == 1 and not widget.request_button.isEnabled()
    transport.events.extend([{'type': 'serial_raw', 'data': b'Net: 12,3 g\r'},
                             {'type': 'mass_line', 'line': 'Net: 12,3 g'}])
    widget._tick()
    assert '12.3 g' in widget.mass_label.text()
    assert 'Valid masses: 1' in widget.count_label.text()
    assert 'hex=' in widget.raw_log.toPlainText() and r'\r' in widget.raw_log.toPlainText()
    assert widget.raw_log.isReadOnly() and widget.raw_log.maximumBlockCount() == 600


@pytest.mark.parametrize('ending', ['close', 'reject', 'accept', 'done', 'quit'])
def test_dialog_all_quit_paths_close_the_port_without_polling_or_commands(dialog, ending):
    widget, transport, now = dialog
    widget.connect_button.click()
    transport.events.append({'type': 'port_open'})
    widget._tick()
    if ending == 'quit':
        widget._quit_application.aboutToQuit.emit()
    elif ending == 'done':
        widget.done(0)
    else:
        getattr(widget, ending)()
    assert transport.close_count == 1 and widget.session.transport is None
    assert not widget.timer.isActive()
    now[0] += 10
    widget._tick()
    assert transport.requests == 0

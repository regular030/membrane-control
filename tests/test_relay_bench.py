"""Real-relay test protocol and Qt gates, using only a fake serial transport."""
import copy
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from membrane_control.controller import AppController
from membrane_control.relay_bench import RelayBenchDialog, RelayBenchSession
from membrane_control.ui import MainWindow


class FakeTransport:
    def __init__(self, port='FAKE-ONLY', baud=115200):
        self.port, self.baud = port, baud
        self.sent = []
        self.events = []
        self.closed = False
        self.close_count = 0

    def send(self, packet):
        assert not self.closed
        self.sent.append(copy.deepcopy(packet))

    def poll(self, _now=None):
        events, self.events = self.events, []
        return events

    def close(self):
        self.closed = True
        self.close_count += 1

    def last(self, command):
        return next(packet for packet in reversed(self.sent) if packet['cmd'] == command)


def identity(request_id, **updates):
    return {'v': 1, 'id': request_id, 'type': 'hello', 'ok': True,
            'device': 'membrane-relay-bench', 'protocol_version': 1,
            'relay_count': 16, 'simulation': False, 'hardware_verified': False, **updates}


def ack(request_id, **updates):
    return {'v': 1, 'id': request_id, 'type': 'ack', 'ok': True, **updates}


def status(**updates):
    return {'v': 1, 'type': 'bench_status', 'uptime_ms': 1000,
            'state': 'disarmed', 'outputs_enabled': False, 'baseline_confirmed': False,
            'baseline_word': 0, 'probe_completed': False, 'probe_id': 0,
            'pulse_bit': None, 'remaining_ms': 0, 'simulation': False,
            'hardware_verified': False, 'fault': None, **updates}


def connect_verified(session, transport):
    session.connect('FAKE-ONLY')
    transport.events.append(identity(transport.last('hello')['id']))
    session.tick()
    transport.events.extend([ack(transport.last('heartbeat')['id']), status()])
    session.tick()


def complete_probe(session, transport, baseline=0):
    session.attest_loads(True)
    session.probe(baseline)
    probe_id = transport.last('bench_probe')['id']
    transport.events.extend([ack(probe_id), status(probe_id=probe_id, probe_completed=True,
                                                  baseline_word=baseline)])
    session.tick()
    assert session.can_confirm
    return probe_id


def arm(session, transport, baseline=0):
    probe_id = complete_probe(session, transport, baseline)
    session.confirm_observation()
    transport.events.extend([ack(transport.last('bench_confirm')['id']),
        status(state='ready', baseline_confirmed=True, probe_id=probe_id,
               probe_completed=True, baseline_word=baseline)])
    session.tick()
    assert session.can_pulse
    return probe_id


@pytest.fixture
def bench():
    now = [100.0]
    transport = FakeTransport()
    session = RelayBenchSession(lambda *_args: transport, lambda: now[0])
    yield session, transport, now
    session.detach()


def test_connection_never_arms_or_sends_output_commands(bench):
    session, transport, _ = bench
    session.connect('FAKE-ONLY')
    assert [packet['cmd'] for packet in transport.sent] == ['hello']
    assert not session.can_probe and not session.can_pulse and not session.loads_disconnected
    assert not session.verified


def test_hello_and_fresh_status_require_heartbeat_ack_before_probe(bench):
    session, transport, _ = bench
    session.connect('FAKE-ONLY')
    transport.events.extend([identity(transport.last('hello')['id']), status()])
    session.tick()
    session.attest_loads(True)
    assert not session.can_probe
    transport.events.append(ack(transport.last('heartbeat')['id']))
    session.tick()
    assert session.can_probe
    assert not session.can_pulse


@pytest.mark.parametrize('updates', [
    {'device': 'basu-membrane-control'}, {'device': 'anything'},
    {'protocol_version': True}, {'protocol_version': 2}, {'relay_count': 8},
    {'relay_count': True}, {'simulation': True}, {'hardware_verified': True},
    {'simulation': 0}, {'hardware_verified': 0}, {'ok': False},
])
def test_wrong_or_malformed_identity_detaches_without_output_commands(bench, updates):
    session, transport, _ = bench
    session.connect('FAKE-ONLY')
    transport.events.append(identity(transport.last('hello')['id'], **updates))
    session.tick()
    assert transport.closed and session.transport is None
    assert session.error and not session.verified
    assert {packet['cmd'] for packet in transport.sent} <= {'hello', 'stop'}


def test_single_pulse_requires_own_completed_acked_and_observed_probe(bench):
    session, transport, _ = bench
    connect_verified(session, transport)
    session.attest_loads(True)
    session.probe(65535)
    probe_id = transport.last('bench_probe')['id']
    assert transport.last('bench_probe') == {'v': 1, 'id': probe_id, 'cmd': 'bench_probe',
        'baseline_word': 65535, 'duration_ms': 500, 'loads_disconnected': True}
    # Neither old completed telemetry nor missing ACK can unlock confirmation.
    transport.events.append(status(probe_completed=True, probe_id=probe_id + 99, baseline_word=65535))
    session.tick()
    assert not session.can_confirm
    transport.events.append(status(probe_completed=True, probe_id=probe_id, baseline_word=65535))
    session.tick()
    assert not session.can_confirm
    transport.events.append(ack(probe_id))
    session.tick()
    assert session.can_confirm and not session.can_pulse
    assert not any(packet['cmd'] == 'bench_confirm' for packet in transport.sent)
    session.confirm_observation()
    confirm = transport.last('bench_confirm')
    assert confirm['probe_id'] == probe_id and confirm['all_relays_off'] is True
    assert confirm['loads_disconnected'] is True and confirm['baseline_word'] == 65535
    transport.events.append(ack(confirm['id']))
    session.tick()
    assert not session.can_pulse  # ACK alone does not prove ready telemetry.
    transport.events.append(status(state='ready', baseline_confirmed=True, probe_completed=True,
                                    probe_id=probe_id, baseline_word=65535))
    session.tick()
    assert session.can_pulse
    session.pulse(15)
    assert transport.last('bench_pulse')['bit'] == 15
    assert transport.last('bench_pulse')['duration_ms'] == 500
    transport.events.append(ack(transport.last('bench_pulse')['id']))
    session.tick()
    assert not session.can_pulse  # Keep a single transaction through completion.
    transport.events.append(status(state='pulsing', outputs_enabled=True, pulse_bit=15,
        remaining_ms=400, baseline_confirmed=True, probe_completed=True,
        probe_id=probe_id, baseline_word=65535))
    session.tick()
    transport.events.append(status(state='ready', baseline_confirmed=True, probe_completed=True,
                                    probe_id=probe_id, baseline_word=65535))
    session.tick()
    assert session.can_pulse


def test_busy_operation_cannot_queue_another_pulse(bench):
    session, transport, _ = bench
    connect_verified(session, transport)
    arm(session, transport)
    session.pulse(2)
    with pytest.raises(ValueError):
        session.pulse(3)
    assert len([packet for packet in transport.sent if packet['cmd'] == 'bench_pulse']) == 1


def test_probe_timeout_withdraws_heartbeats_and_preserves_first_error(bench):
    session, transport, now = bench
    connect_verified(session, transport)
    session.attest_loads(True)
    session.probe(0)
    now[0] += 1.6
    session.tick()
    assert session.transport is None and transport.closed
    assert session.pending == {} and session.operation is None
    assert 'timed out' in session.error
    original_error = session.error
    session.detach('Generic disconnected text')
    now[0] += 10
    session.tick()
    assert session.message == original_error
    assert transport.sent[-1]['cmd'] == 'stop'


def test_disconnect_during_pulse_has_no_queued_output_or_automatic_reconnect(bench):
    session, transport, now = bench
    connect_verified(session, transport)
    arm(session, transport)
    session.pulse(0)
    transport.events.append({'type': 'disconnected', 'error': 'Test cable removed'})
    session.tick()
    assert session.transport is None and session.error == 'Test cable removed'
    assert not session.loads_disconnected and not session.confirmed and not session.observed
    assert session.pending == {} and session.probe_id is None
    count = len(transport.sent)
    now[0] += 100
    session.tick()
    assert len(transport.sent) == count
    with pytest.raises(ValueError):
        session.pulse(1)


@pytest.mark.parametrize('changes', [
    {'simulation': True}, {'hardware_verified': True}, {'outputs_enabled': True},
    {'probe_completed': 1}, {'baseline_word': 3}, {'remaining_ms': 3000},
    {'pulse_bit': 0}, {'state': 'ready', 'baseline_confirmed': False},
    {'type': 'telemetry'}, {'v': True},
])
def test_invalid_status_or_unexpected_mode_detaches(bench, changes):
    session, transport, _ = bench
    connect_verified(session, transport)
    transport.events.append(status(**changes))
    session.tick()
    assert session.transport is None and session.error


def test_unsolicited_ack_cannot_authorize_any_operation(bench):
    session, transport, _ = bench
    connect_verified(session, transport)
    transport.events.append(ack(0xffffff))
    session.tick()
    assert session.transport is None
    assert 'Unexpected' in session.error


def test_negative_ack_preserves_firmware_error(bench):
    session, transport, _ = bench
    connect_verified(session, transport)
    session.attest_loads(True)
    session.probe(0)
    transport.events.append({'v': 1, 'id': transport.last('bench_probe')['id'],
                             'type': 'error', 'ok': False, 'error': 'Fresh heartbeat required'})
    session.tick()
    assert 'Fresh heartbeat required' in session.error
    assert session.transport is None


def test_wrong_pulse_bit_or_reset_is_not_accepted(bench):
    session, transport, _ = bench
    connect_verified(session, transport)
    probe_id = arm(session, transport)
    session.pulse(1)
    transport.events.append(status(state='pulsing', outputs_enabled=True, pulse_bit=2,
        remaining_ms=500, baseline_confirmed=True, probe_completed=True, probe_id=probe_id))
    session.tick()
    assert session.transport is None and 'Unexpected raw relay bit' in session.error


def test_hello_and_status_timeouts_are_bounded(bench):
    session, transport, now = bench
    session.connect('FAKE-ONLY')
    now[0] += 8.1
    session.tick()
    assert session.transport is None and 'HELLO timed out after 8 s' in session.error
    assert 'release IO0/BOOT' in session.error and 'EN/RESET' in session.error


def test_prehello_stale_fault_and_active_frames_cannot_abort_or_authorize_new_session(bench):
    session, transport, _ = bench
    session.connect('FAKE-ONLY')
    transport.events.extend([
        status(state='fault', fault='heartbeat_timeout', uptime_ms=50000),
        status(state='pulsing', outputs_enabled=True, pulse_bit=4, remaining_ms=100,
               probe_id=99, probe_completed=True, baseline_confirmed=True),
        {'type': 'parse_error', 'error': 'ROM text is not JSON'},
        {'v': 1, 'type': 'error', 'ok': False, 'id': 0, 'error': 'invalid JSON'},
        identity(transport.last('hello')['id']), status(uptime_ms=10),
    ])
    session.tick()
    assert session.transport is transport and session.verified and not session.error
    assert not session.can_probe and not session.can_pulse
    assert {packet['cmd'] for packet in transport.sent} == {'hello', 'heartbeat'}
    transport.events.append(ack(transport.last('heartbeat')['id']))
    session.tick()
    assert session.fresh and not session.loads_disconnected
    transport.events.append(status(state='fault', fault='heartbeat_timeout', uptime_ms=11))
    session.tick()
    assert session.transport is None and session.error == 'heartbeat_timeout'


def test_hello_retry_is_bounded_and_only_latest_response_identifies(bench):
    session, transport, now = bench
    session.connect('FAKE-ONLY')
    first_id = transport.last('hello')['id']
    now[0] += 1
    session.tick()
    latest_id = transport.last('hello')['id']
    assert latest_id != first_id and len(session.pending) == 1
    transport.events.append(identity(first_id))
    session.tick()
    assert not session.verified
    assert not any(packet['cmd'] == 'heartbeat' for packet in transport.sent)
    transport.events.extend([identity(latest_id), status()])
    session.tick()
    transport.events.append(ack(transport.last('heartbeat')['id']))
    session.tick()
    arm(session, transport)
    heartbeat_ack = session.last_heartbeat_ack
    transport.events.append(identity(first_id))  # A late known reply must not reset the lease.
    session.tick()
    assert session.can_pulse and session.last_heartbeat_ack == heartbeat_ack
    now[0] += 0.5
    session.tick()
    assert len([packet for packet in transport.sent if packet['cmd'] == 'hello']) == 2
    with pytest.raises(ValueError, match='HELLO would disarm'):
        session._request('hello')


def test_boot_wait_never_retries_forever_or_sends_output_commands(bench):
    session, transport, now = bench
    session.connect('FAKE-ONLY')
    for _ in range(7):
        now[0] += 1
        transport.events.append({'type': 'parse_error'})
        session.tick()
        assert session.transport is transport and not session.verified
        assert len(session.pending) == 1
    now[0] += 1
    session.tick()
    assert session.transport is None
    hello_ids = [packet['id'] for packet in transport.sent if packet['cmd'] == 'hello']
    assert len(hello_ids) == len(set(hello_ids)) == 8
    assert {packet['cmd'] for packet in transport.sent} == {'hello', 'stop'}
    assert transport.close_count == 1


def test_prehello_matching_error_is_not_hidden_by_boot_tolerance(bench):
    session, transport, _ = bench
    session.connect('FAKE-ONLY')
    transport.events.append({'v': 1, 'type': 'error', 'ok': False,
                            'id': transport.last('hello')['id'], 'error': 'unsupported firmware'})
    session.tick()
    assert session.transport is None and 'unsupported firmware' in session.error


def test_retired_hello_still_cannot_claim_an_unexpected_firmware_mode(bench):
    session, transport, now = bench
    session.connect('FAKE-ONLY')
    first_id = transport.last('hello')['id']
    now[0] += 1
    session.tick()
    transport.events.append(identity(first_id, simulation=True))
    session.tick()
    assert session.transport is None and 'Not the 16-channel' in session.error


def test_framing_error_is_not_tolerated_after_identification(bench):
    session, transport, _ = bench
    connect_verified(session, transport)
    transport.events.append({'v': 1, 'type': 'error', 'ok': False, 'id': 0, 'error': 'invalid JSON'})
    session.tick()
    assert session.transport is None and session.error


def test_stale_status_detaches_even_with_heartbeat_ack(bench):
    session, transport, now = bench
    connect_verified(session, transport)
    now[0] += 1.3
    session.tick()
    assert session.transport is None and 'status is stale' in session.error


@pytest.fixture(scope='module')
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(qt_app):
    now = [100.0]
    transport = FakeTransport()
    widget = RelayBenchDialog(selected_port='FAKE-ONLY',
        port_lister=lambda: [('FAKE-ONLY', 'Test double')],
        transport_factory=lambda *_args: transport, clock=lambda: now[0])
    widget.timer.stop()
    yield widget, transport, now
    widget.close()


def test_dialog_connects_only_on_explicit_click_and_requires_observation(dialog):
    widget, transport, _ = dialog
    assert widget.session.transport is None and transport.sent == []
    assert all(button.text() == f'Bit {bit}' for bit, button in enumerate(widget.pulse_buttons))
    assert all(not button.isEnabled() for button in widget.pulse_buttons)
    assert not widget.loads_checkbox.isChecked()
    widget.connect_button.click()
    assert widget.stop_button.isEnabled()
    transport.events.append(identity(transport.last('hello')['id']))
    widget._tick()
    transport.events.extend([ack(transport.last('heartbeat')['id']), status()])
    widget._tick()
    widget.loads_checkbox.click()
    widget.probe_button.click()
    probe_id = transport.last('bench_probe')['id']
    transport.events.extend([ack(probe_id), status(probe_id=probe_id, probe_completed=True)])
    widget._tick()
    assert widget.observation_checkbox.isEnabled()
    assert not any(packet['cmd'] == 'bench_confirm' for packet in transport.sent)
    widget.observation_checkbox.click()
    transport.events.extend([ack(transport.last('bench_confirm')['id']), status(
        state='ready', baseline_confirmed=True, probe_completed=True, probe_id=probe_id)])
    widget._tick()
    assert all(button.isEnabled() for button in widget.pulse_buttons)
    assert 'not monitored' in widget.output_label.text()
    widget.pulse_buttons[0].click()
    widget.pulse_buttons[1].click()
    assert len([packet for packet in transport.sent if packet['cmd'] == 'bench_pulse']) == 1
    assert all(not button.isEnabled() for button in widget.pulse_buttons)


def test_dialog_close_clears_attestations_and_withdraws_heartbeat(dialog):
    widget, transport, now = dialog
    connect_verified(widget.session, transport)
    arm(widget.session, transport)
    widget._render()
    widget.reject()
    assert transport.closed and not widget.timer.isActive()
    assert not widget.loads_checkbox.isChecked() and not widget.session.loads_disconnected
    assert not widget.observation_checkbox.isChecked()
    assert widget.session.probe_id is None and not widget.session.confirmed
    count = len(transport.sent)
    now[0] += 10
    widget._tick()
    assert len(transport.sent) == count


def test_withdrawing_load_confirmation_disconnects_during_operation(dialog):
    widget, transport, _ = dialog
    connect_verified(widget.session, transport)
    arm(widget.session, transport)
    widget._render()
    widget.pulse_buttons[3].click()
    widget.loads_checkbox.click()
    assert widget.session.transport is None and transport.closed
    assert not widget.observation_checkbox.isChecked()


def test_dialog_excludes_known_scale_port(qt_app):
    widget = RelayBenchDialog(selected_port='SCALE-ONLY', excluded_ports={'SCALE-ONLY'},
        port_lister=lambda: [('SCALE-ONLY', 'Scale'), ('FAKE-ONLY', 'Bench')],
        transport_factory=lambda *_args: pytest.fail('No connection requested'))
    widget.timer.stop()
    assert widget.port_combo.findData('SCALE-ONLY') == -1
    widget.close()


def test_main_window_entry_requires_explicit_hardware_mode_and_idle(qt_app, tmp_path, monkeypatch):
    controller = AppController(tmp_path)
    controller.list_ports = lambda: [('FAKE-ONLY', 'Bench')]
    window = MainWindow(controller)
    window.timer.stop()
    opened = []

    class FakeDialog:
        def __init__(self, _parent, **kwargs):
            opened.append(kwargs)

        def exec(self):
            assert controller.driver is None  # No production owner retains the COM port.

        def shutdown(self):
            pass

        def deleteLater(self):
            pass

    monkeypatch.setattr('membrane_control.ui.RelayBenchDialog', FakeDialog)
    try:
        assert window.lab_credit.text() == "Dr. Onita Basu's lab · Carleton University"
        window._update_view(dict(controller.snapshot))
        assert not window.relay_bench_button.isEnabled()
        original_driver = controller.driver
        window._open_relay_bench()
        assert opened == [] and controller.driver is original_driver
        controller.set_simulation(False)
        controller.snapshot['state'] = 'manual'
        window._open_relay_bench()
        assert opened == []
        controller.snapshot['state'] = 'idle'
        window._update_view(dict(controller.snapshot))
        assert window.relay_bench_button.isEnabled()
        window._open_relay_bench()
        assert opened[0]['selected_port'] == 'FAKE-ONLY'
        assert controller.snapshot['hardware_verified'] is False
        assert controller.simulation is False
    finally:
        window.close()


def test_bench_identity_does_not_unlock_production_controller(tmp_path):
    controller = AppController(tmp_path)
    controller.set_simulation(False)
    controller.driver = FakeTransport()
    request_id = controller._request('hello')
    controller._handle_packet(identity(request_id), controller.clock())
    assert not controller.snapshot['controller_connected']
    assert not controller.snapshot['hardware_verified']
    assert controller.device == {}
    with pytest.raises(ValueError):
        controller.start_run()
    with pytest.raises(ValueError):
        controller.set_manual([True] * 7, 20)
    controller.close()

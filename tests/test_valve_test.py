"""Sensorless valve-test protocol, entirely with fake ports and clocks."""
import copy

import pytest

from membrane_control.valve_test import ValveTestSession


class FakeTransport:
    def __init__(self, *_args):
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
            'device': 'membrane-valve-test', 'mode': 'valve_test', 'protocol_version': 1,
            'firmware_version': '0.1.12', 'valve_count': 7, 'simulation': False,
            'hardware_verified': False, 'valve_profile_verified': True,
            'profile_id': 'TEST-ONLY-FAKE-PROFILE', **updates}


def ack(request_id, **updates):
    return {'v': 1, 'id': request_id, 'type': 'ack', 'ok': True, **updates}


def status(**updates):
    return {'v': 1, 'type': 'valve_test_status', 'uptime_ms': 1000, 'state': 'disarmed',
            'profile_id': 'TEST-ONLY-FAKE-PROFILE', 'valve_profile_verified': True,
            'outputs_enabled': False, 'active_valve': 0, 'remaining_ms': 0,
            'fault': None, 'simulation': False, 'hardware_verified': False, **updates}


def connect_verified(session, transport, *, locked=False):
    session.connect('FAKE-ONLY')
    updates = dict(valve_profile_verified=False, profile_id='UNVERIFIED') if locked else {}
    transport.events.append(identity(transport.last('hello')['id'], **updates))
    session.tick()
    transport.events.extend([ack(transport.last('heartbeat')['id']), status(
        **updates, **(dict(state='locked', fault='No reviewed profile') if locked else {}))])
    session.tick()


def arm(session, transport):
    for name in session.attestations:
        session.attest(name, True)
    session.arm()
    transport.events.extend([ack(transport.last('valve_arm')['id']), status(state='ready')])
    session.tick()
    assert session.can_pulse


@pytest.fixture
def valve_session():
    now = [100.0]
    transport = FakeTransport()
    session = ValveTestSession(lambda *_args: transport, lambda: now[0])
    yield session, transport, now
    session.detach()


def test_connect_never_arms_and_locked_profile_stays_visible_without_sensor_dependencies(valve_session):
    session, transport, _ = valve_session
    connect_verified(session, transport, locked=True)
    assert session.transport is transport and session.verified
    assert not session.error and not session.valve_profile_verified
    assert 'Locked' in session.message and 'compiled' in session.message
    assert not session.can_arm and not session.can_pulse
    assert {message['cmd'] for message in transport.sent} == {'hello', 'heartbeat'}
    with pytest.raises(ValueError):
        session.arm()
    with pytest.raises(ValueError):
        session.attest('wiring_checked', True)


@pytest.mark.parametrize('updates', [
    {'device': 'membrane-relay-bench'}, {'device': 'basu-membrane-control'},
    {'mode': 'production'}, {'protocol_version': True}, {'valve_count': 16},
    {'valve_count': True}, {'simulation': True}, {'hardware_verified': True},
    {'simulation': 0}, {'valve_profile_verified': 1}, {'profile_id': ''},
    {'profile_id': 'UNVERIFIED'}, {'profile_id': 'NOT A SAFE ID'}, {'firmware_version': None},
])
def test_wrong_identity_cannot_unlock_outputs(valve_session, updates):
    session, transport, _ = valve_session
    session.connect('FAKE-ONLY')
    transport.events.append(identity(transport.last('hello')['id'], **updates))
    session.tick()
    assert session.transport is None and transport.closed and session.error
    assert not session.armed and not session.can_arm and not session.can_pulse
    assert {message['cmd'] for message in transport.sent} <= {'hello', 'stop'}


def test_all_attestations_heartbeat_and_own_arm_ack_and_new_ready_status_required(valve_session):
    session, transport, _ = valve_session
    connect_verified(session, transport)
    for name in ('wiring_checked', 'pump_isolated'):
        session.attest(name, True)
    assert not session.can_arm
    session.attest('test_area_ready', True)
    saved_heartbeat = session.last_heartbeat_ack
    session.last_heartbeat_ack = None
    assert not session.can_arm
    session.last_heartbeat_ack = saved_heartbeat
    assert session.can_arm
    session.arm()
    request = transport.last('valve_arm')
    assert request == dict(v=1, id=request['id'], cmd='valve_arm',
        profile_id='TEST-ONLY-FAKE-PROFILE', wiring_checked=True,
        pump_isolated=True, test_area_ready=True)
    assert not session.can_pulse
    transport.events.append(ack(request['id']))
    session.tick()
    assert not session.can_pulse  # Initial disarmed telemetry cannot complete arm.
    transport.events.append(status(state='ready'))
    session.tick()
    assert session.can_pulse and session.armed


def test_one_bounded_pulse_requires_matching_active_state_before_reenabling(valve_session):
    session, transport, _ = valve_session
    connect_verified(session, transport)
    arm(session, transport)
    session.pulse(7)
    request = transport.last('valve_pulse')
    assert request == dict(v=1, id=request['id'], cmd='valve_pulse', valve=7, duration_ms=500)
    with pytest.raises(ValueError):
        session.pulse(1)
    transport.events.extend([ack(request['id']), status(state='ready')])
    session.tick()
    assert not session.can_pulse  # Cached idle/ready does not end a requested pulse.
    transport.events.append(status(state='pulsing', outputs_enabled=True, active_valve=7, remaining_ms=300))
    session.tick()
    assert not session.can_pulse
    transport.events.append(status(state='ready'))
    session.tick()
    assert session.can_pulse
    assert len([message for message in transport.sent if message['cmd'] == 'valve_pulse']) == 1


@pytest.mark.parametrize('changes', [
    {'profile_id': 'OTHER-PROFILE'}, {'valve_profile_verified': False},
    {'simulation': True}, {'hardware_verified': True}, {'outputs_enabled': True},
    {'active_valve': 1}, {'remaining_ms': 500}, {'uptime_ms': True},
    {'state': 'pulsing', 'outputs_enabled': True, 'active_valve': 1, 'remaining_ms': 500},
    {'state': 'ready'}, {'state': 'fault', 'fault': 'heartbeat_timeout'},
])
def test_changed_or_unexpected_status_detaches_without_actuation(valve_session, changes):
    session, transport, _ = valve_session
    connect_verified(session, transport)
    transport.events.append(status(**changes))
    session.tick()
    assert transport.closed and session.transport is None and session.error
    assert not session.can_pulse


def test_wrong_active_valve_and_board_reset_disconnect(valve_session):
    session, transport, _ = valve_session
    connect_verified(session, transport)
    arm(session, transport)
    session.pulse(2)
    transport.events.append(status(state='pulsing', outputs_enabled=True, active_valve=3, remaining_ms=400))
    session.tick()
    assert session.transport is None and 'Unexpected energized' in session.error


def test_reboot_and_uptime_wrap_are_distinguished(valve_session):
    session, transport, _ = valve_session
    connect_verified(session, transport)
    session.last_uptime = 0xfffffff0
    transport.events.append(status(uptime_ms=20))
    session.tick()
    assert session.transport is transport
    transport.events.append(status(uptime_ms=1))
    session.tick()
    assert session.transport is None and 'restarted' in session.error


def test_prehello_boot_and_old_fault_frames_never_authorize_and_retry_is_bounded(valve_session):
    session, transport, now = valve_session
    session.connect('FAKE-ONLY')
    first = transport.last('hello')['id']
    transport.events.extend([{'type': 'parse_error'}, status(state='fault', fault='old fault')])
    session.tick()
    assert session.transport is transport and not session.can_arm
    now[0] += 1.01
    session.tick()
    second = transport.last('hello')['id']
    assert second != first
    transport.events.extend([identity(first), identity(second)])
    session.tick()
    assert session.verified
    assert not session.can_arm
    assert len([message for message in transport.sent if message['cmd'] == 'hello']) == 2
    now[0] += 1.3
    session.tick()
    assert session.transport is None and 'stale' in session.error


def test_boot_timeout_does_not_retry_forever(valve_session):
    session, transport, now = valve_session
    session.connect('FAKE-ONLY')
    now[0] += 8.01
    session.tick()
    assert session.transport is None and 'EN/RESET' in session.error
    count = len(transport.sent)
    now[0] += 10
    session.tick()
    assert len(transport.sent) == count


@pytest.mark.parametrize('failure', ['ack_timeout', 'operation_timeout', 'stale', 'unplug'])
def test_failures_close_port_and_never_queue_or_resume_pulses(valve_session, failure):
    session, transport, now = valve_session
    connect_verified(session, transport)
    arm(session, transport)
    session.pulse(1)
    if failure != 'ack_timeout':
        transport.events.append(ack(transport.last('valve_pulse')['id']))
    if failure == 'ack_timeout':
        now[0] += 1.6
        transport.events.append(status(state='ready'))
    elif failure == 'operation_timeout':
        now[0] += 2.6
        transport.events.append(status(state='ready'))
    elif failure == 'stale':
        now[0] += 1.3
    else:
        transport.events.append({'type': 'disconnected', 'error': 'Test cable removed'})
    session.tick()
    assert session.error and session.transport is None and transport.closed
    assert not session.armed and not any(session.attestations.values())
    count = len(transport.sent)
    now[0] += 10
    session.tick()
    assert len(transport.sent) == count
    assert len([message for message in transport.sent if message['cmd'] == 'valve_pulse']) == 1


def test_withdrawn_attestation_stops_session_and_close_is_idempotent(valve_session):
    session, transport, _ = valve_session
    connect_verified(session, transport)
    arm(session, transport)
    session.attest('pump_isolated', False)
    assert session.transport is None and not any(session.attestations.values())
    assert transport.last('stop')
    session.detach()
    assert transport.close_count == 1


def test_unsolicited_ack_and_negative_ack_preserve_error(valve_session):
    session, transport, _ = valve_session
    connect_verified(session, transport)
    transport.events.append(ack(99999))
    session.tick()
    assert 'Unexpected' in session.error and session.transport is None


def test_negative_arm_ack_never_enables_pulses(valve_session):
    session, transport, _ = valve_session
    connect_verified(session, transport)
    for name in session.attestations:
        session.attest(name, True)
    session.arm()
    transport.events.append(dict(v=1, id=transport.last('valve_arm')['id'], type='error', ok=False, error='profile rejected'))
    session.tick()
    assert 'profile rejected' in session.error and not session.can_pulse


def test_posthello_wrong_telemetry_is_not_boot_noise(valve_session):
    session, transport, _ = valve_session
    connect_verified(session, transport)
    transport.events.append({'type': 'parse_error'})
    session.tick()
    assert session.error and session.transport is None

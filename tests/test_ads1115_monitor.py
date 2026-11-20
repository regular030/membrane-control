"""Separate USB sensor acquisition never shares the rig control protocol."""
import pytest

from membrane_control.ads1115_monitor import Ads1115Monitor, DEVICE


class Clock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now


class Transport:
    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.packets = []
        self.identity_requests = 0
        self.closed = False

    def poll(self, now=None):
        packets, self.packets = self.packets, []
        return packets

    def request_identity(self):
        self.identity_requests += 1

    def close(self):
        self.closed = True


def hello(uptime=100):
    return {'v': 1, 'device': DEVICE, 'type': 'hello', 'uptime_ms': uptime,
            'firmware': '0.1.28-ads1115-usb', 'sda_pin': 22, 'scl_pin': 21,
            'adc_address': 0x48, 'bus_ready': True}


def frame(uptime=300, *, ack=True, sequence=1):
    return {'v': 1, 'device': DEVICE, 'type': 'telemetry', 'uptime_ms': uptime,
            'sequence': sequence, 'adc_ack': ack, 'channels': {
                name: {'signal': signal, 'status': 'reading_received', 'raw': raw,
                       'volts': raw * .000125, 'sample_uptime_ms': uptime - 20}
                for name, signal, raw in [('A0', 'pressure', 1200), ('A1', 'flow', 4000),
                                          ('A2', 'pump_feedback', 12000)]}}


def connected():
    clock = Clock()
    session = Ads1115Monitor(Transport, clock)
    session.connect('COM5')
    transport = session.transport
    transport.packets = [{'type': 'port_open'}, hello(), frame()]
    session.tick()
    return session, transport, clock


def assert_no_values(session):
    assert all(x['volts'] is None and x['raw'] is None and x['received_at'] is None
               for x in session.snapshot()['channels'].values())


def test_three_independent_channels_and_read_only_identity():
    session, transport, clock = connected()
    snapshot = session.snapshot()
    assert transport.args == ('COM5', 115200)
    assert transport.kwargs == {'dtr': False}
    assert transport.identity_requests == 1
    assert snapshot['connected'] and snapshot['adc_ack'] and snapshot['fresh']
    assert [x['volts'] for x in snapshot['channels'].values()] == [.15, .5, 1.5]
    assert snapshot['channels']['A0']['received_at'] == pytest.approx(clock.now - .02)
    assert snapshot['identity']['sda_pin'] == 22
    assert snapshot['identity']['scl_pin'] == 21
    snapshot['channels']['A0']['volts'] = 88
    assert session.snapshot()['channels']['A0']['volts'] == .15


def test_normal_controller_is_not_accepted_as_sensor_board():
    session = Ads1115Monitor(Transport, Clock())
    session.connect('COM9')
    session.transport.packets = [{'type': 'port_open'},
                                 {'type': 'hello', 'v': 1, 'device': 'membrane-control', 'uptime_ms': 100}]
    session.tick()
    assert not session.snapshot()['connected']
    assert not session.snapshot()['identified']
    assert 'not the ADS1115' in session.status
    assert_no_values(session)


def test_data_before_identity_does_not_supply_values():
    session = Ads1115Monitor(Transport, Clock())
    session.connect('COM5')
    session.transport.packets = [{'type': 'port_open'}, frame()]
    session.tick()
    assert not session.snapshot()['connected']
    assert_no_values(session)


@pytest.mark.parametrize('path,value', [
    (('v',), True), (('adc_ack',), 1), (('uptime_ms',), True), (('sequence',), False),
    (('channels', 'A0', 'volts'), float('nan')),
    (('channels', 'A0', 'volts'), float('inf')),
    (('channels', 'A0', 'volts'), True),
    (('channels', 'A0', 'raw'), True),
    (('channels', 'A0', 'raw'), 32768),
    (('channels', 'A0', 'volts'), .7),
    (('channels', 'A1', 'signal'), 'pressure'),
    (('channels', 'A2', 'sample_uptime_ms'), True),
])
def test_malformed_packet_clears_previous_values(path, value):
    session, transport, _ = connected()
    message = frame(500, sequence=2)
    target = message
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    transport.packets = [message]
    session.tick()
    assert_no_values(session)
    assert not session.snapshot()['adc_ack']


def test_parse_error_clears_values_and_next_valid_frame_recovers():
    session, transport, _ = connected()
    transport.packets = [{'type': 'parse_error', 'error': 'bad JSON'}]
    session.tick()
    assert_no_values(session)
    transport.packets = [frame(500, sequence=2)]
    session.tick()
    assert session.snapshot()['channels']['A1']['volts'] == .5


def test_nack_clears_even_if_packet_still_contains_old_values():
    session, transport, _ = connected()
    transport.packets = [frame(500, ack=False, sequence=2)]
    session.tick()
    assert_no_values(session)
    assert session.snapshot()['connected']
    assert not session.snapshot()['adc_ack']
    assert 'not responding' in session.status


def test_failed_channel_clears_only_that_channel():
    session, transport, _ = connected()
    message = frame(500, sequence=2)
    message['channels']['A1'].update(status='conversion_timeout', raw=None, volts=None, sample_uptime_ms=None)
    transport.packets = [message]
    session.tick()
    channels = session.snapshot()['channels']
    assert channels['A0']['volts'] == .15
    assert channels['A1']['volts'] is None
    assert channels['A1']['status'] == 'conversion_timeout'
    assert channels['A2']['volts'] == 1.5


def test_pc_deadline_expires_without_a_poll_and_duplicate_does_not_refresh():
    session, transport, clock = connected()
    clock.now += 1
    transport.packets = [frame()]  # Identical uptime and sample is a replay.
    session.tick()
    clock.now += 1.1
    assert_no_values(session)
    assert not session.snapshot()['fresh']
    assert not session.snapshot()['connected']


def test_heartbeat_with_aging_sample_does_not_keep_value_alive():
    session, transport, clock = connected()
    message = frame(3000, sequence=2)
    message['type'] = 'heartbeat'
    message['channels']['A0']['sample_uptime_ms'] = 280
    transport.packets = [message]
    clock.now += 1
    session.tick()
    channels = session.snapshot()['channels']
    assert channels['A0']['volts'] is None
    assert channels['A0']['status'] == 'stale'
    assert channels['A1']['volts'] == .5


def test_future_sample_timestamp_is_unavailable():
    session, transport, _ = connected()
    message = frame(500, sequence=2)
    message['channels']['A0']['sample_uptime_ms'] = 600
    transport.packets = [message]
    session.tick()
    assert session.snapshot()['channels']['A0']['volts'] is None


def test_negative_raw_voltage_is_preserved_without_software_clamp():
    session, transport, _ = connected()
    message = frame(500, sequence=2)
    message['channels']['A2'].update(raw=-834, volts=-.10425)
    transport.packets = [message]
    session.tick()
    assert session.snapshot()['channels']['A2']['volts'] == -.10425


def test_device_restart_requires_new_identity_before_values():
    session, transport, _ = connected()
    transport.packets = [frame(100)]
    session.tick()
    assert not session.identified
    assert_no_values(session)
    transport.packets = [hello(20), frame(250)]
    session.tick()
    assert session.snapshot()['connected']
    assert session.snapshot()['channels']['A2']['volts'] == 1.5


def test_uptime_wrap_is_not_a_restart():
    session, transport, _ = connected()
    session._last_uptime = 0xfffffff0
    transport.packets = [frame(20, sequence=2)]
    session.tick()
    assert session.identified
    assert session.snapshot()['channels']['A0']['volts'] == .15


def test_disconnect_and_reconnect_do_not_reuse_old_identity_or_samples():
    session, old, _ = connected()
    old.packets = [{'type': 'disconnected', 'error': 'USB unplugged'}]
    session.tick()
    assert old.closed
    assert not session.snapshot()['connected']
    assert_no_values(session)
    session.connect('COM10')
    assert not session.error
    session.transport.packets = [{'type': 'port_open'}, frame()]
    session.tick()
    assert not session.identified
    assert_no_values(session)


def test_close_sends_no_stop_or_actuator_command():
    session, transport, _ = connected()
    session.close()
    assert transport.closed
    assert not session.snapshot()['connected']
    assert_no_values(session)


def test_identity_request_retry_is_rate_limited():
    clock = Clock()
    session = Ads1115Monitor(Transport, clock)
    session.connect('COM5')
    transport = session.transport
    transport.packets = [{'type': 'port_open'}]
    session.tick()
    for _ in range(10):
        session.tick()
    assert transport.identity_requests == 1
    clock.now += 1
    session.tick()
    assert transport.identity_requests == 2

"""Independent, read-only USB acquisition from the separate ADS1115 ESP32."""
from __future__ import annotations

import math
import time

from .transport import SerialTransport, close_transport


DEVICE = 'membrane-ads1115-monitor'
CHANNELS = {'A0': 'pressure', 'A1': 'flow', 'A2': 'pump_feedback'}
MAX_AGE_SECONDS = 2.0


class _MonitorTransport(SerialTransport):
    def request_identity(self):
        # The sensor-only firmware accepts bounded ASCII diagnostic commands.
        self._enqueue(b'HELLO\n')


def _uint32(value):
    return type(value) is int and 0 <= value <= 0xffffffff


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _empty_channels(status):
    return {name: {'signal': signal, 'status': status, 'raw': None, 'volts': None,
                   'sample_uptime_ms': None, 'received_at': None}
            for name, signal in CHANNELS.items()}


class Ads1115Monitor:
    """Poll alongside the rig controller; none of these frames control outputs.

    ``connect`` opens a separate serial worker, ``tick`` consumes its events and
    ``snapshot`` returns independent A0/A1/A2 readings. All ages use the supplied
    PC monotonic clock. Invalid, failed and stale channels never retain a value.
    """

    def __init__(self, transport_factory=None, clock=time.monotonic):
        self.transport_factory = transport_factory or _MonitorTransport
        self.clock = clock
        self.transport = None
        self.port = ''
        self.opened = False
        self.identified = False
        self.status = 'Sensor board disconnected'
        self.error = ''
        self.adc_ack = False
        self.uptime_ms = self.sequence = None
        self.received_at = None
        self.identity = {}
        self.channels = _empty_channels('disconnected')
        self._last_identity_request = None
        self._last_uptime = None

    def connect(self, port):
        if self.transport is not None:
            raise ValueError('Disconnect the sensor board before changing its port.')
        if not isinstance(port, str) or not port.strip():
            raise ValueError('Select the sensor board USB port.')
        self.port = port.strip()
        self.opened = self.identified = False
        self.error = ''
        self.identity = {}
        self.uptime_ms = self.sequence = self.received_at = self._last_uptime = None
        self._last_identity_request = None
        self._clear('waiting', 'Opening sensor board USB port')
        try:
            self.transport = self.transport_factory(self.port, 115200, dtr=False)
        except Exception as error:
            self.error = str(error)[:500]
            self._clear('disconnected', self.error)
            return False
        return True

    def disconnect(self):
        transport, self.transport = self.transport, None
        self.opened = self.identified = False
        self.identity = {}
        self.uptime_ms = self.sequence = self.received_at = self._last_uptime = None
        self._last_identity_request = None
        self._clear('disconnected', self.error or 'Sensor board disconnected')
        if transport is not None:
            try:
                close_transport(transport)
            except Exception as error:
                self.error = str(error)[:500]
                self.status = self.error

    close = disconnect

    def clear_selection(self):
        """Release the optional sensor port when selecting the full controller."""
        self.disconnect()
        self.port = ''

    def _clear(self, channel_status, status):
        self.adc_ack = False
        self.channels = _empty_channels(channel_status)
        self.status = status

    def _request_identity(self, now):
        if self._last_identity_request is not None and now - self._last_identity_request < 1.0:
            return
        self.transport.request_identity()
        self._last_identity_request = now

    def _validate_frame(self, packet):
        if (not isinstance(packet, dict) or type(packet.get('v')) is not int or packet['v'] != 1
                or packet.get('device') != DEVICE):
            raise ValueError('Connected device is not the ADS1115 sensor board')
        kind = packet.get('type')
        if kind not in ('hello', 'telemetry', 'heartbeat', 'i2c_scan') or not _uint32(packet.get('uptime_ms')):
            raise ValueError('Invalid sensor board message')
        return kind

    def _accept(self, packet, now):
        kind = self._validate_frame(packet)
        if kind == 'hello':
            if (not isinstance(packet.get('firmware'), str) or not packet['firmware']
                    or type(packet.get('bus_ready')) is not bool
                    or type(packet.get('sda_pin')) is not int
                    or type(packet.get('scl_pin')) is not int
                    or packet['sda_pin'] < 0 or packet['scl_pin'] < 0
                    or packet['sda_pin'] == packet['scl_pin']
                    or type(packet.get('adc_address')) is not int
                    or packet['adc_address'] != 0x48):
                raise ValueError('Invalid sensor board identity')
            self.identified = True
            self.identity = {key: packet[key] for key in
                             ('firmware', 'sda_pin', 'scl_pin', 'adc_address', 'bus_ready')}
            self.received_at = now
            self.uptime_ms = packet['uptime_ms']
            self._last_uptime = None
            self._clear('waiting', 'Sensor board connected; waiting for ADC readings')
            return
        if kind == 'i2c_scan':
            # Diagnostics do not confirm identity, refresh samples or clear an error.
            return
        if not self.identified:
            self._clear('waiting', 'Waiting for sensor board identity')
            return
        uptime = packet['uptime_ms']
        if type(packet.get('adc_ack')) is not bool or not _uint32(packet.get('sequence')):
            raise ValueError('Invalid sensor acquisition status')
        if self._last_uptime is not None:
            delta = (uptime - self._last_uptime) & 0xffffffff
            if delta == 0:
                return  # Replayed packets must not extend the PC freshness deadline.
            if delta >= 0x80000000:
                self.identified = False
                self.received_at = None
                self._last_uptime = None
                self._clear('waiting', 'Sensor board restarted; waiting for identity')
                return
        parsed = _empty_channels('adc_not_responding')
        if packet['adc_ack']:
            source = packet.get('channels')
            if not isinstance(source, dict):
                raise ValueError('Invalid sensor channel data')
            for name, signal in CHANNELS.items():
                sample = source.get(name)
                if not isinstance(sample, dict) or sample.get('signal') != signal:
                    raise ValueError(f'Invalid {name} sensor channel')
                status = sample.get('status')
                if status != 'reading_received':
                    if status not in ('waiting', 'i2c_error', 'config_mismatch', 'conversion_timeout',
                                      'adc_not_responding', 'i2c_initialization_failed'):
                        raise ValueError(f'Invalid {name} acquisition status')
                    if any(sample.get(key) is not None for key in ('raw', 'volts', 'sample_uptime_ms')):
                        raise ValueError(f'Failed {name} reading contains a value')
                    parsed[name]['status'] = status
                    continue
                raw, volts, sampled = sample.get('raw'), sample.get('volts'), sample.get('sample_uptime_ms')
                if (type(raw) is not int or not -32768 <= raw <= 32767
                        or not _finite_number(volts) or not _uint32(sampled)
                        or not math.isclose(volts, raw * 0.000125, rel_tol=0, abs_tol=0.0000005)):
                    raise ValueError(f'Invalid {name} voltage reading')
                age_ms = (uptime - sampled) & 0xffffffff
                if age_ms > MAX_AGE_SECONDS * 1000:
                    parsed[name]['status'] = 'stale'
                    continue
                parsed[name].update(status='reading_received', raw=raw, volts=float(volts),
                                    sample_uptime_ms=sampled, received_at=now - age_ms / 1000.0)
        self.channels = parsed
        self.adc_ack = packet['adc_ack']
        self.sequence = packet['sequence']
        self.uptime_ms = self._last_uptime = uptime
        self.received_at = now
        self.error = ''
        if not self.adc_ack:
            self.status = 'ADC not responding at 0x48'
        elif all(sample['volts'] is not None for sample in parsed.values()):
            self.status = 'ADS1115 readings received'
        else:
            self.status = 'Sensor board connected; one or more ADC readings unavailable'

    def _expire(self, now):
        if self.received_at is not None and now - self.received_at > MAX_AGE_SECONDS:
            self._clear('stale', 'Sensor board data stale')
            return
        for name, sample in self.channels.items():
            if sample['received_at'] is not None and now - sample['received_at'] > MAX_AGE_SECONDS:
                self.channels[name] = _empty_channels('stale')[name]

    def tick(self):
        if self.transport is None:
            return
        now = self.clock()
        try:
            for packet in self.transport.poll(now):
                if not isinstance(packet, dict):
                    self._clear('invalid_data', 'Invalid sensor transport event')
                    continue
                kind = packet.get('type')
                if kind == 'port_open':
                    self.opened = True
                    self.status = 'Waiting for sensor board identity'
                    self._request_identity(now)
                elif kind == 'disconnected':
                    self.error = str(packet.get('error') or 'Sensor board USB disconnected')[:500]
                    self.disconnect()
                    return
                elif kind == 'parse_error':
                    self._clear('invalid_data', 'Malformed sensor board data')
                else:
                    try:
                        self._accept(packet, now)
                    except (ValueError, TypeError, OverflowError) as error:
                        self._clear('invalid_data', str(error))
            self._expire(now)
            if self.opened and (not self.identified or self.received_at is None
                                or now - self.received_at > MAX_AGE_SECONDS):
                self._request_identity(now)
        except Exception as error:
            self.error = str(error)[:500]
            self.disconnect()

    def snapshot(self):
        now = self.clock()
        self._expire(now)
        fresh = self.received_at is not None and now - self.received_at <= MAX_AGE_SECONDS
        return {'connected': bool(self.transport is not None and self.opened and self.identified and fresh),
                'opened': self.opened, 'identified': self.identified, 'port': self.port,
                'status': self.status, 'error': self.error, 'adc_ack': self.adc_ack,
                'uptime_ms': self.uptime_ms, 'sequence': self.sequence,
                'received_at': self.received_at, 'fresh': bool(fresh),
                'identity': dict(self.identity),
                'channels': {name: dict(sample) for name, sample in self.channels.items()}}

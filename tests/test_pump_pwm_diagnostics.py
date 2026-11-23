"""PWM readback is an observation independent of command and drive voltage."""
import copy
import json

import pytest
from PySide6.QtWidgets import QApplication

from membrane_control.controller import AppController, _checked_pump_pwm
from membrane_control.ui import MainWindow


def pwm(**changes):
    return dict(pin=25, frequency_hz=1000, duty_code=614, resolution_bits=12, **changes)


def readback(**changes):
    value = pwm()
    value.update(changes)
    return value


class FakeDriver:
    port = 'FAKE-PWM-DIAGNOSTIC'

    def __init__(self):
        self.sent = []

    def send(self, packet):
        self.sent.append(copy.deepcopy(packet))

    def poll(self, now):
        return []

    def close(self):
        pass


@pytest.fixture
def controller(tmp_path):
    now = [100.0]
    app = AppController(tmp_path, clock=lambda: now[0], simulation=False)
    app.driver = FakeDriver()
    app.device.update(simulation=False, hardware_verified=True)
    yield app, now
    app.close()


def telemetry(app, now, **changes):
    packet = dict(v=1, type='telemetry', uptime_ms=round((now[0] - 99) * 1000), state='idle',
                  valves=[False] * 7, pump_percent=0, simulation=False, hardware_verified=True,
                  pressure_psi=0, flow_ml_min=0, pump_feedback_v=0, step_index=-1, cycle=0,
                  remaining_s=0, fault=None)
    packet.update(changes)
    app._handle_packet(packet, now[0])


def test_valid_readback_is_copied_and_missing_next_frame_clears_it(controller):
    app, now = controller
    sample = pwm()
    telemetry(app, now, pump_pwm=sample)
    assert app.snapshot['pump_pwm'] == sample
    sample['duty_code'] = 4000
    assert app.snapshot['pump_pwm']['duty_code'] == 614
    now[0] += .25
    telemetry(app, now)
    assert app.snapshot['pump_pwm'] is None


@pytest.mark.parametrize('change', [
    dict(pin=True), dict(pin=-1), dict(pin=1), dict(pin=3), dict(pin=6), dict(pin=11),
    dict(pin=20), dict(pin=24), dict(pin=28), dict(pin=31), dict(pin=34),
    dict(frequency_hz=True), dict(frequency_hz=1000.0), dict(frequency_hz=21), dict(frequency_hz=20001),
    dict(resolution_bits=True), dict(resolution_bits=12.0), dict(resolution_bits=7), dict(resolution_bits=17),
    dict(duty_code=True), dict(duty_code=614.0), dict(duty_code=-1), dict(duty_code=4097),
])
def test_malformed_readback_is_ignored_without_losing_good_pressure(controller, change):
    app, now = controller
    telemetry(app, now, pump_pwm=readback(**change), pressure_psi=12)
    assert app.snapshot['pump_pwm'] is None
    assert app.snapshot['pressure_psi'] == 12


@pytest.mark.parametrize('value', [None, [], {}, {'pin': 25}, '15%', False])
def test_bad_or_incomplete_object_clears_previous_readback(controller, value):
    app, now = controller
    telemetry(app, now, pump_pwm=pwm())
    now[0] += .25
    telemetry(app, now, pump_pwm=value)
    assert app.snapshot['pump_pwm'] is None


@pytest.mark.parametrize('value', [readback(pin=33), readback(frequency_hz=22), readback(frequency_hz=20000),
                                   readback(resolution_bits=8, duty_code=256),
                                   readback(resolution_bits=16, duty_code=65536), readback(duty_code=0)])
def test_supported_boundary_values_are_accepted(value):
    assert _checked_pump_pwm(dict(simulation=False, hardware_verified=True, pump_pwm=value)) == value


@pytest.mark.parametrize('flags', [dict(simulation=True), dict(hardware_verified=False),
                                   dict(simulation=0), dict(hardware_verified=1)])
def test_unverified_or_simulated_packets_cannot_publish_register_readback(flags):
    packet = dict(simulation=False, hardware_verified=True, pump_pwm=pwm())
    packet.update(flags)
    assert _checked_pump_pwm(packet) is None


def test_stale_active_stream_and_disconnect_clear_readback(controller):
    app, now = controller
    telemetry(app, now, pump_pwm=pwm(), state='manual', pump_percent=15)
    now[0] += 3
    app.tick()
    assert app.snapshot['pump_pwm'] is None
    app.snapshot['pump_pwm'] = pwm()
    app.disconnect_controller()
    assert app.snapshot['pump_pwm'] is None


def test_manual_request_log_records_the_exact_requested_percentage(controller):
    app, now = controller
    valves = [True, False, True, False, False, False, False]
    app.snapshot.update(controller_connected=True, simulation=False, hardware_verified=True,
                        pressure_psi=0, manual_pump_profile=dict(max_percent=50, valves=valves))
    app.last_telemetry = now[0]
    app.set_manual(valves, 15)
    records = [json.loads(line) for line in app.esp32_log_path.read_text(encoding='utf-8').splitlines()]
    queued = next(row for row in records if row['event'] == 'request_queued' and row['command'] == 'manual')
    assert queued['pump_percent'] == 15.0
    assert queued['request_id'] == app.driver.sent[-1]['id']


@pytest.fixture(scope='module')
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def screen(qt_app, controller):
    app, now = controller
    app.list_ports = lambda: []
    window = MainWindow(app)
    window.timer.stop()
    app.last_telemetry = now[0]
    snapshot = dict(app.snapshot, controller_connected=True, simulation=False, hardware_verified=True,
                    pump_percent=15, pump_feedback_v=7.5, pump_pwm=readback(duty_code=983))
    yield window, app, now, snapshot
    window.close()


def test_ui_separates_command_register_readback_and_measured_drive_level(screen):
    window, app, now, snapshot = screen
    before = list(app.driver.sent)
    window._update_view(snapshot)
    assert window.manual_pump_sent.text() == 'Commanded 15.0%'
    text = window.manual_pump_feedback.text()
    assert 'Controller PWM: 24.0% · IO25 · 1000 Hz (register readback)' in text
    assert 'Drive command feedback 7.50 V · Reported drive level 75.0%' in text
    assert app.driver.sent == before


@pytest.mark.parametrize('change', [dict(pump_pwm=None), dict(pump_pwm=readback(duty_code=True)),
                                    dict(hardware_verified=False), dict(simulation=True),
                                    dict(controller_connected=False)])
def test_unavailable_or_unconfirmed_ui_does_not_show_an_actual_register_duty(screen, change):
    window, app, now, snapshot = screen
    window._update_view(dict(snapshot, **change))
    assert 'Controller PWM:' not in window.manual_pump_feedback.text()


def test_ui_clears_register_display_when_telemetry_is_stale(screen):
    window, app, now, snapshot = screen
    window._update_view(snapshot)
    assert 'Controller PWM:' in window.manual_pump_feedback.text()
    now[0] += 3
    window._update_view(snapshot)
    assert window.manual_pump_feedback.text() == 'Waiting for fresh pump feedback.'

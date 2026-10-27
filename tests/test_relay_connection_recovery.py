"""Recover local serial resources with fake drivers only; never open a COM port."""
import copy
import queue
import threading
import time

import pytest
import serial
from PySide6.QtWidgets import QApplication

from membrane_control.relay_bench import RelayBenchDialog, RelayBenchSession
from membrane_control.transport import SerialTransport


def wait_until(check):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.005)
    pytest.fail('Fake serial worker did not reach the expected state')


class RetryCloseInstrument:
    def __init__(self):
        self.is_open = False
        self.close_count = 0
        self.fail_close = True
        self.fail_read = False
        self.input = queue.Queue()
        self.writes = []

    def open(self):
        self.is_open = True

    @property
    def in_waiting(self):
        return 1

    def read(self, count):
        if self.fail_read:
            raise OSError('original fake read failure')
        try:
            return self.input.get(timeout=.01)
        except queue.Empty:
            return b''

    def write(self, payload):
        assert self.is_open
        self.writes.append(payload)
        return len(payload)

    def close(self):
        self.close_count += 1
        if self.fail_close:
            raise OSError('fake close failed while handle remains open')
        self.is_open = False


def test_failed_driver_close_retains_open_handle_for_an_explicit_retry(monkeypatch):
    device = RetryCloseInstrument()
    monkeypatch.setattr(serial, 'Serial', lambda **_kwargs: device)
    worker = SerialTransport('FAKE-RECOVER-CLOSE')
    try:
        wait_until(lambda: worker._opened)
        with pytest.raises(RuntimeError, match='close failed'):
            worker.close()
        assert device.is_open and worker._connection is device
        assert worker.cleanup_pending
        assert worker.outgoing.empty()
        with pytest.raises(RuntimeError):
            worker.send({'v': 1, 'id': 20, 'cmd': 'bench_pulse', 'bit': 0})
        device.fail_close = False
        worker.close()
        assert not device.is_open and not worker.cleanup_pending
        count = device.close_count
        worker.close()
        assert device.close_count == count
    finally:
        device.fail_close = False
        worker.close()


def test_worker_read_failure_keeps_close_retry_and_original_error(monkeypatch):
    device = RetryCloseInstrument()
    device.fail_read = True
    monkeypatch.setattr(serial, 'Serial', lambda **_kwargs: device)
    worker = SerialTransport('FAKE-RECOVER-READ')
    try:
        wait_until(lambda: worker._terminated.is_set())
        assert worker.cleanup_pending and device.is_open
        errors = [packet['error'] for packet in worker.poll() if packet['type'] == 'disconnected']
        assert errors == ['original fake read failure']
        device.fail_close = False
        worker.close()
        assert not worker.cleanup_pending
        assert worker.poll() == []
    finally:
        device.fail_close = False
        worker.close()


def test_exception_after_handle_is_closed_never_retries_that_handle(monkeypatch):
    class ClosedThenRaises(RetryCloseInstrument):
        def close(self):
            self.close_count += 1
            self.is_open = False
            raise OSError('fake diagnostic after handle was released')

    devices = [ClosedThenRaises(), RetryCloseInstrument()]
    devices[1].fail_close = False
    available = iter(devices)
    monkeypatch.setattr(serial, 'Serial', lambda **_kwargs: next(available))
    old = SerialTransport('FAKE-CLOSED-ERROR')
    new = None
    try:
        wait_until(lambda: old._opened)
        with pytest.raises(RuntimeError, match='after handle was released'):
            old.close()
        assert not old.cleanup_pending and devices[0].close_count == 1
        new = SerialTransport('FAKE-CLOSED-ERROR')
        wait_until(lambda: new._opened)
        assert devices[1].is_open and devices[0].close_count == 1
    finally:
        with pytest.raises(RuntimeError, match='after handle was released'):
            old.close()
        if new is not None:
            new.close()


def test_blocking_driver_close_is_owned_and_recovery_returns_on_its_deadline(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    class BlockingClose(RetryCloseInstrument):
        def close(self):
            self.close_count += 1
            entered.set()
            assert release.wait(timeout=4)
            self.is_open = False

    device = BlockingClose()
    monkeypatch.setattr(serial, 'Serial', lambda **_kwargs: device)
    worker = SerialTransport('FAKE-BLOCKED-CLOSE')
    try:
        wait_until(lambda: worker._opened)
        start = time.monotonic()
        with pytest.raises(RuntimeError, match='still closing'):
            worker.close(timeout=.03)
        assert entered.is_set() and time.monotonic() - start < .3
        assert worker.cleanup_pending and device.close_count == 1
        start = time.monotonic()
        with pytest.raises(RuntimeError, match='still closing'):
            worker.close(timeout=.03)
        assert time.monotonic() - start < .3 and device.close_count == 1
        assert worker.outgoing.empty()
        release.set()
        worker.close()
        assert not worker.cleanup_pending and device.close_count == 1
    finally:
        release.set()
        worker.close()


def test_concurrent_cleanup_lock_wait_uses_the_callers_deadline(monkeypatch):
    device = RetryCloseInstrument()
    device.fail_close = False
    monkeypatch.setattr(serial, 'Serial', lambda **_kwargs: device)
    worker = SerialTransport('FAKE-CLOSE-LOCK')
    try:
        wait_until(lambda: worker._opened)
        worker._close_lock.acquire()
        try:
            start = time.monotonic()
            with pytest.raises(RuntimeError, match='already in progress'):
                worker.close(timeout=.02)
            assert time.monotonic() - start < .3
        finally:
            worker._close_lock.release()
        worker.close()
        assert not worker.cleanup_pending
    finally:
        worker.close()


class BenchTransport:
    def __init__(self):
        self.sent, self.events = [], []
        self.closed = False
        self.close_count = 0
        self.fail_close = False

    @property
    def cleanup_pending(self):
        return not self.closed

    def send(self, packet):
        assert not self.closed
        self.sent.append(copy.deepcopy(packet))

    def poll(self, _now=None):
        packets, self.events = self.events, []
        return packets

    def close(self):
        self.close_count += 1
        if self.fail_close:
            raise RuntimeError('fake pending handle close')
        self.closed = True


def identified(session, transport):
    hello = transport.sent[-1]
    transport.events.append(dict(v=1, type='hello', id=hello['id'], ok=True,
        device='membrane-relay-bench', protocol_version=1, relay_count=16,
        simulation=False, hardware_verified=False))
    session.tick()
    transport.events.extend([
        dict(v=1, type='ack', id=transport.sent[-1]['id'], ok=True),
        dict(v=1, type='bench_status', uptime_ms=100, state='disarmed', outputs_enabled=False,
             baseline_confirmed=False, baseline_word=0, probe_completed=False, probe_id=0,
             pulse_bit=None, remaining_ms=0, simulation=False, hardware_verified=False, fault=None)])
    session.tick()


def test_recovery_must_release_previous_transport_before_replacement():
    old, new = BenchTransport(), BenchTransport()
    created = []

    def factory(*_args):
        driver = [old, new][len(created)]
        created.append(driver)
        return driver

    session = RelayBenchSession(factory, lambda: 100.)
    session.connect('FAKE-ONLY')
    identified(session, old)
    session.attest_loads(True)
    old.fail_close = True
    session.detach()
    assert session.cleanup_pending and not session.verified
    assert not session.loads_disconnected and not session.can_pulse
    with pytest.raises(ValueError, match='Recover connection'):
        session.connect('FAKE-ONLY')
    session.recover('FAKE-ONLY')
    assert created == [old] and session.transport is None
    assert 'close' in session.message.lower()
    old.fail_close = False
    session.recover('FAKE-ONLY')
    assert old.closed and created == [old, new]
    assert not session.cleanup_pending and session.transport is new
    assert [p['cmd'] for p in new.sent] == ['hello']
    assert not session.verified and session.pending
    assert not session.loads_disconnected and not session.observed and not session.confirmed
    session.detach()


def test_recovery_from_live_connection_never_replays_a_probe_or_pulse():
    old, new = BenchTransport(), BenchTransport()
    drivers = iter([old, new])
    session = RelayBenchSession(lambda *_args: next(drivers), lambda: 100.)
    session.connect('FAKE-ONLY')
    identified(session, old)
    session.attest_loads(True)
    session.probe(0)
    session.recover('FAKE-ONLY')
    assert old.closed and old.sent[-1]['cmd'] == 'stop'
    assert [p['cmd'] for p in new.sent] == ['hello']
    assert session.operation is None and session.probe_id is None
    identified(session, new)
    assert not session.can_probe and not session.can_confirm and not session.can_pulse
    assert all(p['cmd'] not in ('bench_probe', 'bench_confirm', 'bench_pulse') for p in new.sent)
    session.detach()


@pytest.fixture
def qt_app():
    yield QApplication.instance() or QApplication([])


def test_dialog_recovery_button_is_explicit_and_clears_checks(qt_app):
    old, new = BenchTransport(), BenchTransport()
    drivers = iter([old, new])
    dialog = RelayBenchDialog(selected_port='FAKE-ONLY',
        port_lister=lambda: [('FAKE-ONLY', 'Test double')],
        transport_factory=lambda *_args: next(drivers), clock=lambda: 100.)
    dialog.timer.stop()
    try:
        assert dialog.session.transport is None and not old.sent
        dialog.connect_button.click()
        identified(dialog.session, old)
        dialog.session.attest_loads(True)
        dialog._render()
        assert dialog.loads_checkbox.isChecked()
        assert dialog.recover_button.text() == 'Recover connection'
        dialog.recover_button.click()
        assert old.closed and dialog.session.transport is new
        assert not dialog.loads_checkbox.isChecked() and not dialog.observation_checkbox.isChecked()
        assert not any(button.isEnabled() for button in dialog.pulse_buttons)
        assert [p['cmd'] for p in new.sent] == ['hello']
    finally:
        dialog.close()


def test_retired_handle_survives_dialog_deletion_and_reopens_without_old_traffic(qt_app, monkeypatch):
    import gc
    import weakref
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid

    devices = []

    def factory(**_kwargs):
        device = RetryCloseInstrument()
        device.fail_close = not devices
        devices.append(device)
        return device

    monkeypatch.setattr(serial, 'Serial', factory)
    options = dict(selected_port='FAKE-DESTROY-RECOVER',
                   port_lister=lambda: [('FAKE-DESTROY-RECOVER', 'Fake driver')])
    old_dialog = RelayBenchDialog(**options)
    old_dialog.timer.stop()
    old_dialog.connect_board()
    old_worker = old_dialog.session.transport
    wait_until(lambda: old_worker._opened)
    old_dialog.close()
    assert old_worker.cleanup_pending and devices[0].is_open
    old_ref = weakref.ref(old_dialog)
    old_dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    del old_dialog
    gc.collect()
    assert old_ref() is None or not isValid(old_ref())
    new_dialog = RelayBenchDialog(**options)
    new_dialog.timer.stop()
    try:
        new_dialog.recover_board()
        assert len(devices) == 1 and new_dialog.session.transport is None
        assert 'not released' in new_dialog.status_label.text()
        devices[0].fail_close = False
        new_dialog.recover_board()
        new_worker = new_dialog.session.transport
        wait_until(lambda: new_worker._opened)
        wait_until(lambda: bool(devices[1].writes))
        assert not devices[0].is_open and not old_worker.cleanup_pending
        assert all(b'bench_' not in payload for device in devices for payload in device.writes)
        assert all(b'heartbeat' not in payload for device in devices for payload in device.writes)
        assert not new_dialog.session.verified
    finally:
        devices[0].fail_close = False
        old_worker.close()
        new_dialog.close()


def test_retired_pending_open_blocks_replacement_until_old_worker_finishes(monkeypatch):
    started, release = threading.Event(), threading.Event()
    devices = []

    class SlowOpen(RetryCloseInstrument):
        def open(self):
            started.set()
            assert release.wait(timeout=4)
            super().open()

    def factory(**_kwargs):
        device = SlowOpen() if not devices else RetryCloseInstrument()
        device.fail_close = False
        devices.append(device)
        return device

    monkeypatch.setattr(serial, 'Serial', factory)
    worker = SerialTransport('FAKE-PENDING-RECOVER')
    replacement = None
    try:
        assert started.wait(timeout=1)
        worker.send({'v': 1, 'id': 1, 'cmd': 'bench_pulse', 'bit': 3})
        with pytest.raises(RuntimeError, match='still shutting down'):
            worker.close(timeout=.01)
        with pytest.raises(RuntimeError, match='not released'):
            SerialTransport('FAKE-PENDING-RECOVER')
        assert len(devices) == 1 and not devices[0].writes
        release.set()
        wait_until(lambda: not worker.cleanup_pending)
        replacement = SerialTransport('FAKE-PENDING-RECOVER')
        wait_until(lambda: replacement._opened)
        assert len(devices) == 2 and not devices[0].is_open
        assert not devices[0].writes
    finally:
        release.set()
        worker.close()
        if replacement is not None:
            replacement.close()


def test_recovery_never_closes_an_unrelated_active_balance(monkeypatch):
    from membrane_control.transport import recover_serial_port

    device = RetryCloseInstrument()
    device.fail_close = False
    monkeypatch.setattr(serial, 'Serial', lambda **_kwargs: device)
    worker = SerialTransport('FAKE-ACTIVE-SCALE', 9600, raw=True)
    try:
        wait_until(lambda: worker._opened)
        recover_serial_port('FAKE-ACTIVE-SCALE')
        assert device.is_open and device.close_count == 0
        worker.request_reading()
        wait_until(lambda: bool(device.writes))
        assert device.writes == [b'!KP\r']
    finally:
        worker.close()


def test_receive_overflow_preserves_terminal_reason_even_when_event_queue_is_full(monkeypatch):
    device = RetryCloseInstrument()
    device.fail_close = False
    monkeypatch.setattr(serial, 'Serial', lambda **_kwargs: device)
    worker = SerialTransport('FAKE-OVERFLOW-RECOVERY')
    try:
        wait_until(lambda: worker._opened)
        device.input.put(b'{"v":1,"type":"bench_status"}\n' * 600)
        wait_until(lambda: worker._terminated.is_set())
        packets = worker.poll()
        errors = [p['error'] for p in packets if p.get('type') == 'disconnected']
        assert len(errors) == 1 and 'receive queue overflow' in errors[0]
        assert len(packets) == 1  # Old malformed/stale status cannot hide the reason.
        assert not worker.cleanup_pending and worker.outgoing.empty()
        assert worker.poll() == []
    finally:
        worker.close()

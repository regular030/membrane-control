"""Exercise the real serial worker with a byte-stream instrument double."""
import json
import queue
import threading
import time

import pytest
import serial

from membrane_control.models import Recipe, Step
from membrane_control.transport import MAX_LINE, SerialTransport, Simulator, close_transport


class Instrument:
    def __init__(self, **kwargs):
        self.input = queue.Queue()
        self.writes = []
        self.closed = False
        self.opened_lines = None

    @property
    def in_waiting(self):
        return 1

    def open(self):
        self.opened_lines = (self.dtr, self.rts)

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def read(self, count):
        try:
            return self.input.get(timeout=0.01)
        except queue.Empty:
            return b""

    def close(self):
        self.closed = True


class BlockingInstrument(Instrument):
    """Cooperative driver double; a real OS handle is never opened."""
    def __init__(self, mode):
        super().__init__()
        self.mode = mode
        self.read_entered = threading.Event()
        self.write_entered = threading.Event()
        self.open_entered = threading.Event()
        self.release_read = threading.Event()
        self.release_write = threading.Event()
        self.release_open = threading.Event()
        self.close_count = 0
        self.cancel_read_count = 0
        self.cancel_write_count = 0
        self.is_open = False

    def open(self):
        self.open_entered.set()
        if self.mode == "open":
            self.release_open.wait(timeout=3)
        super().open()
        self.is_open = True

    def read(self, count):
        if self.mode == "read":
            self.read_entered.set()
            self.release_read.wait(timeout=3)
            return b""
        return super().read(count)

    def write(self, data):
        if self.closed:
            raise OSError("write after handle close")
        self.writes.append(data)
        if self.mode == "write":
            self.write_entered.set()
            self.release_write.wait(timeout=3)
        return len(data)

    def cancel_read(self):
        self.cancel_read_count += 1
        self.release_read.set()

    def cancel_write(self):
        self.cancel_write_count += 1
        self.release_write.set()

    def close(self):
        self.close_count += 1
        self.closed = True
        self.is_open = False
        self.release_read.set()
        self.release_write.set()

    def release_all(self):
        self.release_read.set()
        self.release_write.set()
        self.release_open.set()


def wait_for(worker, predicate):
    packets = []
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        packets.extend(worker.poll())
        if predicate(packets):
            return packets
        time.sleep(0.005)
    pytest.fail(f"Serial worker did not produce expected result: {packets}")


@pytest.fixture
def instrument(monkeypatch):
    device = Instrument()
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: device)
    return device


def test_fragmented_json_and_recovery_after_bad_or_oversize_line(instrument):
    worker = SerialTransport("TEST-ONLY")
    try:
        wait_for(worker, lambda packets: any(p["type"] == "port_open" for p in packets))
        assert instrument.opened_lines == (False, False)
        instrument.input.put(b'{"type":"tele')
        instrument.input.put(b'metry","value":12}\r\n{broken}\n')
        instrument.input.put(b"x" * (MAX_LINE + 1) + b'\n{"type":"recovered"}\n')
        packets = wait_for(worker, lambda items: any(p["type"] == "recovered" for p in items))
        assert {"type": "telemetry", "value": 12} in packets
        assert sum(p["type"] == "parse_error" for p in packets) == 2
        worker.send({"v": 1, "id": 1, "cmd": "hello"})
        deadline = time.monotonic() + 2
        while not instrument.writes and time.monotonic() < deadline:
            time.sleep(0.005)
        assert json.loads(instrument.writes[0]) == {"v": 1, "id": 1, "cmd": "hello"}
    finally:
        worker.close()
    assert instrument.closed


def test_balance_raw_crlf_and_no_json_requirement(instrument):
    worker = SerialTransport("BALANCE-TEST", raw=True)
    try:
        instrument.input.put(b"   +123.4 g\r\n")
        packets = wait_for(worker, lambda items: any(p["type"] == "mass_line" for p in items))
        assert {"type": "mass_line", "line": "+123.4 g"} in packets
    finally:
        worker.close()


def test_stop_discards_queued_start_and_manual_commands():
    # Isolate the queue policy so a worker cannot consume a command mid-assertion.
    worker = queue_only_transport()
    worker.send({"v": 1, "id": 1, "cmd": "start"})
    worker.send({"v": 1, "id": 2, "cmd": "manual"})
    worker.send({"v": 1, "id": 3, "cmd": "heartbeat"})
    worker.send({"v": 1, "id": 4, "cmd": "stop"})
    assert worker.outgoing.qsize() == 1
    assert json.loads(worker.outgoing.get_nowait()[2])["cmd"] == "stop"


def test_exact_line_limit_is_accepted_when_sending():
    worker = queue_only_transport()
    message = {"cmd": "hello", "pad": ""}
    overhead = len(json.dumps(message, separators=(",", ":")).encode())
    message["pad"] = "x" * (MAX_LINE - overhead)
    worker.send(message)
    payload = worker.outgoing.get_nowait()[2]
    assert len(payload) == MAX_LINE + 1 and payload.endswith(b"\n")
    assert json.loads(payload) == message
    message["pad"] += "x"
    with pytest.raises(ValueError, match="line limit"):
        worker.send(message)


def queue_only_transport():
    worker = SerialTransport.__new__(SerialTransport)
    worker.outgoing = queue.PriorityQueue(maxsize=64)
    worker._counter = 0
    worker._stop = threading.Event()
    worker._closing = threading.Event()
    worker._terminated = threading.Event()
    worker._state_lock = threading.RLock()
    worker._terminal_error = None
    worker._terminal_reported = False
    return worker


def test_port_open_failure_is_reported_once_and_rejects_later_sends(instrument):
    message = "Access denied: test port is already in use"

    def locked_open():
        raise PermissionError(message)

    instrument.open = locked_open
    worker = SerialTransport("LOCKED-TEST-PORT")
    try:
        packets = wait_for(worker, lambda items: any(p["type"] == "disconnected" for p in items))
        assert [p for p in packets if p["type"] == "disconnected"] == [{"type": "disconnected", "error": message}]
        worker._thread.join(timeout=1)
        assert not worker._thread.is_alive()
        for _ in range(100):
            assert worker.poll() == []
            with pytest.raises(RuntimeError, match="Access denied"):
                worker.send({"id": 1, "cmd": "heartbeat"})
        assert worker.outgoing.empty()
    finally:
        worker.close()


def test_new_transport_accepts_commands_while_port_is_still_opening(instrument):
    opening = threading.Event()
    allow_open = threading.Event()
    original_open = instrument.open

    def slow_open():
        opening.set()
        assert allow_open.wait(timeout=2)
        original_open()

    instrument.open = slow_open
    worker = SerialTransport("STARTING-TEST-PORT")
    try:
        assert opening.wait(timeout=1)
        worker.send({"v": 1, "id": 1, "cmd": "hello"})
        assert worker.outgoing.qsize() == 1
        allow_open.set()
        wait_for(worker, lambda items: any(p["type"] == "port_open" for p in items))
        deadline = time.monotonic() + 1
        while not instrument.writes and time.monotonic() < deadline:
            time.sleep(0.005)
        assert json.loads(instrument.writes[0])["cmd"] == "hello"
    finally:
        allow_open.set()
        worker.close()
    with pytest.raises(RuntimeError, match="closed"):
        worker.send({"id": 2, "cmd": "heartbeat"})


@pytest.mark.parametrize("mode", ["read", "write"])
def test_close_cancels_blocked_io_releases_handle_and_discards_backlog(monkeypatch, mode):
    device = BlockingInstrument(mode)
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: device)
    worker = SerialTransport("BLOCKED-TEST-PORT")
    try:
        wait_for(worker, lambda items: any(p["type"] == "port_open" for p in items))
        if mode == "write":
            worker.send({"id": 1, "cmd": "manual"})
            assert device.write_entered.wait(timeout=1)
        else:
            assert device.read_entered.wait(timeout=1)
        for index in range(10):
            worker.send({"id": index + 10, "cmd": "heartbeat"})
        worker.close()
        assert device.closed and device.close_count == 1
        assert not worker._thread.is_alive()
        assert worker.outgoing.empty()
        assert device.cancel_read_count and device.cancel_write_count
        writes_at_close = list(device.writes)
        worker.close()
        assert device.close_count == 1 and device.writes == writes_at_close
        with pytest.raises(RuntimeError, match="closed"):
            worker.send({"id": 100, "cmd": "heartbeat"})
    finally:
        device.release_all()
        worker.close()


@pytest.mark.parametrize("with_stop", [False, True])
def test_close_during_pending_open_cannot_leak_or_send_late_traffic(monkeypatch, with_stop):
    device = BlockingInstrument("open")
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: device)
    worker = SerialTransport("LATE-OPEN-TEST")
    try:
        assert device.open_entered.wait(timeout=1)
        worker.send({"id": 1, "cmd": "manual"})
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="still shutting down"):
            worker.close(stop_message={"v": 1, "id": 2, "cmd": "stop"} if with_stop else None, timeout=0.05)
        assert time.monotonic() - started < 0.5
        assert worker.outgoing.empty()
        with pytest.raises(RuntimeError, match="closed"):
            worker.send({"id": 2, "cmd": "heartbeat"})
        device.release_open.set()
        worker._thread.join(timeout=1)
        assert not worker._thread.is_alive()
        assert device.close_count == 1 and device.closed
        assert device.writes == []
        assert not any(p["type"] == "port_open" for p in worker.poll())
        worker.close()
        assert device.close_count == 1
    finally:
        device.release_all()
        worker.close()


def test_explicit_shutdown_stop_bypasses_backlog_and_is_written_before_handle_close(monkeypatch):
    device = BlockingInstrument("read")
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: device)
    worker = SerialTransport("GRACEFUL-STOP-TEST")
    try:
        assert device.read_entered.wait(timeout=1)
        for index in range(10):
            worker.send({"v": 1, "id": index + 1, "cmd": "manual"})
        stop = {"v": 1, "id": 100, "cmd": "stop"}
        close_transport(worker, stop_message=stop)
        assert [json.loads(data) for data in device.writes] == [stop]
        assert device.closed and device.close_count == 1
        assert worker.outgoing.empty() and not worker._thread.is_alive()
        close_transport(worker, stop_message=stop)
        assert len(device.writes) == 1 and device.close_count == 1
    finally:
        device.release_all()
        worker.close()


def test_graceful_shutdown_force_cancels_a_stuck_write_within_deadline(monkeypatch):
    device = BlockingInstrument("write")
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: device)
    worker = SerialTransport("STUCK-WRITE-STOP-TEST")
    try:
        worker.send({"v": 1, "id": 1, "cmd": "manual"})
        assert device.write_entered.wait(timeout=1)
        started = time.monotonic()
        worker.close(stop_message={"v": 1, "id": 2, "cmd": "stop"}, timeout=0.6)
        assert time.monotonic() - started < 0.9
        assert device.closed and device.close_count == 1
        assert device.cancel_write_count > 0 and not worker._thread.is_alive()
        assert not any(json.loads(data)["cmd"] == "heartbeat" for data in device.writes)
    finally:
        device.release_all()
        worker.close()


def test_closed_handle_can_be_reopened_immediately_without_waiting_for_old_worker(monkeypatch):
    lease = set()
    devices = []

    class ExclusiveInstrument(BlockingInstrument):
        def __init__(self):
            super().__init__("read")
        def open(self):
            if self.port in lease:
                raise PermissionError("test exclusive handle is still held")
            lease.add(self.port)
            super().open()
        def close(self):
            super().close()
            lease.discard(self.port)

    def factory(**kwargs):
        device = ExclusiveInstrument()
        devices.append(device)
        return device

    monkeypatch.setattr(serial, "Serial", factory)
    first = SerialTransport("EXCLUSIVE-TEST")
    second = None
    try:
        wait_for(first, lambda items: any(p["type"] == "port_open" for p in items))
        first.close()
        assert "EXCLUSIVE-TEST" not in lease
        second = SerialTransport("EXCLUSIVE-TEST")
        wait_for(second, lambda items: any(p["type"] == "port_open" for p in items))
        assert "EXCLUSIVE-TEST" in lease
    finally:
        first.close()
        if second is not None:
            second.close()
    assert not lease and all(device.close_count == 1 for device in devices)


def test_simultaneous_send_and_close_leaves_no_queued_traffic(monkeypatch):
    device = BlockingInstrument("read")
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: device)
    worker = SerialTransport("CONCURRENT-TEST")
    sending = threading.Event()
    finished = threading.Event()

    def sender():
        sending.set()
        for index in range(1000):
            try:
                worker.send({"v": 1, "id": index + 1, "cmd": "heartbeat"})
            except RuntimeError:
                break
        finished.set()

    thread = threading.Thread(target=sender)
    try:
        assert device.read_entered.wait(timeout=1)
        thread.start()
        assert sending.wait(timeout=1)
        worker.close()
        thread.join(timeout=1)
        assert finished.is_set() and not thread.is_alive()
        assert worker.outgoing.empty() and device.close_count == 1
        assert device.writes == []
    finally:
        device.release_all()
        worker.close()
        thread.join(timeout=1)


def test_original_read_error_survives_cleanup_error_and_handle_close_is_not_repeated(monkeypatch):
    class FailingInstrument(Instrument):
        def __init__(self):
            super().__init__()
            self.close_count = 0
        def read(self, count):
            raise OSError("original cable-read failure")
        def close(self):
            self.close_count += 1
            self.closed = True
            raise OSError("cleanup failure")

    device = FailingInstrument()
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: device)
    worker = SerialTransport("ERROR-CLOSE-TEST")
    packets = wait_for(worker, lambda items: any(p["type"] == "disconnected" for p in items))
    assert [p["error"] for p in packets if p["type"] == "disconnected"] == ["original cable-read failure"]
    for _ in range(2):
        with pytest.raises(RuntimeError, match="cleanup failure"):
            worker.close()
    assert device.close_count == 1 and worker.poll() == []


def test_duck_type_close_helper_always_closes_even_if_stop_send_fails():
    class Adapter:
        def __init__(self):
            self.close_count = 0
        def send(self, packet):
            raise OSError("test link is gone")
        def close(self):
            self.close_count += 1

    adapter = Adapter()
    close_transport(adapter, {"v": 1, "id": 1, "cmd": "stop"})
    assert adapter.close_count == 1


def test_missing_or_unsupported_cancellation_still_closes_the_handle(monkeypatch):
    class UnsupportedCancellation(BlockingInstrument):
        def cancel_read(self):
            raise NotImplementedError("test driver cannot cancel reads")
        def cancel_write(self):
            raise OSError("test driver cannot cancel writes")

    device = UnsupportedCancellation("read")
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: device)
    worker = SerialTransport("NO-CANCEL-TEST")
    try:
        assert device.read_entered.wait(timeout=1)
        worker.close()
        assert device.closed and device.close_count == 1
        assert not worker._thread.is_alive()
    finally:
        device.release_all()
        worker.close()


def test_simultaneous_closers_close_the_same_handle_exactly_once(monkeypatch):
    device = BlockingInstrument("read")
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: device)
    worker = SerialTransport("TWO-CLOSERS-TEST")
    failures = []

    def close():
        try:
            worker.close()
        except Exception as error:
            failures.append(error)

    threads = [threading.Thread(target=close) for _ in range(2)]
    try:
        assert device.read_entered.wait(timeout=1)
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        assert not failures and not any(thread.is_alive() for thread in threads)
        assert device.close_count == 1 and device.closed
        assert not worker._thread.is_alive()
    finally:
        device.release_all()
        worker.close()


def test_exact_line_limit_received_and_oversize_recovers(instrument):
    worker = SerialTransport("TEST-ONLY")
    try:
        message = {"type": "boundary", "pad": ""}
        overhead = len(json.dumps(message, separators=(",", ":")).encode())
        message["pad"] = "x" * (MAX_LINE - overhead)
        body = json.dumps(message, separators=(",", ":")).encode()
        assert len(body) == MAX_LINE
        instrument.input.put(body[:4000])
        instrument.input.put(body[4000:] + b"\n")
        instrument.input.put(body + b' \n{"type":"recovered"}\n')
        packets = wait_for(worker, lambda items: any(p["type"] == "recovered" for p in items))
        assert message in packets
        assert [p["error"] for p in packets if p["type"] == "parse_error"] == ["Serial line too long"]
    finally:
        worker.close()


def simulator_with_recipe(duration=10):
    now = [0.0]
    simulator = Simulator(lambda: now[0])
    recipe = Recipe(name="Timing", steps=[Step("Hold", duration, (True,)*7, 20)])
    simulator.send({"id": 1, "cmd": "load_recipe", "recipe": recipe.to_dict()})
    simulator.send({"id": 2, "cmd": "start"})
    simulator.poll()
    return simulator, now


def test_late_heartbeat_cannot_erase_simulated_watchdog_fault():
    simulator, now = simulator_with_recipe()
    now[0] = 4.0
    simulator.send({"id": 3, "cmd": "heartbeat"})
    telemetry = simulator.poll()[-1]
    assert telemetry["state"] == "fault"
    assert "heartbeat timeout" in telemetry["fault"]
    assert telemetry["pump_percent"] == 0 and not any(telemetry["valves"])


@pytest.mark.parametrize("duration,expected", [(2.999, "idle"), (3.0, "fault"), (3.001, "fault")])
def test_recipe_completion_is_ordered_against_watchdog_deadline(duration, expected):
    simulator, now = simulator_with_recipe(duration)
    now[0] = 4.0
    assert simulator.poll()[-1]["state"] == expected


def test_manual_commands_do_not_refresh_active_watchdog_and_exact_deadline_faults():
    now = [0.0]
    simulator = Simulator(lambda: now[0])
    command = {"id": 1, "cmd": "manual", "valves": [False]*7, "pump_percent": 0}
    simulator.send(command)
    assert simulator.engine.state == "manual"
    now[0] = 2.0
    simulator.send(dict(command, id=2, pump_percent=10))
    assert simulator.last_heartbeat == 0.0
    now[0] = 3.0
    simulator.send({"id": 3, "cmd": "heartbeat"})
    assert simulator.poll()[-1]["state"] == "fault"


def test_simulator_uptime_wraps_to_uint32_without_restarting_engine():
    now = [0.0]
    simulator = Simulator(lambda: now[0])
    now[0] = (2**32 + 17) / 1000
    telemetry = simulator.poll()[-1]
    assert telemetry["uptime_ms"] == 17
    assert telemetry["state"] == "idle"

"""Exercise the real serial worker with a byte-stream instrument double."""
import json
import queue
import time

import pytest
import serial

from membrane_control.transport import MAX_LINE, SerialTransport


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
        instrument.input.put(b"x" * MAX_LINE + b'\n{"type":"recovered"}\n')
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
    worker = SerialTransport.__new__(SerialTransport)
    worker.outgoing = queue.PriorityQueue(maxsize=64)
    worker._counter = 0
    worker.send({"v": 1, "id": 1, "cmd": "start"})
    worker.send({"v": 1, "id": 2, "cmd": "manual"})
    worker.send({"v": 1, "id": 3, "cmd": "heartbeat"})
    worker.send({"v": 1, "id": 4, "cmd": "stop"})
    assert worker.outgoing.qsize() == 1
    assert json.loads(worker.outgoing.get_nowait()[2])["cmd"] == "stop"

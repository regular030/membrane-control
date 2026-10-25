"""Exercise the real serial worker with a byte-stream instrument double."""
import json
import queue
import time

import pytest
import serial

from membrane_control.models import Recipe, Step
from membrane_control.transport import MAX_LINE, SerialTransport, Simulator


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
    worker = SerialTransport.__new__(SerialTransport)
    worker.outgoing = queue.PriorityQueue(maxsize=64)
    worker._counter = 0
    worker.send({"v": 1, "id": 1, "cmd": "start"})
    worker.send({"v": 1, "id": 2, "cmd": "manual"})
    worker.send({"v": 1, "id": 3, "cmd": "heartbeat"})
    worker.send({"v": 1, "id": 4, "cmd": "stop"})
    assert worker.outgoing.qsize() == 1
    assert json.loads(worker.outgoing.get_nowait()[2])["cmd"] == "stop"


def test_exact_line_limit_is_accepted_when_sending():
    worker = SerialTransport.__new__(SerialTransport)
    worker.outgoing = queue.PriorityQueue(maxsize=64)
    worker._counter = 0
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

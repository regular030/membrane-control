"""Bounded background serial I/O and an explicit hardware-free simulator."""
from __future__ import annotations
import json
import math
import queue
import threading
import time
from .engine import SequenceEngine
from .models import Recipe
from . import __version__

MAX_LINE = 8192


class SerialTransport:
    def __init__(self, port, baud=115200, raw=False):
        self.port, self.baud, self.raw = port, baud, raw
        self.incoming = queue.Queue(maxsize=512)
        self.outgoing = queue.PriorityQueue(maxsize=64)
        self._counter = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"serial-{port}")
        self._thread.start()

    def send(self, message):
        body = json.dumps(message, separators=(",", ":"), allow_nan=False, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_LINE:
            raise ValueError("Command exceeds serial line limit")
        payload = body + b"\n"
        self._counter += 1
        if message.get("cmd") == "stop":
            # Do not execute an older queued start/manual command after a stop.
            while True:
                try:
                    self.outgoing.get_nowait()
                except queue.Empty:
                    break
        priority = 0 if message.get("cmd") == "stop" else 2 if message.get("cmd") == "heartbeat" else 1
        try:
            self.outgoing.put_nowait((priority, self._counter, payload))
        except queue.Full:
            self.close()
            raise RuntimeError("Serial command queue is full; reconnect after checking the controller")

    def _emit(self, packet):
        try:
            self.incoming.put_nowait(packet)
        except queue.Full:
            self._stop.set()

    def _run(self):
        import serial
        connection = None
        try:
            # Configure control lines before opening to avoid intentional boot/reset toggles.
            connection = serial.Serial(port=None, baudrate=self.baud, timeout=0.05, write_timeout=0.25)
            connection.dtr = False
            connection.rts = False
            connection.port = self.port
            connection.open()
            self._emit({"type": "port_open"})
            buffer = bytearray()
            discarding = False
            while not self._stop.is_set():
                for _ in range(4):
                    try:
                        _, _, payload = self.outgoing.get_nowait()
                    except queue.Empty:
                        break
                    written = connection.write(payload)
                    if written != len(payload):
                        raise RuntimeError("Incomplete serial write")
                chunk = connection.read(min(max(connection.in_waiting, 1), 1024))
                for byte in chunk:
                    if byte == 10:
                        if not discarding and buffer:
                            try:
                                line = buffer.decode("utf-8").strip()
                                packet = {"type": "mass_line", "line": line} if self.raw else json.loads(line)
                                if isinstance(packet, dict):
                                    self._emit(packet)
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                self._emit({"type": "parse_error", "error": "Malformed serial data"})
                        buffer.clear()
                        discarding = False
                    elif not discarding:
                        buffer.append(byte)
                        if len(buffer) > (256 if self.raw else MAX_LINE):
                            buffer.clear()
                            discarding = True
                            self._emit({"type": "parse_error", "error": "Serial line too long"})
            self._emit({"type": "disconnected", "error": "Serial connection closed"})
        except Exception as error:
            self._emit({"type": "disconnected", "error": str(error)})
        finally:
            if connection is not None:
                connection.close()

    def poll(self, now=None):
        result = []
        for _ in range(512):
            try:
                result.append(self.incoming.get_nowait())
            except queue.Empty:
                break
        if not self._thread.is_alive() and not any(p.get("type") == "disconnected" for p in result):
            result.append({"type": "disconnected", "error": "Serial worker stopped"})
        return result

    def close(self):
        self._stop.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=0.5)


class Simulator:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.engine = SequenceEngine()
        self.events = []
        self.last_heartbeat = self.started
        self.last_poll = self.started
        self.mass = 0.0

    def _advance(self, now):
        # Model the controller's independent clock before a newly arrived host
        # command can refresh its heartbeat. A recipe that already ended before
        # the deadline was safely idle; equality faults because firmware checks
        # the watchdog before advancing a step at that instant.
        deadline = self.last_heartbeat + 3.0
        if self.engine.state in ("running", "manual") and now >= deadline:
            completed_before_timeout = (self.engine.state == "running"
                and self.engine.started + self.engine.recipe.duration_s < deadline)
            if not completed_before_timeout:
                self.engine.fail("Controller heartbeat timeout")
                return
        self.engine.tick(now)

    def send(self, packet):
        now = self.clock()
        self._advance(now)
        command = packet.get("cmd")
        reply = {"v": 1, "id": packet["id"], "type": "ack", "ok": True}
        try:
            if command == "hello":
                reply.update(type="hello", device="basu-membrane-control", firmware_version=__version__,
                             protocol_version=1, valve_count=7, hardware_verified=False, simulation=True)
            elif command == "heartbeat":
                self.last_heartbeat = now
            elif command == "load_recipe":
                self.engine.load(Recipe.from_dict(packet["recipe"]))
            elif command == "start":
                self.engine.start(now)
                self.last_heartbeat = now
            elif command == "manual":
                was_idle = self.engine.state == "idle"
                self.engine.manual(packet["valves"], packet["pump_percent"])
                if was_idle:
                    self.last_heartbeat = now
            elif command == "stop":
                self.engine.stop()
            elif command == "clear_fault":
                self.engine.clear_fault()
            else:
                raise ValueError("Unknown command")
        except (ValueError, KeyError) as error:
            reply.update(type="error", ok=False, error=str(error))
        self.events.append(reply)

    def poll(self, now=None):
        now = self.clock() if now is None else now
        self._advance(now)
        pump = self.engine.pump_percent
        flow = pump * 1.5 if any(self.engine.valves) else 0.0
        flow *= 1 + 0.015 * math.sin(now)
        self.mass += flow / 60 * max(0, min(now - self.last_poll, 5.0))
        self.last_poll = now
        events, self.events = self.events, []
        events.append({"v": 1, "type": "telemetry", "uptime_ms": int((now-self.started)*1000) & 0xffffffff,
            "state": self.engine.state, "step_index": self.engine.step_index, "cycle": self.engine.cycle,
            "remaining_s": self.engine.remaining_s, "valves": list(self.engine.valves), "pump_percent": pump,
            "pressure_psi": pump * 0.12, "flow_ml_min": flow, "pump_feedback_v": pump / 10,
            "fault": self.engine.fault, "hardware_verified": False, "simulation": True})
        return events

    def close(self):
        self.engine.stop()

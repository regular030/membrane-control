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
_retired_lock = threading.RLock()
_retired_transports = {}


def recover_serial_port(port):
    """Retry only this application's retired cleanup owner, never an active port."""
    key = str(port).strip().casefold()
    with _retired_lock:
        previous = _retired_transports.get(key)
    if previous is None:
        return
    try:
        previous.close()
    except Exception as exc:
        if previous.cleanup_pending:
            raise RuntimeError(f'Previous serial connection has not released {port}: {exc}') from exc
        # An error after an already-closed handle is diagnostic, not a port lease.
    if previous.cleanup_pending:
        raise RuntimeError(f'Previous serial connection is still releasing {port}; try Recover connection again.')


def close_transport(transport, stop_message=None):
    """Close real transports and simple simulator/test adapters consistently."""
    if transport is None:
        return
    if stop_message is not None:
        close_with_stop = getattr(transport, "close_with_stop", None)
        if callable(close_with_stop):
            return close_with_stop(stop_message)
        try:
            transport.send(stop_message)
        except Exception:
            pass  # Link failure must never prevent closing the local resource.
    return transport.close()


class SerialTransport:
    def __init__(self, port, baud=115200, raw=False, *, serial_format='8N1', diagnostics=False, dtr=None):
        if serial_format not in ('8N1', '7E1', '7O1'):
            raise ValueError('Serial format must be 8N1, 7E1 or 7O1.')
        if dtr is not None and type(dtr) is not bool:
            raise ValueError('DTR must be true or false when specified.')
        if not raw and (serial_format != '8N1' or diagnostics or dtr is True):
            raise ValueError('Alternate serial formats and raw diagnostics are for the balance only.')
        recover_serial_port(port)
        self.port, self.baud, self.raw = port, baud, raw
        self.serial_format, self.diagnostics = serial_format, bool(diagnostics)
        self.dtr = bool(raw) if dtr is None else dtr
        self.incoming = queue.Queue(maxsize=512)
        self.outgoing = queue.PriorityQueue(maxsize=64)
        self._counter = 0
        self._stop = threading.Event()
        self._closing = threading.Event()
        self._terminated = threading.Event()
        self._state_lock = threading.RLock()
        self._connection_lock = threading.Lock()
        self._handle_close_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._close_thread = None
        self._connection = None
        self._opened = False
        self._final_stop_payload = None
        self._final_stop_done = threading.Event()
        self._close_error = None
        self._terminal_error = None
        self._terminal_reported = False
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"serial-{port}")
        self._thread.start()

    def send(self, message):
        self._enqueue(self._encode(message), message.get('cmd'))

    def request_reading(self):
        """Nimbus Print only (manual section 11.3); no tare or configuration."""
        if not self.raw:
            raise ValueError('A reading request is only supported on a balance transport.')
        with self._connection_lock:
            opened = self._opened and self._connection is not None
        if not opened:
            raise RuntimeError(self._terminal_error or 'Balance port is not open; reconnect or wait for it to open.')
        self._enqueue(b'!KP\r')

    def _enqueue(self, payload, command=None):
        overflow = False
        with self._state_lock:
            if self._closing.is_set() or self._stop.is_set() or self._terminated.is_set() or self._terminal_error is not None:
                raise RuntimeError(self._terminal_error or "Serial connection is closed; reconnect the controller")
            self._counter += 1
            if command == "stop":
                self._discard_outgoing()
            priority = 0 if command == "stop" else 2 if command == "heartbeat" else 1
            try:
                self.outgoing.put_nowait((priority, self._counter, payload))
            except queue.Full:
                overflow = True
        if overflow:
            try:
                self.close()
            finally:
                raise RuntimeError("Serial command queue is full; reconnect after checking the controller")

    @staticmethod
    def _encode(message):
        body = json.dumps(message, separators=(",", ":"), allow_nan=False, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_LINE:
            raise ValueError("Command exceeds serial line limit")
        return body + b"\n"

    def _discard_outgoing(self):
        while True:
            try:
                self.outgoing.get_nowait()
            except queue.Empty:
                return

    def _next_write(self):
        with self._state_lock:
            if self._stop.is_set():
                return None
            if self._closing.is_set():
                payload, self._final_stop_payload = self._final_stop_payload, None
                if payload is None:
                    self._stop.set()
                    return None
                return payload, True
            try:
                return self.outgoing.get_nowait()[2], False
            except queue.Empty:
                return None

    def _emit(self, packet):
        try:
            self.incoming.put_nowait(packet)
        except queue.Full:
            self._stop.set()
            with self._state_lock:
                if self._terminal_error is None:
                    self._terminal_error = 'Serial receive queue overflow; serial traffic stopped. Disconnect and reconnect.'

    def _run(self):
        connection = None
        try:
            import serial
            # Configure control lines before opening to avoid intentional boot/reset toggles.
            settings = dict(port=None, baudrate=self.baud, timeout=0.05, write_timeout=0.25)
            if self.raw:
                settings.update(bytesize=8 if self.serial_format == '8N1' else 7,
                                parity={'8N1': 'N', '7E1': 'E', '7O1': 'O'}[self.serial_format],
                                stopbits=1, xonxoff=False, rtscts=False, dsrdtr=False)
            connection = serial.Serial(**settings)
            with self._connection_lock:
                self._connection = connection
            if self._closing.is_set():
                return
            # Controller UARTs keep reset-related lines inactive. A raw USB
            # balance uses normal DTR readiness, with no RTS/CTS handshaking.
            connection.dtr = self.dtr
            connection.rts = False
            connection.port = self.port
            connection.open()
            with self._connection_lock:
                self._opened = True
            if self._closing.is_set():
                return  # A close during open must not publish readiness or send traffic.
            self._emit({"type": "port_open"})
            buffer = bytearray()
            discarding = False
            raw_cr = False
            while not self._stop.is_set():
                for _ in range(4):
                    item = self._next_write()
                    if item is None:
                        break
                    payload, final_stop = item
                    if self._stop.is_set() or (self._closing.is_set() and not final_stop):
                        continue
                    written = connection.write(payload)
                    if written != len(payload):
                        raise RuntimeError("Incomplete serial write")
                    if final_stop:
                        self._final_stop_done.set()
                        self._stop.set()
                        break
                if self._stop.is_set():
                    break
                if self._closing.is_set():
                    continue
                chunk = connection.read(min(max(connection.in_waiting, 1), 1024))
                if self._closing.is_set() or self._stop.is_set():
                    continue
                if chunk and self.diagnostics:
                    self._emit({'type': 'serial_raw', 'data': bytes(chunk)})
                for byte in chunk:
                    if byte == 10 or (self.raw and byte == 13):
                        if self.raw and byte == 10 and raw_cr:
                            raw_cr = False  # A split CRLF pair is one line.
                            continue
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
                        raw_cr = self.raw and byte == 13
                    elif not discarding:
                        raw_cr = False
                        buffer.append(byte)
                        if len(buffer) > (256 if self.raw else MAX_LINE):
                            buffer.clear()
                            discarding = True
                            self._emit({"type": "parse_error", "error": "Serial line too long"})
        except Exception as error:
            if not self._closing.is_set():
                self._record_disconnect(str(error))
        finally:
            self._close_connection(force=True)
            with self._state_lock:
                self._stop.set()
                self._discard_outgoing()
            self._record_disconnect("Serial connection closed")
            self._terminated.set()
            self._remember_cleanup(worker_finished=True)

    @staticmethod
    def _cancel_io(connection, *, cancel_write=True):
        if connection is None:
            return
        for method in (("cancel_read", "cancel_write") if cancel_write else ("cancel_read",)):
            try:
                cancel = getattr(connection, method, None)
                if cancel is not None:
                    cancel()
            except Exception:
                pass  # Closing the handle below is the fallback for an unsupported cancellation.

    def _close_connection(self, *, force=False):
        # The worker and UI can arrive here together. Do not close one handle
        # concurrently, or forget its owner before a failed close can be retried.
        if not self._handle_close_lock.acquire(blocking=False):
            return
        try:
            with self._connection_lock:
                if self._connection is None or (not self._opened and not force and not self._close_error):
                    return
                if self._close_thread is not None and self._close_thread.is_alive():
                    return
                connection = self._connection
                self._opened = False
                self._close_thread = threading.Thread(target=self._finish_connection_close,
                    args=(connection,), daemon=True, name=f'serial-close-{self.port}')
                self._close_thread.start()
        finally:
            self._handle_close_lock.release()

    def _finish_connection_close(self, connection):
        # Some drivers can block in close(). Keep one owned closer off the GUI
        # thread and retain the resource until it actually finishes. A retry
        # must wait for this same closer, never race another close/open against it.
        self._cancel_io(connection)
        try:
            connection.close()
        except Exception as error:
            self._close_error = str(error) or 'Serial handle close failed'
            if not self._connection_still_open(connection):
                with self._connection_lock:
                    if self._connection is connection:
                        self._connection = None
            self._record_disconnect(self._close_error)
        else:
            with self._connection_lock:
                if self._connection is connection:
                    self._connection = None
            self._close_error = None
        finally:
            self._remember_cleanup()

    @staticmethod
    def _connection_still_open(connection):
        try:
            state = getattr(connection, 'is_open', None)
            if type(state) is bool:
                return state
            closed = getattr(connection, 'closed', None)
            if type(closed) is bool:
                return not closed
        except Exception:
            pass
        return True  # Cannot prove that the driver's handle was released.

    @property
    def cleanup_pending(self):
        with self._connection_lock:
            has_connection = self._connection is not None
        return has_connection or self._thread.is_alive()

    def _remember_cleanup(self, *, worker_finished=False):
        with self._connection_lock:
            has_connection = self._connection is not None
        pending = has_connection or (not worker_finished and self._thread.is_alive())
        key = str(self.port).strip().casefold()
        with _retired_lock:
            if pending:
                _retired_transports[key] = self
            elif _retired_transports.get(key) is self:
                _retired_transports.pop(key)

    def _record_disconnect(self, error):
        # Keep the first failure even if close() also fails or the incoming
        # queue is full. A later poll must not replace it with a generic error.
        with self._state_lock:
            if self._terminal_error is None:
                self._terminal_error = error or "Serial connection closed"
                self._emit({"type": "disconnected", "error": self._terminal_error})

    def poll(self, now=None):
        result = []
        for _ in range(512):
            try:
                packet = self.incoming.get_nowait()
            except queue.Empty:
                break
            if packet.get("type") == "disconnected":
                if self._terminal_reported:
                    continue
                self._terminal_reported = True
            result.append(packet)
        if self._terminal_error is not None or self._terminated.is_set():
            # Failure takes precedence over queued old acknowledgements/status.
            # In particular, queue overflow must expose its reason rather than
            # letting a partial stale packet hide it in the protocol consumer.
            if not self._terminal_reported:
                self._terminal_reported = True
                return [{"type": "disconnected", "error": self._terminal_error or "Serial worker stopped"}]
            return [packet for packet in result if packet.get('type') == 'disconnected']
        return result

    def close(self, stop_message=None, *, timeout=1.0):
        """Withdraw traffic and release the handle within a bounded wait.

        An explicit STOP may be attempted by the worker before cancellation.
        Successful writing is not an acknowledgement of physical execution.
        Unfinished open() calls retain a cleanup obligation in the worker;
        they can never reopen the session or send queued traffic afterwards.
        """
        final_payload = None
        if stop_message is not None:
            if (not isinstance(stop_message, dict) or stop_message.get("cmd") != "stop"
                    or type(stop_message.get("v")) is not int or stop_message["v"] != 1
                    or type(stop_message.get("id")) is not int or not 0 < stop_message["id"] <= 0xffffffff):
                raise ValueError("Shutdown message must be a valid v1 STOP command")
            final_payload = self._encode(stop_message)
        deadline = time.monotonic() + max(0.0, min(float(timeout), 2.0))
        try:
            self._close_impl(final_payload, deadline)
        finally:
            self._remember_cleanup()

    def _close_impl(self, final_payload, deadline):
        if not self._close_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            raise RuntimeError('Serial cleanup is already in progress; try Recover connection again.')
        try:
            with self._connection_lock:
                connection = self._connection
                can_write_stop = self._opened
            with self._state_lock:
                first_close = not self._closing.is_set()
                self._closing.set()
                self._discard_outgoing()
                graceful = (first_close and final_payload is not None and can_write_stop
                            and not self._stop.is_set() and self._terminal_error is None)
                if graceful:
                    self._final_stop_payload = final_payload
                else:
                    self._stop.set()
            # Wake a pending read for an explicit STOP. Give an already-running
            # write its normal short timeout before force-cancelling all I/O.
            self._cancel_io(connection, cancel_write=not graceful)
            if graceful and self._thread is not threading.current_thread():
                self._final_stop_done.wait(timeout=max(0.0, min(0.35, deadline - time.monotonic())))
            with self._state_lock:
                self._stop.set()
                self._final_stop_payload = None
                self._discard_outgoing()
            self._cancel_io(connection)
            self._close_connection()
            if self._thread is not threading.current_thread():
                self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
                if self._thread.is_alive():
                    raise RuntimeError("Serial worker is still shutting down; its pending open will be closed when it returns")
            with self._connection_lock:
                closer = self._close_thread
            if closer is not None and closer is not threading.current_thread():
                closer.join(timeout=max(0.0, deadline - time.monotonic()))
                if closer.is_alive():
                    raise RuntimeError('Serial handle is still closing; try Recover connection again.')
            if self._close_error:
                raise RuntimeError("Serial handle could not be closed: " + self._close_error)
            with self._connection_lock:
                if self._connection is not None:
                    raise RuntimeError('Serial handle is still closing; try Recover connection again.')
        finally:
            self._close_lock.release()

    def close_with_stop(self, message):
        return self.close(stop_message=message)


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

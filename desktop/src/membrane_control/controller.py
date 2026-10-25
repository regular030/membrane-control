"""Application orchestration independent of Qt, with explicit connection/fault gates."""
from __future__ import annotations
from collections import deque
import copy
import json
import math
import logging
from pathlib import Path
import time

from .balance import MassFlow, parse_mass
from .models import Recipe, number, valve_states
from .recipes import built_in_recipes, read_recipe, write_recipe
from .storage import RunStore
from .transport import SerialTransport, Simulator

DEFAULT_SETTINGS = {"membrane_area_m2": 0.01, "density_g_ml": 1.0,
                    "record_interval_s": 1.0, "require_balance": False,
                    "max_pressure_psi": 20.0}


class AppController:
    def __init__(self, data_dir, clock=time.monotonic):
        self.clock = clock
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = RunStore(self.data_dir)
        self.settings = dict(DEFAULT_SETTINGS)
        self.log = deque(maxlen=100)
        self.settings_path = self.data_dir / "settings.json"
        if self.settings_path.exists():
            try:
                loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
                self.settings = self._checked_settings({**self.settings, **loaded})
            except (ValueError, TypeError, OSError):
                self.log.append("Saved settings could not be read; using documented defaults")
        self.presets = built_in_recipes()
        self.recipe = copy.deepcopy(next(iter(self.presets.values())))
        self.driver = None
        self.balance = None
        self.simulation = True
        self.device = {}
        self.pending = {}
        self.next_id = 0
        self.last_telemetry = None
        self.last_mass = None
        self.last_heartbeat = -100.0
        self.connect_started = None
        self.last_hello = -100.0
        self.local_fault = None
        self.mass_flow = MassFlow()
        self.start_phase = None
        self.stop_pending = False
        self.run_started = None
        self.last_record = -100.0
        self.run_id = None
        self.closed = False
        self.snapshot = {"state": "idle", "simulation": True, "controller_connected": False,
            "controller_status": "Not connected", "balance_connected": False,
            "balance_status": "Not connected", "hardware_verified": False,
            "pressure_psi": None, "flow_ml_min": None, "pump_feedback_v": None, "flux_lmh": None, "mass_g": None,
            "balance_flow_ml_min": None, "pump_percent": 0.0, "valves": [False]*7,
            "step_index": -1, "cycle": 0, "remaining_s": 0.0, "fault": None,
            "elapsed_s": 0.0, "run_id": None, "log": [], "recipe_name": self.recipe.name,
            "step_name": "Ready", "start_pending": False, "stop_pending": False}
        self.set_simulation(True)

    @staticmethod
    def _checked_settings(settings):
        result = dict(DEFAULT_SETTINGS)
        result["membrane_area_m2"] = number(settings["membrane_area_m2"], "Membrane area", 0.000001, 10000)
        result["density_g_ml"] = number(settings["density_g_ml"], "Density", 0.01, 30)
        result["record_interval_s"] = number(settings["record_interval_s"], "Recording interval", 0.1, 3600)
        result["max_pressure_psi"] = number(settings.get("max_pressure_psi", 20), "Desktop pressure limit", 0.1, 100)
        if type(settings["require_balance"]) is not bool:
            raise ValueError("Balance requirement must be a boolean")
        result["require_balance"] = settings["require_balance"]
        return result

    def _log(self, message):
        self.log.append(time.strftime("%H:%M:%S") + "  " + str(message))

    def _active(self):
        return self.start_phase is not None or self.stop_pending or self.snapshot["state"] in ("running", "manual")

    def _request(self, command, **values):
        if self.driver is None:
            raise ValueError("Connect a controller first")
        self.next_id += 1
        packet = {"v": 1, "id": self.next_id, "cmd": command, **values}
        self.driver.send(packet)
        if command != "heartbeat":
            self.pending[self.next_id] = (command, self.clock() + 3.0)
        return self.next_id

    def list_presets(self):
        recipes = copy.deepcopy(self.presets)
        custom_directory = self.data_dir / "presets"
        if custom_directory.exists():
            for path in sorted(custom_directory.glob("*.json"))[:100]:
                try:
                    recipe = read_recipe(path)
                    recipes[recipe.name] = recipe
                except (ValueError, OSError):
                    continue
        return recipes

    def load_recipe(self, recipe):
        if self._active():
            raise ValueError("Stop before changing a sequence")
        recipe.validate()
        self.recipe = copy.deepcopy(recipe)
        self.snapshot["recipe_name"] = recipe.name
        self._log(f"Loaded {recipe.name}")

    def save_recipe(self, path, recipe):
        write_recipe(path, recipe)
        # Keep a separate copy available in the preset dropdown next launch.
        import hashlib
        key = hashlib.sha256(recipe.name.encode()).hexdigest()[:16]
        write_recipe(self.data_dir / "presets" / (key + ".json"), recipe)

    def load_recipe_file(self, path):
        return read_recipe(path)

    def update_settings(self, changes):
        if self._active():
            raise ValueError("Stop before changing calibration or recording settings")
        settings = self._checked_settings({**self.settings, **changes})
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(settings, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(self.settings_path)
        self.settings = settings
        self.mass_flow.reset()
        self._log("Settings saved")

    def set_simulation(self, enabled):
        if self._active():
            raise ValueError("Stop before switching connection modes")
        self.disconnect_controller()
        self.disconnect_balance()
        self.simulation = bool(enabled)
        self.snapshot["simulation"] = self.simulation
        self.local_fault = None
        self.snapshot["fault"] = None
        if enabled:
            self.driver = Simulator(self.clock)
            self.connect_started = self.clock()
            self._request("hello")
            self._log("Demo mode: all measurements and outputs are simulated")
        else:
            self._log("Hardware mode: select controller and balance ports")

    @staticmethod
    def list_ports():
        from serial.tools import list_ports
        return [(p.device, p.description) for p in list_ports.comports()]

    def connect_controller(self, port):
        if self.simulation:
            raise ValueError("Turn Demo mode off before connecting real hardware")
        if self._active():
            raise ValueError("Stop before reconnecting")
        if self.balance is not None and self.balance.port == port:
            raise ValueError("Controller and balance need different ports")
        self.disconnect_controller()
        self.driver = SerialTransport(port)
        self.connect_started = self.clock()
        self.last_hello = -100.0
        self.snapshot["controller_status"] = "Opening port; waiting for firmware"
        self._log(f"Opening controller {port}")

    def disconnect_controller(self):
        if self.driver is not None:
            try:
                self.driver.send({"v": 1, "id": 2147483647, "cmd": "stop"})
            except Exception:
                pass
            self.driver.close()
        self.driver = None
        self.pending.clear()
        self.start_phase = None
        self.stop_pending = False
        self.device = {}
        self.last_telemetry = None
        if self.run_id is not None:
            self._finish_run("disconnected")
        if hasattr(self, "snapshot"):
            self.snapshot.update(controller_connected=False, controller_status="Disconnected",
                state="idle", start_pending=False, stop_pending=False, valves=[False]*7, pump_percent=0,
                pressure_psi=None, flow_ml_min=None, pump_feedback_v=None, flux_lmh=None, hardware_verified=False)

    def connect_balance(self, port, baud=9600):
        if self.simulation:
            raise ValueError("Turn Demo mode off before connecting the balance")
        if self._active():
            raise ValueError("Stop before reconnecting a balance")
        if self.driver is not None and self.driver.port == port:
            raise ValueError("Balance and controller need different ports")
        self.disconnect_balance()
        self.balance = SerialTransport(port, baud, raw=True)
        self.snapshot["balance_status"] = "Waiting for a weight reading"
        self._log(f"Opening balance {port} at {baud} baud, 8N1")

    def disconnect_balance(self):
        if self.balance is not None:
            self.balance.close()
        self.balance = None
        self.last_mass = None
        self.mass_flow.reset()
        if hasattr(self, "snapshot"):
            self.snapshot.update(balance_connected=False, balance_status="Disconnected", mass_g=None, balance_flow_ml_min=None)

    def start_run(self):
        if self._active():
            raise ValueError("An operation is already active")
        if self.local_fault or self.snapshot["state"] == "fault":
            raise ValueError("Clear the fault before starting")
        if not self.snapshot["controller_connected"] or self.last_telemetry is None:
            raise ValueError("Wait for a responding controller and fresh telemetry")
        if self.clock() - self.last_telemetry > 2:
            raise ValueError("Controller telemetry is stale")
        if not self.snapshot["simulation"]:
            if not self.snapshot["hardware_verified"] or not self.recipe.hardware_approved:
                raise ValueError("Physical operation requires verified firmware and an approved recipe")
            if self.snapshot["pressure_psi"] is None:
                raise ValueError("Physical operation requires a valid pressure reading")
        if (self.recipe.require_balance or self.settings["require_balance"]) and not self.snapshot["balance_connected"]:
            raise ValueError("This run requires a fresh balance reading")
        self.start_phase = "loading"
        self.snapshot["start_pending"] = True
        try:
            self._request("load_recipe", recipe=self.recipe.to_dict())
        except Exception:
            self.start_phase = None
            self.snapshot["start_pending"] = False
            raise

    def stop_run(self):
        self.start_phase = None
        self.snapshot["start_pending"] = False
        if self.stop_pending:
            return  # Repeated clicks must not extend the acknowledgement deadline.
        if self.driver is not None:
            self.pending.clear()
            self.stop_pending = True
            self.snapshot["stop_pending"] = True
            try:
                self._request("stop")
            except Exception as error:
                self._stop_failed("Stop could not be sent: " + str(error))
                return
        else:
            self._finish_run("stopped")
        self._log("Stop requested")

    def set_manual(self, valves, pump_percent):
        if self.start_phase or self.stop_pending or self.snapshot["state"] not in ("idle", "manual") or self.local_fault:
            raise ValueError("Stop the sequence or clear the fault first")
        if not self.snapshot["controller_connected"]:
            raise ValueError("Controller is not responding")
        valves, pump_percent = valve_states(valves), number(pump_percent, "Pump setting", 0, 100)
        if not self.snapshot["simulation"]:
            if not self.snapshot["hardware_verified"] or not self.recipe.hardware_approved:
                raise ValueError("Physical controls are locked until hardware and recipe are approved")
            if self.snapshot["pressure_psi"] is None:
                raise ValueError("Physical controls require a valid pressure reading")
        self._request("manual", valves=list(valves), pump_percent=pump_percent)

    def clear_fault(self):
        if not self.snapshot["controller_connected"]:
            raise ValueError("Reconnect the controller before clearing a fault")
        if self.stop_pending:
            raise ValueError("Wait for stop confirmation before clearing the fault")
        self._request("clear_fault")

    def _stop_failed(self, reason):
        """Cease heartbeats when stop execution cannot be confirmed.

        Continuing heartbeat traffic after a failed stop would prevent the
        controller watchdog from protecting a still-active output.
        """
        if self.local_fault and self.local_fault not in reason:
            reason = self.local_fault + "; " + reason
        driver, self.driver = self.driver, None
        if driver is not None:
            try:
                driver.close()
            except Exception as error:
                self._log("Serial close failed after unconfirmed stop: " + str(error))
        self.pending.clear()
        self.device = {}
        self.last_telemetry = None
        self.start_phase = None
        self.stop_pending = False
        self.local_fault = reason
        self.snapshot.update(state="fault", fault=reason, start_pending=False, stop_pending=False,
            controller_connected=False, controller_status="Stop unconfirmed; connection closed for watchdog stop",
            hardware_verified=False, pressure_psi=None, flow_ml_min=None, flux_lmh=None, pump_feedback_v=None)
        self._finish_run("fault")
        self._log(reason)

    def _finish_run(self, status):
        if self.run_id is not None:
            if self.run_started is not None:
                self.snapshot["elapsed_s"] = max(0.0, self.clock() - self.run_started)
            self.store.sample(self.run_id, self.snapshot)
            self.store.finish(self.run_id, status)
            self._log(f"Run {self.run_id}: {status}")
        self.run_id = None
        self.snapshot["run_id"] = None

    def _abort(self, reason):
        if self.local_fault == reason:
            return
        self.local_fault = self.local_fault or reason
        self.start_phase = None
        self.snapshot.update(fault=self.local_fault, state="fault", start_pending=False)
        if self.stop_pending:
            # A second fault must not replace an outstanding stop or extend
            # its deadline. Otherwise two alternating faults defeat the watchdog.
            self._finish_run("fault")
            return
        self.pending.clear()
        if self.driver is not None:
            self.stop_pending = True
            self.snapshot["stop_pending"] = True
            try:
                self._request("stop")
            except Exception as error:
                self._stop_failed("Stop could not be sent after fault: " + str(error))
                return
        self._finish_run("fault")
        self._log(reason)

    def _handle_packet(self, packet, now):
        kind = packet.get("type")
        if kind in ("port_open", "parse_error"):
            if kind == "parse_error":
                self._log(packet.get("error", "Invalid serial message"))
            return
        if kind == "disconnected":
            if self._active():
                self._abort("Controller disconnected")
            self.snapshot["controller_connected"] = False
            self.snapshot["controller_status"] = packet.get("error", "Disconnected")
            return
        if type(packet.get("v")) is not int or packet["v"] != 1:
            return
        if kind in ("hello", "ack", "error"):
            pending = self.pending.pop(packet.get("id"), None)
            if pending is None:
                return
            command = pending[0]
            if packet.get("ok") is not True:
                self._log(f"Controller rejected {command}: {packet.get('error', 'unknown error')}")
                if command == "stop":
                    self._stop_failed("Controller rejected stop: " + str(packet.get("error", "unknown error")))
                elif command in ("load_recipe", "start", "manual"):
                    self._abort(str(packet.get("error", "Command rejected")))
                return
            if command == "hello":
                if (kind != "hello" or packet.get("device") != "basu-membrane-control"
                    or type(packet.get("protocol_version")) is not int or packet["protocol_version"] != 1
                    or packet.get("valve_count") != 7 or type(packet.get("simulation")) is not bool
                    or type(packet.get("hardware_verified")) is not bool):
                    self.snapshot["controller_status"] = "Unsupported controller identity or protocol"
                    return
                self.device = dict(packet)
                self.snapshot.update(controller_connected=True, controller_status="Connected",
                                     hardware_verified=packet["hardware_verified"], simulation=packet["simulation"])
                self._log("Controller identified: " + str(packet.get("firmware_version", "unknown")))
            elif command == "load_recipe" and self.start_phase == "loading":
                self.start_phase = "starting"
                self._request("start")
            elif command == "start" and self.start_phase == "starting":
                self.start_phase = None
                self.snapshot["start_pending"] = False
                self.run_started = now
                self.last_record = -100.0
                self.run_id = self.store.start(self.recipe, self.settings, self.device)
                self.snapshot["run_id"] = self.run_id
                self._log(f"Started run {self.run_id}: {self.recipe.name}")
            elif command == "stop":
                self.stop_pending = False
                self.snapshot.update(stop_pending=False, state="fault" if self.local_fault else "idle",
                    valves=[False]*7, pump_percent=0, step_index=-1, cycle=0, remaining_s=0)
                self._finish_run("stopped")
                self._log("Stop acknowledged")
            elif command == "clear_fault":
                self.local_fault = None
                self.snapshot["fault"] = None
                self._log("Fault cleared; system remains idle")
            return
        if kind != "telemetry" or not self.device:
            return
        try:
            valves = valve_states(packet.get("valves"))
            pump = number(packet.get("pump_percent"), "Pump telemetry", 0, 100)
            state = packet.get("state")
            if state not in ("idle", "running", "manual", "fault"):
                raise ValueError("Invalid controller state")
            if packet.get("simulation") is not self.device["simulation"]:
                raise ValueError("Controller mode changed; reconnect required")
            if packet.get("hardware_verified") is not self.device["hardware_verified"]:
                raise ValueError("Controller hardware status changed")
            values = {}
            for key, low, high in (("pressure_psi", -100, 1000), ("flow_ml_min", -1e6, 1e6), ("pump_feedback_v", -1, 12)):
                value = packet.get(key)
                values[key] = None if value is None else number(value, key, low, high)
            step = packet.get("step_index", -1)
            cycle = packet.get("cycle", 0)
            if type(step) is not int or not -1 <= step < 32 or type(cycle) is not int or not 0 <= cycle <= 100:
                raise ValueError("Invalid step or cycle telemetry")
            remaining = number(packet.get("remaining_s", 0), "Remaining duration", 0, 86400)
            fault = packet.get("fault")
            if fault is not None and (not isinstance(fault, str) or len(fault) > 512):
                raise ValueError("Invalid fault message")
        except ValueError as error:
            self._log(str(error))
            return
        previous = self.snapshot["state"]
        self.last_telemetry = now
        self.snapshot.update(values)
        self.snapshot.update(valves=list(valves), pump_percent=pump, step_index=step, cycle=cycle,
            remaining_s=remaining, state="fault" if self.local_fault else state,
            fault=self.local_fault or fault, controller_connected=True,
            controller_status="Connected (dry run)" if packet["simulation"] else "Connected")
        self.snapshot["step_name"] = self.recipe.steps[step].name if 0 <= step < len(self.recipe.steps) else "Ready"
        if state == "fault":
            self._finish_run("fault")
        elif previous == "running" and state == "idle" and self.run_id is not None and not self.stop_pending:
            self._finish_run("completed")
        if (not packet["simulation"] and values["pressure_psi"] is None
                and (state in ("running", "manual") or self.start_phase is not None)):
            self._abort("Pressure reading unavailable during physical operation")
            return
        if state in ("running", "manual") and values["pressure_psi"] is not None and values["pressure_psi"] > self.settings["max_pressure_psi"]:
            self._abort("Desktop pressure limit exceeded")

    def tick(self):
        try:
            self._tick()
        except Exception as error:
            # Stop sending heartbeats after an internal/storage failure. The
            # firmware watchdog remains effective even if a stop cannot be sent.
            logging.exception("Controller update failed")
            if self.driver is not None:
                try:
                    self.driver.send({"v": 1, "id": 2147483646, "cmd": "stop"})
                except Exception:
                    pass
                self.driver.close()
                self.driver = None
            self.pending.clear()
            self.start_phase = None
            self.stop_pending = False
            self.local_fault = "Application stopped: " + str(error)
            self.snapshot.update(state="fault", fault=self.local_fault, controller_connected=False,
                controller_status="Stopped after application error", start_pending=False, stop_pending=False,
                pressure_psi=None, flow_ml_min=None, pump_feedback_v=None, flux_lmh=None)
            self._log(self.local_fault)

    def _tick(self):
        if self.closed:
            return
        now = self.clock()
        if self.driver is not None:
            if now - self.last_heartbeat >= 0.5:
                try:
                    self._request("heartbeat")
                except Exception as error:
                    self._abort(str(error))
                self.last_heartbeat = now
            if self.driver is not None and not self.device and self.connect_started is not None and now-self.connect_started < 8 and now-self.last_hello >= 1:
                self._request("hello")
                self.last_hello = now
            if self.driver is not None:
                for packet in self.driver.poll(now):
                    self._handle_packet(packet, now)
        for request_id, (command, deadline) in list(self.pending.items()):
            if now > deadline:
                self.pending.pop(request_id, None)
                if command == "stop":
                    self._stop_failed("No acknowledgement for stop")
                    break
                if command != "hello":
                    self._abort(f"No acknowledgement for {command}")
                    break
        if self.driver is not None and not self.device and self.connect_started is not None and now-self.connect_started >= 8:
            self.snapshot["controller_status"] = "Adapter found; ESP32 firmware did not respond"
        if self.last_telemetry is not None and now-self.last_telemetry > 2:
            if self._active():
                self._abort("Controller telemetry is stale")
            self.snapshot.update(controller_connected=False, controller_status="Telemetry stale", pressure_psi=None,
                                 flow_ml_min=None, flux_lmh=None, pump_feedback_v=None)
        if self.simulation and self.driver is not None:
            self._accept_mass(now, self.driver.mass)
            self.snapshot["balance_status"] = "Connected (simulated)"
        elif self.balance is not None:
            for packet in self.balance.poll(now):
                if packet.get("type") == "mass_line":
                    try:
                        self._accept_mass(now, parse_mass(packet["line"]))
                    except ValueError:
                        self._log("Ignored balance line: " + packet["line"][:80])
                elif packet.get("type") == "disconnected":
                    self.last_mass = None
                    self.mass_flow.reset()
                    self.snapshot.update(balance_status=packet.get("error", "Disconnected"),
                        balance_connected=False, mass_g=None, balance_flow_ml_min=None)
        if self.last_mass is not None and now-self.last_mass > 3:
            self.snapshot.update(balance_connected=False, balance_status="Weight data stale", mass_g=None, balance_flow_ml_min=None)
            self.mass_flow.reset()
        if self._active() and (self.recipe.require_balance or self.settings["require_balance"]) and not self.snapshot["balance_connected"]:
            self._abort("Required balance reading is unavailable")
        flow = self.snapshot["flow_ml_min"]
        self.snapshot["flux_lmh"] = None if flow is None else flow * 0.06 / self.settings["membrane_area_m2"]
        if self.run_started is not None and self.run_id is not None:
            self.snapshot["elapsed_s"] = max(0.0, now-self.run_started)
        self.snapshot["recipe_name"] = self.recipe.name
        self.snapshot["log"] = list(self.log)
        if self.run_id is not None:
            interval = self.recipe.sample_interval_s
            if now-self.last_record >= interval:
                self.store.sample(self.run_id, self.snapshot)
                self.last_record = now

    def _accept_mass(self, now, mass):
        self.last_mass = now
        self.snapshot.update(mass_g=mass, balance_connected=True, balance_status="Connected",
            balance_flow_ml_min=self.mass_flow.update(now, mass, self.settings["density_g_ml"]))

    def list_runs(self):
        return self.store.list_runs()

    def export_csv(self, path, run_id=None):
        self.store.export(path, run_id)
        self._log("Exported " + str(path))

    def close(self):
        if self.closed:
            return
        try:
            for name, action in (("stop", self.stop_run),
                                 ("controller disconnect", self.disconnect_controller),
                                 ("balance disconnect", self.disconnect_balance)):
                try:
                    action()
                except Exception as error:
                    # A full disk must not prevent serial handles and the
                    # database from being closed during application shutdown.
                    logging.exception("Application close failed during %s", name)
                    self._log("Close error during " + name + ": " + str(error))
        finally:
            try:
                self.store.close()
            except Exception:
                logging.exception("Could not close run database")
            finally:
                self.driver = None
                self.balance = None
                self.closed = True

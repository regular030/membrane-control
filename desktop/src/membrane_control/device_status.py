"""Plain-language device status derived from observed communication and data.

An analog value is evidence of a received reading, not electrical continuity.
No status here treats a relay command as physical valve or pump feedback.
"""
from __future__ import annotations

import math

SENSOR_KEYS = ("pressure", "flow", "pump_feedback")
SENSOR_STATUS_CODES = frozenset(("simulated", "not_configured", "profile_locked",
    "hardware_unavailable", "uncalibrated", "out_of_range", "stale", "reading_received"))


def checked_controller_diagnostics(packet: dict) -> dict:
    """Copy only bounded, known optional HELLO diagnostics; never control flags."""
    result = {}
    mode = packet.get("controller_mode")
    if (type(mode) is str and mode in ("dry_run", "physical")
            and mode == ("dry_run" if packet.get("simulation") is True else "physical")):
        result["controller_mode"] = mode
    reason = packet.get("hardware_status")
    if "hardware_status" in packet and (reason is None or
            (type(reason) is str and 0 < len(reason) <= 160 and reason.isprintable())):
        result["hardware_status"] = reason
    inputs = packet.get("sensor_inputs")
    if type(inputs) is dict:
        result["sensor_inputs"] = {}
        for key in SENSOR_KEYS:
            entry = inputs.get(key)
            if type(entry) is not dict or type(entry.get("calibration_verified")) is not bool:
                continue
            source = entry.get("source")
            if type(source) is not str or source not in ("disabled", "native_adc1", "ads1115"):
                continue
            checked = {"source": source, "calibration_verified": entry["calibration_verified"]}
            field, maximum = ("pin", 39) if source == "native_adc1" else ("channel", 3)
            if source != "disabled":
                value = entry.get(field)
                if type(value) is not int or not -1 <= value <= maximum:
                    continue
                checked[field] = value
            result["sensor_inputs"][key] = checked
    return result


def checked_sensor_status(value) -> dict[str, str]:
    """Ignore malformed/unknown optional diagnostic entries independently."""
    if type(value) is not dict:
        return {}
    return {key: value[key] for key in SENSOR_KEYS
            if type(value.get(key)) is str and value[key] in SENSOR_STATUS_CODES}


def _reading(value):
    return type(value) in (int, float) and math.isfinite(value)


def _sensor_diagnostic(snapshot, key):
    code = checked_sensor_status(snapshot.get("sensor_status")).get(key)
    if code is None:
        inputs = checked_controller_diagnostics(snapshot).get("sensor_inputs", {})
        if inputs.get(key, {}).get("source") == "disabled":
            code = "not_configured"
    name = {"pressure": "pressure", "flow": "flow", "pump_feedback": "pump feedback"}[key]
    messages = {
        "not_configured": (f"Not configured: real {name} channel not set",
            "No real input channel is selected in the controller profile. A connected ESP32 alone does not provide this measurement."),
        "profile_locked": ("Profile locked: inputs not read",
            "The controller profile is not approved, so physical input acquisition remains locked."),
        "hardware_unavailable": ("Input hardware unavailable",
            "The controller could not initialize or communicate with its configured input hardware."),
        "uncalibrated": ("Input not calibrated",
            "The configured input has no verified calibration. Have its interface and calibration checked."),
        "out_of_range": ("Reading invalid/out of range",
            "The controller rejected this input's reading. Check its signal range, protected interface and calibration."),
        "stale": ("Reading stale",
            "The controller has no fresh valid reading for this input."),
        "simulated": ("Simulated: no real reading",
            "The controller marks this channel simulated. No current real numeric reading is available."),
    }
    return messages.get(code)


def device_statuses(snapshot: dict, desktop_simulation: bool) -> list[dict[str, str]]:
    """Return display rows without opening ports or probing instruments."""
    rows = []

    def add(key, label, status, detail, level="muted"):
        rows.append(dict(key=key, label=label, status=status, detail=detail, level=level))

    if desktop_simulation:
        for key, label in (("controller", "ESP32"), ("balance", "Scale"),
                           ("pressure", "Pressure sensor"), ("flow", "Flow sensor"),
                           ("pump_feedback", "Pump voltage feedback"), ("outputs", "Valves / pump")):
            add(key, label, "Simulated", "Demo mode uses virtual devices. No physical connection is checked.", "warning")
        return rows

    connected = snapshot.get("controller_connected") is True
    dry_run = connected and snapshot.get("simulation") is True
    if connected:
        add("controller", "ESP32", "Connected (dry run)" if dry_run else "Connected",
            "ESP32 firmware is responding. Its measurements and outputs are simulated." if dry_run
            else "ESP32 firmware is responding.", "warning" if dry_run else "success")
    else:
        add("controller", "ESP32", "Not connected", snapshot.get("controller_status") or "Connect the controller in Connections and settings.")

    balance = snapshot.get("balance_connected") is True and _reading(snapshot.get("mass_g"))
    add("balance", "Scale", "Connected" if balance else "Not connected",
        "Receiving fresh weight readings from the selected scale port." if balance
        else snapshot.get("balance_status") or "Connect the scale in Connections and settings.", "success" if balance else "muted")

    for key, label, field in (("pressure", "Pressure sensor", "pressure_psi"),
                              ("flow", "Flow sensor", "flow_ml_min"),
                              ("pump_feedback", "Pump voltage feedback", "pump_feedback_v")):
        if dry_run:
            add(key, label, "Simulated", "The connected ESP32 is running dry-run firmware. This is a generated reading.", "warning")
        elif connected and _reading(snapshot.get(field)):
            add(key, label, "Reading received", "A valid reading is arriving from the controller. Wiring and calibration still need verification.", "success")
        elif connected and snapshot.get(field) is None and (diagnostic := _sensor_diagnostic(snapshot, key)):
            add(key, label, *diagnostic, "warning")
        else:
            add(key, label, "No reading", "No current valid reading is available. Check the controller, input interface and sensor.", "warning")

    if dry_run:
        add("outputs", "Valves / pump", "Simulated", "Dry-run firmware does not operate the physical outputs.", "warning")
    else:
        add("outputs", "Valves / pump", "Not monitored", "Valve-position and pump-running feedback are not monitored. A command does not confirm physical operation.")
    return rows

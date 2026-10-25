"""Plain-language device status derived from observed communication and data.

An analog value is evidence of a received reading, not electrical continuity.
No status here treats a relay command as physical valve or pump feedback.
"""
from __future__ import annotations

import math


def _reading(value):
    return type(value) in (int, float) and math.isfinite(value)


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
        else:
            add(key, label, "No reading", "No current valid reading is available. Check the controller, input interface and sensor.", "warning")

    if dry_run:
        add("outputs", "Valves / pump", "Simulated", "Dry-run firmware does not operate the physical outputs.", "warning")
    else:
        add("outputs", "Valves / pump", "Not monitored", "Valve-position and pump-running feedback are not monitored. A command does not confirm physical operation.")
    return rows

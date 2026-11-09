"""Read-only sensor commissioning tools for a normal controller connection."""
from __future__ import annotations

from itertools import pairwise
import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)


CHANNELS = {
    "pressure": ("Pressure", "IO34", "psi", 0, 100, "pressure_psi"),
    "flow": ("Flow", "SVP / IO36", "mL/min", 13, 100, "flow_ml_min"),
    "pump_feedback": ("Pump voltage output", "SVN / IO39", "V", 0, 10, "pump_feedback_v"),
}
# Factory firmware sets pressure and flow to 2.5 dB and pump feedback to 11 dB.
ADC_RANGE_MV = {"pressure": (100, 1250), "flow": (100, 1250), "pump_feedback": (150, 2450)}
# Certificate points are pre-divider volts and engineering units. Use the upper
# recorded pressure zero of 0.005 V and round to the ESP32's millivolt resolution.
CERTIFICATE_POINTS = {
    key: tuple((round(volts * 1000 / 5), value) for volts, value in points)
    for key, points in {
        "pressure": ((0.005, 0), (2.502, 50), (5.004, 100)),
        "flow": ((1.01, 20), (2.48, 50), (5.00, 100)),
    }.items()
}


def _interpolate(mv, lower, upper):
    low_mv, low_value = lower
    high_mv, high_value = upper
    return low_value + (high_value - low_value) * (mv - low_mv) / (high_mv - low_mv)


def sensor_display_estimate(channel, mv, reference=(False, None), zero_mv=None):
    """Return a display-only estimate and its source or unavailable reason."""
    fit_active, estimate = reference
    if fit_active:
        return estimate, "reference-based estimate" if estimate is not None else "outside reference range"
    low, high = ADC_RANGE_MV[channel]
    if not low <= mv <= high:
        return None, "outside ADC range"
    if mv == zero_mv:
        return None, "matches observed zero voltage"
    if channel == "pump_feedback":
        return (mv / 200, "nominal estimate") if mv <= 2000 else (None, "outside nominal range")
    points = CERTIFICATE_POINTS[channel]
    if mv < points[0][0]:
        return None, "below certificate range (20 mL/min)"
    for lower, upper in pairwise(points):
        if mv <= upper[0]:
            return _interpolate(mv, lower, upper), "certificate estimate"
    return None, "above certificate range"


def observed_zero_baseline(channel, zero_mv, current_mv=None):
    low, high = ADC_RANGE_MV[channel]
    note = "" if low <= zero_mv <= high else " (outside ADC range)"
    change = f" · raw change {current_mv - zero_mv:+d} mV" if current_mv is not None else ""
    return f"Observed zero baseline {zero_mv} mV{note}{change}"


class SensorSetupDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._driver = None
        self._zero = {}
        self._references = {}
        self._live = {}
        self._capture_ready = False
        self.setWindowTitle("Sensor setup")
        self.resize(610, 440)

        layout = QVBoxLayout(self)
        introduction = QLabel(
            "Pressure and flow estimates use the sensor certificates and an assumed 5:1 divider. "
            "Capture a zero to compare raw voltages. Two independent measured references are optional. "
            "Run protection uses the commissioned pressure input."
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)
        self.connection_status = QLabel()
        self.connection_status.setWordWrap(True)
        layout.addWidget(self.connection_status)

        form = QFormLayout()
        self.live_labels = {}
        for key, (name, pin, *_rest) in CHANNELS.items():
            label = QLabel()
            label.setWordWrap(True)
            label.setAccessibleName(f"{name} live sensor reading")
            self.live_labels[key] = label
            form.addRow(f"{name} · {pin}", label)
        self.channel = QComboBox()
        for key, (name, *_rest) in CHANNELS.items():
            self.channel.addItem(name, key)
        self.channel.currentIndexChanged.connect(self._select_channel)
        form.addRow("Sensor to check", self.channel)
        self.reference_value = QLineEdit()
        self.reference_value.textChanged.connect(self.refresh)
        self.reference_label = QLabel()
        self.reference_label.setBuddy(self.reference_value)
        form.addRow(self.reference_label, self.reference_value)
        self.reference_hint = QLabel()
        self.reference_hint.setWordWrap(True)
        form.addRow(self.reference_hint)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.zero_button = QPushButton("Capture zero baseline")
        self.zero_button.clicked.connect(self._capture_zero)
        self.reference_button = QPushButton("Capture known reference")
        self.reference_button.clicked.connect(self._capture_reference)
        self.clear_button = QPushButton("Clear selected points")
        self.clear_button.clicked.connect(self._clear_selected)
        for button in (self.zero_button, self.reference_button, self.clear_button):
            button.setAutoDefault(False)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.points_detail = QLabel()
        self.points_detail.setWordWrap(True)
        self.points_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.points_detail)
        self.action_status = QLabel()
        self.action_status.setWordWrap(True)
        layout.addWidget(self.action_status)
        layout.addStretch()
        footer = QHBoxLayout()
        self.copy_button = QPushButton("Copy setup readings")
        self.copy_button.clicked.connect(self._copy_report)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        footer.addWidget(self.copy_button)
        footer.addStretch()
        footer.addWidget(close_button)
        layout.addLayout(footer)
        self._select_channel()

    def _select_channel(self):
        key = self.channel.currentData()
        unit = CHANNELS[key][2]
        self.reference_label.setText(f"Measured reference ({unit})")
        self.reference_value.setPlaceholderText(f"Enter a measured value in {unit}")
        self.reference_hint.setText({
            "pressure": "Use a steady reading from an independent gauge. Below 100 mV at the ESP32, check the signal with a voltmeter.",
            "flow": "Use a steady timed collection from the measured path. Divide collected mL by seconds and multiply by 60. Below 100 mV at the ESP32, check with a voltmeter.",
            "pump_feedback": "Measure volts at the pump output before the divider.",
        }[key])
        self.reference_value.clear()
        self.action_status.clear()
        self.refresh()

    def sync_connection(self):
        snapshot = self.controller.snapshot
        connected = snapshot["controller_connected"] and not self.controller.simulation and not snapshot["simulation"]
        driver = self.controller.driver if connected else None
        if not connected or driver is not self._driver:
            if self._zero or self._references:
                self.action_status.setText("Connection changed. The previous setup points were cleared.")
            self._zero.clear()
            self._references.clear()
            self._driver = driver
        return connected

    def zero_baselines(self):
        return self.controller.snapshot["live_sensor_zero"] | self._zero

    def clear_pressure_flow_zero(self):
        self._zero.pop("pressure", None)
        self._zero.pop("flow", None)
        self.refresh()

    def refresh(self):
        snapshot = self.controller.snapshot
        connected = self.sync_connection()
        last = self.controller.last_telemetry
        fresh = connected and last is not None and self.controller.clock() - last <= 2
        self._live = snapshot.get("live_sensor_voltages", {}) if fresh else {}
        self._capture_ready = (bool(self._live) and snapshot["state"] == "idle"
            and not snapshot["hardware_verified"] and not self.controller.local_fault
            and not snapshot["fault"] and not any(snapshot.get(flag) for flag in
                ("start_pending", "stop_pending", "manual_pending")))
        if self.controller.simulation:
            note = "Open the app in hardware mode and connect the normal ESP32 controller to view sensors."
        elif not connected:
            note = "Connect the normal ESP32 controller in Connections and settings."
        elif not fresh:
            note = "Waiting for fresh controller readings."
        elif snapshot["hardware_verified"]:
            note = "This controller is commissioned. Current calibrated readings appear below."
        elif not self._live:
            note = "Waiting for live input voltages. Use normal controller firmware with live sensor support."
        elif self._capture_ready:
            note = "Live input voltages. Capture a zero baseline or enter an independent reference."
        else:
            note = "Live input voltages. Stop the controller and clear any fault before capturing points."
        uptime_ms = self.controller.last_controller_uptime
        if self._live and uptime_ms is not None:
            note += f" Latest ESP32 sample at {uptime_ms / 1000:.2f} s."
        self.connection_status.setText(note)
        zero_baselines = self.zero_baselines()
        for key, (_, _, unit, _, _, field) in CHANNELS.items():
            value = self._live.get(key)
            if value is not None:
                reading = f"{value} mV at the ESP32"
                zero = zero_baselines.get(key)
                estimate, source = sensor_display_estimate(key, value, self.reference_estimate(key, value), zero)
                if estimate is not None:
                    reading += f" · {source} {estimate:.2f} {unit}"
                else:
                    reading += f" · {source}"
                if zero is not None:
                    reading += " · observed zero saved"
            elif fresh and snapshot["hardware_verified"] and snapshot.get(field) is not None:
                reading = f"{snapshot[field]:.2f} {unit}"
            else:
                reading = "Waiting"
            self.live_labels[key].setText(reading)

        key = self.channel.currentData()
        unit = CHANNELS[key][2]
        zero = zero_baselines.get(key)
        references = self._references.get(key, ())
        points = [observed_zero_baseline(key, zero, self._live.get(key))] if zero is not None else []
        points.extend(f"Reference {index} · {mv} mV at {value:g} {unit}"
                      for index, (mv, value) in enumerate(references, start=1))
        self.points_detail.setText("\n".join(points) or
            "A zero baseline shows the raw voltage change. Two known readings can replace the certificate estimate for this connection.")
        can_capture_channel = self._capture_ready and key in self._live
        self.zero_button.setEnabled(can_capture_channel)
        self.reference_button.setEnabled(can_capture_channel and len(references) < 2
            and bool(self.reference_value.text().strip()))
        self.clear_button.setEnabled(key in self._zero or bool(references))
        self.copy_button.setEnabled(bool(self._live or zero_baselines or self._references))

    def reference_estimate(self, key, current_mv):
        points = sorted(self._references.get(key, ()))
        if len(points) != 2:
            return False, None
        lower, upper = points
        if not lower[0] <= current_mv <= upper[0]:
            return True, None
        return True, _interpolate(current_mv, lower, upper)

    def _capture_zero(self):
        self.refresh()
        key = self.channel.currentData()
        if not self._capture_ready or key not in self._live:
            return
        condition = {
            "pressure": "the system is depressurized and the reference gauge reads zero",
            "flow": "liquid has stopped moving through the flow sensor",
            "pump_feedback": "a voltmeter across the pump voltage output reads zero",
        }[key]
        driver = self._driver
        answer = QMessageBox.question(self, "Confirm zero baseline",
            f"Confirm {condition}. This records the observed voltage without changing calibration.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        self.refresh()
        if (answer == QMessageBox.StandardButton.Ok and self._capture_ready
                and self._driver is driver and key in self._live):
            self._zero[key] = self._live[key]
            self.action_status.setText("Zero baseline captured.")
            self.refresh()

    def _capture_reference(self):
        self.refresh()
        key = self.channel.currentData()
        if not self._capture_ready or key not in self._live:
            return
        _, _, unit, minimum, maximum, _ = CHANNELS[key]
        try:
            reference = float(self.reference_value.text())
        except ValueError:
            reference = math.nan
        if not math.isfinite(reference) or not minimum <= reference <= maximum:
            self.action_status.setText(f"Enter a measured reference from {minimum} to {maximum} {unit}.")
            return
        mv = self._live[key]
        min_mv, max_mv = ADC_RANGE_MV[key]
        if not min_mv <= mv <= max_mv:
            self.action_status.setText(f"This input is outside its usable voltage range ({min_mv} to {max_mv} mV at the ESP32). Check it with a voltmeter.")
            return
        points = self._references.get(key, ())
        if len(points) >= 2:
            return
        if points:
            old_mv, old_value = points[0]
            if abs(mv - old_mv) < 20 or (mv - old_mv) * (reference - old_value) <= 0:
                self.action_status.setText(
                    "Use a different measured value with a matching change of at least 20 mV at the ESP32.")
                return
        self._references[key] = [*points, (mv, reference)]
        self.reference_value.clear()
        self.action_status.setText("Dashboard reference estimate is active within the measured range." if points else
            "First reference captured. Enter a second measured reference to use the fit on Dashboard.")
        self.refresh()

    def _clear_selected(self):
        key = self.channel.currentData()
        self._zero.pop(key, None)
        self._references.pop(key, None)
        self.action_status.setText("Selected setup points cleared.")
        self.refresh()

    def _copy_report(self):
        self.refresh()
        zero_baselines = self.zero_baselines()
        if not (self._live or zero_baselines or self._references):
            return
        rows = ["Membrane Control sensor setup", "Diagnostic values and reference points for review"]
        for key, (name, pin, unit, *_rest) in CHANNELS.items():
            value = self._live.get(key)
            rows.append(f"{name} ({pin})")
            if value is not None:
                note = " (below ADC range)" if value < ADC_RANGE_MV[key][0] else ""
                rows.append(f"  Latest: {value} mV{note}")
            if key in zero_baselines:
                rows.append(f"  {observed_zero_baseline(key, zero_baselines[key], value)}")
            for mv, reference in self._references.get(key, ()):
                rows.append(f"  Reference: {mv} mV at {reference:g} {unit}")
            points = self._references.get(key, ())
            if len(points) == 2:
                (first_mv, first_value), (second_mv, second_value) = points
                scale = 1000 * (second_value - first_value) / (second_mv - first_mv)
                offset = first_value - scale * first_mv / 1000
                rows.append(f"  Two-point fit: {scale:.6g} {unit}/V at ESP32, offset {offset:.6g} {unit}")
        QApplication.clipboard().setText("\n".join(rows))
        self.action_status.setText("Setup readings copied.")

"""Display estimates from the separate ADC board; never controller permissions."""
from __future__ import annotations

import math


ADC_CHANNELS = {"pressure": "A0", "flow": "A1", "pump_feedback": "A2"}
ADC_FIELDS = {"pressure": "pressure_psi", "flow": "flow_ml_min", "pump_feedback": "pump_feedback_v"}
ADC_UNITS = {"pressure": "psi", "flow": "mL/min", "pump_feedback": "V"}
_ZERO_NOISE_VOLTS = 0.005
_PRESSURE_POINTS = ((0.005 / 5, 0.0), (2.502 / 5, 50.0), (5.004 / 5, 100.0))


def adc_monitor_selected(snapshot):
    monitor = snapshot.get("adc_monitor")
    return type(monitor) is dict and bool(monitor.get("port"))


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def adc_display_readings(snapshot):
    """Return independently available raw volts and labelled display estimates."""
    monitor = snapshot.get("adc_monitor")
    if not adc_monitor_selected(snapshot):
        return {}
    available = (monitor.get("connected") is True and monitor.get("identified") is True and monitor.get("fresh") is True
                 and monitor.get("adc_ack") is True)
    channels = monitor.get("channels")
    channels = channels if type(channels) is dict else {}
    readings = {}
    for signal, channel in ADC_CHANNELS.items():
        source = channels.get(channel)
        source = source if type(source) is dict else {}
        volts = source.get("volts")
        valid = (available and source.get("status") == "reading_received" and _finite(volts))
        reading = dict(channel=channel, signal=signal, volts=volts if valid else None,
                       value=None, unit=ADC_UNITS[signal], status="unavailable",
                       note=str(monitor.get("status") or "Waiting for sensor board"))
        if valid:
            volts = float(volts)
            reading["status"] = "reading_received"
            if volts < -_ZERO_NOISE_VOLTS:
                reading["note"] = "below GND · check signal and shared ground"
            elif volts > 3.3:
                reading["note"] = "above ADC supply range"
            else:
                nonnegative = max(0.0, volts)
                if signal == "pressure":
                    lower, upper = (_PRESSURE_POINTS[:2] if nonnegative <= _PRESSURE_POINTS[1][0]
                                    else _PRESSURE_POINTS[1:])
                    reading["value"] = max(0.0, lower[1] + (nonnegative - lower[0])
                                           * (upper[1] - lower[1]) / (upper[0] - lower[0]))
                    reading["note"] = "certificate estimate · 5:1 divider"
                    if nonnegative > _PRESSURE_POINTS[-1][0]:
                        reading["note"] += " · above certificate range"
                elif signal == "flow":
                    reading["value"] = nonnegative * 100
                    reading["note"] = "calibration estimate · 5:1 divider"
                    if nonnegative < 0.13:
                        reading["note"] += " · below 13 mL/min calibrated range"
                    elif nonnegative > 1:
                        reading["note"] += " · above 100 mL/min calibrated range"
                else:
                    reading["value"] = nonnegative * 5
                    reading["note"] = "nominal drive voltage · 5:1 divider"
                    if nonnegative > 2:
                        reading["note"] += " · above nominal 10 V range"
                if volts < 0:
                    reading["note"] += " · near-zero ADC offset"
        readings[signal] = reading
    return readings


def adc_display_values(snapshot, area_m2):
    """Engineering estimates for rendering/recording, separate from control data.

    An empty dictionary means no external monitor was selected. A selected but
    stale monitor returns explicit None values so old controller data cannot
    appear as current readings from this sensor board.
    """
    readings = adc_display_readings(snapshot)
    if not readings:
        return {}
    values = {field: readings[signal]["value"] for signal, field in ADC_FIELDS.items()}
    flow = values["flow_ml_min"]
    values["flux_lmh"] = (flow * 0.06 / area_m2 if flow is not None and _finite(area_m2)
                          and area_m2 > 0 else None)
    return values

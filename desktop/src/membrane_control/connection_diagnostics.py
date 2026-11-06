"""Prepare a shareable, read-only summary of the controller connection."""
import json
import re

from . import __version__


_COM_PORT = re.compile(r"COM[1-9][0-9]{0,3}", re.IGNORECASE)
_IDENTIFIER = re.compile(
    r"\b(?:BTHENUM|BTHLEDEVICE|USB|FTDIBUS|ACPI|PCI|HID|ROOT|SWD|SERENUM)\\\S+"
    r"|\b(?:VID|PID|REV|DEV)_[0-9a-f]+\b"
    r"|(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"
    r"|(?<![0-9a-f])(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}(?![0-9a-f])"
    r"|(?<![0-9a-f])[0-9a-f]{12}(?![0-9a-f])"
    r"|\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_PRIVATE_FIELD = re.compile(
    r"\b(?:serial\s+(?:number|id)|ser|s/n|hardware\s+id|password|passphrase|"
    r"authorization|credential|token|api[_ -]?key|pin(?:\s+code)?|passkey|pairing\s+code)\s*[:=]\s*"
    r"(?:Bearer\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)
_EVENT_FIELDS = (
    "time_utc", "event", "port", "connection_id", "host_monotonic_ms", "state",
    "telemetry_age_ms", "controller_uptime_ms", "observed_uptime_ms", "baud", "command",
    "request_id", "request_age_ms", "firmware_version", "firmware", "reset_reason",
    "transport", "reason", "status",
)


def _shareable_text(value, limit=512):
    text = " ".join(str(value).split())
    text = _PRIVATE_FIELD.sub("[redacted]", text)
    return _IDENTIFIER.sub("[redacted]", text)[:limit]


def _port_name(value):
    return value.upper() if isinstance(value, str) and _COM_PORT.fullmatch(value) else None


def _event_lines(history):
    for line in history.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or not isinstance(event.get("event"), str):
            continue
        fields = {}
        for key in _EVENT_FIELDS:
            if key not in event:
                continue
            value = event[key]
            if key == "port":
                fields[key] = _port_name(value)
            elif isinstance(value, str):
                fields[key] = _shareable_text(value)
            elif value is None or type(value) in (int, bool):
                fields[key] = value
        states = event.get("commanded_valves")
        if isinstance(states, dict):
            fields["commanded_valves"] = {valve: states[valve] for valve in ("V1", "V2", "V3", "V4", "V5", "V7")
                                          if states.get(valve) in ("ON", "OFF")}
        yield json.dumps(fields, ensure_ascii=False)


def connection_diagnostics(*, selected_port, active_port, status, simulation, list_ports, history):
    lines = ["Membrane Control connection diagnostics", f"App version: {__version__}",
             f"Mode: {'Desktop simulation' if simulation else 'Hardware'}",
             f"Selected controller port: {_port_name(selected_port) or 'None'}",
             f"Active controller port: {_port_name(active_port) or 'None'}",
             f"Controller status: {_shareable_text(status) or 'Unknown'}", "", "Detected serial ports:"]
    try:
        ports = [f"  {name}  {_shareable_text(description, 160)}".rstrip()
                 for port, description in list_ports() if (name := _port_name(port))]
    except Exception as exc:
        ports = [f"  Port scan failed ({type(exc).__name__})."]
    lines.extend(ports or ["  None found."])
    lines.extend(("", "Recent ESP32 events:"))
    lines.extend(list(_event_lines(history)) or ["  None recorded."])
    return "\n".join(lines) + "\n"

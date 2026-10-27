"""Scale connection choices and bounded read-only requests use fake ports only."""
import pytest

from membrane_control.controller import AppController


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


class Balance:
    def __init__(self, port, baud=115200, raw=False, **options):
        self.port, self.baud, self.raw = port, baud, raw
        self.options = options
        self.events = []
        self.requests = 0
        self.opened = False
        self.closed = False
        self.error = None

    def poll(self, now):
        packets, self.events = self.events, []
        if any(packet.get("type") == "port_open" for packet in packets):
            self.opened = True
        return packets

    def request_reading(self):
        if self.error:
            raise RuntimeError(self.error)
        if not self.opened or self.closed:
            raise RuntimeError("Fake balance port is not open")
        self.requests += 1

    def close(self):
        self.closed = True


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr("membrane_control.controller.SerialTransport", Balance)
    clock = Clock()
    controller = AppController(tmp_path, clock)
    controller.set_simulation(False)
    yield controller, clock
    controller.close()


def open_balance(controller, **options):
    controller.connect_balance("FAKE-SCALE", **options)
    balance = controller.balance
    balance.events.append({"type": "port_open"})
    controller.tick()
    return balance


@pytest.mark.parametrize("serial_format", ["8N1", "7E1", "7O1"])
def test_serial_format_forwarded_and_connection_not_claimed_before_weight(app, serial_format):
    controller, _ = app
    controller.connect_balance("FAKE-SCALE", 4800, serial_format, polling=False)
    assert controller.balance.raw and controller.balance.baud == 4800
    assert controller.balance.options == ({} if serial_format == "8N1" else {"serial_format": serial_format})
    assert not controller.snapshot["balance_connected"]
    assert controller.snapshot["mass_g"] is None
    assert not controller.snapshot["balance_polling"]
    assert any(serial_format in line for line in controller.log)


@pytest.mark.parametrize("changes", [
    {"serial_format": "8E1"}, {"serial_format": []}, {"serial_format": True},
    {"baud": True}, {"baud": 9600.0}, {"baud": 0}, {"baud": 115201},
    {"polling": 1}, {"port": ""}, {"port": "COM6\nBAD"},
])
def test_invalid_connection_options_do_not_close_existing_scale(app, changes):
    controller, _ = app
    balance = open_balance(controller, polling=False)
    options = {"port": "OTHER-FAKE", "baud": 9600, "serial_format": "8N1", "polling": True, **changes}
    with pytest.raises(ValueError):
        controller.connect_balance(**options)
    assert controller.balance is balance and not balance.closed


def test_default_format_still_supports_original_transport_constructor(app, monkeypatch):
    controller, _ = app
    calls = []

    def old_constructor(port, baud=115200, raw=False):
        calls.append((port, baud, raw))
        return Balance(port, baud, raw)

    monkeypatch.setattr("membrane_control.controller.SerialTransport", old_constructor)
    controller.connect_balance("FAKE-OLD")
    assert calls == [("FAKE-OLD", 9600, True)]


def test_initial_fixed_read_request_waits_for_port_open_and_does_not_fake_mass(app):
    controller, clock = app
    controller.connect_balance("FAKE-SCALE")
    balance = controller.balance
    for _ in range(3):
        controller.tick()
        clock.now += 0.5
    assert balance.requests == 0
    balance.events.append({"type": "port_open"})
    controller.tick()
    assert balance.requests == 1
    assert controller.snapshot["mass_g"] is None
    assert not controller.snapshot["balance_connected"]
    assert controller.last_mass is None


def test_polling_is_at_most_once_per_second_with_no_catchup_burst(app):
    controller, clock = app
    balance = open_balance(controller)
    for delta in (0.1, 0.2, 0.69):
        clock.now += delta
        controller.tick()
    assert balance.requests == 1
    clock.now += 0.01
    controller.tick()
    assert balance.requests == 2
    clock.now += 100
    controller.tick()
    assert balance.requests == 3
    controller.tick()
    assert balance.requests == 3
    assert not any("Requested the current balance" in line for line in controller.log)


def test_fresh_valid_stream_suppresses_requests_but_invalid_data_does_not(app):
    controller, clock = app
    balance = open_balance(controller)
    for index in range(1, 5):
        clock.now += 0.75
        balance.events.append({"type": "mass_line", "line": f"+{index}.000 g"})
        controller.tick()
    assert balance.requests == 1
    assert controller.snapshot["mass_g"] == 4
    assert controller.snapshot["balance_connected"]
    clock.now += 1
    balance.events.append({"type": "mass_line", "line": "NO VALID MASS"})
    controller.tick()
    assert balance.requests == 2
    assert controller.snapshot["mass_g"] == 4
    assert controller.last_mass == clock() - 1


def test_manual_request_needs_open_transport_but_not_first_weight_and_is_bounded(app):
    controller, clock = app
    with pytest.raises(ValueError, match="real balance"):
        controller.request_balance_reading()
    controller.connect_balance("FAKE-SCALE", polling=False)
    balance = controller.balance
    with pytest.raises(ValueError, match="port to open"):
        controller.request_balance_reading()
    balance.events.append({"type": "port_open"})
    controller.tick()
    assert controller.request_balance_reading() is True
    assert balance.requests == 1
    assert controller.snapshot["mass_g"] is None
    assert not controller.snapshot["balance_connected"]
    assert any("Requested the current balance" in line for line in controller.log)
    assert controller.request_balance_reading() is False
    assert balance.requests == 1
    clock.now += 1
    assert controller.request_balance_reading() is True
    assert balance.requests == 2


def test_disabled_polling_still_accepts_weights_and_has_explicit_request(app):
    controller, clock = app
    balance = open_balance(controller, polling=False)
    clock.now += 10
    controller.tick()
    assert balance.requests == 0
    controller.request_balance_reading()
    balance.events.append({"type": "mass_line", "line": "+0.000 g"})
    controller.tick()
    assert controller.snapshot["mass_g"] == 0
    assert controller.snapshot["balance_connected"]


def test_original_scale_disconnect_error_is_preserved_and_polling_stops(app):
    controller, clock = app
    balance = open_balance(controller)
    balance.events.append({"type": "mass_line", "line": "+1.000 g"})
    controller.tick()
    reason = "Access denied: fake scale port was closed"
    balance.events.extend([{"type": "disconnected", "error": reason},
                           {"type": "mass_line", "line": "+99.000 g"}])
    controller.tick()
    requests = balance.requests
    assert controller.balance is None and balance.closed
    assert controller.snapshot["balance_status"] == reason
    assert controller.snapshot["mass_g"] is None
    assert not controller.snapshot["balance_connected"]
    for _ in range(10):
        clock.now += 10
        controller.tick()
    assert balance.requests == requests
    assert controller.snapshot["balance_status"] == reason


def test_failed_request_detaches_dead_scale_without_fake_weight_or_controller_fault(app):
    controller, clock = app
    balance = open_balance(controller)
    balance.error = "Original fake write failure"
    clock.now += 1
    controller.tick()
    assert controller.balance is None and balance.closed
    assert controller.snapshot["balance_status"] == balance.error
    assert controller.local_fault is None
    assert controller.snapshot["mass_g"] is None


def test_explicit_request_failure_is_reported_and_releases_scale(app):
    controller, _ = app
    balance = open_balance(controller, polling=False)
    balance.error = "Fake scale disconnected"
    with pytest.raises(RuntimeError, match="Fake scale disconnected"):
        controller.request_balance_reading()
    assert controller.balance is None and balance.closed
    assert controller.snapshot["balance_status"] == balance.error


def test_disconnect_and_close_stop_requests_immediately(app):
    controller, clock = app
    balance = open_balance(controller)
    controller.disconnect_balance()
    assert balance.closed and not controller.balance_port_open
    assert not controller.snapshot["balance_polling"]
    with pytest.raises(ValueError, match="real balance"):
        controller.request_balance_reading()
    clock.now += 5
    controller.tick()
    assert balance.requests == 1
    second = open_balance(controller)
    controller.close()
    clock.now += 5
    controller.tick()
    assert second.closed and second.requests == 1


def test_scale_polling_continues_during_independent_valve_only_mode(app):
    controller, clock = app
    balance = open_balance(controller)
    controller.snapshot["state"] = "manual_valves"
    controller.settings["require_balance"] = True
    clock.now += 1
    controller.tick()
    assert balance.requests == 2 and controller.local_fault is None


def test_old_balance_fake_without_request_method_is_not_queried_or_faulted(app):
    controller, clock = app

    class OldBalance:
        port = "FAKE-OLD"

        def poll(self, now):
            return [{"type": "port_open"}]

        def close(self):
            pass

    controller.balance = OldBalance()
    controller.balance_polling = True
    controller.tick()
    clock.now += 5
    controller.tick()
    assert controller.local_fault is None
    with pytest.raises(ValueError, match="does not support"):
        controller.request_balance_reading()

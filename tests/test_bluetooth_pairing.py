"""Pairing confirmation remains a local operator action on a fresh USB code."""
import threading

from membrane_control.bluetooth_pairing import BluetoothPairingSession


class FakeTransport:
    def __init__(self):
        self.events = []
        self.sent = []
        self.closed = threading.Event()

    def poll(self, _now):
        events, self.events = self.events, []
        return events

    def pairing_command(self, text):
        self.sent.append(text)

    def close(self):
        self.closed.set()


def session():
    now = [10.0]
    transport = FakeTransport()
    value = BluetoothPairingSession(transport_factory=lambda *_args, **_kwargs: transport,
                                   clock=lambda: now[0])
    value.connect()
    transport.events = [{"type": "port_open"}]
    value.tick()
    return value, transport, now


def test_only_explicit_confirmation_sends_the_exact_current_code():
    value, transport, _ = session()
    assert transport.sent == ["PAIR"]
    value._line("Bluetooth pairing code: 005123")
    assert value.can_confirm and value.code == "005123"
    value.tick()
    assert transport.sent == ["PAIR"]
    assert value.confirm()
    assert transport.sent == ["PAIR", "CONFIRM 005123"]
    assert not value.can_confirm


def test_expired_code_is_not_sent_and_retry_waits_for_a_new_code():
    value, transport, now = session()
    value._line("Bluetooth pairing code: 539570")
    now[0] += 25
    value.tick()
    assert value.code is None and not value.can_confirm
    assert not value.confirm()
    assert all(not text.startswith("CONFIRM") for text in transport.sent)
    value.retry()
    value.tick()
    value._line("Bluetooth pairing code: 123456")
    assert value.can_confirm and value.code == "123456"


def test_failures_and_ready_messages_clear_the_previous_code():
    value, transport, _ = session()
    value._line("Bluetooth pairing code: 123456")
    value._line("Bluetooth: pairing failed; physical control locked")
    assert not value.can_confirm and value.code is None
    value._line("Bluetooth: pairing ready (120 seconds)")
    assert "Add device" in value.status and value.code is None


def test_saved_confirmation_releases_usb_without_restarting_pairing():
    value, transport, _ = session()
    value._line("Bluetooth pairing code: 123456")
    value.confirm()
    value._line("Bluetooth: pairing saved; restarting normal mode")
    assert value.saved and value.transport is None
    assert transport.closed.wait(1)
    count = len(transport.sent)
    value.retry()
    value.tick()
    assert len(transport.sent) == count


def test_other_text_and_malformed_codes_never_enable_confirmation():
    value, _transport, _now = session()
    for line in ("123456", "Bluetooth pairing code: 12345", "Bluetooth pairing code: 1234567",
                 "prefix Bluetooth pairing code: 123456", "Bluetooth pairing code: abcdef"):
        value._line(line)
        assert not value.can_confirm

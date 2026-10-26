from membrane_control.controller import AppController


class BenchPort:
    def __init__(self):
        self.messages = []
        self.closed = False

    def send(self, packet):
        self.messages.append(packet)

    def close(self):
        self.closed = True


def test_relay_test_identity_releases_port_without_accepting_experiment_controller(tmp_path):
    controller = AppController(tmp_path)
    controller.set_simulation(False)
    port = BenchPort()
    controller.driver = port
    request = controller._request("hello")
    controller._handle_packet({"v": 1, "id": request, "type": "hello", "ok": True,
        "device": "membrane-relay-bench", "protocol_version": 1, "relay_count": 16,
        "simulation": False, "hardware_verified": False}, controller.clock())
    assert port.closed
    assert controller.driver is None
    assert not controller.device
    assert not controller.snapshot["controller_connected"]
    assert not controller.snapshot["hardware_verified"]
    assert "open Relay board test" in controller.snapshot["controller_status"]
    assert [message["cmd"] for message in port.messages] == ["hello"]
    controller.close()

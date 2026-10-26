import pytest
from membrane_control.controller import AppController


class ClosingPort:
    def __init__(self, fail=False):
        self.fail = fail
        self.closed = False
        self.stop = None

    def send(self, message):
        pass

    def close_with_stop(self, message):
        self.stop = message
        self.close()

    def close(self):
        self.closed = True
        if self.fail:
            raise RuntimeError("test driver close failed")


def test_planned_controller_disconnect_uses_bounded_stop_close(tmp_path):
    controller = AppController(tmp_path)
    controller.set_simulation(False)
    port = controller.driver = ClosingPort()
    controller.disconnect_controller()
    assert port.closed and port.stop["cmd"] == "stop"
    assert controller.driver is None
    controller.close()


def test_failed_controller_close_still_clears_connection_state(tmp_path):
    controller = AppController(tmp_path)
    controller.set_simulation(False)
    port = controller.driver = ClosingPort(fail=True)
    controller.device = {"hardware_verified": True}
    controller.snapshot.update(controller_connected=True, hardware_verified=True)
    controller.pending[1] = ("hello", 10)
    with pytest.raises(RuntimeError, match="close failed"):
        controller.disconnect_controller()
    assert port.closed
    assert controller.driver is None and not controller.device and not controller.pending
    assert not controller.snapshot["controller_connected"]
    assert not controller.snapshot["hardware_verified"]
    controller.close()


def test_application_close_releases_balance_even_if_controller_close_raises(tmp_path):
    controller = AppController(tmp_path)
    controller.set_simulation(False)
    first = controller.driver = ClosingPort(fail=True)
    second = controller.balance = ClosingPort()
    controller.close()
    assert first.closed and second.closed
    assert second.stop is None  # Never send a JSON controller STOP to the scale.
    assert controller.driver is None and controller.balance is None and controller.closed

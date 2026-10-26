"""Qt window, modal and application shutdown must release every fake device."""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from membrane_control.__main__ import _run_event_loop
from membrane_control.controller import AppController
from membrane_control.relay_bench import RelayBenchDialog
from membrane_control.ui import MainWindow


class SerialDouble:
    def __init__(self, port='FAKE-BENCH'):
        self.port = port
        self.closed = False
        self.close_count = 0
        self.sent = []

    def send(self, packet):
        assert not self.closed
        self.sent.append(dict(packet))

    def poll(self, _now=None):
        return []

    def close(self):
        self.closed = True
        self.close_count += 1


@pytest.fixture(scope='module')
def qt_app():
    app = QApplication.instance() or QApplication([])
    previous = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)
    yield app
    app.setQuitOnLastWindowClosed(previous)


def make_bench(parent=None):
    wire = SerialDouble()
    dialog = RelayBenchDialog(parent, selected_port=wire.port,
        port_lister=lambda: [(wire.port, 'Test double')],
        transport_factory=lambda *_args: wire)
    dialog.connect_board()
    return dialog, wire


@pytest.mark.parametrize('action', ['accept', 'reject', 'done', 'close', 'shutdown'])
def test_every_dialog_close_path_stops_timer_and_releases_port(qt_app, action):
    dialog, wire = make_bench()
    dialog.show()
    qt_app.processEvents()
    if action == 'done':
        dialog.done(0)
    else:
        getattr(dialog, action)()
    assert wire.closed and wire.close_count == 1
    assert dialog.session.transport is None and not dialog.timer.isActive()
    assert not dialog.loads_checkbox.isChecked() and not dialog.observation_checkbox.isChecked()
    assert not dialog.connect_button.isEnabled()
    sent = len(wire.sent)
    dialog.shutdown()
    dialog._tick()
    dialog.connect_board()  # A closing dialog must never reopen its port.
    dialog.close()
    assert wire.close_count == 1 and len(wire.sent) == sent
    assert dialog._quit_application is None


@pytest.fixture
def window_with_devices(qt_app, tmp_path):
    controller = AppController(tmp_path)
    controller.list_ports = lambda: [('FAKE-BENCH', 'Test double')]
    controller.set_simulation(False)
    window = MainWindow(controller)
    controller_wire, scale_wire = SerialDouble('FAKE-CONTROLLER'), SerialDouble('FAKE-SCALE')
    controller.driver, controller.balance = controller_wire, scale_wire
    dialog, bench_wire = make_bench(window)
    window._relay_bench_dialog = dialog
    yield window, controller, dialog, (controller_wire, scale_wire, bench_wire)
    window.shutdown()
    window.close()


def test_parent_window_close_closes_bench_controller_and_scale_once(window_with_devices):
    window, controller, dialog, wires = window_with_devices
    window.show()
    dialog.show()
    window.close()
    assert controller.closed and window._relay_bench_dialog is None
    assert not window.timer.isActive() and not dialog.timer.isActive()
    assert all(wire.closed and wire.close_count == 1 for wire in wires)
    window.shutdown()
    window._on_tick()
    window.close()
    assert all(wire.close_count == 1 for wire in wires)


def test_loop_exception_runs_cleanup_even_without_about_to_quit(window_with_devices):
    window, controller, dialog, wires = window_with_devices

    class Signal:
        def connect(self, slot):
            self.slot = slot

        def disconnect(self, slot):
            assert self.slot == slot
            self.slot = None

    class LoopFailure:
        aboutToQuit = Signal()

        def exec(self):
            raise RuntimeError('Test event loop failure')

    with pytest.raises(RuntimeError, match='event loop failure'):
        _run_event_loop(LoopFailure(), window)
    assert controller.closed and dialog.session.transport is None
    assert all(wire.closed and wire.close_count == 1 for wire in wires)


def test_bench_close_failure_does_not_skip_other_device_cleanup(window_with_devices, monkeypatch):
    window, controller, dialog, wires = window_with_devices
    original_close = wires[2].close

    def close_then_error():
        original_close()
        raise RuntimeError('Test close reporting failure')

    monkeypatch.setattr(wires[2], 'close', close_then_error)
    window.shutdown()
    assert all(wire.closed and wire.close_count == 1 for wire in wires)
    assert controller.closed and dialog.session.transport is None
    assert 'Test close reporting failure' in dialog.session.error


def test_qt_timer_teardown_error_does_not_skip_device_cleanup(window_with_devices, monkeypatch):
    window, controller, dialog, wires = window_with_devices

    def destroyed_timers(*_args):
        raise RuntimeError('Test deleted Qt wrapper')

    monkeypatch.setattr(window, 'findChildren', destroyed_timers)
    window.shutdown()
    assert controller.closed and dialog.session.transport is None
    assert all(wire.closed and wire.close_count == 1 for wire in wires)
    assert not window.timer.isActive()


def test_modal_exec_return_without_close_event_still_releases_session(qt_app, tmp_path, monkeypatch):
    controller = AppController(tmp_path)
    controller.set_simulation(False)
    controller.list_ports = lambda: [('FAKE-BENCH', 'Test double')]
    window = MainWindow(controller)
    window.timer.stop()
    captured = []

    class LoopExitDialog(RelayBenchDialog):
        def __init__(self, parent, **kwargs):
            self.wire = SerialDouble()
            super().__init__(parent, transport_factory=lambda *_args: self.wire, **kwargs)
            self.connect_board()
            captured.append(self)

        def exec(self):
            assert self.timer.isActive() and not self.wire.closed
            return 0  # Qt can unwind modal exec without reject/closeEvent on exit.

    monkeypatch.setattr('membrane_control.ui.RelayBenchDialog', LoopExitDialog)
    try:
        window._open_relay_bench()
        assert captured[0].wire.closed and captured[0].wire.close_count == 1
        assert not captured[0].timer.isActive()
        assert window._relay_bench_dialog is None
    finally:
        window.close()


@pytest.mark.parametrize('exit_kind', ['quit', 'exit', 'parentclose'])
def test_real_qt_event_loop_and_modal_exit_release_fake_handles(tmp_path, exit_kind):
    """Use an isolated Qt process so app.exit cannot affect other UI tests."""
    repo = Path(__file__).resolve().parents[1]
    source = textwrap.dedent('''
        import json, sys
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from membrane_control.__main__ import _run_event_loop
        from membrane_control.controller import AppController
        from membrane_control.relay_bench import RelayBenchDialog
        from membrane_control.ui import MainWindow
        import membrane_control.ui as ui
        class Wire:
            def __init__(self, port='FAKE-BENCH'):
                self.port=port; self.closed=False; self.count=0
            def send(self, packet): pass
            def poll(self, now=None): return []
            def close(self): self.closed=True; self.count+=1
        app=QApplication([])
        controller=AppController(sys.argv[1])
        controller.set_simulation(False)
        controller.list_ports=lambda:[('FAKE-BENCH','Test double')]
        window=MainWindow(controller)
        scale=Wire('FAKE-SCALE'); controller.balance=scale
        captures=[]; cleanups=[]
        class Modal(RelayBenchDialog):
            def __init__(self, parent, **kwargs):
                self.wire=Wire()
                super().__init__(parent,transport_factory=lambda *a:self.wire,**kwargs)
                self.connect_board(); captures.append(self.wire)
            def shutdown(self):
                super().shutdown()
                cleanups.append(not self.timer.isActive() and self.session.transport is None)
        ui.RelayBenchDialog=Modal
        window.show()
        QTimer.singleShot(0,window._open_relay_bench)
        if sys.argv[2]=='exit':
            finish=lambda:app.exit(3)
        elif sys.argv[2]=='parentclose':
            finish=window.close
        else:
            finish=app.quit
        QTimer.singleShot(150,finish)
        result=_run_event_loop(app,window)
        print(json.dumps(dict(result=result,controller_closed=controller.closed,
            bench_closed=bool(captures) and captures[0].closed,
            bench_close_count=captures[0].count if captures else 0,
            scale_closed=scale.closed,scale_close_count=scale.count,
            window_timer_active=window.timer.isActive(),
            bench_cleanup=bool(cleanups) and all(cleanups),
            bench_ref_cleared=window._relay_bench_dialog is None)))
    ''')
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    env['PYTHONPATH'] = str(repo / 'desktop' / 'src') + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run([sys.executable, '-c', source, str(tmp_path), exit_kind],
                            cwd=repo, env=env, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report == dict(result=3 if exit_kind == 'exit' else 0, controller_closed=True,
        bench_closed=True, bench_close_count=1, scale_closed=True, scale_close_count=1,
        window_timer_active=False, bench_cleanup=True, bench_ref_cleared=True)

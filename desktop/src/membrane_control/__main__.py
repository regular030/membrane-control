"""Start the desktop app. Demo is always the default; hardware never auto-connects."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys


def _run_event_loop(app, window):
    """Qt quit signals and exceptional loop exits share the same device owner."""
    app.aboutToQuit.connect(window.shutdown)
    try:
        return app.exec()
    finally:
        window.shutdown()
        try:
            app.aboutToQuit.disconnect(window.shutdown)
        except (RuntimeError, TypeError):
            pass


def main():
    parser = argparse.ArgumentParser(description="Membrane Control")
    parser.add_argument("--demo", action="store_true", help="Use simulated devices (default)")
    parser.add_argument("--data-dir", type=Path, help="Operator data directory")
    parser.add_argument("--screenshot", type=Path, help="Save a UI screenshot after startup")
    parser.add_argument("--quit-after", type=float, help="Exit after a number of seconds (testing)")
    args = parser.parse_args()
    data_dir = args.data_dir or Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "BasuMembraneControl"
    data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(data_dir / "application.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtCore import QTimer
    from .controller import AppController
    from .ui import MainWindow
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, "#f4f6f8"),
                        (QPalette.ColorRole.WindowText, "#182b3b"),
                        (QPalette.ColorRole.Base, "#ffffff"),
                        (QPalette.ColorRole.AlternateBase, "#f6f8fa"),
                        (QPalette.ColorRole.Text, "#182b3b"),
                        (QPalette.ColorRole.Button, "#edf1f4"),
                        (QPalette.ColorRole.ButtonText, "#182b3b"),
                        (QPalette.ColorRole.Highlight, "#176b83"),
                        (QPalette.ColorRole.HighlightedText, "#ffffff")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setApplicationName("Membrane Control")
    app.setOrganizationName("Basu Lab")
    controller = AppController(data_dir)
    window = MainWindow(controller)
    def exception_handler(kind, value, traceback):
        logging.critical("Application error", exc_info=(kind, value, traceback))
        window.shutdown_relay_bench()
        window.shutdown_valve_test()
        try:
            controller.stop_run()
        except Exception:
            logging.exception("Could not send stop")
        QMessageBox.critical(window, "Application error", str(value) + "\nA stop was requested. Check the system before continuing.")
    sys.excepthook = exception_handler
    window.show()
    if args.screenshot:
        def capture():
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(args.screenshot))
        QTimer.singleShot(750, capture)
    if args.quit_after is not None:
        QTimer.singleShot(max(1000, int(args.quit_after*1000)), app.quit)
    return _run_event_loop(app, window)


if __name__ == "__main__":
    raise SystemExit(main())

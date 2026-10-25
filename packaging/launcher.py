"""PyInstaller entry point for the portable Windows application."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def launch() -> int:
    """Start the app and preserve otherwise invisible windowed-launch errors."""
    try:
        from membrane_control.__main__ import main

        return int(main() or 0)
    except Exception:
        details = traceback.format_exc()
        data_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        log_path = data_root / "BasuMembraneControl" / "logs" / "launcher-error.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(details, encoding="utf-8")
            message = f"Basu Membrane Control could not start.\n\nDetails: {log_path}"
        except OSError:
            message = "Basu Membrane Control could not start.\n\n" + details[-1800:]
        if sys.platform == "win32" and os.environ.get("BASU_HEADLESS") != "1":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "Basu Membrane Control", 0x10)
        else:
            print(message, file=sys.stderr)
            print(details, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(launch())

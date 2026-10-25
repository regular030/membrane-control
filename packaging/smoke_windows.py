"""Launch the built executable in isolated Demo mode and verify a screenshot."""

from __future__ import annotations

import argparse
import os
import struct
import subprocess
import tempfile
from pathlib import Path

from build_windows import APP_NAME, ROOT, package_version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    executable = args.executable or ROOT / "dist" / "app" / f"{APP_NAME}-{package_version()}-windows-x64.exe"
    if not executable.is_file():
        parser.error(f"Executable not found: {executable}")
    with tempfile.TemporaryDirectory(prefix="basu-package-smoke-") as directory:
        temporary = Path(directory)
        screenshot = temporary / "demo.png"
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["BASU_HEADLESS"] = "1"
        environment["LOCALAPPDATA"] = str(temporary)
        result = subprocess.run(
            [str(executable.resolve()), "--demo", "--data-dir", str(temporary / "data"),
             "--screenshot", str(screenshot), "--quit-after", "2"],
            check=False,
            timeout=90,
            cwd=temporary,
            env=environment,
        )
        if result.returncode:
            failure_log = temporary / "BasuMembraneControl" / "logs" / "launcher-error.log"
            details = failure_log.read_text(encoding="utf-8") if failure_log.exists() else "No launcher error log was produced."
            raise RuntimeError(f"Packaged application exited with code {result.returncode}:\n{details}")
        if not screenshot.is_file():
            raise RuntimeError("The executable did not produce the requested Demo screenshot.")
        header = screenshot.read_bytes()[:24]
        if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("The Demo screenshot is not a valid PNG.")
        width, height = struct.unpack(">II", header[16:24])
        if width < 640 or height < 400:
            raise RuntimeError(f"Unexpected Demo window size: {width} x {height}")
        print(f"Packaged Demo launch passed: {width} x {height} PNG; clean exit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

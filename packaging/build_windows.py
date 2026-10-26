"""Build a self-contained Windows executable and portable release ZIP.

Run on Windows after installing the project's development dependencies:
    python packaging/build_windows.py

PyInstaller and PlatformIO must already be installed in the active Python
environment. Firmware builds can download their pinned toolchain dependencies.
No device driver is installed and no serial port is opened by this script.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "desktop" / "src" / "membrane_control"
APP_NAME = "MembraneControl"


def package_version() -> str:
    """Read the version without importing GUI code during a build."""
    init_file = PACKAGE / "__init__.py"
    if init_file.exists():
        tree = ast.parse(init_file.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets):
                    return str(ast.literal_eval(node.value))
    import tomllib

    with (ROOT / "pyproject.toml").open("rb") as stream:
        return str(tomllib.load(stream)["project"]["version"])


def validate_version(value: str) -> str:
    normalized = value.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]*)", normalized):
        raise ValueError(f"Invalid release version: {value!r}")
    if normalized != package_version():
        raise ValueError("Release tag version must match the package version.")
    return normalized


def write_checksums(paths: list[Path], destination: Path) -> None:
    lines = []
    for path in sorted(paths, key=lambda item: item.name):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        lines.append(f"{digest.hexdigest()}  {path.name}\n")
    destination.write_text("".join(lines), encoding="utf-8")


def build(version: str, clean: bool = True, firmware_archive: Path | None = None) -> Path:
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Build this Windows x64 executable on Windows x64 with 64-bit Python.")
    if sys.maxsize <= 2**32:
        raise RuntimeError("A 64-bit Python interpreter is required.")
    try:
        importlib.metadata.version("pyinstaller")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("PyInstaller is missing. Install the project's development dependencies first.") from exc

    binary_name = f"{APP_NAME}-{version}-windows-x64"
    build_dir = ROOT / "build" / "pyinstaller"
    app_dir = ROOT / "dist" / "app"
    release_dir = ROOT / "dist" / "release"
    spec_dir = ROOT / "build" / "spec"
    for directory in (build_dir, app_dir, release_dir, spec_dir):
        directory.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name",
        binary_name,
        "--distpath",
        str(app_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(spec_dir),
        "--paths",
        str(ROOT / "desktop" / "src"),
        "--collect-data",
        "membrane_control",
        "--collect-data",
        "pyqtgraph",
        str(ROOT / "packaging" / "launcher.py"),
    ]
    if clean:
        command.insert(4, "--clean")
    # Resolve Qt's Windows ICU dependency from Windows, not unrelated tools
    # (e.g. Poppler) that happen to put an incompatible icuuc.dll on PATH.
    # PyInstaller adds the package-specific Qt/NumPy DLL directories itself.
    environment = os.environ.copy()
    windows = Path(environment.get("SystemRoot", "C:/Windows"))
    environment["PATH"] = os.pathsep.join(str(path) for path in (
        Path(sys.executable).parent, Path(sys.base_prefix),
        windows / "System32", windows, windows / "System32" / "Wbem"))
    subprocess.run(command, check=True, cwd=ROOT, env=environment)
    executable = app_dir / f"{binary_name}.exe"
    if not executable.is_file():
        raise RuntimeError(f"Build completed without the expected executable: {executable}")

    released_exe = release_dir / executable.name
    shutil.copy2(executable, released_exe)
    manifest = {
        "application": "Membrane Control",
        "version": version,
        "platform": "windows-x64",
        "build_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "prototype": True,
        "hardware_commissioned": False,
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("PyInstaller", "PySide6", "pyqtgraph", "pyserial", "numpy")
        },
    }
    manifest_path = release_dir / f"{binary_name}-build.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    archive_path = release_dir / f"{binary_name}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(released_exe, released_exe.name)
        archive.write(manifest_path, "BUILD-INFO.json")
        for source, name in (
            (ROOT / "packaging" / "PORTABLE-README.txt", "READ-ME-FIRST.txt"),
            (ROOT / "docs" / "START-HERE.md", "START-HERE.md"),
            (ROOT / "docs" / "installation.md", "installation.md"),
            (ROOT / "docs" / "operator-guide.md", "operator-guide.md"),
            (ROOT / "docs" / "full-firmware.md", "full-firmware.md"),
        ):
            archive.write(source, name)
        if firmware_archive is not None:
            archive.write(firmware_archive, firmware_archive.name)
    write_checksums([released_exe, archive_path, manifest_path], release_dir / "SHA256SUMS.txt")
    print(f"Release executable: {released_exe}")
    print(f"Portable ZIP: {archive_path}")
    print(f"Checksums: {release_dir / 'SHA256SUMS.txt'}")
    return released_exe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Package version or matching v-prefixed release tag")
    parser.add_argument("--incremental", action="store_true", help="Reuse local PyInstaller analysis caches")
    args = parser.parse_args()
    try:
        version = validate_version(args.version or package_version())
        from build_firmware import build_firmware
        firmware_archive = build_firmware(version)
        executable = build(version, clean=not args.incremental, firmware_archive=firmware_archive)
        from build_setup import build_setup
        build_setup(version, executable, firmware_archive=firmware_archive)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

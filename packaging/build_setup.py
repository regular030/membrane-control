"""Build a no-Python-required Windows setup EXE containing the app and sources."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def payload_sources(root: Path, executable: Path) -> dict[str, Path]:
    sources = {"app/MembraneControl.exe": executable}
    for relative in (
        "packaging/setup_windows.ps1", "packaging/flash_dry_run.ps1",
        "packaging/install_cp210x.ps1", "packaging/driver-config.json",
        "packaging/python-runtime.json", "docs/setup-new-pc.md",
        "docs/START-HERE.md", "docs/operator-guide.md", "hardware/balance-usb-setup.md",
        "docs/relay-board-test.md", "protocol/relay-bench.md",
    ):
        sources[relative] = root / relative
    for source in sorted((root / "firmware").rglob("*")):
        relative = source.relative_to(root)
        if not source.is_file() or any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            continue
        if source.suffix not in {".h", ".hpp", ".cpp", ".c", ".py", ".ini", ".md"}:
            continue
        sources[relative.as_posix()] = source
    for name, source in sources.items():
        if not source.is_file():
            raise RuntimeError(f"Required setup payload file is missing: {name}")
    return sources


def create_payload(root: Path, executable: Path, version: str, archive: Path) -> dict:
    sources = payload_sources(root, executable)
    configuration = json.loads((root / "packaging/python-runtime.json").read_text(encoding="utf-8"))
    manifest = {
        "version": version, "app": "app/MembraneControl.exe", "python": configuration,
        "files": {name: hashlib.sha256(source.read_bytes()).hexdigest() for name, source in sources.items()},
    }
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, source in sources.items():
            output.write(source, name)
        output.writestr("setup-manifest.json", json.dumps(manifest, indent=2) + "\n")
    return manifest


def build_setup(version: str, executable: Path) -> Path:
    if os.name != "nt":
        raise RuntimeError("Build the setup EXE on Windows x64.")
    directory = ROOT / "build" / "setup"
    archive = directory / "payload.zip"
    create_payload(ROOT, executable, version, archive)
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    candidates = [windows / "Microsoft.NET" / framework / "v4.0.30319" / "csc.exe"
                  for framework in ("Framework64", "Framework")]
    compiler = next((path for path in candidates if path.is_file()), None)
    if compiler is None:
        raise RuntimeError("The Windows .NET Framework C# compiler was not found.")
    destination = ROOT / "dist" / "release" / f"MembraneControl-Setup-{version}-windows-x64.exe"
    command = [str(compiler), "/nologo", "/target:exe", "/platform:x64", "/optimize+",
               "/reference:System.IO.Compression.dll", "/reference:System.IO.Compression.FileSystem.dll",
               f"/resource:{archive},MembraneControl.Payload.zip", f"/out:{destination}",
               str(ROOT / "packaging/setup_bootstrap.cs")]
    subprocess.run(command, cwd=ROOT, check=True)
    from build_windows import write_checksums
    release = destination.parent
    stem = f"MembraneControl-{version}-windows-x64"
    write_checksums([destination, executable, release / (stem + ".zip"), release / (stem + "-build.json")],
                    release / "SHA256SUMS.txt")
    print(f"Fresh-PC setup: {destination}")
    return destination


if __name__ == "__main__":
    from build_windows import package_version
    version = package_version()
    build_setup(version, ROOT / "dist/release" / f"MembraneControl-{version}-windows-x64.exe")

"""The setup must ship the checked sources, never local caches or experiment data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_builder", ROOT / "packaging/build_setup.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def fake_source(tmp_path):
    required = [
        "packaging/setup_windows.ps1", "packaging/flash_dry_run.ps1",
        "packaging/install_cp210x.ps1", "packaging/driver-config.json",
        "docs/setup-new-pc.md", "docs/START-HERE.md", "docs/operator-guide.md",
        "hardware/balance-usb-setup.md", "firmware/platformio.ini", "firmware/src/main.cpp",
        "docs/relay-board-test.md", "protocol/relay-bench.md",
        "hardware/pump-interface.md",
        "docs/full-firmware.md",
    ]
    for relative in required:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("checked source", encoding="utf-8")
    (tmp_path / "packaging/python-runtime.json").write_text(json.dumps({"version": "3.14.10"}))
    executable = tmp_path / "MembraneControl.exe"
    executable.write_bytes(b"test app binary")
    return executable


def test_payload_hashes_actual_bytes_and_excludes_local_files(tmp_path):
    executable = fake_source(tmp_path)
    for relative in ("firmware/.pio/build/secret.h", "firmware/__pycache__/cached.py", "firmware/operator.sqlite"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("must not ship")
    archive_path = tmp_path / "out/payload.zip"
    builder.create_payload(tmp_path, executable, "1.2.3", archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read("setup-manifest.json"))
        assert manifest["version"] == "1.2.3"
        assert archive.read(manifest["app"]) == executable.read_bytes()
        assert not any("secret" in name or "__pycache__" in name or "sqlite" in name for name in archive.namelist())
        assert set(archive.namelist()) == set(manifest["files"]) | {"setup-manifest.json"}
        for relative, digest in manifest["files"].items():
            assert hashlib.sha256(archive.read(relative)).hexdigest() == digest


def test_incomplete_setup_fails_before_creating_bundle(tmp_path):
    executable = fake_source(tmp_path)
    (tmp_path / "packaging/setup_windows.ps1").unlink()
    archive_path = tmp_path / "payload.zip"
    with pytest.raises(RuntimeError, match="setup_windows.ps1"):
        builder.create_payload(tmp_path, executable, "1.2.3", archive_path)
    assert not archive_path.exists()


def test_setup_authenticates_full_firmware_archive(tmp_path):
    executable = fake_source(tmp_path)
    firmware = tmp_path / "MembraneControl-Firmware-1.2.3-esp32.zip"
    firmware.write_bytes(b"compiled firmware archive fixture")
    output = tmp_path / "payload.zip"
    builder.create_payload(tmp_path, executable, "1.2.3", output, firmware)
    relative = "firmware-release/" + firmware.name
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("setup-manifest.json"))
        assert archive.read(relative) == firmware.read_bytes()
        assert manifest["files"][relative] == hashlib.sha256(firmware.read_bytes()).hexdigest()


def test_setup_does_not_silently_omit_missing_firmware_archive(tmp_path):
    executable = fake_source(tmp_path)
    with pytest.raises(RuntimeError, match="firmware-release"):
        builder.create_payload(tmp_path, executable, "1.2.3", tmp_path / "payload.zip", tmp_path / "missing.zip")

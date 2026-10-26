"""Offline firmware packaging: metadata addresses, complete sources and provenance."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import zipfile

import pytest


SPEC = importlib.util.spec_from_file_location(
    "firmware_bundle_builder", Path(__file__).parents[1] / "packaging/build_firmware.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.fixture
def bundle_project(tmp_path, monkeypatch):
    root = tmp_path / "project with spaces"
    root.mkdir()
    for name in builder.REQUIRED_SOURCES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// complete source " + name, encoding="utf-8")
    for name in ("firmware/test/test_control/test_main.cpp", "firmware/test/mocks/Arduino.h",
                 "firmware/include/RelayBenchCore.h", "protocol/relay-bench.md", "docs/full-firmware.md"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture " + name, encoding="utf-8")
    for name in ("firmware/.pio/libdeps/passwords.txt", "firmware/.env", "work/credentials.txt",
                 "firmware/__pycache__/secret.py", "firmware/.pio/cache/token.txt",
                 "firmware/include/ValveTestProfile.local.h"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("DO NOT SHIP CREDENTIALS", encoding="utf-8")
    core = tmp_path / "isolated platformio"
    tool = core / "packages/tool-esptoolpy"
    tool.mkdir(parents=True)
    (tool / "esptool.py").write_text("# mock tool", encoding="utf-8")
    (tool / "package.json").write_text('{"version":"2.40900.250804"}', encoding="utf-8")
    boot_app = core / "packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"
    boot_app.parent.mkdir(parents=True)
    boot_app.write_bytes(b"boot-app-fixture")
    metadata = {}
    # Deliberately nondefault generated addresses catch hard-coded flash assumptions.
    for target in builder.TARGETS:
        build_dir = root / "firmware/.pio/build" / target
        build_dir.mkdir(parents=True)
        (build_dir / "bootloader.bin").write_bytes(b"\xe9\x03\x02\x20" + b"BOOT" * 8)
        partition = struct.pack("<HBBII16sI", 0x50aa, 0, 0, 0x12000, 0x100000, b"factory", 0)
        (build_dir / "partitions.bin").write_bytes(partition + b"\xff" * 32)
        (build_dir / "firmware.bin").write_bytes(b"\xe9" + target.encode() * 5)
        defines = ["ARDUINO_ESP32_DEV"]
        if target not in ("esp32-relay-bench", "esp32-valve-test"):
            defines.append("BASU_DRY_RUN=" + ("1" if target == "esp32-dry-run" else "0"))
        metadata[target] = {
            "env_name": target, "build_type": "release", "defines": defines,
            "prog_path": str(build_dir / "firmware.elf"),
            "extra": {"application_offset": "0x12000", "flash_images": [
                {"offset": "0x1000", "path": str(build_dir / "bootloader.bin")},
                {"offset": "0x9000", "path": str(build_dir / "partitions.bin")},
                {"offset": "0xf000", "path": str(boot_app)},
            ]},
        }
    calls = []

    def run(arguments, environment):
        calls.append(arguments)
        assert environment["PLATFORMIO_CORE_DIR"] == str(core.resolve())
        if "metadata" in arguments:
            destination = Path(arguments[arguments.index("--json-output-path") + 1])
            destination.write_text(json.dumps(metadata), encoding="utf-8")
        elif "merge_bin" in arguments:
            output = Path(arguments[arguments.index("--output") + 1])
            pairs = arguments[arguments.index("--flash_size") + 2:]
            images = [(int(pairs[index], 0), Path(pairs[index + 1]).read_bytes())
                      for index in range(0, len(pairs), 2)]
            merged = bytearray(b"\xff") * max(offset + len(data) for offset, data in images)
            for offset, data in images:
                merged[offset:offset + len(data)] = data
            output.write_bytes(merged)
        else:
            assert "run" in arguments

    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "_run", run)
    monkeypatch.setattr(builder.importlib.metadata, "version", lambda name: "6.2.0")
    monkeypatch.setenv("PLATFORMIO_CORE_DIR", str(core))
    return root, metadata, calls, run


def test_complete_bundle_uses_metadata_addresses_and_matches_every_hash(bundle_project):
    root, _, calls, _ = bundle_project
    output = builder.build_firmware("0.1.10")
    assert output == root / "dist/release/MembraneControl-Firmware-0.1.10-esp32.zip"
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert "firmware/test/test_control/test_main.cpp" in names
        assert "firmware/test/mocks/Arduino.h" in names
        assert "firmware/compact_paths.py" in names
        assert "firmware/native_compiler.py" in names
        assert not any(".pio" in name or "credentials" in name or ".env" in name for name in names)
        assert all(b"DO NOT SHIP CREDENTIALS" not in archive.read(name) for name in names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["bundle_version"] == "0.1.10"
        assert manifest["hardware_commissioned"] is False
        for name, digest in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        for line in archive.read("SHA256SUMS.txt").decode().splitlines():
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        for target in builder.TARGETS:
            item = manifest["targets"][target]
            assert item == json.loads(archive.read(f"images/{target}/manifest.json"))
            assert item["hardware_verified"] is False
            assert item["simulation"] == (target == "esp32-dry-run")
            assert [part["offset"] for part in item["flash_images"]] == ["0x1000", "0x9000", "0xf000", "0x12000"]
            factory = archive.read(item["factory_image"]["file"])
            assert item["factory_image"]["offset"] == "0x0"
            assert factory[:0x1000] == b"\xff" * 0x1000
            for part in item["flash_images"]:
                data = archive.read(part["file"])
                offset = int(part["offset"], 0)
                assert factory[offset:offset + len(data)] == data
        assert b"LOCKED" in archive.read("README.md")
    assert len(calls) == 2 + len(builder.TARGETS)  # one build, one metadata query, one merge per target
    assert not any(value in ("upload", "erase", "--port", "--upload-port") for call in calls for value in call)


def test_reuse_requires_source_provenance_and_is_reproducible(bundle_project):
    root, _, calls, _ = bundle_project
    first = builder.build_firmware("0.1.10").read_bytes()
    calls.clear()
    second = builder.build_firmware("v0.1.10", build=False).read_bytes()
    assert first == second
    assert all("merge_bin" in call for call in calls)
    (root / "firmware/include/BoardConfig.h").write_text("changed source", encoding="utf-8")
    with pytest.raises(ValueError, match="matching firmware build metadata"):
        builder.build_firmware("0.1.10", build=False)


def test_cannot_reuse_unrecorded_build(bundle_project):
    with pytest.raises(ValueError, match="matching firmware build metadata"):
        builder.build_firmware("0.1.10", build=False)


@pytest.mark.parametrize("bad_version", ["../x", "1/2/3", "", "0.1.10\\x", "0.1.10:evil"])
def test_archive_version_cannot_escape_release_directory(bundle_project, bad_version):
    with pytest.raises(ValueError, match="version"):
        builder.build_firmware(bad_version)


@pytest.mark.parametrize("mutation, expected", [
    (lambda m: m.update(prog_path="C:/not-the-project/firmware.elf"), "application path"),
    (lambda m: m["extra"]["flash_images"][0].update(path="C:/not-the-project/bootloader.bin"), "outside"),
    (lambda m: m["extra"]["flash_images"][1].update(offset="0x1001"), "overlap"),
    (lambda m: m["extra"].update(application_offset="0x13000"), "application partition"),
    (lambda m: m["defines"].append('BASU_VERIFIED_PROFILE_HEADER="commissioned.h"'), "commissioned"),
    (lambda m: m["defines"].remove("BASU_DRY_RUN=0"), "simulation flag"),
])
def test_rejects_mismatched_or_unsafe_build_metadata(bundle_project, mutation, expected):
    _, metadata, _, _ = bundle_project
    mutation(metadata["esp32-physical"])
    with pytest.raises(ValueError, match=expected):
        builder.build_firmware("0.1.10")


def test_rejects_application_larger_than_generated_partition(bundle_project):
    root, _, _, _ = bundle_project
    (root / "firmware/.pio/build/esp32-physical/firmware.bin").write_bytes(b"x" * (0x100000 + 1))
    with pytest.raises(ValueError, match="exceeds its generated partition"):
        builder.build_firmware("0.1.10")


def test_reviewed_valve_profile_cannot_be_packaged_as_locked_factory_image(bundle_project):
    _, metadata, _, _ = bundle_project
    metadata['esp32-valve-test']['defines'].append('BASU_VALVE_PROFILE_HEADER="reviewed.h"')
    with pytest.raises(ValueError, match='commissioned'):
        builder.build_firmware('0.1.12')


def test_local_commissioning_profile_is_not_in_factory_source_bundle(bundle_project):
    root, _, _, _ = bundle_project
    sources = builder.source_files(root)
    assert 'firmware/include/ValveTestProfile.local.h' not in sources


def test_rejects_merge_corruption(bundle_project, monkeypatch):
    _, _, _, real_run = bundle_project

    def corrupt(arguments, environment):
        real_run(arguments, environment)
        if "merge_bin" in arguments:
            Path(arguments[arguments.index("--output") + 1]).write_bytes(b"corrupted")

    monkeypatch.setattr(builder, "_run", corrupt)
    with pytest.raises(ValueError, match="differs from its verified"):
        builder.build_firmware("0.1.10")


def test_source_changes_during_compile_require_rebuild(bundle_project, monkeypatch):
    root, _, _, real_run = bundle_project

    def changing(arguments, environment):
        real_run(arguments, environment)
        if "metadata" in arguments:
            (root / "firmware/src/main.cpp").write_text("concurrent edit", encoding="utf-8")

    monkeypatch.setattr(builder, "_run", changing)
    with pytest.raises(RuntimeError, match="changed during the build"):
        builder.build_firmware("0.1.10")


def test_compile_failure_does_not_publish_archive(bundle_project, monkeypatch):
    root, _, _, _ = bundle_project

    def fail(arguments, environment):
        raise subprocess.CalledProcessError(1, arguments)

    monkeypatch.setattr(builder, "_run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        builder.build_firmware("0.1.10")
    assert not list(root.rglob("*.zip"))

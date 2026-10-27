"""Package complete ESP32 sources and offline, merged images without opening USB."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("esp32-dry-run", "esp32-relay-bench", "esp32-valve-test", "esp32-physical")
PURPOSES = {
    "esp32-dry-run": "Protocol test with simulated measurements; no relay or sensor GPIO access.",
    "esp32-relay-bench": "Real relay pulses on an unloaded board only; no pump or sensor control.",
    "esp32-valve-test": "Sensor-free solenoid valve commissioning; reviewed valve-only profile required, factory profile locked.",
    "esp32-physical": "Normal controller: six confirmed manual valve toggles without sensors; pump/experiments require full configuration.",
}
REQUIRED_SOURCES = (
    "firmware/README.md", "firmware/platformio.ini", "firmware/compact_paths.py",
    "firmware/native_compiler.py", "firmware/src/main.cpp", "firmware/src/relay_bench_main.cpp",
    "firmware/include/BoardProfile.h", "firmware/include/BoardConfig.h",
    "firmware/include/ManualValveConfig.h",
    "firmware/src/valve_test_main.cpp", "firmware/include/ValveTestCore.h",
    "firmware/include/ValveTestProfile.h", "firmware/include/ValveTestConfig.h",
    "firmware/examples/PwmConverterProfile.example.h",
    "firmware/examples/pwm-converter-bench/platformio.ini",
    "firmware/examples/pwm-converter-bench/src/main.cpp",
    "firmware/examples/pwm-converter-bench/README.md",
)
SOURCE_SUFFIXES = {".h", ".hpp", ".cpp", ".c", ".py", ".ini", ".md", ".txt"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_name(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or "\\" in value or ":" in value or path.is_absolute()
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ValueError("Unsafe firmware archive path")
    return path.as_posix()


def checked_file(path: Path, root: Path) -> Path:
    path, root = Path(path), Path(root).resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or path.is_symlink() or not resolved.is_file():
        raise ValueError(f"Firmware input is missing or outside its permitted directory: {path.name}")
    if resolved.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Firmware input exceeds the package size limit")
    return resolved


def source_files(root: Path) -> dict[str, bytes]:
    result = {}
    for source in sorted((root / "firmware").rglob("*")):
        relative = source.relative_to(root)
        if (not source.is_file() or source.suffix not in SOURCE_SUFFIXES
                or source.name.endswith(".local.h")
                or any(part.startswith(".") or part in ("__pycache__", "work", "cache") for part in relative.parts)):
            continue
        name = archive_name(relative.as_posix())
        result[name] = checked_file(source, root / "firmware").read_bytes()
    for name in REQUIRED_SOURCES:
        if name not in result:
            raise ValueError(f"Required firmware source is missing: {name}")
    for name in ("protocol/v1.md", "protocol/relay-bench.md", "docs/relay-board-test.md",
                 "protocol/valve-test.md", "docs/valve-test.md",
                 "docs/flow-sensor-troubleshooting.md",
                 "docs/normal-valves.md", "docs/scale-connection.md",
                 "docs/pwm-converter-setup.md", "hardware/procurement.md",
                 "docs/full-firmware.md", "hardware/README.md", "hardware/relay-board-pin-plan.md",
                 "hardware/pump-interface.md", "packaging/build_firmware.py", "LICENSE"):
        path = root / name
        if path.is_file():
            result[archive_name(name)] = checked_file(path, root).read_bytes()
    return result


def _run(arguments: list[str], environment: dict[str, str]) -> None:
    subprocess.run(arguments, cwd=ROOT, env=environment, check=True, timeout=900)


def _offset(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("Flash offsets must be explicit integers from PlatformIO metadata")
    try:
        result = int(value, 0) if isinstance(value, str) else value
    except ValueError as exc:
        raise ValueError("Invalid flash offset in PlatformIO metadata") from exc
    if not 0 <= result < 16 * 1024 * 1024:
        raise ValueError("Flash offset is outside the supported ESP32 range")
    return result


def _partition_size(data: bytes, application_offset: int, flash_size: int) -> int:
    """Read the generated ESP32 table, rather than guessing an application slot."""
    entries = []
    for position in range(0, len(data) - 31, 32):
        magic = struct.unpack_from("<H", data, position)[0]
        if magic == 0xffff:
            break
        if magic == 0xebeb:
            if hashlib.md5(data[:position]).digest() != data[position + 16:position + 32]:
                raise ValueError("Partition-table MD5 does not match")
            break
        if magic != 0x50aa:
            raise ValueError("Invalid ESP32 partition table")
        _, kind, _subtype, offset, size, _label, _flags = struct.unpack_from("<HBBII16sI", data, position)
        if size == 0 or offset + size > flash_size:
            raise ValueError("Partition extends outside the compiled flash size")
        entries.append((offset, offset + size, kind))
    for left, right in zip(sorted(entries), sorted(entries)[1:]):
        if left[1] > right[0]:
            raise ValueError("Generated partitions overlap")
    matches = [end - start for start, end, kind in entries if kind == 0 and start == application_offset]
    if len(matches) != 1:
        raise ValueError("PlatformIO application offset does not match an application partition")
    return matches[0]


def flash_inputs(metadata: dict, target: str, core_dir: Path) -> tuple[list[tuple[int, Path, bytes]], int]:
    if metadata.get("env_name") != target or metadata.get("build_type") != "release":
        raise ValueError("Incorrect firmware build metadata")
    defines = metadata.get("defines", [])
    if not isinstance(defines, list) or "ARDUINO_ESP32_DEV" not in defines:
        raise ValueError("Firmware bundle requires the classic esp32dev board target")
    if any(any(flag in str(value) for flag in ("BASU_VERIFIED_PROFILE_HEADER", "BASU_VALVE_PROFILE_HEADER")) for value in defines):
        raise ValueError("A commissioned physical profile cannot be labelled as the unverified factory build")
    if target not in ("esp32-relay-bench", "esp32-valve-test"):
        expected = "BASU_DRY_RUN=" + ("1" if target == "esp32-dry-run" else "0")
        if expected not in defines:
            raise ValueError("Firmware target simulation flag does not match its label")
    build_dir = ROOT / "firmware" / ".pio" / "build" / target
    program = Path(metadata.get("prog_path", ""))
    if program.resolve() != (build_dir / "firmware.elf").resolve():
        raise ValueError("Unexpected firmware application path")
    extra = metadata.get("extra", {})
    extras = extra.get("flash_images")
    if not isinstance(extras, list) or len(extras) != 3:
        raise ValueError("Expected three explicit PlatformIO support images")
    images = []
    names = set()
    for entry in extras:
        path = Path(entry.get("path", ""))
        if path.name in names or path.name not in {"bootloader.bin", "partitions.bin", "boot_app0.bin"}:
            raise ValueError("Unexpected or duplicate support image")
        names.add(path.name)
        allowed = (core_dir / "packages" / "framework-arduinoespressif32" / "tools" / "partitions"
                   if path.name == "boot_app0.bin" else build_dir)
        path = checked_file(path, allowed)
        images.append((_offset(entry.get("offset")), path, path.read_bytes()))
    application = checked_file(program.with_suffix(".bin"), build_dir)
    application_offset = _offset(extra.get("application_offset"))
    images.append((application_offset, application, application.read_bytes()))
    images.sort(key=lambda value: value[0])
    bootloader = next(data for _, path, data in images if path.name == "bootloader.bin")
    # ESP32 image header: byte 3 high nibble encodes 1, 2, 4, ... MiB.
    if len(bootloader) < 4 or bootloader[0] != 0xe9 or bootloader[2] > 3 or bootloader[3] >> 4 > 7:
        raise ValueError("Invalid ESP32 bootloader image header")
    flash_size = (1 << 20) << (bootloader[3] >> 4)
    if flash_size != 4 * 1024 * 1024:
        raise ValueError("This esp32dev bundle expects a compiled 4 MB flash image")
    previous_end = 0
    for offset, _path, data in images:
        if not data or offset < previous_end or offset + len(data) > flash_size:
            raise ValueError("Firmware images overlap or exceed compiled flash capacity")
        previous_end = offset + len(data)
    partitions = next(data for _, path, data in images if path.name == "partitions.bin")
    if len(application.read_bytes()) > _partition_size(partitions, application_offset, flash_size):
        raise ValueError("Firmware application exceeds its generated partition")
    return images, flash_size


def _readme(version: str) -> bytes:
    return f"""# Membrane Control firmware bundle {version}

This ZIP includes complete firmware sources, native tests, pinned PlatformIO
configuration, individual flash images and a merged factory.bin for each target.
The bundle version follows the desktop release; individual firmware versions may
remain unchanged. See manifest.json and each target's manifest.json for hashes
and the exact addresses exported by PlatformIO. No device was opened or flashed
while creating this bundle.

The source-only firmware/examples/pwm-converter-bench project provides a separate
converter signal test with the pump and valve contact loads disconnected. It is
not a fifth factory image. Its README explains explicit confirmation, serial
commands and bounded tests; do not use it to operate the pump or valves.

Choose one target:

- esp32-dry-run: simulated protocol/recipe testing, without relay/sensor GPIO.
- esp32-relay-bench: REAL relay pulses on a bare, unloaded board only. Follow
  docs/relay-board-test.md. This does not operate the pump or read sensors.
- esp32-valve-test: one solenoid pulse at a time without sensors or a DAC.
  The factory profile is LOCKED. A reviewed valve-only profile is required;
  see docs/valve-test.md. Keep the pump physically isolated.
- esp32-physical: NORMAL controller with the user-confirmed six manual valves
  V1-V6 = bits0-5, all LOW off. Dashboard ON/OFF works without sensors or a
  separate valve profile. Pump and experiment configuration remains incomplete.

factory.bin contains the bootloader, partition table, boot_app0 and application,
and is written at offset 0x0. Individual firmware.bin is only the application;
its address is in that target's manifest. Do not write firmware.bin at 0x0.
The merge preserves compiled flash mode/frequency/size header settings.

Use the installed Flash ESP32 shortcut or build from firmware/platformio.ini
with PlatformIO Core 6.2.0. Source builds download the pinned ESP32 toolchain and
ArduinoJson library; those caches are intentionally excluded. Close other serial
programs, identify the correct port, and confirm board power/wiring before any
upload. A three-wire external UART may need IO0/EN download entry and an EN reset
with IO0 released after flashing. Uploading replaces the existing program.

For source builds: python -m platformio run -d firmware -e <chosen-target>
Native tests: python -m platformio test -d firmware -e native

Desired flow is desktop experiment metadata, not automatic flow regulation.
No pressure calibration, pump interface or production approval is supplied here.
""".encode("utf-8")


def _zip_bytes(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(archive_name(name), date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def build_firmware(version: str, release_dir=None, build: bool = True) -> Path:
    version = str(version).removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[A-Za-z0-9.+-]*)", version):
        raise ValueError("Invalid firmware bundle release version")
    if importlib.metadata.version("platformio") != "6.2.0":
        raise RuntimeError("Firmware packaging requires PlatformIO Core 6.2.0")
    environment = os.environ.copy()
    core_dir = Path(environment.get("PLATFORMIO_CORE_DIR", ROOT / "work" / "platformio")).resolve()
    environment.update(PLATFORMIO_CORE_DIR=str(core_dir),
                       PLATFORMIO_BUILD_DIR=str(ROOT / "firmware" / ".pio" / "build"),
                       PLATFORMIO_LIBDEPS_DIR=str(ROOT / "firmware" / ".pio" / "libdeps"),
                       PLATFORMIO_SETTING_ENABLE_TELEMETRY="No", PLATFORMIO_DISABLE_UPGRADE_CHECK="true")
    source = source_files(ROOT)
    source_hashes = {name: sha256(data) for name, data in source.items() if name.startswith("firmware/")}
    work_dir = ROOT / "build" / "firmware-bundle"
    work_dir.mkdir(parents=True, exist_ok=True)
    if not work_dir.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Firmware staging directory escapes the project")
    metadata_path = work_dir / "platformio-metadata.json"
    provenance_path = work_dir / "source-hashes.json"
    prefix = [sys.executable, "-m", "platformio", "--no-ansi"]
    if build:
        arguments = prefix + ["run", "-d", str(ROOT / "firmware")]
        for target in TARGETS:
            arguments += ["-e", target]
        _run(arguments, environment)
        arguments = prefix + ["project", "metadata", "-d", str(ROOT / "firmware"),
                              "--json-output-path", str(metadata_path)]
        for target in TARGETS:
            arguments += ["-e", target]
        _run(arguments, environment)
        after = source_files(ROOT)
        if {name: sha256(data) for name, data in after.items() if name.startswith("firmware/")} != source_hashes:
            raise RuntimeError("Firmware sources changed during the build; rerun after edits finish")
        provenance_path.write_text(json.dumps(source_hashes, sort_keys=True), encoding="utf-8")
    if (not metadata_path.is_file() or not provenance_path.is_file()
            or json.loads(provenance_path.read_text(encoding="utf-8")) != source_hashes):
        raise ValueError("No matching firmware build metadata; build the bundle before using build=False")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    tool_dir = core_dir / "packages" / "tool-esptoolpy"
    tool = checked_file(tool_dir / "esptool.py", tool_dir)
    tool_version = json.loads(checked_file(tool_dir / "package.json", tool_dir).read_text(encoding="utf-8"))["version"]
    if not str(tool_version).startswith("2.40900."):
        raise ValueError("Expected the pinned PlatformIO esptool 4.9 package")
    payload = dict(source)
    payload["README.md"] = _readme(version)
    target_manifests = {}
    with tempfile.TemporaryDirectory(prefix="merge-", dir=work_dir) as temporary:
        temporary = Path(temporary)
        if not temporary.resolve().is_relative_to(work_dir.resolve()):
            raise ValueError("Firmware temporary directory escapes staging")
        for target in TARGETS:
            images, flash_size = flash_inputs(metadata.get(target, {}), target, core_dir)
            folder = "images/" + target + "/"
            image_manifest = []
            for offset, path, data in images:
                name = folder + path.name
                payload[name] = data
                image_manifest.append({"file": name, "offset": hex(offset), "size_bytes": len(data), "sha256": sha256(data)})
            factory = temporary / (target + "-factory.bin")
            arguments = [sys.executable, str(tool), "--chip", "esp32", "merge_bin", "--format", "raw",
                         "--output", str(factory), "--target-offset", "0x0", "--flash_mode", "keep",
                         "--flash_freq", "keep", "--flash_size", "keep"]
            for offset, path, _data in images:
                arguments += [hex(offset), str(path)]
            _run(arguments, environment)
            merged = checked_file(factory, temporary).read_bytes()
            expected = bytearray(b"\xff") * max(offset + len(data) for offset, _path, data in images)
            for offset, _path, data in images:
                expected[offset:offset + len(data)] = data
            if merged != expected:
                raise ValueError("Merged factory image differs from its verified component images")
            name = folder + "factory.bin"
            payload[name] = merged
            manifest = {"environment": target, "purpose": PURPOSES[target], "chip": "esp32", "board": "esp32dev",
                        "hardware_commissioned": False, "hardware_verified": False,
                        "simulation": target == "esp32-dry-run", "flash_size_bytes": flash_size,
                        "flash_options": {"flash_mode": "keep", "flash_freq": "keep", "flash_size": "keep"},
                        "flash_images": image_manifest,
                        "factory_image": {"file": name, "offset": "0x0", "size_bytes": len(merged), "sha256": sha256(merged)}}
            target_manifests[target] = manifest
            payload[folder + "manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest = {"schema_version": 1, "bundle_version": version, "platformio_core_version": "6.2.0",
                "esptool_package_version": tool_version, "hardware_commissioned": False,
                "targets": target_manifests, "files": {name: sha256(data) for name, data in sorted(payload.items())}}
    payload["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    payload["SHA256SUMS.txt"] = "".join(f"{sha256(data)}  {name}\n" for name, data in sorted(payload.items())).encode("utf-8")
    destination = Path(release_dir) if release_dir is not None else ROOT / "dist" / "release"
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = destination / f"MembraneControl-Firmware-{version}-esp32.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, data in sorted(payload.items()):
            _zip_bytes(archive, name, data)
    print(f"Firmware bundle: {archive_path}")
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version")
    parser.add_argument("--no-build", action="store_true", help="Reuse source-matching existing build metadata and images")
    args = parser.parse_args()
    version = args.version
    if version is None:
        tree = ast.parse((ROOT / "desktop/src/membrane_control/__init__.py").read_text(encoding="utf-8"))
        version = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets))
    try:
        build_firmware(version, build=not args.no_build)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Firmware package failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

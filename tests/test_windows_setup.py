"""Run PowerShell setup logic with fake payloads and mocked external actions.

No interpreter installation, download, driver change, build or serial-port access
is performed by these tests. Windows PowerShell 5.1 is used when available.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "packaging/setup_windows.ps1"
FLASH = ROOT / "packaging/flash_dry_run.ps1"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(not POWERSHELL or sys.platform != "win32", reason="Windows PowerShell setup tests")


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(script, *, check=True):
    result = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, timeout=30)
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def definitions(script=SETUP):
    return f". {ps_quote(script)} -DefinitionsOnly; "


@pytest.fixture
def payload(tmp_path):
    source = tmp_path / "payload with spaces & apostrophe's [data]"
    source.mkdir()
    content = {
        "app/MembraneControl.exe": b"fake packaged executable for checksum tests",
        "packaging/setup_windows.ps1": SETUP.read_bytes(),
        "packaging/flash_dry_run.ps1": FLASH.read_bytes(),
        "firmware/platformio.ini": b"[env:esp32-dry-run]\nplatform=espressif32\n[env:esp32-relay-bench]\nplatform=espressif32\n[env:esp32-physical]\nplatform=espressif32\n",
        "firmware/src/main.cpp": b"// fake source, never compiled\n",
        "firmware/include/BoardProfile.h": b"// unconfigured\n",
        "firmware/include/BoardConfig.h": b"// pins=-1\n",
    }
    for relative, data in content.items():
        file = source / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
    manifest = {"version": "0.1.7", "app": "app/MembraneControl.exe",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in content.items()},
        "python": {"version": "3.14.10", "kind": "zip",
            "url": "https://www.python.org/ftp/python/3.14.10/python-3.14.10-amd64.zip",
            "sha256": "cc28026a650970cc1570bb127312f1f9634eb67abfe157ae6ca1acbbc627d091"}}
    write_manifest(source, manifest)
    return source, manifest, tmp_path / "installed app & user's [lab]"


def write_manifest(source, manifest):
    (source / "setup-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_plan_validates_hashes_and_has_no_install_or_environment_side_effects(payload):
    source, _, target = payload
    result = run_ps(definitions() + "$env:PLATFORMIO_CORE_DIR='unchanged'; "
        f"Invoke-MembraneSetup -PayloadRoot {ps_quote(source)} -Destination {ps_quote(target)} -PlanOnly; "
        "if ($env:PLATFORMIO_CORE_DIR -cne 'unchanged') { throw 'environment changed' }")
    plan = json.loads(result.stdout)
    assert plan["version"] == "0.1.7" and Path(plan["installRoot"]) == target
    assert plan["pythonVersion"] == "3.14.10"
    assert plan["flashes_board"] is False and plan["installs_drivers"] is False
    assert plan["firmware_targets"] == ["esp32-dry-run", "esp32-relay-bench", "esp32-physical"]
    assert plan["full_controller"] == {"environment": "esp32-physical",
        "commissioning_required": True, "shipped_profile_verified": False}
    assert not target.exists()


@pytest.mark.parametrize("relative", ["../escape.txt", "C:/escape.txt", "firmware/../escape.txt",
    r"firmware\..\escape.txt", "firmware/NUL.txt", "firmware/extra."])
def test_unsafe_manifest_paths_are_rejected_before_install(payload, relative):
    source, manifest, target = payload
    manifest["files"][relative] = "a" * 64
    write_manifest(source, manifest)
    result = run_ps(definitions() + f"Invoke-MembraneSetup -PayloadRoot {ps_quote(source)} -Destination {ps_quote(target)} -PlanOnly", check=False)
    assert result.returncode != 0
    assert "Unsafe" in result.stderr or "escapes" in result.stderr
    assert not target.exists()


def test_hash_mismatch_fails_before_creating_install_directory(payload):
    source, _, target = payload
    (source / "app/MembraneControl.exe").write_bytes(b"corrupted")
    result = run_ps(definitions() + f"Invoke-MembraneSetup -PayloadRoot {ps_quote(source)} -Destination {ps_quote(target)}", check=False)
    assert result.returncode != 0 and "SHA256 mismatch" in result.stderr
    assert not target.exists()


def test_python_fallback_cannot_use_untrusted_url(payload):
    source, manifest, target = payload
    manifest["python"]["url"] = "https://example.invalid/python.zip"
    write_manifest(source, manifest)
    result = run_ps(definitions() + f"Invoke-MembraneSetup -PayloadRoot {ps_quote(source)} -Destination {ps_quote(target)} -PlanOnly", check=False)
    assert result.returncode != 0 and "python.org" in result.stderr
    assert not target.exists()


def mocked_setup_script(payload, fail_module=""):
    source, _, target = payload
    return definitions() + f"""
    $script:Calls = @(); $script:Shortcuts = $false
    function Get-SetupPython {{ param($Checked); return (Join-Path $Checked.InstallRoot 'tools/python-3.14.10/python.exe') }}
    function Test-SetupPython {{ param($PythonPath, $ExpectedVersion); return $true }}
    function New-SetupShortcuts {{ param($Destination); $script:Shortcuts=$true }}
    function Invoke-SetupCommand {{
        param($FilePath, [string[]]$ArgumentList, [switch]$Capture)
        $script:Calls += [PSCustomObject]@{{file=$FilePath;args=$ArgumentList;core=$env:PLATFORMIO_CORE_DIR}}
        if ($ArgumentList -contains {ps_quote(fail_module)} -and {ps_quote(fail_module)} -ne '') {{ throw 'mock dependency/build failure' }}
    }}
    $env:PLATFORMIO_CORE_DIR='previous-core'
    $failed=$false
    try {{ Invoke-MembraneSetup -PayloadRoot {ps_quote(source)} -Destination {ps_quote(target)} }}
    catch {{ $failed=$true }}
    [PSCustomObject]@{{calls=$script:Calls;shortcuts=$script:Shortcuts;failed=$failed;core=$env:PLATFORMIO_CORE_DIR}} | ConvertTo-Json -Depth 7 -Compress
    """


def result_json(output):
    return json.loads(output.strip().splitlines()[-1])


def test_setup_installs_pinned_tools_and_builds_all_three_targets_without_upload(payload):
    source, _, target = payload
    result = result_json(run_ps(mocked_setup_script(payload)).stdout)
    assert not result["failed"] and result["shortcuts"]
    assert result["core"] == "previous-core"
    args = [call["args"] for call in result["calls"]]
    assert args[0][:3] == ["-I", "-m", "venv"]
    assert "--isolated" in args[1] and "platformio==6.2.0" in args[1] and "pyserial==3.5" in args[1]
    assert args[2][-6:] == ["-e", "esp32-dry-run", "-e", "esp32-relay-bench", "-e", "esp32-physical"]
    assert "upload" not in sum(args, [])
    assert result["calls"][2]["core"] == str(target / "tools/platformio")
    assert (target / "MembraneControl.exe").read_bytes() == (source / "app/MembraneControl.exe").read_bytes()
    assert (target / "firmware/src/main.cpp").exists()
    assert "Setup complete" in next((target / "logs").glob("setup-*.log")).read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("module", ["pip", "platformio"])
def test_failed_dependency_or_build_has_no_success_or_shortcuts_and_is_retryable(payload, module):
    _, _, target = payload
    result = result_json(run_ps(mocked_setup_script(payload, module)).stdout)
    assert result["failed"] and not result["shortcuts"]
    assert result["core"] == "previous-core"
    log = next((target / "logs").glob("setup-*.log")).read_text(encoding="utf-8-sig")
    assert "SETUP FAILED" in log and "Setup complete" not in log
    assert "rerun" in log
    assert not (target / "setup-manifest.json").exists()


def test_python_archive_hash_mismatch_never_extracts_or_runs(payload):
    _, manifest, target = payload
    result = run_ps(definitions() + f"""
        [IO.Directory]::CreateDirectory({ps_quote(target / 'tools')}) | Out-Null
        $checked=[PSCustomObject]@{{InstallRoot={ps_quote(target)};Manifest=({ps_quote(json.dumps(manifest))} | ConvertFrom-Json)}}
        function Invoke-WebRequest {{ param([switch]$UseBasicParsing,$Uri,$OutFile); [IO.File]::WriteAllText($OutFile,'corrupt archive') }}
        function Expand-CheckedPython {{ throw 'EXTRACTION MUST NOT RUN' }}
        Get-SetupPython -Checked $checked
    """, check=False)
    assert result.returncode != 0 and "SHA256 mismatch" in result.stderr
    assert "EXTRACTION MUST NOT RUN" not in result.stderr
    assert not (target / "tools/python-3.14.10").exists()


@pytest.mark.parametrize("destination", ["C:\\", "C:", "\\\\server\\share\\"])
def test_install_cannot_target_drive_or_network_share_root(payload, destination):
    source, _, _ = payload
    result = run_ps(definitions() + f"Invoke-MembraneSetup -PayloadRoot {ps_quote(source)} -Destination {ps_quote(destination)} -PlanOnly", check=False)
    assert result.returncode != 0
    assert "root" in result.stderr.lower() or "drive-relative" in result.stderr.lower()


def test_archive_traversal_is_rejected_before_any_extraction(payload, tmp_path):
    import zipfile
    archive = tmp_path / "bad-python.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("../escaped.txt", "must not extract")
    target = tmp_path / "runtime"
    result = run_ps(definitions() + f"Expand-CheckedPython -Archive {ps_quote(archive)} -Destination {ps_quote(target)}", check=False)
    assert result.returncode != 0 and "Unsafe" in result.stderr
    assert not target.exists() and not (tmp_path / "escaped.txt").exists()


def test_python_probe_runs_with_windows_powershell_native_argument_marshalling():
    expected = ".".join(map(str, sys.version_info[:3]))
    result = run_ps(definitions() + f"Test-SetupPython -PythonPath {ps_quote(sys.executable)} -ExpectedVersion {ps_quote(expected)} | ConvertTo-Json")
    assert result_json(result.stdout) is True


@pytest.mark.parametrize("port", ["COM0", "COM3; whoami", "COM3 & bad", "COM-2", "COM3 extra"])
def test_flash_rejects_command_like_port_names_without_opening_anything(payload, port):
    _, _, target = payload
    result = run_ps(definitions(FLASH) + f"Get-DryRunFlashPlan -Root {ps_quote(target)} -ComPort {ps_quote(port)}", check=False)
    assert result.returncode != 0 and "Windows COM port" in result.stderr


def prepare_flash_target(target):
    python = target / "tools/.venv/Scripts/python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"never executed")
    firmware = target / "firmware/platformio.ini"
    firmware.parent.mkdir()
    firmware.write_text("[env:esp32-dry-run]\n[env:esp32-relay-bench]\n[env:esp32-physical]", encoding="utf-8")


@pytest.mark.parametrize("selected", [None, "esp32-dry-run", "esp32-relay-bench",
    "ESP32-RELAY-BENCH", "esp32-physical", "ESP32-PHYSICAL"])
def test_flash_plan_selects_only_allowed_target_and_preserves_paths_as_arguments(payload, selected):
    _, _, target = payload
    prepare_flash_target(target)
    parameter = "" if selected is None else " -Firmware " + ps_quote(selected)
    result = run_ps(definitions(FLASH) + f"Invoke-DryRunFlash -Root {ps_quote(target)} -ComPort ' com4 ' -PlanOnly" + parameter)
    plan = json.loads(result.stdout)
    expected = (selected or "esp32-dry-run").lower()
    assert plan["port"] == "COM4" and plan["environment"] == expected
    assert plan["selected_firmware"] == expected
    assert plan["arguments"][plan["arguments"].index("-e") + 1] == expected
    assert plan["arguments"][-3:] == ["upload", "--upload-port", "COM4"]
    assert str(target / "firmware") in plan["arguments"]
    assert plan["commissioning_required"] is (expected == "esp32-physical")
    assert plan["physical_outputs_locked_by_default"] is (expected == "esp32-physical")
    assert "--no-ansi" in plan["arguments"]
    assert not (target / "logs").exists()


@pytest.mark.parametrize("target", ["esp32-physical;whoami", "esp32-relay-bench;whoami", "other"])
def test_flash_rejects_unsupported_firmware_before_any_work(payload, target):
    _, _, destination = payload
    result = run_ps(definitions(FLASH) + f"Invoke-DryRunFlash -Root {ps_quote(destination)} -ComPort COM4 -PlanOnly -Firmware {ps_quote(target)}", check=False)
    assert result.returncode != 0 and "ValidateSet" in result.stderr
    assert not destination.exists()
    # The external script entry point enforces the same allow-list.
    result = run_ps(f"& {ps_quote(FLASH)} -InstallRoot {ps_quote(destination)} -Port COM4 -Plan -Firmware {ps_quote(target)}", check=False)
    assert result.returncode != 0 and "ValidateSet" in result.stderr
    assert not destination.exists()


@pytest.mark.parametrize("selected", ["esp32-dry-run", "esp32-relay-bench", "esp32-physical"])
def test_any_upload_can_be_cancelled_without_executing_the_fake_tool(payload, selected):
    _, _, target = payload
    prepare_flash_target(target)
    result = run_ps(definitions(FLASH) + "function Read-Host { return 'CANCEL' }; " +
        f"Invoke-DryRunFlash -Root {ps_quote(target)} -ComPort COM4 -Firmware {ps_quote(selected)}")
    assert "Cancelled. No board was opened or flashed." in result.stdout
    assert selected in result.stdout
    assert not (target / "logs").exists()
    if selected == "esp32-relay-bench":
        assert "OPERATES REAL RELAYS" in result.stdout
        assert "COM, NO and NC" in result.stdout
    elif selected == "esp32-physical":
        assert "FULL CONTROLLER (SETUP REQUIRED)" in result.stdout
        assert "physical outputs are locked" in result.stdout
        assert "not dry run" in result.stdout
        assert "Dry-run firmware uses generated" not in result.stdout


def test_shortcuts_preserve_default_and_explicitly_select_relay_bench(payload):
    _, _, destination = payload
    result = run_ps(definitions() + f"@(Get-SetupShortcutSpecs -Destination {ps_quote(destination)}) | ConvertTo-Json -Depth 4")
    shortcuts = {item["Name"]: item for item in json.loads(result.stdout)}
    assert set(shortcuts) == {"Membrane Control", "Flash ESP32 dry run", "Flash relay board test",
        "Flash full controller (setup required)", "USB driver help"}
    assert shortcuts["Membrane Control"]["Target"] == str(destination / "MembraneControl.exe")
    assert shortcuts["Membrane Control"]["Arguments"] == ""
    for name, target in [("Flash ESP32 dry run", "esp32-dry-run"), ("Flash relay board test", "esp32-relay-bench"),
        ("Flash full controller (setup required)", "esp32-physical")]:
        spec = shortcuts[name]
        assert spec["Target"].lower().endswith(r"\powershell.exe")
        assert f'-File "{destination / "packaging/flash_dry_run.ps1"}"' in spec["Arguments"]
        assert f'-InstallRoot "{destination}"' in spec["Arguments"]
        assert spec["Arguments"].endswith("-Firmware " + target)
    assert "-Firmware" not in shortcuts["USB driver help"]["Arguments"]
    assert f'-Root "{destination}"' in shortcuts["USB driver help"]["Arguments"]
    assert not destination.exists()  # Metadata inspection creates no actual shortcuts.

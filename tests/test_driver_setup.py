"""Exercise driver helper gates without downloading, elevating or installing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest


REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "packaging" / "install_cp210x.ps1"
CONFIG = REPO / "packaging" / "driver-config.json"
POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(sys.platform != "win32" or not POWERSHELL,
                                reason="Windows PowerShell helper")


def ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(body: str, *, success: bool = True) -> subprocess.CompletedProcess:
    source = f". {ps_quote(HELPER)} -DefinitionsOnly\n$ErrorActionPreference = 'Stop'\n" + body
    result = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-Command", source], capture_output=True, text=True,
                            timeout=30)
    if success:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0, result.stdout
    return result


@pytest.fixture
def install_root(tmp_path):
    root = tmp_path / "installation with spaces"
    (root / "packaging").mkdir(parents=True)
    shutil.copyfile(CONFIG, root / "packaging" / CONFIG.name)
    return root


@pytest.fixture
def package(install_root):
    """Synthetic package: signature command is mocked, never trusted on the PC."""
    stage = install_root / "driver-cache" / "fixture"
    stage.mkdir(parents=True)
    archive = stage / "driver.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("silabser.inf", "[Version]\nCatalogFile=silabser.cat\n")
        z.writestr("silabser.cat", "not a real catalog")
        z.writestr("x64/silabser.sys", "not a real driver")
    config_file = install_root / "packaging" / CONFIG.name
    config = json.loads(config_file.read_text())
    config.update(available=True, sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    config_file.write_text(json.dumps(config))
    return install_root, stage, archive


def test_plan_reports_disabled_driver_without_actions(install_root):
    result = run_ps(f"Invoke-Cp210xHelp -InstallRoot {ps_quote(install_root)} -ShowPlan")
    plan = json.loads(result.stdout)
    assert plan["mode"] == "manual_only"
    assert plan["automatic_install"] is False
    assert plan["archive_available"] is False
    assert plan["sha256"] is None
    assert "403" in plan["reason"]
    assert not (install_root / "driver-cache").exists()


def test_manual_help_defaults_no_and_performs_no_download_or_elevation(install_root):
    result = run_ps("""
function Read-Host { return '' }
function Invoke-WebRequest { throw 'UNEXPECTED DOWNLOAD' }
function Start-Process { throw 'UNEXPECTED PROCESS' }
function Install-Cp210xVerified { throw 'UNEXPECTED INSTALL' }
""" + f"Invoke-Cp210xHelp -InstallRoot {ps_quote(install_root)}")
    assert "no driver is bundled or installed" in result.stdout
    assert "chipset is unknown" in result.stdout
    assert not (install_root / "driver-cache").exists()


def test_manual_browser_action_requires_yes_and_uses_vendor_url(install_root):
    result = run_ps("""
function Read-Host { return 'yes' }
function Start-Process { param($FilePath) Write-Output ('BROWSER:' + $FilePath) }
function Invoke-WebRequest { throw 'UNEXPECTED DOWNLOAD' }
""" + f"Invoke-Cp210xHelp -InstallRoot {ps_quote(install_root)}")
    assert "BROWSER:https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers" in result.stdout


def test_disabled_pin_rejects_elevated_path_before_installer(install_root):
    result = run_ps("""
function Install-Cp210xVerified { throw 'UNEXPECTED INSTALL' }
""" + f"Invoke-Cp210xHelp -InstallRoot {ps_quote(install_root)} -VerifiedStage 'unused'",
                    success=False)
    assert "disabled for this release" in result.stderr
    assert "UNEXPECTED INSTALL" not in result.stderr


@pytest.mark.parametrize("relative", ["../outside", r"folder\..\outside", r"C:\outside", "file:stream"])
def test_paths_cannot_escape_or_use_alternate_streams(install_root, relative):
    result = run_ps(f"Resolve-Cp210xChild {ps_quote(install_root)} {ps_quote(relative)}",
                    success=False)
    assert "must be relative" in result.stderr


def test_hash_pin_is_required_before_reading_archive(install_root):
    result = run_ps(f"""
$config = Get-Cp210xConfiguration {ps_quote(install_root)}
Assert-Cp210xArchive 'file-that-does-not-exist.zip' $config
""", success=False)
    assert "No verified driver archive is pinned" in result.stderr


def test_hash_mismatch_rejects_modified_archive(package):
    root, _, archive = package
    archive.write_bytes(archive.read_bytes() + b"modified")
    result = run_ps(f"""
$config = Get-Cp210xConfiguration {ps_quote(root)}
Assert-Cp210xArchive {ps_quote(archive)} $config
""", success=False)
    assert "SHA256 mismatch" in result.stderr


def test_enabled_but_declined_does_not_download(package):
    root, _, _ = package
    result = run_ps("""
function Read-Host { return 'N' }
function Invoke-WebRequest { throw 'UNEXPECTED DOWNLOAD' }
function Start-Process { throw 'UNEXPECTED ELEVATION' }
""" + f"Invoke-Cp210xHelp -InstallRoot {ps_quote(root)}")
    assert "No driver changes requested" in result.stdout


def test_archive_traversal_rejected_before_extraction(install_root, tmp_path):
    archive = tmp_path / "unsafe.zip"
    destination = install_root / "stage"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../outside.txt", "unsafe")
    result = run_ps(f"Expand-Cp210xArchive {ps_quote(archive)} {ps_quote(destination)}", success=False)
    assert "must be relative" in result.stderr
    assert not (install_root / "outside.txt").exists()


def package_validation(package, status: str, subject: str) -> str:
    root, stage, archive = package
    return f"""
$config = Get-Cp210xConfiguration {ps_quote(root)}
Expand-Cp210xArchive {ps_quote(archive)} {ps_quote(stage / 'expanded')}
function Get-AuthenticodeSignature {{
    [pscustomobject]@{{Status={ps_quote(status)}; SignerCertificate=[pscustomobject]@{{Subject={ps_quote(subject)}}}}}
}}
Assert-Cp210xPackage {ps_quote(stage)} $config
"""


def test_validated_package_requires_pinned_bytes_and_valid_expected_catalog(package):
    result = run_ps(package_validation(package, "Valid",
                    "CN=Microsoft Windows Hardware Compatibility Publisher, O=Microsoft Corporation"))
    assert "silabser.inf" in result.stdout


@pytest.mark.parametrize("status,subject", [
    ("NotTrusted", "CN=Microsoft Windows Hardware Compatibility Publisher"),
    ("NotSigned", "CN=Microsoft Windows Hardware Compatibility Publisher"),
    ("Valid", "CN=Unrelated Publisher"),
])
def test_catalog_signature_or_publisher_failure_stops_package(package, status, subject):
    result = run_ps(package_validation(package, status, subject), success=False)
    assert "catalog signature is not valid" in result.stderr


def test_extracted_bytes_are_rechecked_before_trusting_signature(package):
    root, stage, archive = package
    result = run_ps(f"""
$config = Get-Cp210xConfiguration {ps_quote(root)}
Expand-Cp210xArchive {ps_quote(archive)} {ps_quote(stage / 'expanded')}
Set-Content -LiteralPath {ps_quote(stage / 'expanded' / 'silabser.inf')} -Value 'tampered'
function Get-AuthenticodeSignature {{ throw 'UNEXPECTED SIGNATURE CHECK' }}
Assert-Cp210xPackage {ps_quote(stage)} $config
""", success=False)
    assert "differs from the pinned archive" in result.stderr
    assert "UNEXPECTED SIGNATURE CHECK" not in result.stderr

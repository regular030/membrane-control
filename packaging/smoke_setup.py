"""Check the real setup EXE without installing tools, downloading or opening USB."""
from pathlib import Path
import subprocess
import tempfile
from build_windows import ROOT, package_version


def main():
    executable = ROOT / "dist/release" / f"MembraneControl-Setup-{package_version()}-windows-x64.exe"
    if not executable.is_file():
        raise RuntimeError(f"Setup EXE missing: {executable}")
    with tempfile.TemporaryDirectory(prefix="membrane-setup-plan-") as folder:
        target = Path(folder) / "New PC test with spaces"
        result = subprocess.run([str(executable), "--plan", "--target", str(target)],
                                capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError("Setup plan failed:\n" + result.stdout + result.stderr)
        if target.exists():
            raise RuntimeError("Setup plan unexpectedly created the installation folder.")
        if package_version() not in result.stdout or "3.14.10" not in result.stdout:
            raise RuntimeError("Setup plan omitted its app/Python version.\n" + result.stdout)
        print("Setup EXE plan passed: verified bundled payload; no installation or USB access.")


if __name__ == "__main__":
    main()

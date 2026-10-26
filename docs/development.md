# Development and release

The desktop is Python with PySide6, pyqtgraph, pyserial and NumPy. Firmware is
Arduino C++ built through PlatformIO. Desktop simulation and firmware dry-run
are the starting configurations. Neither establishes physical commissioning.

## Run from source

Use Python 3.12 x64. From the repository root on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e ".[dev]"
.\.venv\Scripts\python.exe -m membrane_control --demo
```

Activate the environment or keep using its explicit interpreter.
`requirements-lock.txt` pins the seven top-level versions used for the initial
build; transitive packages remain resolved by pip. Do not
install application packages into an operator's machine at each startup.

For a clean smoke test with separate sample data:

```powershell
.\.venv\Scripts\python.exe -m membrane_control --demo --data-dir .\work\smoke-data --screenshot .\work\demo.png --quit-after 2
.\.venv\Scripts\python.exe -m pytest
```

On a headless runner, set `QT_QPA_PLATFORM=offscreen`. The app's screenshot
argument is for QA and does not require connected instruments. Confirm the
screenshot visually when changing the UI.
Check whole-interface zoom with Ctrl + -, Ctrl + + / Ctrl + =, and Ctrl + 0
(reset to 100%), including the status bar's displayed percentage. Check both
limits, 60% and 150%, and controls with keyboard focus. Each launch starts at 100%.

See `firmware/README.md` for firmware build, upload and commissioning details.
The default command-line build is:

```powershell
pio run -d firmware -e esp32-dry-run
```

Keep pin maps, input ranges, calibration and process-safe states explicit.
Sample experiment presets must stay labelled as demonstrations until the lab
approves the sequence. Do not put original private attachments, secrets or
operator databases in Git.

## Build the Windows executable

Build on Windows x64 using 64-bit Python; PyInstaller output is platform
specific. Install development dependencies first, then run:

```powershell
.\.venv\Scripts\python.exe packaging\build_windows.py
.\.venv\Scripts\python.exe packaging\smoke_windows.py
```

The build creates a single windowed executable, a portable ZIP, dependency
build metadata and `SHA256SUMS.txt` under `dist/release/`. It bundles the Python
runtime and application libraries. Device drivers are intentionally external.
No installer or administrator access is required for ordinary app execution.

Package resources, including preset JSON, belong inside `membrane_control`
and must be read with `importlib.resources`. The build collects that package's
data. Runtime records must go to the configured data directory, never beside
an extracted one-file executable or inside its temporary resource directory.

`smoke_windows.py` runs the actual EXE in isolated Demo mode, requests a PNG,
checks its dimensions and requires a clean process exit. Also test on a clean
Windows account without Python installed before lab distribution. Verify
device-driver and physical-interface behavior separately on the bench.

## CI and draft releases

The CI workflow runs Python tests on Windows and Ubuntu, builds ESP32 dry-run
firmware, and then builds and smoke-tests the Windows artifact. A failure in
verification prevents the package job from running.

For an authorized release, set the package version, commit the reviewed
changes and tag the commit `v0.1.5` (or the matching next version). The release
workflow checks the version, repeats verification, builds and smoke-tests the
EXE, uploads a workflow artifact and creates a **draft prerelease**. A
maintainer reviews the assets and publishes the prerelease. A private
repository's release assets require an authorized GitHub account.

The release notes must state what was actually tested. Demo-mode software
tests and a firmware compile do not establish safe mains switching, correct
pump voltages, approved chemical recipes, calibrated readings or long-run
physical reliability. Record bench test results before changing that status.

For extended operation, evaluate database growth, graph memory bounds, log
rotation, data backup, USB recovery, sleep settings and planned OS restarts.
Recovery may restore communication and diagnostics but must not resume a run
without an explicit operator action.

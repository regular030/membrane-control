Basu Membrane Control 0.1.0 is a lab prototype of the replacement desktop
application and ESP32 controller firmware.

The Windows executable bundles its Python runtime and application libraries.
Start in Demo mode to explore the dashboard, simulated instruments, recipe
workflow and data recording. USB drivers remain separate vendor components.

Local validation: 58 desktop tests, 16 native firmware tests, both ESP32 builds
and a clean launch/exit of the packaged Windows EXE passed. GitHub-hosted CI
was unavailable for this release; these assets were built and checked locally.
See docs/validation.md in the repository for scope and remaining bench checks.

The physical rig has not been commissioned. The factory firmware build uses
dry-run outputs. Hardware pin assignments, pump interfaces, sensor calibration,
valve safe states and process limits require verification before operation.
CIP, CWF and Fouling examples demonstrate the new software workflow; they are
not approved reproductions of the missing LabVIEW sequence logic.

Download the Windows x64 executable directly, or download and extract the ZIP
for the executable and operating instructions. SHA256SUMS.txt identifies the
published build files. Private repository downloads require GitHub access.

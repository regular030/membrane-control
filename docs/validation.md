# Software validation

## Desktop version 0.1.1

Local checks on Windows 11 x64, 25 October 2026: **72 desktop tests passed**.
The device-status tests cover desktop simulation, disconnected hardware, stale
values, valid zero readings, invalid values, a real scale alongside dry-run
firmware, and unavailable physical output feedback. Qt tests also check the
visible status text and the compact window layout. The packaged EXE is smoke
tested separately for launch, screenshot and clean exit.

The ESP32 firmware is unchanged from 0.1.0. The physical rig remains
uncommissioned. Connected communication, received analog values and physical
actuator feedback are deliberately different statuses.

## Version 0.1.0 baseline

Local checks completed on Windows 11 x64, 25 October 2026.

| Check | Result |
| --- | --- |
| Desktop unit, serial-worker and Qt integration tests | 58 passed |
| Firmware native tests with instrument/GPIO doubles | 16 passed |
| ESP32 factory dry-run build | Passed |
| ESP32 commissioning-gated physical build | Passed |
| Source application Demo startup and screenshot | Passed, clean exit |
| Actual packaged Windows EXE Demo startup and screenshot | Passed, 1360 x 940 PNG and clean exit |

The packaged application was built with Python 3.12.14, PyInstaller 6.22.3,
PySide6 6.12.0, pyqtgraph 0.14.0, NumPy 2.5.4 and pyserial 3.5. PlatformIO
6.2.0 built the firmware with the versions pinned in `firmware/platformio.ini`.

Desktop checks include sequence timing, validation, mass conversion, record
export, Stop acknowledgement, stale readings, rejected/dropped Stop commands,
storage failures, pending-command cancellation, custom presets and bounded
chart buffers. A failed Stop causes heartbeat withdrawal rather than indefinite
retries. Multiple simultaneous faults cannot extend its acknowledgement deadline.

Firmware checks include heartbeat timeout, pressure limit/freshness, clock
rollover, strict JSON types, atomic recipe replacement, DAC failure restoring
safe valve outputs, and zero GPIO/I2C access in simulation or with an unverified
physical profile. No board was flashed for these checks.

GitHub-hosted workflows are included, but could not execute for this first
release because Actions was unavailable on the repository account. The first
release assets were built and checked locally. This is not a claim of green
GitHub CI or a clean-machine installation test.

## Still required on the bench

- Verify the actual board pin map, relay polarity and startup/reset behavior.
- Validate the pump model, connector returns, DAC voltages and stop contact.
- Verify protected input wiring and sensor calibration against known signals.
- Confirm balance USB settings and real output lines.
- Obtain approved CIP/CWF/Fouling sequences and process shutdown states.
- Test the enclosed valve assembly, actual load switching and independent shutdown.
- Run a clean Windows installation check and an extended physical recording test.

The firmware's physical profile remains unverified. Compilation does not
establish electrical compatibility, correct sensor readings or 24/7 reliability.

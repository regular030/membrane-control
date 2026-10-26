# Software validation

## Desktop version 0.1.5

Native interface zoom, checked locally on Windows 11 x64, 26 October 2026:

- All 126 desktop tests passed, including 32 Qt UI tests.
- The packaged Windows EXE opened, produced a 1360 x 940 screenshot and exited cleanly.
- Ctrl + -, Ctrl + + / =, shifted plus/equal variants and Ctrl + 0 were tested
  with focus in text fields, table cells, the activity log and a plot.
- Font sizes, layout spacing, control sizes, table columns/rows and native plot
  labels scale from fixed 100% baselines. Repeated zoom/reset does not accumulate
  rounding changes. New/imported rows and refreshing status styles keep the zoom.
- Tests confirm zoom sends no controller commands and preserves experiment
  settings, recipe values and displayed data. Stop remains available during a run.
- All five tabs were checked at 60%, 80% and 100% across 1360 x 940,
  1080 x 760 and 960 x 680 windows, plus 150% at 1360 x 940. Page scrolling
  keeps larger content reachable. Zoom does not force the outer window to resize.
- Warm zoom changes measured approximately 92-291 ms in local QA under concurrent
  test load. These measurements are specific to this machine.

Zoom starts at 100% each launch and ranges from 60% to 150% in 10% steps.
Firmware is unchanged from 0.1.3. No physical equipment was operated for these checks.

## Desktop version 0.1.4

Naming update, checked locally on Windows 11 x64, 25 October 2026:

- All 116 desktop tests passed.
- The newly named `MembraneControl-0.1.4-windows-x64.exe` opened, produced a
  1360 x 940 screenshot and exited cleanly.
- The Help credit to Dr. Onita Basu's research lab was visually reviewed at
  1360 x 940 and 1080 x 760, including scrolling to the bottom.
- The existing operator data location and firmware protocol identity were
  retained for compatibility. Firmware remains at 0.1.3 with the results below.

No board was flashed and no physical rig was exercised for this naming update.

## Desktop and firmware version 0.1.3

Local review on Windows 11 x64, 25 October 2026:

| Check | Result |
| --- | --- |
| Desktop controller, transport, storage, model and Qt tests | 116 passed |
| Firmware native tests | 18 passed |
| ESP32 dry-run build | Passed, 322897 bytes flash / 32800 bytes RAM |
| ESP32 commissioning-gated physical build | Passed, 331141 bytes flash / 32800 bytes RAM |
| All five UI tabs at 1360 x 940 and 1080 x 760 | Visually reviewed, with scrolling checked |
| Actual packaged Windows EXE launch | Passed, 1360 x 940 PNG and clean exit |
| Relative documentation links | Resolve in repository; portable guides use online links for source-only documents |

The review fixed pending-manual-command races, incorrect early/completed run
statuses, invalid acknowledgement handling, stale manual control and incomplete
CSV exports. Tests include delayed acknowledgement of a very short run,
unexpected early idle, detectable controller resets, uptime rollover and changed
hardware-verification flags. Uptime alone is not a unique boot-session identifier.
The simulator checks watchdog deadlines before accepting a newly arrived command.
Firmware rejects malformed JSON and invalid Unicode before decoding commands.

The first-use review added Help, Start here, explicit blocked-start reasons,
matching preset names and clearer manual pump commands. CSV export is disabled
while operating so a synchronous export cannot block control heartbeats.
The portable ZIP includes the short guide and operator instructions.

These were local software checks. No board was flashed, no real serial connection
was exercised and no physical wiring or loads were tested. GitHub-hosted Actions
remain unavailable for this account. Clean-machine Windows installation and
extended operation remain unverified. See the bench checklist below.

## Desktop version 0.1.2

Local checks on Windows 11 x64, 25 October 2026: **73 desktop tests passed**.
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

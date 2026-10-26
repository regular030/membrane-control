# Software validation

Latest hardware update, 26 October 2026: the user now identifies the balance as
an **Adam Nimbus NBL 8201e**, uses its USB-B I/O connection, and confirms a second
Windows COM port appears. The user reports that no weight arrives; balance-side
serial settings will be checked later. Older
release records below describe the green RS232 adapter used at that time. The
Cole-Parmer drive is now identified as **75211-30, 60-3600 RPM, 0.1 HP**. Its
manufacturer-authored manual and DB15 diagram confirm 0-10 V command 1(+)/3(-),
0-10 V feedback 9(+)/5(-), and start/stop contact 10/12. Actual mode, harness
continuity, conditioning and calibration remain unverified. No physical outputs
were operated to establish these documentation findings.

## PWM converter support, version 0.1.13

Checked locally on Windows x64, 26 October 2026:

- All **421 desktop/packaging tests** passed with native exit 0. After adding
  the converter source/example and handoff to the required release payload,
  all **25 focused firmware/setup packaging tests** passed again.
- All **67 native firmware tests** passed, including 18 new PWM cases. Checks
  cover invalid/unreviewed configuration, pin conflicts, full-scale duty,
  driver failures, zero initialization, independent contact ordering, measured
  settling, stop/fault cancellation, and source-specific I2C behavior.
- All four main ESP32 targets compiled. The new source-only converter bench
  example also compiled separately with the pinned ESP32 toolchain. It was
  reviewed for bounded input parsing, five-second limits, one test per explicit
  confirmation, and GPIO25-only output without relay or pump-contact control.
- The production PWM driver and its delayed RUN activation received a separate
  code review. RUN is considered only after a current controller safety tick;
  a serial acknowledgement cannot release the contact. Factory profiles retain
  their unverified state. The measured settling interval has no usable default.
- Both GitHub workflows pass local actionlint. The repository remains public;
  local commissioned profiles and operator data are excluded from release files.
- The final Windows EXE launched in isolated demo mode, produced a 1360 x 940
  screenshot and exited cleanly. The Setup EXE verified its embedded payload
  using its read-only plan without installation, downloads or USB access. The
  firmware ZIP contains four merged images plus complete sources, including
  the separate converter bench project and profile template. SHA256 manifests
  cover the release assets. Hosted Actions remain blocked by the existing
  account billing lock, so these release files were built and checked locally.

No hardware or serial port was operated. The selected EC Buying converter has
not arrived, so its output voltage, settling, supply behavior and response to
lost PWM have not been measured. The pump harness returns, isolated stop
interface, protected/calibrated analog inputs and complete rig acceptance remain
outstanding. Balance USB-B serial settings and receipt of mass remain unresolved.

## Sensor-free valve test, version 0.1.12

Checked locally on Windows x64, 26 October 2026:

- All **421 desktop/packaging tests** passed in one process with native exit 0
  and no warnings in the final run. The added checks cover dedicated identity,
  locked profiles, session attestations, matching acknowledgements, stale data,
  restart detection, single pulses, no queued output, window/Qt shutdown and
  COM-port ownership. Normal controller identity rejects valve-test firmware
  and releases its port with a useful next step.
- All **49 native firmware tests** passed, including 16 new valve-test cases.
  All four ESP32 targets built successfully. The factory valve profile is locked
  and does not access GPIO; native mocks also check reviewed mapping, polarity,
  unused-bit preservation, pulse deadline, watchdog expiry and forbidden commands.
- Setup/flash plan tests cover all four target selections, explicit valve-test
  commissioning status, cancellation, target injection rejection, shortcut
  arguments and bundle completeness. Local commissioned profile headers are
  excluded, and factory-image packaging rejects commissioned profile macros.
- The new dialog was checked with fake ports at a compact size and zoomed layouts.
  Seven named 500 ms commands, unavailable sensors, isolated pump requirements,
  guide link and visible Stop are separate from experiment controls. Displayed
  states are commands, not measured valve or relay-contact positions.

No physical rig or serial port was operated. Kunshpreet reports All LOW leaves
the relays off and All HIGH turns them on. The individual raw-bit to valve map,
safe reset/OE response, mains load installation and valve-only reviewed profile
remain outstanding. The scale has a USB-B COM connection but no confirmed mass
stream. Pump DAC, protected inputs and corrected return references remain to be
installed and commissioned. The software watchdog is not an independent safety
system.

The final Windows EXE produced a 1360 x 940 demo screenshot and exited cleanly.
The setup EXE verified its embedded payload and read-only plan without installing,
downloading dependencies or opening USB. Four merged ESP32 images were verified
against their generated component addresses/bytes and bundled with complete
sources; SHA256 manifests cover the release files. Both workflows pass actionlint.
Hosted Actions remain blocked by the existing account billing lock, so this
release was built and verified locally.

## Live runtime table, version 0.1.11

Checked locally on Windows 11 x64, 26 October 2026:

- All 338 desktop/packaging tests passed with native process exit code 0.
  New checks cover exact database/sample timestamps, detached records, sample
  intervals, final samples, failed writes producing no display event, bounded
  memory and compatibility of old CSV records.
- UI checks cover recorded rows only, unavailable measurements, all seven
  commanded valve states, the 1,000-row limit, Follow latest and retained scroll
  position, new-run clearing, completed-run retention and final samples.
- A simulated run was visually inspected at 1360 x 940 with seven live rows.
  Time, runtime, cycle/step and the main measurements are placed first; other
  measurements and statuses remain accessible through horizontal scrolling.
  Existing compact-window, scrolling and zoom checks passed.
- The packaged application launched, produced its screenshot and exited cleanly.
  The setup EXE authenticated its embedded payload and read-only plan without
  installation, dependency downloads or serial-port access.
- Firmware logic is unchanged from 0.1.10. Its compiled images were reused only
  after the source hashes matched saved PlatformIO build metadata; merged
  images were verified against component bytes. The prior 33 native firmware
  tests and all three target builds passed as recorded below.
- Both workflows pass local actionlint. Hosted Actions remain blocked by the
  account billing lock; release files were built and checked locally.

No hardware was operated or flashed. The scale is still connected through an
unidentified green RS232 adapter, and the lab PC has not exposed its COM port.
The Nimbus native-USB driver applies to the balance's USB-B I/O path instead.
Wiring, calibration and complete physical rig commissioning remain outstanding.

## Desired flow and complete firmware bundle, version 0.1.10

Checked locally on Windows 11 x64, 26 October 2026:

- All 320 desktop/packaging tests passed. Targets persist through preset
  save/import, are independently graphed and exported, and cannot change during
  active operations. Firmware commands omit the comparison target. Old recipes
  and recorded samples remain readable without fabricating measured flow.
- Compact-window checks cover unclipped valve and target controls, scrolling
  and zoom. Port-list tests cover adapters plugged in after startup, preserving
  selections and leaving genuinely missing Windows devices absent.
- An initial combined Qt test process passed its assertions but failed during
  native finalization. The test harness now owns one QApplication per session
  and disposes plot widgets, scenes and windows through normal Qt deferred
  deletion while Qt is alive. It does not suppress process exits or alter app
  shutdown. Both the normal source app and packaged app exited cleanly.
- All 33 native firmware safety tests passed and all three ESP32 targets built.
  PlatformIO metadata supplied component offsets of 0x1000, 0x8000, 0xe000 and
  0x10000. Each merged factory image at 0x0 matched its component bytes exactly.
- The firmware ZIP's source/config/helper/test files, per-target manifests,
  component/factory images and checksums were verified. All target manifests
  report hardware_verified=false; the physical factory profile remains locked.
- The regular EXE produced a 1360 x 940 PNG and exited cleanly. The real setup
  EXE authenticated its payload and installation plan without installing tools
  or opening USB. Its payload and the portable ZIP include the firmware bundle.
- Both workflows pass local actionlint. Hosted Actions remain blocked by the
  account billing lock; published binaries were built and checked locally.

No physical board, relay, pump or sensor was operated in these checks. The
scale's adapter has not been identified: the lab PC currently exposes only the
ESP32 port. Interface wiring, calibration, a clean-PC installation and complete
rig commissioning still require on-site verification.

## Serial shutdown and relay startup, version 0.1.9

Checked locally on Windows 11 x64, 26 October 2026:

- All 255 desktop tests passed. New regressions cover blocked reads and writes,
  cancellation fallback, late serial opens, concurrent shutdown, discarded queued
  traffic, bounded STOP attempts and immediate reopening of an exclusive fake
  port. No real serial device was opened by these tests.
- A reproducer confirmed that the previous Qt event-loop exit path could leave
  the bench transport open and its timers active. Main-window, modal-dialog,
  direct event-loop exit and exception cleanup paths now have regression checks.
- Pre-HELLO stale status and framing errors no longer abort identification.
  Tests cover bounded startup retries, delayed replies and strict checks after
  identity is established. No relay authorization is granted by a retry.
- The packaged app launched, produced a 1360 x 940 screenshot and exited cleanly.
  The setup EXE authenticated its payload and read-only installation plan without
  downloading dependencies, installing tools or opening USB.
- Both workflows pass actionlint with optional ShellCheck/Pyflakes disabled.
  GitHub's failed 0.1.8 tag/main check annotations report an account billing lock;
  their jobs executed no steps. Version 0.1.9 release files were built locally.

Firmware is unchanged from version 0.1.8. Its 33 native tests and all three
ESP32 target builds passed as recorded below. The user supplied a successful
relay-bench upload log, but no physical relay or complete rig was operated in
these release checks. A separate clean-PC installation remains unverified.

If a native driver blocks inside its open call beyond the shutdown deadline,
the transport reports that limitation. Once the open returns, its worker closes
the handle without sending commands. Software cannot promise to interrupt an
unresponsive native driver. The fake blocked-read/write and open-race cases do
verify prompt cleanup for their exercised paths.

## Real unloaded relay-board test, version 0.1.8

Checked locally on Windows 11 x64, 26 October 2026:

- All 221 desktop tests passed, including the existing UI/zoom checks, 38 new
  relay-bench session/UI cases, the separate-identity rejection case and updated
  PowerShell upload/setup checks.
- All 33 native firmware tests passed: 18 experiment-controller tests and 15 new
  relay-bench cases covering both baseline polarities, all 16 bits, GPIO ordering,
  strict JSON fields, bounded timing, late heartbeats, ready-state lease expiry,
  probe IDs, reset/STOP and clock rollover.
- ESP32 builds passed for dry run, commissioning-gated physical operation and
  relay bench. The new bench target uses 294945 bytes flash and 29744 bytes RAM;
  it selects only its own main source and has no Wire dependency.
- The bench dialog was visually reviewed at 850 x 720 and 700 x 650 using a fake
  serial-protocol device. All 16 bit controls, rest-pattern observations and Stop
  remain reachable. Its real transport was not opened during these checks.
- The app EXE launched, produced a 1360 x 940 screenshot and exited cleanly.
  The actual setup EXE verified its bundled payload and read-only plan without
  creating an install target, downloading tools or opening USB.
- Both workflow files pass actionlint with optional ShellCheck/Pyflakes disabled.
- Before making the repository public at the user's request, reachable Git
  history was checked for credential patterns, private attachments and operator
  data. No blocker was found. Local untracked data remains excluded from Git.

The user reported successful dry-run flashing and app communication on the lab
board before this update. That establishes the UART path, not relay mapping or
safe physical operation. No new firmware was uploaded or relay operated by these
release checks. The production profile remains unverified and cannot be unlocked
through the bench tool. Full physical rig commissioning is still outstanding.

## Fresh-PC setup, version 0.1.7

Checked locally on Windows 11 x64, 26 October 2026:

- All 173 software tests passed: the existing 130 desktop tests and 43 setup,
  driver-helper and bundle checks. External installs, downloads and serial ports
  are mocked in the setup unit tests.
- The real setup EXE compiled with the Windows .NET Framework compiler. Its
  `--plan` smoke check authenticated the embedded payload, accepted a target
  containing spaces and left that install target absent. No tools were installed
  or downloaded by this check.
- The regular app EXE opened, produced a 1360 x 940 PNG and exited cleanly.
- The official full PythonCore 3.14.10 x64 ZIP matched its published SHA256. An
  isolated runtime created a venv, installed PlatformIO 6.2.0 and pyserial 3.5,
  and freshly compiled 48 firmware/framework translation units. The dry-run build
  passed: 323057 bytes flash, 32800 bytes RAM. A native PowerShell 5.1 interpreter
  probe was also exercised, including the fix for its argument-quoting behavior.
- Python and pip downloads succeeded. A fresh compiler download hit a PlatformIO
  mirror DNS failure. The compile reused cached package archives only after their
  SHA256 and sizes matched the live publisher metadata. A completely fresh
  network installation and a separate clean Windows PC remain unverified.
- Silicon Labs' driver archive returned HTTP 403. Automatic driver installation
  stays disabled, with no invented hash or unsigned fallback. The helper provides
  official guidance. Its tests cover disabled downloads and validation failures.
- Both GitHub workflow files pass local actionlint with optional ShellCheck and
  Pyflakes integration disabled. Hosted Actions remain blocked by account billing.

Setup never uploads firmware. No real serial port, board or physical rig was
operated during these software checks. The controller firmware source is unchanged.

## Desktop version 0.1.6

Serial disconnect handling, checked locally on Windows 11 x64, 26 October 2026:

- All 130 desktop tests passed, including the unchanged Qt UI coverage.
- New regressions exercise a serial port that fails to open with access denied,
  a running controller unplug, preserved original errors over 100 later ticks,
  one-time terminal error reporting, rejected sends to closed workers and a slow
  port opening that still accepts queued startup commands.
- Failed transports detach immediately. Idle failures issue no futile STOP and
  accumulate no heartbeat queue. Active failures fault and withdraw heartbeats.
- The packaged Windows EXE opened, produced a 1360 x 940 screenshot and exited cleanly.
- Firmware setup instructions now cover a fresh Windows clone without `.venv`
  and an external USB-to-UART adapter on the 16-relay board.

Serial tests use doubles; no real serial port was opened for these checks.
Firmware is unchanged from 0.1.3. No board was flashed or physical rig operated.

## Automatic GitHub builds, 26 October 2026

- Both workflow YAML files pass actionlint 1.7.12. Optional ShellCheck and
  Pyflakes integration were unavailable and disabled for this local check.
- The publishing shell script passes Bash syntax checking. Local mocked runs
  confirm successful current-main publication, skipped stale commits and refusal
  to publish an asset whose checksum changed. Windows CRLF checksum files are supported.
- Automatic main builds publish only after the existing desktop, firmware and
  packaged-EXE checks succeed. Each development release points to its tested commit.
- GitHub's latest hosted run did not start any jobs. Its annotation reports recent
  account payment failures or a spending limit that needs increasing. This account
  issue prevents an end-to-end hosted build until resolved in GitHub Billing & plans.

No application or firmware code changed in this workflow update.

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

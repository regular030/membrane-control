Membrane Control 0.1.10 adds desired-flow comparison and a full ESP32 firmware bundle, and includes the serial-port shutdown and relay-startup fixes from 0.1.9.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download

For an app-only update, download **MembraneControl-0.1.10-windows-x64.exe** or the matching portable ZIP under **Assets**. Close the old app first. **MembraneControl-Setup-0.1.10-windows-x64.exe** also updates installed shortcuts and flashing scripts, and can set up a new PC without an existing Python installation. Initial tool downloads require internet. USB drivers remain separate.

**These desktop fixes do not require reflashing the existing relay-test firmware.** After an upload through a TX/RX/GND-only adapter, release IO0/BOOT and briefly press EN/RESET before connecting. The uploader's "Hard resetting via RTS pin" message does not establish that such an adapter reset the board.

## Desired flow and scale connections

Set **Desired flow (mL/min)** on Dashboard with **Apply target**, or in Sequence editor. It saves with presets, appears as a labelled dashed curve alongside measured flow, and is retained in run records and CSV exports. It is a comparison target, not an automatic pump-speed controller. Pump settings remain explicit percentages until the interface and flow calibration are established.

Opening **Connections and settings** refreshes serial-port lists while preserving selections. The Balance panel explains that the scale can appear under its USB-to-RS232 adapter's name. If Windows shows only the ESP32 port, the scale adapter's connection/driver still needs checking; the app cannot create the missing port.

## Full firmware included

**MembraneControl-Firmware-0.1.10-esp32.zip** includes full controller source and compiled images for dry run, relay bench and commissioning-gated physical control, with flash offsets and checksums. The portable app ZIP and Setup also include this archive. Setup adds **Flash full controller (setup required)** and prepares all three targets without uploading.

The full controller includes sensor/ADC acquisition, pump DAC interfaces, timed valve sequences, telemetry, pressure protection and the communication watchdog. Its shipped hardware profile remains unverified and physical operation stays locked. The old Arduino/LabVIEW source does not establish the missing electrical interfaces. See [full firmware instructions](https://github.com/regular030/membrane-control/blob/v0.1.10/docs/full-firmware.md).

## Serial and layout fixes

- Closing the main window, relay-test dialog or Qt event loop now stops connection timers and closes controller, balance and relay-test transports. Cleanup also runs after the event loop returns.
- Serial shutdown cancels blocked I/O, discards queued traffic and closes the handle. Planned controller shutdown can attempt one bounded STOP write before closing; this is not an acknowledgement that hardware stopped. A connection that finishes opening late cannot send stale commands.
- Relay-test startup ignores stale status and boot framing messages before a valid identity response. HELLO retries are bounded to eight seconds. Identity, mode, status and heartbeat checks stay strict after identification.
- Connection timeouts now explain the IO0/EN reset procedure. Setup and flashing scripts disable ANSI formatting to avoid visible escape-code clutter.
- Compact windows use their controls' natural minimum height, keeping the valve buttons and new flow controls readable while scrolling and zooming.

COM4 can remain listed in Device Manager while the USB adapter is plugged in. Releasing the port means another program can open it, not that the adapter disappears.

## Pump wiring clarification

The DB15 connector does not determine the signal range. Pump **VOUT is feedback from the pump**, to be read through a protected/scaled ADC input. A DAC would generate the command **into the pump's VIN/speed input**, if its exact model and selected mode confirm a 0-10 V input. The photographed tags describe 0-10 V, but the installed drive model still needs confirmation. See the [pump interface notes](https://github.com/regular030/membrane-control/blob/v0.1.10/hardware/pump-interface.md).

## Validation and limits

All **320 desktop and packaging tests** passed, including blocked-I/O, late-open, immediate fake-port reopening, application-exit, desired-flow persistence and firmware-bundle integrity checks. The packaged app launched and exited cleanly, and the setup EXE passed its read-only payload/plan check. Both workflows pass local actionlint. See the [validation record](https://github.com/regular030/membrane-control/blob/v0.1.10/docs/validation.md).

All **33 native firmware tests** and fresh builds of all three ESP32 targets passed. Merged image bytes were checked against their component images and actual PlatformIO flash offsets. No board was flashed or physical rig operated during these release checks. A clean-PC installation and physical commissioning remain outstanding. Hosted GitHub Actions are blocked before executing steps by the account's billing lock; these release files were built and checked locally.

The repository remains public at the user's request. The main screen and relay-test window retain the credit to Dr. Onita Basu's lab. The relay-test tool cannot run experiments or replace the missing protected sensor and pump interfaces.

[Relay board test](https://github.com/regular030/membrane-control/blob/v0.1.10/docs/relay-board-test.md) |
[New-PC setup](https://github.com/regular030/membrane-control/blob/v0.1.10/docs/setup-new-pc.md)

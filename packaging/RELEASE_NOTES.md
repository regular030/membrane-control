Membrane Control 0.1.9 fixes serial-port shutdown and relay-test connection startup.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download

For an app-only update, download **MembraneControl-0.1.9-windows-x64.exe** or the matching portable ZIP under **Assets**. Close the old app first. **MembraneControl-Setup-0.1.9-windows-x64.exe** also updates installed shortcuts and flashing scripts, and can set up a new PC without an existing Python installation. Initial tool downloads require internet. USB drivers remain separate.

**These desktop fixes do not require reflashing the existing relay-test firmware.** After an upload through a TX/RX/GND-only adapter, release IO0/BOOT and briefly press EN/RESET before connecting. The uploader's "Hard resetting via RTS pin" message does not establish that such an adapter reset the board.

## Fixes

- Closing the main window, relay-test dialog or Qt event loop now stops connection timers and closes controller, balance and relay-test transports. Cleanup also runs after the event loop returns.
- Serial shutdown cancels blocked I/O, discards queued traffic and closes the handle. Planned controller shutdown can attempt one bounded STOP write before closing; this is not an acknowledgement that hardware stopped. A connection that finishes opening late cannot send stale commands.
- Relay-test startup ignores stale status and boot framing messages before a valid identity response. HELLO retries are bounded to eight seconds. Identity, mode, status and heartbeat checks stay strict after identification.
- Connection timeouts now explain the IO0/EN reset procedure. Setup and flashing scripts disable ANSI formatting to avoid visible escape-code clutter.

COM4 can remain listed in Device Manager while the USB adapter is plugged in. Releasing the port means another program can open it, not that the adapter disappears.

## Pump wiring clarification

The DB15 connector does not determine the signal range. Pump **VOUT is feedback from the pump**, to be read through a protected/scaled ADC input. A DAC would generate the command **into the pump's VIN/speed input**, if its exact model and selected mode confirm a 0-10 V input. The photographed tags describe 0-10 V, but the installed drive model still needs confirmation. See the [pump interface notes](https://github.com/regular030/membrane-control/blob/v0.1.9/hardware/pump-interface.md).

## Validation and limits

All **255 desktop tests** passed, including blocked-I/O, late-open, immediate fake-port reopening and application-exit regressions. The packaged app launched and exited cleanly, and the setup EXE passed its read-only payload/plan check. Both workflows pass local actionlint. See the [validation record](https://github.com/regular030/membrane-control/blob/v0.1.9/docs/validation.md).

Firmware is unchanged from 0.1.8, whose 33 native tests and three ESP32 builds passed. No board was flashed or physical rig operated during these release checks. A clean-PC installation and physical commissioning remain outstanding. Hosted GitHub Actions are blocked before executing steps by the account's billing lock; these release files were built and checked locally.

The repository remains public at the user's request. The main screen and relay-test window retain the credit to Dr. Onita Basu's lab. The relay-test tool cannot run experiments or replace the missing protected sensor and pump interfaces.

[Relay board test](https://github.com/regular030/membrane-control/blob/v0.1.9/docs/relay-board-test.md) |
[New-PC setup](https://github.com/regular030/membrane-control/blob/v0.1.9/docs/setup-new-pc.md)

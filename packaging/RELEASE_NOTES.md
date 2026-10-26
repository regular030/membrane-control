Membrane Control 0.1.12 adds a separate valve test that does not need sensors.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download

Close the old app and download **MembraneControl-0.1.12-windows-x64.exe** for an app-only update, or **MembraneControl-Setup-0.1.12-windows-x64.exe** for installed shortcuts and new-PC setup. Python is bundled with the app; Setup also prepares the firmware tools. Valve testing needs the matching dedicated firmware and a reviewed valve-only profile.

## Valve tests without sensors

Under **Connections and settings**, **1. Bare relay board test** identifies the unloaded board's polarity and channel mapping. **2. Valve test (no sensors)** is a separate window with seven V1-V7 **Energize 500 ms** buttons, a visible Stop and session checks. It requires no pressure sensor, flow sensor, scale or pump DAC. The pump must be physically isolated.

The factory valve-test image is **locked** until a maintainer compiles the measured relay mapping, rest word and reviewed reset/OE and load behavior into its separate profile. All LOW off / All HIGH on is now recorded as the user's observed polarity; individual valve mapping and load-wiring checks remain outstanding. No screenshot, checkbox or upload establishes safe physical operation. See the [valve test handoff](https://github.com/regular030/membrane-control/blob/v0.1.12/docs/valve-test.md).

The firmware allows one bounded pulse at a time and ends the session after heartbeat loss. Wrong firmware, mismatched/stale replies, reset, Stop, disconnect or app close cannot automatically rearm. The original bare-board and production controller gates remain separate. Status describes commands, not measured valve position. The live runtime table, presets and desired-flow comparison remain available in the normal application.

## Firmware and scale connection

**MembraneControl-Firmware-0.1.12-esp32.zip** includes complete sources and four compiled targets: dry-run, bare relay bench, valve test and physical controller, with offsets and checksums. The portable ZIP and Setup include it. Setup adds **Flash valve test (setup required)**. Custom reviewed local profiles are excluded from public source bundles, and the factory-image packager rejects builds containing commissioned profile macros. Both physical profiles remain locked by default.

The pump handoff covers DFR0971/GP8403 wiring, DB15 command 1/3, feedback 9/5 and separate start/stop contact 10/12. It explicitly distinguishes signal returns and the module's non-isolated ground. A verified manufacturer purchase link is supplied; an exact compatible Amazon listing could not be confirmed. The scale is now connected by USB-B I/O and has a second COM port, but weight receipt remains unresolved; the user will check its serial settings later. See the [balance guide](https://github.com/regular030/membrane-control/blob/v0.1.12/hardware/balance-usb-setup.md).

## Validation

All **421 desktop/packaging tests** and **49 native firmware tests** passed. All four ESP32 targets build. Further results are recorded in the [validation record](https://github.com/regular030/membrane-control/blob/v0.1.12/docs/validation.md). No physical rig was operated for this release. A separate clean-PC installation and rig commissioning remain outstanding. Hosted GitHub Actions remain blocked by the account billing lock; these binaries are built and checked locally.

Membrane Control 0.1.8 adds real relay-board test firmware and a separate desktop test window for the unloaded 16-channel board.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download

Under **Assets**, download **MembraneControl-Setup-0.1.8-windows-x64.exe** and double-click it. Close the old app before updating. Setup installs the app, Python, PlatformIO and the ESP32 compiler/framework, and adds a **Flash relay board test** shortcut. No existing Python installation is needed; first-time dependency downloads require internet.

## Test the real relay board

With every contact terminal disconnected from loads, flash the new relay-board test target. Open the updated app, turn Simulation mode off and choose **Connections and settings > Relay board test**. The separate window checks the test firmware identity, lets you test an off/rest pattern and requires your observation before enabling one 500 ms raw-bit pulse at a time. Record which printed relay number changes for bits 0-15.

This target drives real outputs through the candidate GPIO14/13/12/5 shift-register interface. It does not touch GPIO4, I2C, the pump or sensors. A two-second firmware pulse limit and one-second heartbeat lease bound operation; Stop, a new connection and reset clear the baseline confirmation. Status describes commanded outputs, not contact feedback. The first rest-pattern test can energize multiple bare relays, so no valve or pump wiring may be attached.

The main screen and bench window credit **Dr. Onita Basu's lab at Carleton University**. The repository is now public at the user's request. The regular **MembraneControl-0.1.8-windows-x64.exe** and matching portable ZIP remain available for app-only updates. USB drivers remain separate.

## Validation

All **221 desktop tests** and **33 native firmware tests** passed. All three ESP32 targets compiled. The app EXE and setup EXE were checked locally; the bench window was visually reviewed with a simulated protocol double. See the [validation record](https://github.com/regular030/membrane-control/blob/v0.1.8/docs/validation.md). A full setup on a separate clean PC and the new firmware's physical relay behavior remain to be checked.

No board was flashed or physical rig operated during these release checks. The dry-run target remains the default, and the experiment controller's existing physical safeguards remain required. The relay bench target cannot run recipes or replace the missing protected sensor and pump interfaces.

[Relay board test](https://github.com/regular030/membrane-control/blob/v0.1.8/docs/relay-board-test.md) |
[New-PC setup](https://github.com/regular030/membrane-control/blob/v0.1.8/docs/setup-new-pc.md) |
[Firmware setup](https://github.com/regular030/membrane-control/blob/v0.1.8/firmware/README.md)

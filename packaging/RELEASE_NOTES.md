Membrane Control 0.1.7 adds a one-file Windows setup for a new PC, including Python and the ESP32 firmware tools.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download

Under **Assets**, download **MembraneControl-Setup-0.1.7-windows-x64.exe** and double-click it. No existing Python installation is needed. Internet is required for the official Python runtime and firmware dependencies. Setup installs the app, its own Python, PlatformIO and the ESP32 compiler/framework, and creates app and dry-run flashing shortcuts.

## Setup behavior

Setup runs for the current user. It verifies bundled file hashes and the official Python ZIP before use, records progress in a log, and prebuilds the dry-run firmware without opening a serial port. It does not register a global Python installation or change PATH. Firmware upload remains a separate action on the COM port chosen by the operator.

USB drivers remain separate. The optional USB driver help shortcut provides official guidance; automatic CP210x driver installation is disabled because the vendor archive was unavailable for verification. The scale adapter's chipset must be identified before choosing its driver.

The regular **MembraneControl-0.1.7-windows-x64.exe** and matching ZIP remain available for app-only use. Those downloads already bundle the app's Python runtime and libraries.

## Validation

All **173 software tests passed**. The app EXE passed its launch check, and the actual setup EXE verified its embedded payload and read-only setup plan. A dedicated Python 3.14.10 runtime installed PlatformIO 6.2.0 and compiled dry-run firmware. Fresh compiler download encountered a package-mirror DNS error; the compile used cached archives checked against the publisher's SHA256 values. A complete installation on a clean separate PC remains to be checked. See the [validation record](https://github.com/regular030/membrane-control/blob/v0.1.7/docs/validation.md).

ESP32 firmware source is unchanged from 0.1.3. No board was flashed or physical rig tested for this update. Factory firmware remains a dry run, with physical operation awaiting commissioning. GitHub-hosted Actions remain blocked by the account's billing/spending-limit error; release checks run locally.

[New-PC setup](https://github.com/regular030/membrane-control/blob/v0.1.7/docs/setup-new-pc.md) |
[Installation](https://github.com/regular030/membrane-control/blob/v0.1.7/docs/installation.md) |
[Firmware setup and flashing](https://github.com/regular030/membrane-control/blob/v0.1.7/firmware/README.md)

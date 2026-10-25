Membrane Control 0.1.4 updates the project and application name.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download

Under **Assets**, download **MembraneControl-0.1.4-windows-x64.exe** and double-click it. The matching app ZIP includes the EXE and short guides. Leave **Simulation mode** checked and click **Start here** for a practice run. Python and application libraries are bundled.

## Changes

- Renamed the private repository to `regular030/membrane-control`.
- Updated app labels, Windows download names and documentation links to Membrane Control.
- Added the lab credit to the README, app Help and portable guide.
- Kept the existing operator data location, so previously recorded runs remain available.

The prior release's Start here guide, connection statuses, editable presets and control fixes are included. The existing firmware protocol and physical commissioning gates are retained. ESP32 firmware remains at version 0.1.3.

## Validation

Local Windows checks: **116 desktop tests passed**. The packaged EXE opened, produced a screenshot and exited cleanly. The updated Help tab was visually reviewed. GitHub-hosted Actions remain unavailable for this account; this release was built and checked locally.

Firmware is unchanged from 0.1.3, whose two ESP32 builds and 18 native tests passed. No board was flashed or physical rig tested for this release. Factory firmware remains a dry run. CIP, CWF and Fouling presets are demonstration templates pending lab approval.

[Start here](https://github.com/regular030/membrane-control/blob/v0.1.4/docs/START-HERE.md) |
[Installation](https://github.com/regular030/membrane-control/blob/v0.1.4/docs/installation.md) |
[Firmware setup](https://github.com/regular030/membrane-control/blob/v0.1.4/firmware/README.md) |
[Validation](https://github.com/regular030/membrane-control/blob/v0.1.4/docs/validation.md)

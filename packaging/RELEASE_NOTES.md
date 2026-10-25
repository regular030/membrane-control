Basu Membrane Control 0.1.3 makes first use easier and fixes run-status and serial-command edge cases.

## Download and open

Under **Assets**, download **BasuMembraneControl-0.1.3-windows-x64.exe** and double-click it. Or extract the matching app ZIP for the EXE and short guides. The automatic **Source code** ZIP is for developers.

Python and application libraries are bundled. Leave **Simulation mode** checked and click **Start here** for a practice run. USB drivers are separate vendor components. Replacing the EXE preserves recorded data in the operator data folder.

## Changes

- Added Start here, a Help tab and a shorter README and operator guide. Dashboard explains why Start is unavailable and shows the next action.
- Fixed custom-preset selection, manual command acknowledgement and the pump's Sent readout. Valve changes preserve the last sent pump setting.
- Fixed very short run completion, unexpectedly early idle reporting and detectable controller restarts. Invalid acknowledgements cannot confirm an action, and malformed JSON/Unicode is rejected by firmware.
- CSV includes pump-voltage feedback and device statuses. Export waits until operation stops so a long export cannot delay controller heartbeats. Run history selects the most recent run.

## Validation and remaining hardware work

Local Windows checks: **116 desktop tests**, **18 native firmware tests** and both ESP32 firmware builds passed. All five UI tabs were visually checked at 1360 x 940 and 1080 x 760. The packaged Windows EXE was launched, produced a screenshot and exited cleanly. GitHub-hosted Actions remain unavailable for this account; this release was built and checked locally.

No ESP32 was flashed and no real instrument connection was tested for this release. The physical rig has not been commissioned. Factory firmware remains a dry run, and the physical board profile is unconfigured. CIP, CWF and Fouling presets are examples pending lab approval. Clean-machine installation and extended physical operation still need testing.

[Start here](https://github.com/regular030/basu-membrane-control/blob/v0.1.3/docs/START-HERE.md) |
[Installation](https://github.com/regular030/basu-membrane-control/blob/v0.1.3/docs/installation.md) |
[Firmware setup](https://github.com/regular030/basu-membrane-control/blob/v0.1.3/firmware/README.md) |
[Validation](https://github.com/regular030/basu-membrane-control/blob/v0.1.3/docs/validation.md)

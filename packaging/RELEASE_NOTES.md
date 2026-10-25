Basu Membrane Control 0.1.1 adds a visible Device connections panel to the dashboard.

- ESP32 and scale show Connected or Not connected.
- Pressure, flow and pump-voltage inputs show Reading received or No reading.
- Desktop Demo devices and ESP32 dry-run measurements are labelled Simulated.
- Valves and pump movement show Not monitored because the current interfaces do not provide physical position/running feedback.
- Compact windows keep the connection panel visible while charts and manual controls scroll.

Download the Windows x64 EXE and double-click it, or extract the matching ZIP.
Python and the application libraries are bundled. USB drivers remain separate
vendor components. Existing recorded data is preserved in the operator data
folder when replacing the EXE.

Local validation: 72 desktop tests passed. The packaged Windows EXE was also
launched and checked for a screenshot and clean exit. Firmware is unchanged
from 0.1.0, whose two ESP32 builds and 16 native firmware tests passed.
GitHub-hosted Actions remain unavailable for this account; the release is built
and checked locally.

The physical rig has not been commissioned. The default ESP32 firmware uses
dry-run outputs, and its physical profile remains unconfigured. CIP, CWF and
Fouling recipes are examples pending lab approval.

[Installation](https://github.com/regular030/basu-membrane-control/blob/v0.1.1/docs/installation.md) |
[Operator guide](https://github.com/regular030/basu-membrane-control/blob/v0.1.1/docs/operator-guide.md) |
[Firmware setup](https://github.com/regular030/basu-membrane-control/blob/v0.1.1/firmware/README.md) |
[Validation](https://github.com/regular030/basu-membrane-control/blob/v0.1.1/docs/validation.md)

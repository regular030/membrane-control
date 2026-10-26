Membrane Control 0.1.5 adds keyboard zoom for the whole interface.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download

Under **Assets**, download **MembraneControl-0.1.5-windows-x64.exe** and double-click it, or extract the matching portable ZIP. Python and application libraries are bundled.

## Resize the interface

- **Ctrl + -**: zoom out.
- **Ctrl + +** or **Ctrl + =**: zoom in.
- **Ctrl + 0**: reset to 100%.

Zoom changes in 10% steps from 60% to 150%. The current percentage appears at the bottom right. Each launch starts at 100%.

Text, controls, spacing, table sizes and graph labels scale together. Smaller zoom allows the interface to fit in a smaller window. Zoom adjusts the display; experiment values retain their units and values.

## Validation

All **126 desktop tests passed**, including 32 Qt UI tests. See the [validation record](https://github.com/regular030/membrane-control/blob/v0.1.5/docs/validation.md) for the completed desktop, shortcut, visual and packaged EXE checks. GitHub-hosted Actions remain unavailable for this account; release checks run locally.

ESP32 firmware is unchanged from 0.1.3. No board was flashed or physical rig tested for this interface update. Factory firmware remains a dry run, with example recipes pending lab approval.

[Start here](https://github.com/regular030/membrane-control/blob/v0.1.5/docs/START-HERE.md) |
[Installation](https://github.com/regular030/membrane-control/blob/v0.1.5/docs/installation.md) |
[Operator guide](https://github.com/regular030/membrane-control/blob/v0.1.5/docs/operator-guide.md)

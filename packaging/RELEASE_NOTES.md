Membrane Control 0.1.6 fixes misleading connection errors when a serial port cannot open or the controller is unplugged.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download

Under **Assets**, download **MembraneControl-0.1.6-windows-x64.exe** and double-click it, or extract the matching portable ZIP. Python and application libraries are bundled. Firmware build tools and USB drivers are separate.

## Connection errors

A failed serial connection now detaches immediately and keeps its original error, such as access denied or a disconnected USB adapter. It no longer accumulates commands on a stopped worker and replaces the useful error with "queue full" or "No acknowledgement for stop". An active run disconnect still faults and withdraws heartbeats immediately.

The firmware guide now includes first-time Windows tool setup and dry-run flashing instructions for the 16-relay board with an external USB-to-UART adapter. Confirm the actual board input voltage and polarity before applying power. The listing alone does not verify 12 V compatibility.

Balance instructions now cover the photographed USB-to-RS232 adapter, alongside the alternative USB-B I/O connection.

## Validation

All **130 desktop tests passed**, including regressions for failed port opening, active USB disconnects, preserved error messages and slow port startup. The packaged Windows EXE was also checked for launch, screenshot and clean exit. See the [validation record](https://github.com/regular030/membrane-control/blob/v0.1.6/docs/validation.md).

ESP32 firmware is unchanged from 0.1.3. No board was flashed or physical rig tested for this update. Factory firmware remains a dry run, with physical operation awaiting commissioning. GitHub-hosted Actions remain blocked by the account's billing/spending-limit error; release checks run locally.

[Start here](https://github.com/regular030/membrane-control/blob/v0.1.6/docs/START-HERE.md) |
[Installation](https://github.com/regular030/membrane-control/blob/v0.1.6/docs/installation.md) |
[Firmware setup and flashing](https://github.com/regular030/membrane-control/blob/v0.1.6/firmware/README.md)

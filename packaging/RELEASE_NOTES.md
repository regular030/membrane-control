Membrane Control 0.1.20 recovers some lost manual-valve replies and shows an advancing sample time on the live sensor panel.

Developed for **Dr. Onita Basu's lab at Carleton University**.

Download **MembraneControl-Setup-0.1.20-windows-x64.exe** from Assets. Use **Flash normal controller** from the updated setup for valve receipts.

- A fresh ESP32 telemetry frame can confirm a valve command using the exact pending request ID and matching requested states. An unconfirmed command still triggers Stop. This recovery does not resend valve commands or change the watchdog.
- **Dashboard → Live sensor check** shows the ESP32's sample time so steady readings are distinguishable from a frozen display. Test voltages require no manual configuration on factory firmware.
- The guides describe how to investigate a complete serial dropout and how to measure two reference points for a calibrated profile.

See the [serial recovery guide](https://github.com/regular030/membrane-control/blob/v0.1.20/docs/serial-recovery.md) and [sensor guide](https://github.com/regular030/membrane-control/blob/v0.1.20/docs/flow-sensor-troubleshooting.md).

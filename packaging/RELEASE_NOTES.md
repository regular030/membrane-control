Membrane Control 0.1.11 adds a live runtime readings table to Dashboard.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download

Close the old app and download **MembraneControl-0.1.11-windows-x64.exe** for an app-only update, or **MembraneControl-Setup-0.1.11-windows-x64.exe** for installed shortcuts and new-PC setup. Python is bundled with the app; Setup also prepares the separate firmware tools. This table update does not require reflashing the ESP32.

## Live readings

The table beneath the graphs adds rows from actual saved samples at the sequence's recording interval. It shows timestamp/runtime, cycle and step, desired/measured flow, balance-derived flow, pressure, flux, mass, pump command/feedback, all seven commanded valve states, mode and device/fault status.

Missing values display **Unavailable**. **Follow latest** can be disabled to inspect older rows. The display retains the latest 1,000 rows for bounded memory use; complete records stay in SQLite and CSV exports. Completed run rows stay visible until the next run begins. Final recorded samples also appear.

The table does not generate measurements or change actuator commands. Desired flow remains a comparison target pending pump/interface calibration.

## Firmware and scale connection

**MembraneControl-Firmware-0.1.11-esp32.zip** includes the full source and compiled dry-run, relay-bench and physical controller images, offsets and checksums. The portable ZIP and Setup also include it. The physical factory profile stays unverified and locked until wiring and calibration are established. The main screen retains Dr. Onita Basu's lab credit.

The Nimbus USB driver applies to the scale's built-in USB-B **I/O** connection. The existing green USB-to-RS232 adapter needs its own identified driver. If Windows exposes only the ESP32 COM port, the app has no scale port to read. See the [balance connection guide](https://github.com/regular030/membrane-control/blob/v0.1.11/hardware/balance-usb-setup.md).

## Validation

All **338 desktop/packaging tests** passed with a clean native process exit. The packaged app launch and setup payload/plan checks also passed. See the [validation record](https://github.com/regular030/membrane-control/blob/v0.1.11/docs/validation.md). Firmware logic is unchanged from 0.1.10, whose 33 native tests and all three ESP32 builds passed; source-matching compiled images were revalidated for this bundle. No physical rig was operated for this release. A separate clean-PC installation and rig commissioning remain outstanding. Hosted GitHub Actions remain blocked by the account billing lock; these binaries were built and checked locally.

Membrane Control 0.1.28 adds an open-bucket pump test and reports pump feedback separately from the commanded speed.

Developed for **Dr. Onita Basu's lab at Carleton University**.

- The USB open-bucket test stages 50%, closes the RUN relay for up to 10 seconds, and retains the controller's acknowledgment after the test. The lab confirmed water flow at about 165 mL/min on the Masterflex display and confirmed that the pump stopped when the test ended.
- The commissioning build reads the pump feedback divider on IO34. The normal Dashboard can report drive feedback in volts and, with a configured tachometer input, measured RPM.
- Windows Setup includes shortcuts for the explicit pump tests and normal controller flashing. The firmware bundle includes the open-bucket test and normal Bluetooth images.
- Normal CWF operation requires a compiled rig profile and a calibrated pressure signal at startup. Use the open-bucket test only with its separate discharge setup.

[Installation instructions](https://github.com/regular030/membrane-control/blob/v0.1.28/docs/installation.md)

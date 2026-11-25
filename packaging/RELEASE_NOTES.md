Membrane Control 0.1.30 adds estimated flow entry, a clean-water flux test preset and explicit balance connection controls.

Developed for **Dr. Onita Basu's lab at Carleton University**.

- Enter an estimated pump flow on the Dashboard or for a step in the Sequence editor. The estimate uses the measured 49 mL/min at 11% and covers up to 49 mL/min.
- Select **CWF water test** to load the lab's reviewed V1/V3 clean-water sequence.
- The balance serial port stays closed at startup. Connect explicitly when weighing is needed and use Disconnect to release the port even if no readings have arrived.
- The lab's ADS1115 profile reads pressure on A0 and drives pump PWM on IO23. It accepts near-zero pressure input down to −6 mV and enforces the existing 80 psi firmware cutoff.

[Installation instructions](https://github.com/regular030/membrane-control/blob/v0.1.30/docs/installation.md)

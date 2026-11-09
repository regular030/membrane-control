Membrane Control 0.1.26 uses the pressure and flow calibration certificate points for live Dashboard estimates.

Developed for **Dr. Onita Basu's lab at Carleton University**.

- With the rig stopped and zero pressure and flow verified, click **Zero pressure and flow** to capture a baseline for the current connection. The Dashboard shows live estimates wherever the certificate points and ADC input range support them.
- The zero baseline shows changes in raw voltage. Near-zero pressure can fall below the usable ADC range, and the flow certificate starts at 20 mL/min. The Dashboard labels those ranges.
- **Sensor setup** still accepts two independent references when available. The commissioned firmware profile drives run data and pressure protection.

[Sensor setup instructions](https://github.com/regular030/membrane-control/blob/v0.1.26/docs/flow-sensor-troubleshooting.md#set-up-the-pressure-and-flow-readings)

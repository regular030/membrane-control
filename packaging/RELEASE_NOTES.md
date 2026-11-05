Membrane Control 0.1.19 adds live sensor checks and a persistent ESP32 connection log.

Developed for **Dr. Onita Basu's lab at Carleton University**.

Download **MembraneControl-Setup-0.1.19-windows-x64.exe** from Assets. The new app records serial events with compatible controller firmware. Use **Flash normal controller** from the updated setup for live sensor voltages and ESP32 reset reporting.

- **Dashboard → Live sensor check** shows GPIO34 pressure, GPIO36 flow, and optional GPIO39 pump feedback in millivolts while idle or using manual valves. Estimates assume the documented divider and sensors. Calibrated readings and experiment protection still require a reviewed profile.
- **Connections and settings → Copy ESP32 log** copies recent valve commands, acknowledgements, link errors, timeouts and reset information. The log survives app restarts and omits the routine sample stream.
- The pump profile template records the lab-confirmed **bit 15**, LOW for STOP and HIGH for RUN. The factory firmware leaves the pump output off, with manual V3 available as before.

See [serial recovery](https://github.com/regular030/membrane-control/blob/v0.1.19/docs/serial-recovery.md) and the [sensor test guide](https://github.com/regular030/membrane-control/blob/v0.1.19/docs/flow-sensor-troubleshooting.md#test-the-connected-sensors).

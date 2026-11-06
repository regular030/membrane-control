Membrane Control 0.1.24 lets the normal ESP32 Bluetooth firmware use the saved bench pairing and adds a shareable connection report.

Developed for **Dr. Onita Basu's lab at Carleton University**.

- Install **MembraneControl-Setup-0.1.24-windows-x64.exe** and run **Flash normal controller (Bluetooth)** with the valve and pump loads isolated. Flash over USB and try the existing outgoing Bluetooth COM port first.
- If the controller reports a missing bond on its wired boot log, use **Flash ESP32 Bluetooth test** to enroll the lab PC and verify that the board saves one bond before reflashing the normal Bluetooth firmware.
- Under **Connections and settings**, **Copy connection diagnostics** collects the selected and detected COM ports, current status and recent ESP32 connection events for troubleshooting.

[Bluetooth controller instructions](https://github.com/regular030/membrane-control/blob/v0.1.24/docs/full-firmware.md#run-the-normal-controller-over-bluetooth) · [Sensor setup instructions](https://github.com/regular030/membrane-control/blob/v0.1.24/docs/flow-sensor-troubleshooting.md#set-up-the-pressure-and-flow-readings)

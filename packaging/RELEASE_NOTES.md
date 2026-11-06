Membrane Control 0.1.23 adds normal ESP32 controller operation over Bluetooth and a **Sensor setup** window for live inputs and reference checks.

Developed for **Dr. Onita Basu's lab at Carleton University**.

- Install **MembraneControl-Setup-0.1.23-windows-x64.exe**. With the loads isolated, use **Flash normal controller (Bluetooth)** to upload over the wired USB-to-UART port. Keep the existing pairing from **Flash ESP32 Bluetooth test**, then connect to its outgoing Bluetooth COM port in the app. The normal build uses real manual valve outputs and the same hardware profile as the wired controller.
- Open **Sensor setup** on Dashboard or under **Connections and settings** to see live pressure, flow and pump feedback pin voltages. Capture a per-sensor zero and two measured reference points, then copy the readings and calculated fit for the rig's profile.
- Firmware discards the previous control session when Bluetooth disconnects. Wired firmware writes each reply as one complete serial frame. Hardware testing on the lab rig remains pending.

[Bluetooth controller instructions](https://github.com/regular030/membrane-control/blob/v0.1.23/docs/full-firmware.md#run-the-normal-controller-over-bluetooth) · [Sensor setup instructions](https://github.com/regular030/membrane-control/blob/v0.1.23/docs/flow-sensor-troubleshooting.md#set-up-the-pressure-and-flow-readings)

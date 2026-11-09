Membrane Control 0.1.25 incorporates the tested Bluetooth reconnection fix and improves live sensor estimates and manual valve commands.

Developed for **Dr. Onita Basu's lab at Carleton University**.

- Install **MembraneControl-Setup-0.1.25-windows-x64.exe**. If the board is still on the v0.1.24 Bluetooth image, use **Flash normal controller (Bluetooth)** over wired USB with the valve and pump loads isolated, then use the existing outgoing Bluetooth port.
- The Dashboard shows a labeled live estimate for each sensor in range. With two measured points in **Sensor setup**, it uses your fit within the captured range for that connection. Commissioned readings continue to drive the run and its protection.
- The serial queue sends the opening Bluetooth heartbeat before a subsequently queued manual valve command. Use the normal Dashboard toggles to hold a valve open and **Stop valves** to release all valves. A lost controller link still releases them.

[Bluetooth controller instructions](https://github.com/regular030/membrane-control/blob/v0.1.25/docs/full-firmware.md#run-the-normal-controller-over-bluetooth) · [Sensor setup instructions](https://github.com/regular030/membrane-control/blob/v0.1.25/docs/flow-sensor-troubleshooting.md#set-up-the-pressure-and-flow-readings)

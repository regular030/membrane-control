# Bluetooth debug handoff

Use this checklist to troubleshoot the ESP32 Bluetooth controller from its
attached Windows PC. Start with the connection and boot checks before testing
outputs or sensor inputs.

[Membrane Control v0.1.24](https://github.com/regular030/membrane-control/releases/tag/v0.1.24)
ships a compatibility fix for the bench pairing and a **Copy connection
diagnostics** button. The v0.1.23 physical service could ask Windows to
upgrade the saved pairing and then refuse the pairing request. The new
firmware uses the existing saved link key, requires an encrypted connection,
and allows only the saved peer.

## First checks on the attached PC

1. Confirm the chat is running on the PC with the ESP32 attached. Start by
   checking the app version, the wired USB-to-UART COM port and the outgoing
   Bluetooth COM port. Verify their current numbers in Windows. It may display the existing
   Bluetooth pairing under the name `MembraneControl-Bench`.
2. Capture one failed attempt with **Connections and settings → Copy
   connection diagnostics**. With valve and pump loads isolated, capture the
   ESP32 boot and Bluetooth messages from the wired port at **115200 baud**.
   In the physical Bluetooth image, the wired port is for flashing and
   diagnostics. The app connects through the outgoing Bluetooth port.
3. Verify the board was flashed with **Flash normal controller (Bluetooth)**
   from the v0.1.24 Setup, using a regular upload that preserves the pairing.
   Look for `Bluetooth: protected serial service started for one saved bond`
   and, on connection, `Bluetooth: saved device opened the protected serial connection`.
   Turn off desktop **Simulation**. The app should show **Connected** and
   the `hello_identified` event should show `transport: bluetooth_spp`. The
   firmware handshake version field can still say `0.1.20`.
4. If the board reports `no enrolled bench bond`, follow the enrollment steps
   in the [Bluetooth firmware guide](full-firmware.md#run-the-normal-controller-over-bluetooth).
   Confirm `Bluetooth bench saved bonds: 1` and **Connected (dry run)**
   before reflashing the normal Bluetooth image. With a working physical
   connection and loads isolated, test one relay and verify it releases on
   disconnect. Record the selected ports, boot messages and result.

After the connection works, use **Dashboard → Sensor setup** to check live
pressure on IO34 and flow on SVP/GPIO36. Capture two measured references per
sensor and use **Copy setup readings**. Setup estimates are separate from the
commissioned run profile and pressure protection. See the
[sensor setup guide](flow-sensor-troubleshooting.md#set-up-the-pressure-and-flow-readings)
and [wired recovery guide](serial-recovery.md).

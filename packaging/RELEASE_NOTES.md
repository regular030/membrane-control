Membrane Control 0.1.17 adds a finder for the pump's spare onboard relay and updates the wiring guide for the Masterflex 75211-70 DB25 drive.

Developed for **Dr. Onita Basu's lab at Carleton University**.

## Update

Download and run **MembraneControl-Setup-0.1.17-windows-x64.exe** from Assets. The installer includes the desktop app, flashing tools, and ESP32 firmware.

## Find the pump relay

Open **Connections and settings → Bare relay board test** and enable **Find pump relay (spare bits only)**. The finder disables the six valve buttons and leaves only the spare bits available. With all loads disconnected, pulse a spare bit and check COM to NO on the relay you wired for the pump. Record the raw bit and the relay's printed channel number. The factory controller leaves the pump relay unassigned until the wiring is confirmed and the rig profile is reviewed.

See the [relay finder instructions](https://github.com/regular030/membrane-control/blob/v0.1.17/docs/relay-board-test.md#find-the-pumps-spare-relay) and the [wiring guide](https://github.com/regular030/membrane-control/blob/v0.1.17/docs/ordered-parts-wiring.md).

## Firmware and balance

A reviewed ESP32 profile can use an unused onboard relay for pump start/stop. The template records GPIO25 for PWM and GPIO34, GPIO36, and GPIO39 for the conditioned pressure, flow, and optional pump-feedback signals. Normal six-valve controls remain available without sensors. The lab reported working balance readings over USB-B with default settings.

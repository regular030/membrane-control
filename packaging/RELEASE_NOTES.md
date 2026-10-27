Membrane Control 0.1.15 adds normal-firmware control for the six confirmed valves and improves Adam Nimbus scale communication.

Developed for **Dr. Onita Basu's lab at Carleton University**.

## Download and update

Install **MembraneControl-Setup-0.1.15-windows-x64.exe**. Close the app's controller connection, use the installed **Flash normal controller** shortcut to upload `esp32-physical`, then reconnect with Simulation mode off. Updating only the app does not update the ESP32.

## Six valves in normal firmware

The user confirmed **six valves: V1-V6 = relay bits 0-5, LOW off and HIGH energized**. Dashboard now shows six ON/OFF controls above the measurements. They work with normal firmware without pressure, flow, balance, DAC, a valve-profile form or extra approval checkboxes. The states persist until changed or stopped, replacing the need to use the old 500 ms test program for this task.

The dedicated valve-only command holds pump_percent at zero. Stop turns all six off; reconnect, reset and the existing three-second communication watchdog do not resume an old valve state. Bits6-15 stay LOW, and the unused seventh legacy wire slot is rejected if true. Pump/manual and automatic experiment configuration requirements remain separate. The six-valve capability does not claim that missing sensor channels are configured.

Follow [normal valve controls](https://github.com/regular030/membrane-control/blob/v0.1.15/docs/normal-valves.md). Older pulse/relay tools remain optional under Connections and settings.

## Adam Nimbus scale

The main scale connection can request weights automatically at most once per second when data is not streaming, using the documented fixed Print command. It can also request a reading explicitly. Formats NONE8N1 / EVEN7E1 / ODD7O1 and4800 baud are supported; raw balances accept CR, LF and CRLF. The parser accepts documented Net fields, decimal comma and form boundaries without treating Gross/Tare/ID as net mass.

Raw-balance USB DTR readiness now defaults on; ESP32 reset/control lines retain their previous behavior. No tare, zero, reset or scale-settings commands are sent. A request does not count as a received weight. The separate **Test scale / raw data** window shows actual received bytes, escaped text/hex, decoded lines, valid masses and errors, and releases the normal scale port first.

The lab's current settings are **COM6 /9600**, USB-B I/O. The physical display works, but a live response is not yet verified because COM6 is on the separate lab PC. Use the [scale connection guide](https://github.com/regular030/membrane-control/blob/v0.1.15/docs/scale-connection.md) if it still reports no weight. DTR is a compatibility improvement, not a confirmed diagnosis of this particular unit.

## Validation

**657 desktop/packaging tests passed**, with four real-symlink cases skipped for unavailable Windows privilege. **98 native firmware tests and all four ESP32 target builds passed.** Serial tests use fake streams and include actual byte framing, fixed Print requests, format/DTR handling, bounded polling, no invented weight evidence and cleanup. The packaged app launched and exited cleanly; Setup verified its payload without installation or USB access. Release checksums and actionlint passed. See [validation](https://github.com/regular030/membrane-control/blob/v0.1.15/docs/validation.md).

No physical valves or lab serial ports were operated while preparing this release. Hosted Actions retain the existing account billing lock; these binaries are built and verified locally.

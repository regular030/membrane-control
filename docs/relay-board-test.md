# Test the real relay board

Use this when only the ESP32 relay board and its USB-to-UART adapter are
connected. This firmware operates real relay outputs. Keep every relay contact
terminal disconnected from pumps, valves and other loads throughout this test.
Confirm the board's rated supply and polarity before powering it.

## Install and flash

1. Close Membrane Control and any serial monitor. Install the latest
   **MembraneControl-Setup** release if this computer does not have the new tools.
2. Open the **Flash relay board test** shortcut. Enter the controller's COM port,
   currently COM4 on the lab laptop, and follow the upload prompt.
3. At `Connecting...`, hold **IO0**, briefly press **EN**, and release IO0 when
   writing starts. After a successful upload, release IO0 and press EN again.

For a source checkout instead, update the source and run from its root:

```powershell
$env:PLATFORMIO_CORE_DIR = Join-Path (Get-Location) 'work/platformio'
.\.venv\Scripts\python.exe -m platformio run -d firmware -e esp32-relay-bench -t upload --upload-port COM4
```

The existing `esp32-dry-run` target remains available for a communication-only
test. The `esp32-physical` experiment target still needs the pump and protected
sensor interfaces and a verified configuration; it is not the relay test target.

## Open the test controls

Open the new Membrane Control app. Turn **Simulation mode** off, choose the
controller port under **Connections and settings**, then open **Relay board test**.
Connect from the test window. The normal experiment connection is released first
so the two windows do not fight over the same COM port.

1. Confirm that all relay contact terminals are disconnected from loads.
2. Select the **All LOW** rest pattern and test it briefly. The test may energize
   several bare relays because their active polarity has not been measured yet.
3. If all relays stayed off during that pattern, confirm the observation. If they
   turned on, test **All HIGH** instead and confirm only the pattern that left
   every relay off. If neither does, stop and check the board before proceeding.
4. Pulse one raw bit at a time and record which numbered relay changes. A raw
   shift-register bit is not necessarily the same number as a physical relay.
5. Use **Stop** to disable the shift-register outputs and clear the confirmation.
   Closing or disconnecting also withdraws the heartbeat. Confirm the relays'
   actual response rather than assuming an output-enable command proves it.

The app requests 500 ms pulses. Firmware caps any accepted pulse at two seconds
and expires its heartbeat lease after one second. It does not keep outputs on
between pulses. Reconnecting never restores a previous confirmation or pulse.

## Record the result

Use the numbers printed at the contact terminals. With no external load wiring,
check COM-NO/NC continuity as well as the indicator/click. Record a fault instead
of calling an unresponsive or stuck contact successful.

| Raw bit | Physical relay number | Indicator and contacts checked |
| --- | --- | --- |
| 0 | | |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |
| 7 | | |
| 8 | | |
| 9 | | |
| 10 | | |
| 11 | | |
| 12 | | |
| 13 | | |
| 14 | | |
| 15 | | |

This establishes a candidate relay mapping. It does not approve mains load wiring,
pump operation, pressure protection or an experiment sequence. No sensor readings
are invented by this firmware. The board reports `hardware_verified: false`.

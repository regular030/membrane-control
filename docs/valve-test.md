# Test one valve without sensors

This tool is for the rig's seven single-coil solenoid valves. It does not need
the pressure sensor, flow sensor, balance or pump DAC. The pump must be
physically isolated, and no experiment or automatic sequence runs here.
Developed for Dr. Onita Basu's lab at Carleton University.

## What can be tested today

There are two different tools under **Connections and settings**:

| Tool | Loads | Firmware | Purpose |
| --- | --- | --- | --- |
| **1. Bare relay board test** | Every COM/NO/NC load wire disconnected | `esp32-relay-bench` | Find the all-off pattern and measure raw-bit to physical relay mapping. |
| **2. Valve test (no sensors)** | Only the seven reviewed solenoid circuits | `esp32-valve-test` with a reviewed valve-only profile | Energize one named valve for 500 ms and observe its response. |

**The downloadable factory valve-test image is locked.** On 26 October 2026,
Kunshpreet reported that **All LOW left the relays off and All HIGH turned them
on**. This supports a candidate all-off rest word of 0; it does not establish
the individual channel mapping, loaded safe states or reset/OE response.
Uploading firmware or checking app boxes cannot replace that review.
It will connect and explain what is missing. Normal experiment controls retain
their own separate hardware and pressure requirements.

## Handoff for Raj and the lab technician

1. With contact loads disconnected, use the [bare-board guide](relay-board-test.md).
   Record the rest pattern and each raw bit's actual numbered relay. Check contact
   continuity as well as clicks/LEDs. Do not assume bit 0 means relay 1.
2. Record which seven checked relays serve V1 through V7. Establish that the full
   sixteen-bit rest word and disabled-OE, reset and power-loss behavior release
   every solenoid, including unused outputs. An LED alone cannot establish this.
3. Have the lab's qualified technician check the mains installation. The recorded
   Granzow coils are **110-120 V AC**, independent of the board's DC power supply.
   Relay-board suitability, inductive-load ratings, protection, enclosure,
   earthing and safe hydraulic conditions must be checked. Ordinary Dupont leads
   are not mains load wiring. The pump's low-voltage dry contact must never be
   connected to the valve live distribution.
4. Isolate pump power and its remote-control connections. Approve the test area's
   fluid path for each individually energized valve. This mode has no sensor
   interlock and is not a pressure-producing test or a cleaning procedure.
5. A maintainer copies `firmware/examples/ValveTestProfile.example.h` to
   `firmware/include/ValveTestProfile.local.h` and fills it from those recorded
   results. Keep the example unchanged. Assign a unique profile ID, seven unique
   measured raw bits and the full rest word. Set the review flags only for checks
   actually completed. The example contains placeholders and cannot operate loads.
6. In `firmware/platformio.ini`, under `[env:esp32-valve-test]`, add the following
   build flag, preserving the existing source filter and base flags:

   ```ini
   build_flags = ${env.build_flags} -DBASU_VALVE_PROFILE_HEADER=\"ValveTestProfile.local.h\"
   ```

   Build and upload from this reviewed checkout, with loads disconnected during
   the initial upload:

   ```powershell
   $env:PLATFORMIO_CORE_DIR = Join-Path (Get-Location) 'work/platformio'
   .\.venv\Scripts\python.exe -m platformio run -d firmware -e esp32-valve-test -t upload --upload-port COM4
   ```

   Replace COM4 if Windows assigns a different controller port. Close the app's
   port first. For a three-wire UART adapter, use IO0/EN download entry and press
   EN once afterward with IO0 released. The installed **Flash valve test (setup
   required)** shortcut builds the installed source; it also needs the reviewed
   local profile and build flag in that installed copy. The factory ZIP does not
   contain a commissioned profile. Custom profiles are excluded from Git/release
   sources, and the factory bundle builder rejects compiled custom profiles.

## Use the controls

1. Open the latest app and stop any run. Uncheck **Simulation mode**.
2. In **Connections and settings**, select the ESP32 port, then choose
   **2. Valve test (no sensors)**. Connect in that window. The regular controller
   connection is released first; the scale has a separate port and is not needed.
3. Confirm that the displayed profile ID matches the reviewed installation. A
   **Locked** message needs the maintainer steps above, not another checkbox.
4. Complete the three session checks for reviewed wiring, isolated pump and a
   safe test area. Click **Arm valve tests**.
5. Press one V1-V7 **Energize 500 ms** button. Observe and record the actual
   valve response. The app reports commands, not open/closed position feedback.
   The other buttons are unavailable until the pulse finishes.
6. **STOP and disconnect** ends the session. Closing the window/app also requests
   Stop and releases the COM port. Reconnecting requires the checks again.

The desktop requests 500 ms. Firmware accepts only bounded 100-2000 ms pulses,
allows one at a time, and ends the session after a one-second heartbeat expiry.
This is an additional software limit, not a substitute for independent safe
wiring. Stop, reset and reconnection never resume an old pulse automatically.

Record date, profile ID, V1-V7 observed operation and any sticking/leakage/fault.
Do not label a failed valve successful because its relay clicked. For motorized,
reversing or latching actuators, stop and obtain their wiring and travel-time
specification; this single-coil solenoid tool does not support them.

Pump speed control is a later step. See the [DAC and pump wiring handoff](../hardware/pump-interface.md).

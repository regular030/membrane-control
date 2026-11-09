# Full ESP32 firmware in the release

Version 0.1.26 includes the complete controller source and compiled ESP32 images,
alongside the Windows application. Download
`MembraneControl-Firmware-0.1.26-esp32.zip` under the GitHub release's **Assets**.
The portable application ZIP also contains it. Setup installs it in
`firmware-release/` and installs the editable source in `firmware/`.

## Choose the right program

| Firmware target | What it does |
| --- | --- |
| `esp32-dry-run` | Full recipe/communications logic with generated readings and no relay or pump output. Use for connection and app checks. |
| `esp32-relay-bench` | Real unloaded relay pulses through the board's candidate shift-register interface. Separate test window; no sensors, pump or experiments. |
| `esp32-valve-test` | Sensor-free, one-at-a-time solenoid pulses using a separate reviewed valve profile. No pump or sensor protection; the supplied factory profile stays locked. |
| `esp32-physical` | Normal controller. The six installed valves V1-V5/V7 use bits 0, 1, 2, 3, 5, 6 and work manually without sensors or profile forms. The factory image shows live sensor voltages during manual valve operation and while idle. Full pump/experiment operation still needs its configured interfaces and inputs. |
| `esp32-bluetooth-physical` | Normal controller over Bluetooth. Setup builds this from source with the same hardware profile as the wired controller. |

All targets are for the ESP32-WROOM/classic ESP32 profile used by this project.
The full controller source is `firmware/src/main.cpp`; its I/O implementation is
`firmware/include/Hardware.h`. The hardware profile entry point is
`firmware/include/BoardProfile.h`.

## Upload from the installed setup

1. Close any app connection or serial monitor using the selected COM port.
2. For an initial upload, keep valve/pump loads disconnected. Use **Flash ESP32
   dry run**, **Flash relay board test**, **Flash valve test (setup required)**, or **Flash normal
   controller** from the installed shortcuts. The helper asks for the COM port
   and explicit upload confirmation.
3. With an external adapter lacking reset wiring, hold IO0, press/release EN,
   then release IO0 to enter the bootloader. After upload, release IO0 and press
   EN once to run the program. A successful write does not prove an automatic
   reset happened.
4. Open the matching app screen. The relay-bench target uses **1. Bare relay board
   test** and the valve-test target uses **2. Valve test (no sensors)** under
   **Connections and settings**. The controller targets use the main controller connection. The
   physical target can report an unverified pump/experiment profile while its
   separate confirmed manual-valve capability is ready.

Setup prepares all four build targets without opening a COM port or uploading.
For this rig, use **Flash normal controller** (`esp32-physical`), then the six
Dashboard ON/OFF buttons. No separate pulse-test program/profile is required.
V6 is absent: wire-array index 5 is reserved false, while V7 uses index 6.
Factory manual valve control keeps bit 4 and bits 7-15 LOW. A reviewed full
profile may use a separately tested spare for pump start/stop. Firmware advertises the explicit
`manual_valve_ids: [1,2,3,4,5,7]` and `valve_bits: [0,1,2,3,5,6]` mapping.
See [six valves with normal firmware](normal-valves.md).
App 0.1.14 adds **Set up valve mapping and firmware** in the valve-test window.
It builds a private reviewed valve profile without editing the shared source;
see [Valve test](valve-test.md). The factory image remains locked.
The helper builds from installed source before upload, so a reviewed custom
profile can be rebuilt later. The separate firmware ZIP includes precompiled
images, offsets and checksums for tools that can flash raw ESP32 binaries; follow
its README and manifest rather than treating `firmware.bin` as a complete image.

## Test the connection over Bluetooth

Use the **Flash ESP32 Bluetooth test** shortcut from Setup 0.1.22. It compiles
the optional `esp32-bluetooth-dry-run` firmware from the installed source and
uploads it over the existing USB-to-UART adapter. The Bluetooth firmware
simulates readings and outputs so you can check the wireless link with the
valve and pump loads isolated.

1. Close the app connection. Run the shortcut and select the **wired COM
   port**. Complete the usual IO0/EN upload steps.
2. In Windows, open **Settings → Bluetooth & devices → Add device → Bluetooth**
   and pair with **MembraneControl-Bench**.
3. Open **Bluetooth & devices → Devices → More Bluetooth settings → COM Ports**.
   Select the **outgoing** port for MembraneControl-Bench. If Windows has
   not assigned one, use **Add → Outgoing** to create it.
4. Open Membrane Control in hardware mode, then select the
   Bluetooth COM port in **Connections and settings**. The app should report
   **Connected (dry run)**. Check that the telemetry keeps updating, then
   disconnect and reconnect once.

Use **Flash normal controller** with the wired COM port to return to regular
operation. An ESP32 power drop can interrupt both links. This trial checks
Bluetooth communication while the controller is powered and idle or simulated.
[ESP32 Bluetooth Classic SPP](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/bluetooth.html)
· [Windows SPP support](https://learn.microsoft.com/en-us/windows-hardware/drivers/bluetooth/general-bluetooth-support-in-windows)

## Run the normal controller over Bluetooth

1. Use the same lab PC and ESP32 that passed the **MembraneControl-Bench** test.
   Keep the Windows pairing. If the board is new, pair and run the unloaded
   Bluetooth test first. The normal Bluetooth firmware uses the one existing
   bond saved on the ESP32.
2. Isolate the valve and pump loads. Close the app connection, open **Flash
   normal controller (Bluetooth)** from Setup, and select the **wired**
   USB-to-UART COM port for upload. Use the helper's IO0/EN steps. Keep the
   flash settings and use a regular upload so the saved pairing is preserved.
3. Open the app in hardware mode. In **Connections and settings**, select
   the same **outgoing Bluetooth COM port** that worked in the bench test.
   The normal Bluetooth firmware keeps the name `MembraneControl-Bench`. The
   app should show **Connected**. Verify one unloaded relay, then check that
   disconnecting the app releases the relay before using the rig.
4. Use the six manual valve controls and **Sensor setup**. The Bluetooth
   build uses the same pump, run and sensor profile as the wired controller.
   A reconnect starts a new session with outputs in their configured safe state.

If the outgoing Bluetooth COM port is missing, check **More Bluetooth settings
→ COM Ports**. If Windows still lists the paired controller, use **Add →
Outgoing** to restore its port. If the pairing is also missing, return to the
unloaded Bluetooth test to pair and verify the outgoing port before flashing
the normal Bluetooth firmware again. The wired COM port on the Bluetooth
firmware carries boot diagnostics.

If Windows opens the port but the app gets no reply, click **Copy connection
diagnostics** in **Connections and settings**. The report includes the selected
port, detected ports and recent ESP32 connection events. Also capture the
wired USB-to-UART boot log at 115200 baud with the loads isolated. Keep the
Windows pairing for the first retry after upgrading from 0.1.23.

If the boot log reports no enrolled bench bond, flash the Bluetooth test
again. While that test is running, remove the stale Windows entry for this
controller and pair `MembraneControl-Bench` using **Add device**. The test
firmware prints the number of saved bonds on the wired console. Confirm it
reports one bond and that the outgoing Bluetooth COM port works. Then flash
the normal Bluetooth firmware again using the same board and PC. If it reports
multiple bonds, use **Flash normal controller** for wired operation until the
board is enrolled to a single lab PC.

## Finish the physical hardware profile

The installed Masterflex 75211-70 uses the Garosa 3.3P-10V PWM converter.
The PWM backend is available alongside the earlier GP8403 option. Use a
reviewed compiled profile with measured settling and a verified pump contact.
The lab confirmed 74HC595 bit 15 for the pump, with LOW for STOP and HIGH for RUN.
The reviewed-profile template records that bit. The factory image leaves it off.
GPIO26 is only for the external contact-driver alternative. See
[PWM converter setup](pwm-converter-setup.md) for the wiring and checks.

The firmware sources also include a standalone
[`pwm-converter-bench` example](../firmware/examples/pwm-converter-bench/README.md)
for converter-only measurements before sensors are ready. It requires the pump
and all relay contact loads disconnected and is built separately from source;
the four main factory image choices above are unchanged.

The older separate [Valve test](valve-test.md) remains optional. Its legacy
seven-slot `BASU_VALVE_PROFILE_HEADER` and short-pulse workflow do not approve a
full experiment and are not needed for this rig's normal six-valve controls.

The source supports hardware interfaces; it does not infer their wiring from
the original Arduino pin names. A reviewed profile must establish the actual
relay-bit mapping/polarity and safe valve states, protected/scaled sensor
inputs and calibration, pump speed-input interface and return references,
start/stop interface and process pressure limit. See the
[pin plan](../hardware/relay-board-pin-plan.md),
[pump findings](../hardware/pump-interface.md), and
[firmware setup guide](../firmware/README.md).

The full source accepts a separately reviewed profile through
`BASU_VERIFIED_PROFILE_HEADER`; the default remains unverified. An app checkbox
does not replace that profile. Do not copy 5 V/10 V analog signals directly to
ESP32 GPIOs, or use a connector number alone as a voltage specification.

**Desired flow (mL/min)** is currently a saved comparison target. It does not
implement automatic flow control or change firmware pump percentages. Establish
the pump interface and flow calibration before adding that control loop.

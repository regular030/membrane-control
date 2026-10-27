# Full ESP32 firmware in the release

Version 0.1.15 includes the complete controller source and compiled ESP32 images,
alongside the Windows application. Download
`MembraneControl-Firmware-0.1.15-esp32.zip` under the GitHub release's **Assets**.
The portable application ZIP also contains it. Setup installs it in
`firmware-release/` and installs the editable source in `firmware/`.

## Choose the right program

| Firmware target | What it does |
| --- | --- |
| `esp32-dry-run` | Full recipe/communications logic with generated readings and no relay or pump output. Use for connection and app checks. |
| `esp32-relay-bench` | Real unloaded relay pulses through the board's candidate shift-register interface. Separate test window; no sensors, pump or experiments. |
| `esp32-valve-test` | Sensor-free, one-at-a-time solenoid pulses using a separate reviewed valve profile. No pump or sensor protection; the supplied factory profile stays locked. |
| `esp32-physical` | Normal controller. The six confirmed manual valve toggles work without sensors. Full pump/experiment operation still needs its configured interfaces and inputs. |

All targets are for the ESP32-WROOM/classic ESP32 profile used by this project.
The full controller source is `firmware/src/main.cpp`; its I/O implementation is
`firmware/include/Hardware.h`. The hardware profile entry point is
`firmware/include/BoardProfile.h`.

## Upload from the installed setup

1. Close any app connection or serial monitor using the selected COM port.
2. For an initial upload, keep valve/pump loads disconnected. Use **Flash ESP32
   dry run**, **Flash relay board test**, **Flash valve test (setup required)**, or **Flash full controller (setup
   required)** from the installed shortcuts. The helper asks for the COM port
   and explicit upload confirmation.
3. With an external adapter lacking reset wiring, hold IO0, press/release EN,
   then release IO0 to enter the bootloader. After upload, release IO0 and press
   EN once to run the program. A successful write does not prove an automatic
   reset happened.
4. Open the matching app screen. The relay-bench target uses **1. Bare relay board
   test** and the valve-test target uses **2. Valve test (no sensors)** under
   **Connections and settings**. The controller targets use the main controller connection. The
   physical target reports that its profile has not been verified.

Setup prepares all four build targets without opening a COM port or uploading.
For this rig, use **Flash normal controller** (`esp32-physical`), then the six
Dashboard ON/OFF buttons. No separate pulse-test program/profile is required.
See [six valves with normal firmware](normal-valves.md).
App 0.1.14 adds **Set up valve mapping and firmware** in the valve-test window.
It builds a private reviewed valve profile without editing the shared source;
see [Valve test](valve-test.md). The factory image remains locked.
The helper builds from installed source before upload, so a reviewed custom
profile can be rebuilt later. The separate firmware ZIP includes precompiled
images, offsets and checksums for tools that can flash raw ESP32 binaries; follow
its README and manifest rather than treating `firmware.bin` as a complete image.

## Finish the physical hardware profile

The selected Amazon EC Buying module uses a **PWM signal**, not I2C. Version
0.1.13 adds this pump-command option alongside the existing GP8403 driver.
Select the converter in the reviewed compiled profile; do not use a GP8403
profile or assume that an upload completes the wiring. The guide and example
profile explain the PWM pin, independent STOP contact and analog settling checks:
[PWM converter setup](pwm-converter-setup.md).

The firmware sources also include a standalone
[`pwm-converter-bench` example](../firmware/examples/pwm-converter-bench/README.md)
for converter-only measurements before sensors are ready. It requires the pump
and all relay contact loads disconnected and is built separately from source;
the four main factory image choices above are unchanged.

For valve-only checks before sensors/DAC arrive, follow [Valve test](valve-test.md).
Its separate `BASU_VALVE_PROFILE_HEADER` establishes only the seven solenoid
channels and reviewed rest/reset behavior. It does not approve a full experiment.

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
ESP32 GPIOs, or interpret the DB15 connector as a voltage specification.

**Desired flow (mL/min)** is currently a saved comparison target. It does not
implement automatic flow control or change firmware pump percentages. Establish
the pump interface and flow calibration before adding that control loop.

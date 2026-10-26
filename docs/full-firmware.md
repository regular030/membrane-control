# Full ESP32 firmware in the release

Version 0.1.10 includes the complete controller source and compiled ESP32 images,
alongside the Windows application. Download
`MembraneControl-Firmware-0.1.10-esp32.zip` under the GitHub release's **Assets**.
The portable application ZIP also contains it. Setup installs it in
`firmware-release/` and installs the editable source in `firmware/`.

## Choose the right program

| Firmware target | What it does |
| --- | --- |
| `esp32-dry-run` | Full recipe/communications logic with generated readings and no relay or pump output. Use for connection and app checks. |
| `esp32-relay-bench` | Real unloaded relay pulses through the board's candidate shift-register interface. Separate test window; no sensors, pump or experiments. |
| `esp32-physical` | Full controller, with recipe timing, relay outputs, sensor/ADC acquisition, pump DAC support, telemetry, pressure protection and communication watchdog. The shipped hardware profile is unverified, so physical operation remains locked. |

All targets are for the ESP32-WROOM/classic ESP32 profile used by this project.
The full controller source is `firmware/src/main.cpp`; its I/O implementation is
`firmware/include/Hardware.h`. The hardware profile entry point is
`firmware/include/BoardProfile.h`.

## Upload from the installed setup

1. Close any app connection or serial monitor using the selected COM port.
2. For an initial upload, keep valve/pump loads disconnected. Use **Flash ESP32
   dry run**, **Flash relay board test**, or **Flash full controller (setup
   required)** from the installed shortcuts. The helper asks for the COM port
   and explicit upload confirmation.
3. With an external adapter lacking reset wiring, hold IO0, press/release EN,
   then release IO0 to enter the bootloader. After upload, release IO0 and press
   EN once to run the program. A successful write does not prove an automatic
   reset happened.
4. Open the matching app screen. The relay-bench target uses **Relay board
   test**; the controller targets use the main controller connection. The
   physical target reports that its profile has not been verified.

Setup prepares all three build targets without opening a COM port or uploading.
The helper builds from installed source before upload, so a reviewed custom
profile can be rebuilt later. The separate firmware ZIP includes precompiled
images, offsets and checksums for tools that can flash raw ESP32 binaries; follow
its README and manifest rather than treating `firmware.bin` as a complete image.

## Finish the physical hardware profile

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

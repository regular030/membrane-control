# ESP32 controller firmware

The default build is a **simulation**: `BASU_DRY_RUN=1`. It exchanges the real v1
serial protocol and runs the recipe engine, but never initializes or accesses
relay GPIO, sensor GPIO or I2C. Measurements are explicitly simulated and every
hello/telemetry message reports `simulation: true` and `hardware_verified: false`.
Nothing in this repository establishes that the physical rig is commissioned.

## One-time setup on each Windows computer

The downloaded EXE runs the desktop app. It does not include the firmware build
tools or upload firmware. A fresh clone or source ZIP also has no `.venv` folder;
that folder is created locally and must not be copied from another computer.

Open PowerShell in the repository root, where `pyproject.toml` and `firmware/`
are visible. With Python 3.12 installed, run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "platformio==6.2.0"
```

Python 3.12 is the version used for local project validation. If `py -3.12` is
unavailable, install Python from [python.org](https://www.python.org/downloads/windows/)
or check the installed versions with `py -0p` before choosing an interpreter.
PlatformIO's general requirements are documented
[here](https://docs.platformio.org/en/latest/core/installation/requirements.html).
No virtual-environment activation or PowerShell execution-policy change is needed.
If `.\.venv\Scripts\python.exe` is not recognized, the environment was not created
successfully in the current project folder. Complete this setup before proceeding.

## Build without flashing

From the repository root in PowerShell, with PlatformIO installed in the local
virtual environment:

```powershell
$env:PLATFORMIO_CORE_DIR = Join-Path (Get-Location) 'work/platformio'
.\.venv\Scripts\python.exe -m platformio run -d firmware -e esp32-dry-run
.\.venv\Scripts\python.exe -m platformio run -d firmware -e esp32-physical
.\.venv\Scripts\python.exe -m platformio test -d firmware -e native
```

The physical environment also compiles, but the shipped unverified profile
refuses all physical actuation. These commands do **not** upload firmware.
Native tests require a C++ compiler. The helper uses an existing GNU compiler or
Windows LLVM installation, or `BASU_HOST_CXX`; it does not install a compiler.
The ESP32 platform and ArduinoJson
dependency are pinned in `platformio.ini`; the PlatformIO platform supplies its
Arduino framework and cross compiler.

## First communication test on the 16-relay ESP32 board

This test replaces the board's existing sketch with dry-run firmware. It tests
USB/UART communication only; it does not commission the relays or rig.

1. Leave all pump and valve contact wiring disconnected. Confirm the actual PCB
   input voltage and polarity before applying external power. The seller's
   5-12 V listing and 5 V diagram conflict; 5 V relay-coil markings alone do not
   settle the board's supply rating. Do not apply an unverified 12 V supply.
2. With power off, check the adapter uses **3.3 V TTL** signal levels. Connect
   adapter TX to board RXD0/GPIO3, RX to TXD0/GPIO1 and GND to GND. Do not use
   RS-232 or RS-485 signals. With a separately powered board, leave the adapter's
   3.3 V and 5 V supply outputs unconnected. Use the board header's actual labels,
   not an assumed pin order from a product photo.
3. Close Membrane Control and all serial monitors so they release the port.
   Identify the controller adapter in Device Manager by unplugging/replugging
   that adapter only. The balance's USB-to-RS-232 cable is a separate device and
   has a different COM port. A detected USB adapter does not prove the ESP32 is
   powered or responding.
4. After setup above and confirmed power/wiring, build and upload. Replace `COM3`
   if Device Manager identifies a different controller port:

   ```powershell
   $env:PLATFORMIO_CORE_DIR = Join-Path (Get-Location) 'work/platformio'
   .\.venv\Scripts\python.exe -m platformio run -d firmware -e esp32-dry-run -t upload --upload-port COM3
   ```

   The first build downloads the pinned toolchain and libraries. An initial
   `SUCCESS` for compilation alone is not proof of upload; the upload output must
   show the ESP32 was detected, flash was written and data verified.
5. If the uploader stays at `Connecting...`, hold **IO0/BOOT**, press and release
   **EN/RST**, then release IO0 once the chip connects and writing starts. If it
   times out, enter download mode again and retry the upload. After a successful
   upload, release IO0 and press EN/RST to run the new sketch if it has not reset
   automatically. A TX/RX/GND-only connection generally needs these manual buttons.
6. Open the app, turn desktop Simulation mode off and select the controller COM
   port. Expect **Connected (dry run)**, with simulated readings and outputs.
   This firmware does not intentionally operate any relay GPIO. The scale can
   be connected separately with its own serial settings; its connection is not
   needed to flash the ESP32. The unverified physical build cannot operate the rig.

References: [Espressif UART wiring](https://docs.espressif.com/projects/esptool/en/latest/esp32/esptool/serial-connection.html)
and [manual bootloader instructions](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html).

## First USB bench test with a Freenove WROVER-E

This is a communication test with the separate Freenove development board. It
does not verify the Srliya relay PCB or any rig wiring. The current `esp32dev`
dry-run build targets the classic ESP32 and needs neither camera nor SD/PSRAM
initialization. A board labelled ESP32-S3 needs its own build target instead.

1. Connect the Freenove board with a **data-capable** USB cable. A lit power LED
   proves power only. Check Windows Device Manager under **Ports (COM & LPT)**,
   then unplug/replug the board to identify its port. Freenove's official
   [FNK0060 resources](https://github.com/Freenove/Freenove_ESP32_WROVER_Board)
   include CH340 drivers. Use the driver matching the device actually detected;
   the separately purchased CP2102 relay-board adapter uses a different driver.
2. From the repository root, list ports without opening them:

   ```powershell
   .\.venv\Scripts\python.exe -m serial.tools.list_ports -v
   ```

   If no port appears, stop here and check the cable, USB socket and driver.
   Selecting a different firmware target cannot fix a USB bridge that Windows
   has not detected. No COM port means uploading and the real serial test remain
   unverified.
3. Leave all rig loads and added interfaces disconnected. The dry-run firmware
   leaves camera and SD interfaces unused. If an inserted SD card prevents
   entering download mode, disconnect USB power, remove the card and reconnect.
   Freenove's SD slot uses GPIO2, which affects classic ESP32 download boot mode.
4. After identifying the correct port, build and upload **only the dry-run**
   environment. Replace `COM7` with the port identified above:

   ```powershell
   $env:PLATFORMIO_CORE_DIR = Join-Path (Get-Location) 'work/platformio'
   .\.venv\Scripts\python.exe -m platformio run -d firmware -e esp32-dry-run -t upload --upload-port COM7
   ```

   Uploading replaces the board's existing sketch. If automatic reset cannot
   connect, hold **BOOT/IO0**, press and release **EN/RESET**, then release BOOT
   once the uploader connects. Do not choose the physical environment for this
   test.
5. Close serial monitors before opening the desktop app; only one program can
   own the port. In **Connections and settings**, turn **Simulation mode** off
   to select the real USB port. The connected firmware must still report
   **Connected (dry run)** and simulated pressure/flow/output statuses. The
   balance can use a separate real USB port while the ESP32 stays in dry run.

Camera/SD wiring on the Freenove board differs from the final relay board.
In particular, Freenove's camera uses GPIO21/22; the proposed relay-board I2C
allocation must not be transplanted onto an attached camera interface.
References: [Freenove camera pins](https://github.com/Freenove/Freenove_ESP32_WROVER_Board/blob/main/C/Sketches/Sketch_06.1_CameraWebServer/camera_pins.h),
[Freenove SD pins](https://github.com/Freenove/Freenove_ESP32_WROVER_Board/blob/main/C/Sketches/Sketch_03.1_SDMMC_Test/Sketch_03.1_SDMMC_Test.ino),
[Espressif boot-mode instructions](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html).

## Commissioning gates

All GPIO assignments, shift-register valve bits and ADC channels start at `-1`.
The candidate Srliya 16-channel board is represented by a 16-bit 74HC595 driver.
The seller's sample now identifies data GPIO14, clock GPIO13, latch GPIO12 and
enable GPIO5; these are recorded in the [proposed pin plan](../hardware/relay-board-pin-plan.md).
They do not establish relay bit order, reset wiring or a verified physical profile.
`BoardConfig` also supports a seven-output direct-GPIO board.

To create a reviewed physical profile, provide a header implementing
`basu::compiledBoardConfig()` and select it using the compile definition
`BASU_VERIFIED_PROFILE_HEADER`. The factory `BoardProfile.h` remains unverified.
The profile must explicitly attest `verifiedBoardConfig`, safe valve states and
pressure limit, DAC interface and conditioned sensor calibration. Validation
rejects missing/conflicting pins, UART0/flash pins, duplicated relay bits and
invalid ADC channels. Boot-strapping pins, exposed module pins, OE pull-ups and
power-up relay behavior still require electrical review and bench measurement.

The 74HC595 OE pin is mandatory, with explicit polarity, bit order, unused output
levels, valve mapping and valve polarity. An independently effective hardware
OE/STOP default is required during reset, before firmware can execute. Safe valve
states are process-specific; all-false defaults are placeholders behind a closed
commissioning gate. The pump always commands zero and opens its configured RUN
contact on stop. Confirm that this contact sense actually stops the installed
pump in its selected mode before enabling physical operation.
The current driver controls the pump contact through a separate configured GPIO;
using spare onboard relay 8 for it still requires a driver change and verified
channel mapping. The driver does not control 74HC595 SRCLR: confirm that the
actual board holds it inactive, or add a verified clear-pin interface before
approving a profile. A seller's four-pin sample does not settle that question.

A physical recipe also needs `hardware_approved: true`. Manual control requires
the same verified compiled profile and fresh pressure protection. Neither a
recipe flag nor a desktop checkbox can enable an unverified profile.

## Drivers

- **GP8403/DFR0971:** checked I2C writes use the manufacturer's range/output
  register layout. Both DAC channels are zeroed at initialization; no EEPROM
  output storage is used. The separate pump contact stays stopped while valve
  states and command voltage change. The firmware checks DAC communication;
  an I2C acknowledgement is not proof of an accurate output voltage. Disconnect
  the pump while verifying 0-10 V output and reset/startup behavior.
- **ADS1115:** nonblocking, single-shot, 128 SPS conversions scan up to three
  configured channels. The gain range is +/-4.096 V, but the protected input
  voltage must remain within the actual 3.3 V supply. A 0-5 V sensor or 0-10 V
  pump signal cannot be connected directly. Input scaling, filtering, clamps,
  reference/ground connections and power sequencing are external requirements.
- **Native ADC1:** optionally reads `analogReadMilliVolts()` on reviewed ADC1
  pins. It is an alternative driver, not a claim that the research system's
  analog front end has been built or calibrated.
- **Calibration:** pin volts are converted with `unitsPerVolt` and `offset`;
  reviewed pin-voltage and engineering-unit bounds determine validity. Optional
  rail rejection helps, but cannot prove that a sensor is connected or correct.
  A valid zero-output pressure sensor may require `rejectRails=false` after the
  interface design is reviewed; an ordinary 0-5 V input cannot distinguish zero
  pressure from every open-circuit condition without additional hardware.
  Pump feedback is volts, not measured flow or physical valve-position feedback.

Register sources:
[DFRobot GP8403 implementation](https://github.com/DFRobot/DFRobot_GP8403/blob/master/DFRobot_GP8403.cpp),
[DFRobot module specification](https://wiki.dfrobot.com/dfr0971),
[TI ADS1115 datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf).

## Runtime behavior

See `../protocol/v1.md` for the shared wire contract. UART is 115200 8N1. Frames
are newline-delimited JSON, at most 8192 bytes excluding LF. CRLF is accepted.
Nested/oversized/malformed objects and trailing data are rejected. Strings must
have valid UTF-8 or properly paired Unicode escapes; embedded NUL is rejected.
Unquoted keys, single-quoted strings and non-JSON number spellings are rejected.
Parser errors
whose ID cannot be trusted use response `id: 0`; they do not change outputs.
Serial input work is bounded per loop so a bad stream cannot starve the watchdog.

Recipes have at most 32 steps of 0.1-86400 seconds, repeat 1-100, last at most seven days and contain
explicit V1-V7 states and pump percent. Validation is atomic. A running recipe
cannot be replaced and manual commands cannot override it. Step timings use
unsigned monotonic differences across `millis()` rollover and never call delay.
`remaining_s` is the remaining time in the current step. `cycle` is 1-based while
running and 0 before a run/manual operation. Completion returns to idle with safe
outputs. Startup and reconnection never resume a run.

Only valid `heartbeat` commands refresh the heartbeat. While running/manual,
3000 ms without one stops and latches a fault. Physical operation additionally
requires valid, recent pressure below the compiled limit. `stop` works in every
state and preserves a fault latch; `clear_fault` returns a stopped controller to
idle without restarting. Hardware/I2C failures may require correcting the cause
and resetting the controller to reinitialize the driver.

Telemetry is approximately 4 Hz. Missing, invalid or stale measurements are null.
CSV recording interval belongs to the desktop and does not slow firmware safety
checks. Balance availability is enforced by the desktop because the balance is
attached to the computer; it is not visible directly to ESP32 firmware.

The serial watchdog and software stop are not an independent emergency stop or
certified protection system. Physical shutdown, pressure relief and safe wiring
remain hardware/process requirements.

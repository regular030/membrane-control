# ESP32 controller firmware

The default build is a **simulation**: `BASU_DRY_RUN=1`. It exchanges the real v1
serial protocol and runs the recipe engine, but never initializes or accesses
relay GPIO, sensor GPIO or I2C. Measurements are explicitly simulated and every
hello/telemetry message reports `simulation: true` and `hardware_verified: false`.
Nothing in this repository establishes that the physical rig is commissioned.

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

## Commissioning gates

All GPIO assignments, shift-register valve bits and ADC channels start at `-1`.
The candidate Srliya 16-channel board is represented by a 16-bit 74HC595 driver;
**no pin mapping from a visually similar board has been assumed**. `BoardConfig`
also supports a seven-output direct-GPIO board.

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
Nested/oversized/malformed objects and trailing data are rejected. Parser errors
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

# Unloaded PWM-converter bench example

This **source-only example** measures no sensors and controls no actuators. It
generates candidate **GPIO25**, 3.3 V PWM, **1 kHz**, 12-bit timer resolution to
bench-check the selected [EC Buying B0CPJGFCGR converter](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR)
before the full controller's pressure/profile commissioning. It is a separate
PlatformIO project, not a fifth factory image, GUI shortcut or production mode.
Flashing it replaces the board's current program. Normal app connections do not
understand this example's serial text protocol.

## Disconnect first

Keep **every pump DB15 wire disconnected**, the pump stop circuit isolated,
and **all external relay COM/NO/NC contact wires disconnected throughout**.
Do not connect the pump while this firmware is installed. This example does
not configure relays, pressure/flow/feedback ADCs or a pump-stop GPIO.

Confirm GPIO25 is exposed and suitable on the actual board. With power off,
connect GPIO25 to converter PWM and the reviewed ESP32/supply reference to
converter GND. Power converter VIN only from a verified regulated supply inside
its stated 3.3-12 V range; a nominal 12 V supply needs tolerance/startup checks.
Select the received module's **0-10 V** output range. Its reference is shared,
not isolated. Connect only a voltmeter between converter OUT and GND; keep OUT
disconnected from the pump. See the [pump handoff](../../../hardware/pump-interface.md).

## Build and upload manually on an installed Windows PC

Open PowerShell. The default installer location is shown below; substitute the
actual install folder if changed. These commands use the installer's private
Python/PlatformIO and a separate example project. No global Python is needed.

```powershell
$benchRoot = Join-Path $env:LOCALAPPDATA 'Programs/MembraneControl'
$benchPython = Join-Path $benchRoot 'tools/.venv/Scripts/python.exe'
$benchProject = Join-Path $benchRoot 'firmware/examples/pwm-converter-bench'
$env:PLATFORMIO_CORE_DIR = Join-Path $benchRoot 'tools/platformio'
& $benchPython -I -m platformio run -d $benchProject
```

For a repository checkout, use its `.venv/Scripts/python.exe`, this example
folder, and the checkout's `work/platformio` cache instead. The platform is
pinned to `espressif32@6.12.0`, classic ESP32/Arduino. First-time builds need
Internet access if the required packages are absent.
Keep the source within the complete `firmware` tree: the project reuses
`../../compact_paths.py` for Windows compiler path handling. It does not import
production controller code, require pressure sensors or use the main project.

Before uploading, close the desktop controller connection, every serial monitor
and other program holding the board's COM port. Confirm the disconnections above.
Choose the actual board COM port from Device Manager, then run the explicit
upload command (replace **COM4** if different):

```powershell
& $benchPython -I -m platformio run -d $benchProject -t upload --upload-port COM4
```

For a three-wire USB-UART adapter without automatic reset, hold IO0/BOOT,
press/release EN/RESET, then release IO0 to enter the bootloader before upload.
After upload, leave IO0 released and briefly press EN/RESET to run the example.
Its GPIO starts LOW and channel attachment explicitly uses zero duty. This is
a commanded state, not a measured converter voltage.

Open a **115200 baud** serial monitor sending newline-terminated commands. For
example, this manual command opens only the COM port you specify:

```powershell
& $benchPython -I -m platformio device monitor --port COM4 --baud 115200 --eol LF --filter send_on_enter --echo --no-reconnect
```

## Bench sequence

1. With the pump/relay loads still disconnected, send `0` and measure OUT.
2. Send the exact uppercase phrase `PUMP DISCONNECTED`, press Enter, then send
   **one** of `25`, `50`, `75`, `100` within five seconds. Each positive command
   requires a fresh phrase. The intended output targets are respectively
   **2.5, 5, 7.5, 10 V**; record the actual voltage, ripple and time to settle.
   Timer duty codes are 1024/2048/3072/**4096**; 100% is continuously HIGH.
3. Send `STOP` or `0` to command zero immediately and disarm. Otherwise positive
   output expires after **at most five seconds**, commands zero and disarms.
   A second command while positive is rejected and stops the test; it cannot
   queue or extend an output. Invalid/oversized input also commands zero.
4. Repeat the disconnected measurement after expiry, manual STOP, reset,
   removed PWM, converter/ESP32 power loss and both power-up orders. Include a
   previously nonzero output. Measure both the drop to zero and settling before
   recording an appropriate full-controller `pwmSettleMs` commissioning value.

The firmware cannot detect USB-UART cable removal, converter presence or the
actual analog OUT. The five-second local limit still runs after loss of serial
communication, but **lost PWM or commanded zero is not proof of zero analog
output**. Measure it with the pump disconnected. A reset/power failure can make
GPIO25 high impedance before the program runs. This example has no independent
pump stop contact control and must never operate a connected pump.

After bench work, restore the intended firmware manually with loads still
disconnected. A reviewed production profile, protected/calibrated pressure
input, correct signal returns and independently verified stop interface remain
required before actual pump operation.

The checked ESP-IDF LEDC API supports duty values through `2^resolution` on this
12-bit classic ESP32 timer. Configuration and duty-write return codes are
checked; driver errors lock further testing until reset. See the bundled
ESP-IDF `driver/ledc.h` and [Espressif LEDC reference](https://docs.espressif.com/projects/esp-idf/en/v4.4.8/esp32/api-reference/peripherals/ledc.html).

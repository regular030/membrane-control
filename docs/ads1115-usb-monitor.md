# Separate ADS1115 USB sensor board

The current lab replacement ESP32 also owns the valves and pump. For that
single-board setup use the [full lab rig firmware](lab-rig-ads1115.md), rather
than this optional sensor-only target.

The `esp32-ads1115-usb-monitor` target runs on a second ESP32. It reports real
ADS1115 conversions over USB at 115200 baud and initializes only UART0 and I2C.

| ADS1115 terminal | Connection |
| --- | --- |
| VDD | ESP32 3V3 |
| GND | ESP32 GND and all three divider negative terminals |
| SDA | GPIO22 |
| SCL | GPIO21 |
| ADDR | GND (address `0x48`) |
| A0 | Pressure divider S |
| A1 | Flow divider S |
| A2 | Pump feedback divider S |
| A3, ALERT/RDY | Unused |

SDA22/SCL21 is intentional for the current wiring. Each sensor uses its
existing 5:1 divider. Input voltages must stay within the ADC supply rails.
The reported `volts` field is the voltage at the ADS1115 input after the
divider, without a software zero offset or engineering-unit calibration.

Build from the repository root:

```powershell
python -m platformio run -d firmware -e esp32-ads1115-usb-monitor
```

Select this environment explicitly when uploading to the second board. A fresh
board needs the bootloader, partition table, boot application and firmware from
this build; PlatformIO's upload target includes these files.

On boot the board emits a JSON `hello` with its pins and acquisition settings,
then an `i2c_scan`. `telemetry` arrives five times per second and `heartbeat`
once per second. Every reading has an independent signed raw count, pin voltage,
status and sample timestamp. A failed read clears that channel to JSON `null`.
`sequence` advances for every sampling cycle; `adc_ack` states whether address
`0x48` answered the latest probe. A heartbeat alone does not establish that the
ADC is responding.

Send newline-terminated `HELLO`, `PING`, `STATUS` or `I2CSCAN` over USB to request
identification, a heartbeat/current readings or a full nonreserved-address scan.
The bus runs at 25 kHz. Each channel uses single-ended mode, a +/-4.096 V PGA
range and 128 SPS single-shot conversions, with a bounded completion wait.
Signed conversion counts use 0.000125 volts per count, as specified in the
[TI ADS1115 datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf).

The dashboard automatically opens the paired rig's outgoing Bluetooth port and
the scale on COM6. Connect this optional separate sensor board manually under
**Connections and settings > Optional separate sensor board**. Choose its USB
port, such as COM5, and connect. The board must identify itself as
`membrane-ads1115-monitor` before the app accepts measurements.

The dashboard shows pressure in psi from the supplied certificate, flow in
mL/min using 100 mL/min per ADC volt, and pump drive feedback in volts using
the 5:1 divider. These are marked as estimates. The actual signed ADC voltage
and A0/A1/A2 labels remain visible beside the engineering values. Small negative
ADC offsets near zero display as approximately zero while preserving raw volts;
a larger negative voltage displays directly with a ground-check note.

The graphs and run records use this selected source. Recorded readings include
its identity/status, raw voltages, estimate flag and the original controller
measurements. CSV exports append the raw ADC voltages and source/estimate labels.
Missing, failed or stale readings clear within two seconds instead of falling
back to the relay board's sensor inputs. This independent measurement connection
does not change the rig firmware's output permissions or pressure protection.

# Full lab rig on the replacement ESP32

Use target `esp32-lab-rig-ads1115` for the replacement board. It runs the full
controller, all six valves, pump command/RUN and all three ADS1115 inputs on the
same ESP32. Its Bluetooth name is **MembraneControl-Rig**. This uses Bluetooth
Classic serial (SPP), which Windows exposes as an outgoing COM port.

| Connection | Assignment |
| --- | --- |
| ADS1115 SDA | GPIO22 |
| ADS1115 SCL | GPIO21, 25 kHz |
| ADS1115 ADDR | GND, address 0x48 |
| ADS1115 VDD / GND | ESP32 3V3 / common GND |
| A0 | Unused |
| A1 | Flow divider S |
| A2 | Pump feedback divider S, DB25 14/5 |
| A3 | Pressure divider S (moved from A0) |
| Divider negative terminals | Common ADC/ESP32/sensor return |
| Relay data / clock / latch / OE | GPIO14 / 13 / 12 / 5 |
| V1,V2,V3,V4,V5,V7 | Register bits 0,1,2,3,5,6; no V6 |
| Pump speed converter PWM | GPIO25, 1 kHz |
| Pump RUN contact | Register bit 15, DB25 15/17 |

The profile uses the reported 5:1 dividers and pressure certificate endpoints
0 psi at 0.005 V and 100 psi at 5.004 V before division. Pressure is
`(ADC volts - 0.001) * 500 / 4.999`. The 80 psi stop threshold corresponds to
0.80084 V at A3. Very small ADS zero offsets are treated as zero engineering
units within the explicitly configured 2 mV tolerance; the actual signed raw
voltage is still reported. Missing, failed or stale conversions stay unavailable.

Flow is 100 mL/min per ADC volt; its certificate range is 13–100 mL/min.
Pump feedback is five times the A2 voltage in drive volts. Feedback is the
drive's analog speed command, rather than a measurement of shaft rotation or
delivered flow. Large negative inputs remain invalid engineering readings and
are displayed as their actual ADC voltage.

The confirmed manual pump profile retains a 50% maximum, V1 and V3 open with
other valves off, and a 1500 ms converter settling delay before closing RUN.
Stop opens RUN, sets pump speed to zero and turns all six valve outputs off.
The pressure cutoff is 80 psi. ADS1115 reads near-zero pressure directly, so
the former native-ADC startup timeout is not used.

Build and upload the explicit lab target:

```powershell
python -m platformio run -d firmware -e esp32-lab-rig-ads1115
python -m platformio run -d firmware -e esp32-lab-rig-ads1115 -t upload --upload-port COM5
```

To enroll this new board once, open its USB console at 115200 baud and send
`PAIR` followed by a newline. Select **MembraneControl-Rig** in Windows Add
Bluetooth device. Compare the Windows code with the USB console code and send
`CONFIRM 123456` using the actual six-digit code. The controller saves the bond
and restarts normal operation. Subsequent connections reuse this pairing.

The app detects the new board's outgoing Bluetooth port (peer
`8C94DF4F8AEA`) and connects the scale separately on COM6. COM9 remains the old
board's pairing and may have a different number on another laptop. The optional
separate USB ADC monitor is not used for this full-rig setup. No outputs start
automatically when the app connects.

The lab's `examples/lab-cwf-ads1115.json` preset opens V1/V3, runs the pump at
25% for one minute, then stops the pump and turns the valves off. Import it as
**CWF water test**. Its desired flow is a comparison target, not an automatic
flow controller or a calibration of delivered pump flow.

GitHub Actions builds this lab image as a separately labelled
`MembraneControl-LabRigADS1115-esp32` artifact. Its images, flash support files,
build information and checksums are distinct from the generic factory images.

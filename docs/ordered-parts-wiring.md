# Wiring the ordered HiLetgo dividers and EC Buying converter

Updated 3 November 2026 for Dr. Onita Basu's lab at Carleton University.

Selected parts are **HiLetgo B01HTC4XKY** (five passive voltage-divider modules,
use three) and **EC Buying B0CPJGFCGR** (PWM to 0-10 V command converter).
The later OSEPP/DFR1036 shopping alternatives are not the selected build.

## What is ready in the software

GitHub was checked on 3 November: **v0.1.16** is the newest published release.
It includes normal sensor-independent control of V1, V2, V3, V4, V5 and V7,
serial recovery, the PWM converter driver, analog input support and a separate
unloaded PWM bench example. It does **not** include a completed, calibrated
sensor/pump profile for this wiring.

The factory normal image leaves pressure, flow and pump feedback unconfigured;
its full hardware profile is not validated. A wire alone cannot enable readings.
The current source initializes ADC acquisition only after the complete full
profile validates. The existing example only selects pressure GPIO34; it is an
unverified template, not a finished configuration. This guide records the new
flow/feedback assignments without claiming that the released image uses them.

The remaining work is to configure and calibrate the three inputs, select the
PWM backend, complete the pump stop interface and grounding, measure converter
settling, and finish process/fault settings. The legacy seven-slot full-profile
map also needs an explicit unused V6 policy; it must never energize absent V6
or unused bit 4. Existing normal manual valve control is already configured.

This guide is a source documentation update. It does not alter the v0.1.16 EXE
or firmware archive and does not upload or enable anything on the lab board.

## Board pins

Use the printed labels on the same breakout-header side as GPIO35. GPIO names
are not physical hole numbers. **Leave GPIO35 unused** following the reported
possible overvoltage; the health of the other inputs still needs checking.

| Function | ESP32 breakout label | Connection |
| --- | --- | --- |
| Pressure measurement | **IO34 / GPIO34** | Divider 1 S output |
| Flow analog measurement | **SVP / VP / GPIO36** | Divider 2 S output |
| Pump speed feedback measurement | **SVN / VN / GPIO39** | Divider 3 S output, after resolving pump analog references |
| Pump speed command PWM | **IO25 / GPIO25** | EC Buying PWM input |
| Pump start/stop driver | **IO26 / GPIO26** | Separate 3.3 V-compatible isolated contact-interface input |
| Low-voltage reference | **GND** | Sensor/divider references; pump references need the review below |

GPIO34, GPIO36 and GPIO39 are ADC1 inputs. They are input-only. The onboard
relay chain already uses GPIO14/13/12/5; leave those traces alone.

## There is no 3.3 V switch on the HiLetgo board

It is a fixed approximately **5:1 resistor divider**. Its signal output is
approximately input / 5, rather than a regulated 3.3 V supply.

| Measured signal at screw input | Expected S output |
| --- | --- |
| 0 V | 0 V |
| 5 V | 1 V |
| 10 V | 2 V |

The normal pressure/flow ranges therefore become 0-1 V and pump feedback becomes
0-2 V. The label "0-25 V" does not make a 25 V input suitable for the ESP32:
25 V would produce about 5 V at S. Do not connect an unscaled 5/10 V signal to
an ESP32 input. A passive divider provides no isolation or comprehensive fault
protection. Verify ratio, loading and filtering on the received module.

### Each divider's terminals

With the GPIO disconnected, identify the received module's labels:

| Module terminal | Purpose |
| --- | --- |
| Screw **VCC / positive** | The signal being measured. This is **not** the sensor's red power wire. |
| Screw **GND / negative** | That signal's return |
| Header **S** | Divided analog output to the chosen ADC input |
| Header **-** | Signal reference to ESP32 GND, after checking continuity to screw GND |
| Header **+** | Leave disconnected until its actual PCB connection is established |

The seller text says to supply header +, while common passive variants leave
it unused. The listing does not resolve that revision ambiguity. Do not guess
that + is a 3.3 V selection or connect it to 12 V. Check the unpowered traces
or continuity before making that connection. A true two-resistor divider needs
no separate supply. With ESP32 disconnected, verify 5 V at the screw input gives
about 1 V between S and -, and 10 V gives about 2 V where applicable.

## Pressure and flow wiring

Keep each sensor's red power wire on the appropriate external regulated supply.
The identified Omega PX309-100G5V accepts 9-30 V power and outputs 0-5 V.
The McMillan 101 T option accepts 11.5-15 V and has a 0-5 V analog output.
Verified regulated 12 V is within both supply ranges; neither sensor should
be powered from an ESP32 GPIO or from the divider S output.

| Sensor wire / terminal | Connect to |
| --- | --- |
| Pressure red, power + | External regulated +12 V |
| Pressure black, return | Supply negative / reviewed ESP32 GND and divider 1 screw GND |
| Pressure white, analog output | Divider 1 screw VCC |
| Divider 1 S | **IO34** |
| Divider 1 header - | ESP32 GND |
| Flow red, power + | External regulated +12 V |
| Flow black, return | Supply negative / reviewed ESP32 GND and divider 2 screw GND |
| Flow white, analog output | Divider 2 screw VCC |
| Divider 2 S | **SVP / GPIO36** |
| Divider 2 header - | ESP32 GND |

These colors match the recorded harness; trace any replacement cable instead
of assuming its colors. Insulate the flow sensor's separate unused pulse wire.
Its specified pulse peak is 7.5 V, not a direct 3.3 V logic input. This plan
uses analog output, not I2C or pulse counting.

## Pump signals and references

For the Cole-Parmer **75211-30 DB15** connector:

| Pump circuit | Signal pin | Its specified return |
| --- | --- | --- |
| Voltage speed command into pump | **1** | **3** |
| Voltage speed feedback out of pump | **9** | **5** |
| Start/stop contact | **10** | **12** |

The old four labels identify 1, 9, 10 and 12, but do not establish where analog
returns 3 and 5 go. Locate those returns in the actual connector/harness.
Do not substitute pin 12 for both analog returns.

### Resolve the common-ground arrangement before attaching the pump

Both ordered modules are **nonisolated**. Converter GND tied to pump return 3
and feedback-divider GND tied to return 5, each referenced to ESP32 GND,
would **externally join pump pins 3 and 5**. Confirm that this is permitted for
the drive and installation, or use appropriate isolated analog interfaces.
The following pump terminal assignments describe the planned circuits; they
do not establish that this common-reference arrangement has been verified.
Keep the pump signals disconnected until that question and harness returns
are resolved. Pin 12 remains on the isolated start/stop contact side.

### Speed command: ESP32 to EC Buying converter to pump

| From | To |
| --- | --- |
| GPIO25 | Converter **PWM** |
| Verified regulated supply within **3.3-12 V** | Converter **VIN** |
| Reviewed supply/ESP32 reference | Converter **GND** |
| Converter **OUT** | Pump DB15 **1**, after reference and output checks |
| Converter output reference / GND | Pump DB15 **3**, after reference checks |

Select the converter's **0-10 V output** range. Its VIN is its module power;
the pump's label VIN denotes its speed-command signal. They are not the same
connection. A nominal 12 V supply is at this module's advertised maximum, so
its actual tolerance/startup must stay within the rating. Do not copy the
3.3-5 V-only power instructions for the unselected DFR1036 alternative.

The source PWM backend proposes 1 kHz. First use the separate
[unloaded bench example](../firmware/examples/pwm-converter-bench/README.md)
with the pump disconnected and measure OUT/GND at 0/25/50/75/100% duty.
Intended outputs are 0/2.5/5/7.5/10 V. This bench example replaces the current
program when flashed and does not speak the normal app's protocol.

### Speed feedback: pump to divider 3 to ESP32

After resolving the references above, pump DB15 **9** is the 0-10 V signal
to divider 3 screw VCC; pump **5** is that signal's return to divider 3 GND.
Divider 3 **S** goes to **SVN / GPIO39**; its - joins the reviewed ADC reference.
The nominal result is 0-2 V at GPIO39. This is not the converter OUT signal.

### Start/stop requires a separate contact interface

Neither ordered module supplies the pump's isolated start/stop contact.
Use GPIO26 only on the control side of a suitable **3.3 V-compatible isolated
contact interface**. Its isolated contact terminals connect across pump DB15
**10 and 12**. Confirm its exact input, supply and stopped/default behavior.
Do not connect GPIO26, sensor +12 V or the valve power bus directly to 10/12.
Pump operation cannot be considered fully wired until this interface exists.

## USB connections and installed valves

- Retain the existing USB-UART connection: adapter TX to ESP32 RX/GPIO3,
  adapter RX to ESP32 TX/GPIO1, and GND to GND, using 3.3 V TTL signals.
  With the board externally powered, leave adapter power outputs disconnected.
- The Adam Nimbus USB-B **I/O** port goes directly to the PC through a data
  cable. It takes no ESP32 GPIO. Select its separate COM port in the app.
- Retain the confirmed valve relay mapping: V1->bit0, V2->bit1, V3->bit2,
  V4->bit3, V5->bit5, V7->bit6. No V6, bit4 unused, LOW off.
  See [normal valve controls](normal-valves.md). The photographed coils are
  110-120 VAC loads; the 12 V controller supply does not power them. Keep their
  load wiring separate from these low-voltage sensor/pump interfaces.

## How the code knows about a sensor

These analog sensors do not send an identification or "connected" packet.
The ESP32 ADC measures a voltage repeatedly. Firmware then applies the measured
divider ratio and sensor calibration to obtain pressure, flow or feedback.

An unplugged ADC wire can float or sit near zero; a connected sensor can also
legitimately output zero. Therefore a plausible voltage alone cannot establish
cable presence. A 5:1 divider is not a sensor-presence detector. Check a known
physical change against both the meter voltage and the reported value.

The app should distinguish **input not configured**, **uncalibrated**,
**reading received**, **out of range** and **stale**. The firmware already has
those diagnostics, but the factory inputs are unconfigured. "Reading received"
means fresh acquisition passed its configured checks, not a verified physical
cable handshake. The USB ESP32 and balance connections use different digital
protocols; do not apply their connection semantics to analog sensor wires.

## Sources and verification limits

- [HiLetgo seller listing](https://www.amazon.ca/dp/B01HTC4XKY) and the user's
  supplied product-description screenshot: fixed 5:1 division; header + revision
  remains unresolved.
- [EC Buying seller specification](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR):
  3.3-12 V supply, 3.3 V PWM compatibility, 0-10 V output option, nonisolated.
- [Espressif pin definitions](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.html).
- [Omega datasheet](https://assets.omega.com/pdf/test-and-measurement-equipment/pressure/pressure-transducers/PX309.pdf).
- [McMillan manual](https://www.mcmflow.com/wp-content/uploads/2015/02/101-M002.pdf).
- [Manufacturer-authored pump manual, mirrored copy](https://manualmachine.com/coleparmer/7521130/15945005-instruction-manual/),
  printed pages 12-13.

No lab port was opened, wiring measured, firmware uploaded or physical output
operated while preparing this guide. Pin assignments are a design handoff;
they do not establish the health of the board after the reported overvoltage.

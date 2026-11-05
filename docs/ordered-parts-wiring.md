# Wiring the installed pump, pressure sensor and flow sensor

For Dr. Onita Basu's lab at Carleton University. The current plan uses the
**Masterflex 75211-70 DB25** pump, the
[Garosa 3.3P-10V PWM converter](https://www.amazon.ca/Voltage-Module-Voltage-Converter-Digital-Analog/dp/B07WZNV1V2) and
**HiLetgo B01HTC4XKY** passive divider modules.

The factory controller can operate the six confirmed valves manually. Pump
control and analog acquisition need a reviewed full hardware profile with
calibrated inputs, a verified spare pump relay and measured converter settling.
The pump relay bit remains unassigned.

## Board pins

Use the printed labels on the same breakout-header side as GPIO35. GPIO names
are not physical hole numbers. **Leave GPIO35 unused** following the reported
possible overvoltage; the health of the other inputs still needs checking.

| Function | ESP32 breakout label | Connection |
| --- | --- | --- |
| Pressure measurement | **IO34 / GPIO34** | Divider 1 S output |
| Flow analog measurement | **SVP / VP / GPIO36** | Divider 2 S output |
| Pump speed feedback measurement | **SVN / VN / GPIO39** | Divider 3 S output, after resolving pump analog references |
| Pump speed command PWM | **IO25 / GPIO25** | Garosa PWM+ |
| Pump start/stop | **Spare onboard relay**, bit to be verified | GPIO26 is reserved only for the external contact-driver alternative |
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

## Pump connections

The [75211-70 manual](https://manualmachine.com/masterflex/7521170/15984751-instruction-manual/) gives the DB25 assignments.
Use the actual molded pin numbers. With the pump unplugged and all electronics
disconnected, trace the six soldered wires and any DB25-to-DB15 adapter. See the
[pump interface](../hardware/pump-interface.md) for the required adapter map.

| Pump DB25 wire | Connect to |
| --- | --- |
| **1** speed command | Garosa **AO+** |
| **3** command return | Garosa **AO-** |
| **15** start/stop | Verified spare relay **COM** |
| **17** start/stop reference | Same relay **NO** |
| **14** speed command output | Divider 3 screw **VCC**, after grounding review |
| **5** output return | Divider 3 screw **GND**, after grounding review |

### Garosa power and PWM

With its labels readable, the pictured converter terminals from left to right
are **PWM-**, **PWM+**, **Supply+**, **Supply-**, **AO-** and **AO+**.

| Converter terminal | Connect to |
| --- | --- |
| PWM- | ESP32 **GND** |
| PWM+ | ESP32 **IO25** |
| Supply+ | Regulated **+24 V DC** |
| Supply- | Converter supply negative |

Set the **5V input jumper** with power off. The selected 3.3P-10V variant uses
3.3 V PWM on this setting. The listing specifies 15-30 V supply and the board
is marked 12-30 V. Use 24 V to satisfy both. Keep 24 V off ESP32 pins and the
12 V sensor supply. ESP32 IO25 and pump DB25 pin 25 are distinct. Pump pin 25
is unused.

With the pump disconnected, use the
[unloaded example](../firmware/examples/pwm-converter-bench/README.md) to
measure AO+ relative to AO- at 1 kHz and 0%, 50%, and 100% duty. The targets
are about 0, 5 and 10 V, with a maximum of 10 V. Check zero after PWM loss and
power cycling, and measure settling before approving the profile.

### Divider 3 and pump reference

Divider 3 **S** goes to **SVN / GPIO39**. On the verified passive divider,
**-** connects to ESP32 GND and **+** stays open. Confirm the ratio and
continuity between the two ground terminals with the ESP32 disconnected.
The pump's 0-10 V output should become approximately 0-2 V at S.

Leave pump pins 14 and 5 disconnected until reference review. Pin 5 is pump
earth. The divider connects it to ESP32 ground. If the converter, USB or
shared supply already connects ESP32 ground to pin 3, adding the divider
joins pin 3 to pump earth. Verify the actual paths or use an isolated feedback
interface. Pin 17 is the dry-contact reference. Keep it on the relay side.

### Pump contact and drive settings

Use COM and NO from one physically unused relay after identifying its bit with
the [unloaded relay test](relay-board-test.md). Keep the selected contact pair
free of any mains COM jumper and external voltage. The factory firmware has
no selected pump bit. An external 3.3 V-compatible contact driver on GPIO26
remains an alternative, with its dry contacts connected to the same 15/17 pair.

On the pump, choose **Voltage Input**, exit to **Continuous Pump Mode**, set
**START/STOP required ON**, and turn **AUTO START OFF**. With START/STOP set
to its factory default OFF, a sufficient analog command can run the drive with
the contact open. Confirm the settings and stop response during commissioning.

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
- [Garosa 3.3P-10V seller specification](https://www.amazon.ca/Voltage-Module-Voltage-Converter-Digital-Analog/dp/B07WZNV1V2).
- [Espressif pin definitions](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.html).
- [Omega datasheet](https://assets.omega.com/pdf/test-and-measurement-equipment/pressure/pressure-transducers/PX309.pdf).
- [McMillan manual](https://www.mcmflow.com/wp-content/uploads/2015/02/101-M002.pdf).
- [Masterflex 75211-70 operating manual, manufacturer-authored mirror](https://manualmachine.com/masterflex/7521170/15984751-instruction-manual/),
  A-1299-1142 Edition 02, pp. 3-21 to 3-24.

No lab port was opened, wiring measured, firmware uploaded or physical output
operated while preparing this guide. Pin assignments are a design handoff;
they do not establish the health of the board after the reported overvoltage.

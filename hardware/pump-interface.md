# Cole-Parmer 75211-30 pump interface

The user identified the installed drive as **Cole-Parmer 75211-30**, with a
**60-3600 RPM, 0.1 HP** nameplate. This is the current DB15 digital gear-pump
profile, separate from the later Masterflex L/S/DB25 equipment.

## Manufacturer-documented signals

Cole-Parmer/Barnant operating manual **A-1299-0853, Edition 03** explicitly
covers models 75211-30 and 75211-35. Its remote-control section and DB15 diagram
on printed pages 12-13 document a 0-10 V voltage command, a separate 0-10 V speed
feedback signal and a contact input for remote start/stop. Select/check the
**V** mode for voltage control; current-loop modes are separate options.

The diagram was visually checked, including the individual signal returns:

| Function | DB15 signal | DB15 return | ESP32-side interface role |
| --- | --- | --- | --- |
| Speed command into pump | Pin 1 (+) | Pin 3 (-) | Suitable 0-10 V DAC/output stage, using the input's specified return |
| Speed feedback from pump | Pin 9 (+) | Pin 5 (-) | Protected/scaled ADC input, using the output's specified return |
| Remote start/stop | Pin 10 | Pin 12 | Suitable isolated dry-contact interface across the pair |

These are connector pin numbers, not wire colors or positions along an ESP32
header. Check molded connector numbers and continuity with equipment disconnected
before changing the harness. The diagram does not show pins 3, 5 and 12 joined;
do not substitute pin 12 for both analog returns or blindly join the returns.

The user's follow-up photos repeat the four cable tags with both an **Old
DB15** column and a **New DB25** column. Use the old DB15 numbers for this
75211-30. The DB25 annotations do not establish another drive's pinout.

The earlier cable tags listed **1, 9, 10 and 12**. If that is the complete
harness, the documented analog returns are absent unless they are connected
elsewhere. Trace the actual circuit before migrating it. Do not apply Arduino
VIN, the relay-board supply or a GPIO output to the start/stop pair.

With the harness disconnected from both drive and controller, a continuity
check can establish whether DB15 pins 3 or 5 are already wired to the labelled
ground conductor inside the plug. Record any existing connections rather than
adding bridges based on the generic GROUND tag. The photos alone do not show
the internal wiring or an analog scaling stage.

The operating range is documented; the installed mode, actual cable continuity,
reference/ground arrangement and calibration still need verification. This is
not confirmation of a complete physical wiring profile or an absolute maximum
input-voltage damage threshold.

## Why the old Arduino can still have worked

The old board was an Arduino Mega 2560 with 5 V I/O. The user confirms the
notebook's direct connections: orange pump speed input to **D3**, white pump
feedback to **A8**, blue to GND beside AREF/D13, and red start/stop to the
Arduino VIN header. Do not assume an unseen external DAC or conversion board.
D3 supports PWM;
`analogWrite()` does not generate a 10 V analog command by itself. A lower
command range or external conditioning could explain the old setup. The old
bridge code does not identify that circuitry. The pump manual does not establish
raw PWM as a supported replacement for its DC voltage input.

Likewise, a 0-10 V feedback capability does not prove that 10 V was ever present
at the old Arduino input. Any existing divider or protection must be traced.
Do not connect raw pump feedback directly to an Arduino or ESP32 analog input.

A GP8403/DFR0971 remains a candidate 0-10 V command source. Its VOUT terminal
would drive **pump pin 1**, referenced through the verified interface to
**pump pin 3**. Pump pin 9 is an output to an ADC, not a destination for the DAC.
Input/output isolation and returns must be resolved before choosing a common-
ground module arrangement. The shipped firmware keeps its profile unverified.

## Handoff: connecting the DFR0971 when it arrives

Use the **DFRobot Gravity DFR0971, GP8403, two-channel I2C 0-10 V DAC**.
The [manufacturer's module specification](https://www.dfrobot.com/product-2613.html)
permits a 3.3-5 V supply and 2.7-5 V I2C high levels. For this ESP32 plan,
power the module from a verified **3.3 V** rail so its I2C pull-ups also use
3.3 V. The module generates the higher analog output voltage internally;
do not connect the relay board's 12 V supply to the DAC's VCC terminal.

**First, with the pump and controller unplugged and the DB15 harness
disconnected at both ends:** identify the molded connector pin numbers and
record continuity from pins **1, 3, 5, 9, 10 and 12** to each wire. Check for
existing bridges and any divider/filter/amplifier. Repair or replace the
harness if the separate returns cannot be identified. Do not infer connections
from the four cable tags alone.

Then use this proposed connection table, subject to review of the actual
relay-board header and pump grounding:

| From | To | Check |
| --- | --- | --- |
| ESP32 verified 3.3 V rail | DFR0971 VCC/+ | Module supply, not pump motor power |
| ESP32 GND | DFR0971 GND/- | Logic and DAC reference |
| ESP32 GPIO21 | DFR0971 SDA/D | Proposed I2C data pin; confirm header label |
| ESP32 GPIO22 | DFR0971 SCL/C | Proposed I2C clock pin; confirm header label |
| DFR0971 VOUT0 | Pump DB15 pin 1 (+) | Analog speed command |
| DFR0971 output GND | Pump DB15 pin 3 (-) | Only after the input-reference/grounding review |

The DAC schematic shares analog-output GND with logic GND: **this module is
not an isolated output stage**. The last connection therefore references the
pump input to ESP32/USB ground. If that is unsuitable for the installed pump
and laptop grounding, use a reviewed isolated interface instead. This table
does not authorize joining pump returns **3, 5 and 12**.

Keep the pump disconnected for the first DAC test. Configure I2C address
**0x58** only if the address switches match the manufacturer's table; select
the **0-10 V output range** and channel **0**. With a voltmeter between VOUT0
and output GND, verify commanded 0 V and several nonzero values, then verify
return to 0 V on stop/reset and after a power cycle. Use a separate reviewed
bench procedure: the normal app's shipped physical profile is locked, and
the relay-board test firmware does not drive this DAC.

The remaining pump connections are separate:

- **Start/stop:** a suitable isolated signal contact across **DB15 10/12**,
  electrically separate from any mains valve relay bus. No external voltage
  is applied to this pair. Its GPIO/driver and stop behavior still require a
  reviewed physical profile; buying the DAC alone does not complete this path.
- **Feedback:** **DB15 9 (+)/5 (-)** goes through a separately designed,
  protected/scaled ADC interface. Leave it insulated and disconnected until
  that interface is reviewed. Do not connect it to the DAC output or raw GPIO.

Only after the harness, grounding, stop contact, pressure input, output mapping
and calibration pass commissioning should the pump be connected and operated
in its verified **V** mode. GPIO21/22 are proposed profile assignments, not
confirmation that the shipped firmware or a header position is configured.

## Recorded old wiring

| Notebook wire | Recorded Arduino connection | What must be checked |
| --- | --- | --- |
| Orange, pump VIN | Digital 3 | Continuity to DB15 pin 1, input return pin 3 and any PWM/voltage conditioning |
| White, pump VOUT | Analog A8, confirmed by the user | Continuity to pin 9, output return pin 5 and actual feedback voltage |
| Blue, ground | GND beside AREF/13; cable tag says DB15 pin 12 | This is the documented start/stop return; check where analog returns 3/5 went |
| Red, start/stop | Arduino VIN | Verify pin 10/contact circuit; do not copy the old power-terminal connection |

The archive contains generic NI LIFA bridge code, not native LabVIEW VIs. In
`10. LabVIEWInterface-C UF membrane codes-OB_RR.txt`, lines 140-145 configure or
write host-selected digital pins; lines 186-199 read a host-selected analog
channel or perform a host-selected PWM write. The base sketch's custom sections
are empty. The six LabVIEW document images show front panels, not pin constants.
The notebook's D3 connection and Duty Cycle (0-255) indicator suggest PWM, but do
not recover the full circuit. Pressure A10 and flow A12 also come from the
notebook rather than fixed bridge assignments.

## Amazon PWM-converter alternative

The user's preference is Amazon rather than DigiKey because of delivery.
An actual Canadian listing is
[EC Buying PWM-to-voltage converter, B0CPJGFCGR](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR).
Its own product description specifies 3.3-12 V module supply, 3.3-24 V PWM
high level, 22 Hz-20 kHz input, and selectable 0-5/0-10 V output. It explicitly
states no isolation and a shared supply/signal/output ground. Price and delivery
to the lab address were not exposed; check the offer before ordering.

This is a candidate for **ESP32 3.3 V PWM -> converter -> pump DC speed input**.
A regulated 12 V supply is within its stated module-supply range. It avoids
depending on the pump to interpret raw PWM. It does not use I2C and **cannot be
operated by the GP8403 driver in release 0.1.12**; a separate PWM output driver,
reviewed output pin and startup/watchdog tests must be added before use.

The intended pump-side output remains OUT to DB15 pin 1, with the correctly
reviewed module reference to pin 3. Because the converter is not isolated,
resolve its reference to ESP32/USB and pump grounds before connecting it.
First test it with the pump disconnected: verify its range selection, output
at several duty cycles, zero command, reset, loss of PWM and power sequencing.
Do not assume loss of PWM guarantees a zero output. The independent pump
stop contact remains required. Feedback 9/5 still needs protected/scaled ADC
acquisition; the command converter does not protect the feedback input.

The original archive was re-read for this clarification. In its
`10. LabVIEWInterface-C UF membrane codes-OB_RR.txt`, line 187 calls
`analogRead(command[2])` and line 199 calls
`analogWrite(command[2], command[3])`. LabVIEW supplies the channel/pin and duty
value at runtime. The ZIP has no native `.vi` files, so it cannot recover those
host-side constants or scaling. The notebook supplies the physical mapping.
Pressure A10 and flow A12 are analog channels, not I2C connections.

## Revision and calibration

The user's 60-3600 RPM nameplate agrees with the service manual's model listing.
The older operating manual's specification page lists 180-3600 RPM. Preserve
that revision discrepancy and do not assume an exact volts-to-RPM or mL/min
conversion. Verify the installed drive's behavior and pump-head calibration.

## Sources

- [Cole-Parmer/Barnant operating manual, mirror](https://manualmachine.com/coleparmer/7521130/15945005-instruction-manual/), A-1299-0853 Edition 03, printed pages 12-13 and 21.
- [Cole-Parmer/Barnant service manual, mirror](https://www.manualslib.com/manual/1449189/Cole-Parmer-75211-30.html), model listing identifies 75211-30 at 60-3600 RPM.
- [Arduino Mega 2560 specifications](https://store.arduino.cc/products/arduino-mega-2560-rev3) and [PWM guide](https://support.arduino.cc/hc/en-us/articles/9350537961500-Use-PWM-output-with-Arduino).
- [DFRobot GP8403/DFR0971 specification](https://wiki.dfrobot.com/dfr0971).
- [DFRobot DFR0971 schematic, first page](https://dfimg.dfrobot.com/wiki/19365/DFR0971_gp8403-dac-module_schematics_V1.0.pdf), shared logic/output ground and I2C pull-ups to VCC.

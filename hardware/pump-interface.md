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

The old board was an Arduino Mega 2560 with 5 V I/O. D3 supports PWM;
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

## Recorded old wiring

| Notebook wire | Recorded Arduino connection | What must be checked |
| --- | --- | --- |
| Orange, pump VIN | Digital 3 | Continuity to DB15 pin 1, input return pin 3 and any PWM/voltage conditioning |
| White, pump VOUT | Analog A8 or A9; handwriting unclear | Continuity to pin 9, output return pin 5 and existing input scaling |
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

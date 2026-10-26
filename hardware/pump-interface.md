# Cole-Parmer 75211-30 pump interface

The installed drive is **Cole-Parmer 75211-30**, identified by the user as
60-3600 RPM, 0.1 HP. This plan uses its **DB15** connector. The later Masterflex
L/S / DB25 equipment is a separate profile.

The selected speed-command interface is the
[EC Buying PWM-to-voltage converter, Amazon.ca B0CPJGFCGR](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR).
Order **one** for this pump. A second GP8403 DAC or replacement Arduino is not
needed for this command path. The converter adds the speed command; the pump
still needs a separate stop contact and protected analog acquisition.

## Pump signals and the existing harness

The manufacturer-authored Cole-Parmer/Barnant operating manual A-1299-0853,
Edition 03, covers 75211-30 and 75211-35. Its printed pages 12-13 give:

| Function | DB15 signal | DB15 return | New interface |
| --- | --- | --- | --- |
| DC speed command into pump | Pin 1 (+) | Pin 3 (-) | Converter OUT and reviewed output reference |
| Speed feedback from pump | Pin 9 (+) | Pin 5 (-) | Protected/scaled ADC input |
| Remote start/stop | Pin 10 | Pin 12 | Isolated dry contact across this pair |

Check the drive's **V** remote mode for voltage control. Connector pin numbers
are not wire colors or positions on an ESP32 header. Verify the molded numbers
and continuity with the pump, controller and harness disconnected. The diagram
does not show pins 3, 5 and 12 joined; do not bridge their returns by assumption.

The four existing tags identify **DB15 1, 9, 10 and 12**. Trace where analog
returns **3 and 5** go before adding a ground connection. They may be connected
inside the plug or elsewhere; the photos do not establish that. Repair/replace
the harness if the correct returns cannot be identified. Use the tags' old
DB15 numbers; their new DB25 column does not apply to this drive.

## What can be prepared now

With all equipment unplugged, label and continuity-check the harness, locate
the ESP32 breakout labels, and plan a secured low-voltage terminal strip for
power, PWM, analog command and feedback. Preserve the already established
USB-UART wiring. Keep all pump signal wires insulated until their interfaces
and references are checked. Keep this low-voltage wiring separate from the
110-120 VAC valve contacts and their COM bus.

The user has observed LOW = relay off and HIGH = relay on. That observation
does not identify which shift-register bit drives each physical valve terminal,
or establish reset/OE behavior and safe fluid routing. Record those separately
in the [bare-board mapping procedure](../docs/relay-board-test.md).

## Connecting the EC Buying converter when it arrives

The seller's own specification lists a **3.3-12 V supply**, **3.3-24 V PWM high
level**, 22 Hz-20 kHz input and selectable 0-5/0-10 V output, default 0-10 V.
It is **not isolated**: its power, PWM and analog output share GND. These are
seller specifications, not measurements on the received unit. Confirm the
actual terminal labels and output-range jumper/pad before wiring.

Use a regulated supply whose actual output, including tolerance and startup,
stays inside the stated range. **12 V is its stated maximum, not spare margin**;
verify the existing supply rather than assuming a nominal 12 V label is enough.
Do not substitute a 15 V or 24 V supply for this converter. This supply rating
is separate from the unresolved relay-board input rating.

| From | To | Purpose / prerequisite |
| --- | --- | --- |
| Verified regulated DC supply, within 3.3-12 V | Converter VIN | Module power; not pump motor power |
| Supply negative and ESP32 GND, after reference review | Converter GND | Common power/PWM/output reference; resolve ESP32/USB and pump grounding first |
| ESP32 **GPIO25**, proposed | Converter PWM | 3.3 V logic, proposed 1 kHz PWM; confirm exposed header and reviewed profile |
| Converter OUT | Pump DB15 **pin 1 (+)** | Connect only after the unloaded output tests below |
| Converter GND / reviewed output reference | Pump DB15 **pin 3 (-)** | Nonisolated connection; review before joining to pump reference |

The converter performs **PWM -> DC analog voltage**. Do not wire raw ESP32 PWM
directly to the pump's voltage-command input. GPIO25 is a candidate assignment,
not a physical header position or an already approved profile. The converter
has no SDA/SCL connection. The GND row does not authorize joining pump returns
3, 5 and 12. If a common-ground interface is unsuitable for the installed
pump/laptop arrangement, use a reviewed isolated analog interface instead.

### First bench checks: pump disconnected

1. Disconnect the DB15 harness from the pump and keep its start/stop circuit
   open. Verify the converter's supply and **0-10 V** range selection.
2. With a voltmeter between converter OUT and GND, request duty cycles
   **0%, 25%, 50%, 75%, 100%**. The intended corresponding command voltages are
   **0, 2.5, 5, 7.5, 10 V**. Record the actual values, settling and ripple;
   validate the chosen PWM frequency rather than treating these targets as
   measured output.
3. Verify zero command and the separate stop contact on STOP, communication/
   heartbeat loss, controller reset, unplugged PWM and converter/ESP32 power
   sequencing. Include removal of pulses from a nonzero command and restoration
   of each power source. Do not assume loss of PWM forces the analog output to
   zero or that a stopped app proves the motor stopped.
4. Keep the pump disconnected until these checks, harness continuity, references,
   signal protection, stop behavior and the required pressure channel pass review.
   Use a dedicated reviewed bench procedure; the ordinary factory physical
   profile is locked. Neither relay/valve test firmware drives this converter.

## Separate pump stop and feedback paths

**Start/stop:** use an isolated dry-contact interface with a verified 3.3 V
ESP32-compatible control input, rated for the pump's signal-contact circuit.
Its isolated contact side connects only across **DB15 10/12**. Proposed
**GPIO26** controls the interface, subject to profile review; it never connects
to the pump pins directly. Keep its contact wiring electrically separate from
the mains valve COM bus. Never apply the old Arduino VIN connection, relay-board
supply, GPIO voltage or 120 VAC to this pair. Verify that interface power loss,
reset and STOP leave the pump in its documented stopped state.

The current driver uses a separate `pumpContactPin`; it does not pack pump RUN
into an unused onboard 74HC595 bit. Do not substitute a spare valve-board
channel without a corresponding reviewed driver and separation design.

**Feedback:** pump **DB15 9 (+)/5 (-)** goes through a protected, range-matched
0-10 V input-conditioning stage before an ADC. This is a measurement coming
from the pump, not the converter output. The PWM converter provides no feedback
input protection. Pressure and flow also need their own conditioned 0-5 V
inputs. See [analog acquisition](relay-board-pin-plan.md#analog-measurements-and-pump-command).

## Firmware profile and operation

The PWM output is an alternative backend selected in a **reviewed compiled
production profile**, not a GUI checkbox or a substitute for commissioning.
The GP8403 backend remains the default for existing profiles. The selected
converter does not need the GP8403 or its I2C connection. An ADS1115, if selected
for measurements, still needs its own I2C connection and verified conditioning.

The maintainer's compiled `BoardConfig` uses these fields for the selected
backend. Values below are proposed assignments, not a ready-to-flash profile:

| Field | Selected/proposed value | Commissioning meaning |
| --- | --- | --- |
| `pumpCommandSource` | `PumpCommandSource::PwmConverter` | Explicitly selects PWM instead of the default `Gp8403` |
| `pwmConverterInterfaceVerified` | Defaults to `false` | Only a reviewed profile can approve the measured interface; changing the flag alone is not verification |
| `pumpPwmPin` | `25`, candidate | Must be exposed and free of board/peripheral conflicts |
| `pumpPwmChannel` | `0` | Reviewed LEDC channel; no conflicting PWM use |
| `pumpPwmFrequencyHz` | `1000` | Within the selected module's stated input range; verify actual output |
| `pumpPwmResolutionBits` | `12` | Duty-code resolution, not a claim of 12-bit analog accuracy |
| `pwmSettleMs` | `0` until measured | Invalid placeholder; review an actual 10-5000 ms settling interval before permitting RUN |
| `pumpContactPin` | `26`, candidate | Separate reviewed isolated stop-contact interface |

The PWM branch initializes at zero duty. Its software STOP path commands the
pump contact to STOP before zeroing PWM and changing valve outputs; communication
faults use the same stop path. Reset/power loss still depend on the external
interface's measured fail-stop behavior. New nonzero commands hold the pump
stopped for the reviewed `pwmSettleMs` interval; activation occurs only after
the current controller safety tick. Stop/fault cancels pending activation. The
configured command percentage is not a measured motor speed. The PWM branch does not require or
probe a GP8403. With native ADC1 measurements it needs no I2C bus; selecting an
ADS1115 still requires I2C. PWM alone cannot detect an unplugged converter or
confirm the analog OUT voltage.

Production operation continues to require the verified board/safe-state profile,
calibrated pressure input, reviewed recipe and working independent pump stop
contact. Missing sensors remain unavailable; selecting PWM does not generate
readings or unlock physical operation. Pump output remains a percentage of the
command range. The Desired flow mL/min field is a comparison target until the
pump/head calibration and any closed-loop controller are validated.

## Recorded old Arduino wiring and code evidence

| Notebook wire | Recorded Mega 2560 connection | Migration check |
| --- | --- | --- |
| Orange, pump VIN | Digital D3 | DB15 1/3 command circuit; D3 produced PWM, not a true 10 V analog output |
| White, pump VOUT | Analog **A8**, confirmed by user | DB15 9/5 feedback circuit and any existing divider/protection |
| Blue, ground | GND beside AREF/D13; tag says DB15 12 | Locate missing analog returns 3/5; do not copy a common-ground assumption |
| Red, start/stop | Arduino VIN | Replace with the verified isolated contact circuit; do not copy the power-terminal connection |
| Pressure | Analog **A10** | Conditioned pressure ADC channel |
| Flow | Analog **A12** | Conditioned flow ADC channel |

**A8, A10 and A12 are analog inputs, not I2C.** Arduino's official Mega pinout
and PWM guide identify D3 as PWM-capable. The old direct connections are the
user's evidence; do not invent an unseen DAC. The pump manual documents a DC
voltage command, so the old circuit's behavior does not establish raw PWM as a
supported full-range replacement.

The archive's `10. LabVIEWInterface-C UF membrane codes-OB_RR.txt` has
`analogRead(command[2])` at line 187 and
`analogWrite(command[2], command[3])` at line 199. The host supplies channels and
duty values at runtime. The ZIP lacks native `.vi` files, so it does not recover
host-side scaling or pin constants. The notebook supplies the physical mapping.
Any original dividers, voltage levels and calibration must still be checked.

## Revision and sources

The user's 60-3600 RPM nameplate agrees with the service manual's model listing;
the older operating manual lists 180-3600 RPM. Preserve that discrepancy and
calibrate the actual installed drive/head rather than assuming a volts-to-RPM
or mL/min conversion. The future DB25 pump needs its own manual/profile.

- [EC Buying Amazon.ca product specification and pin description](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR), checked 26 October 2026. Price and delivery to the lab remain unverified.
- [Cole-Parmer/Barnant operating manual, manufacturer-authored copy on a mirror](https://manualmachine.com/coleparmer/7521130/15945005-instruction-manual/), A-1299-0853 Edition 03, printed pages 12-13 and 21.
- [Cole-Parmer/Barnant service manual, mirror](https://www.manualslib.com/manual/1449189/Cole-Parmer-75211-30.html), 75211-30 model listing.
- [Arduino Mega 2560 official board resources and pinout](https://docs.arduino.cc/hardware/mega-2560/) and [official PWM guide](https://support.arduino.cc/hc/en-us/articles/9350537961500-Use-PWM-output-with-Arduino).
- [TI ADS1115 input limits](https://www.ti.com/lit/ds/symlink/ads1115.pdf).

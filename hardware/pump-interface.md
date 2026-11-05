# Masterflex 75211-70 pump interface

The installed drive is the **Masterflex 75211-70 digital gear pump** with a
**DB25** remote connector. Use its A-1299-1142 Edition 02 manual, Figure 3-13.
The six-wire handoff below uses the Garosa 3.3P-10V converter and a planned
spare onboard relay for start/stop. The relay channel and bit still need
verification. For the full controller wiring, see the
[ordered-parts guide](../docs/ordered-parts-wiring.md).

## Six pump wires

| Pump DB25 pin | Function | Controller endpoint |
| --- | --- | --- |
| **1** | 0-10 V voltage command | Garosa **AO+** |
| **3** | Speed-command input return | Garosa **AO-** |
| **14** | 0-10 V running command output | HiLetgo divider 3 screw **VCC**, after reference review |
| **5** | Running command output return, at pump earth | Divider 3 screw **GND**, after reference review |
| **15** | Remote start/stop input | Selected spare relay **COM** |
| **17** | Start/stop reference, at pump earth | Same relay **NO** |

Turn the pump off before fitting or removing its remote cable. With the pump
unplugged and the harness disconnected from all electronics, use continuity to
identify each soldered wire by the molded connector number. Check adjacent pins
for solder bridges. The connector's solder side and mating face are mirrored.

A DB25-to-DB15 adapter is usable only after tracing both ends. An adapter that
preserves the old signal assignments needs DB25 **1/3/14/5/15/17** to reach
DB15 **1/3/9/5/10/12**, respectively. These are desired mappings, not verified
connections inside this cable. The old four tags cover only 1, 9, 10 and 12 on
the DB15 end. In particular, verify whether the adapter carries analog returns
3 and 5. If it does not, use the six traced DB25 wires directly.

## Garosa converter wiring

Use the [Garosa B07WZNV1V2 listing](https://www.amazon.ca/Voltage-Module-Voltage-Converter-Digital-Analog/dp/B07WZNV1V2)
and the received board marked **3.3P-10V**. With the printed labels upright, the
pictured terminals read left to right:

| Garosa terminal | Connection |
| --- | --- |
| **PWM- / DIN-** | ESP32 **GND** |
| **PWM+ / DIN+** | ESP32 **IO25 / GPIO25** |
| **Supply+** | Regulated **+24 V DC** for the converter |
| **Supply-** | That supply's negative terminal |
| **AO-** | Pump DB25 **3** after bench checks |
| **AO+** | Pump DB25 **1** after bench checks |

Fit the PWM-input jumper in the **5V** position with power off. The 3.3P-10V
variant accepts 3.3 V PWM in that position. The seller specifies **15-30 V DC**
supply, while the pictured power terminal is marked **12-30 V**. Use a regulated
24 V supply within both ranges. The 12 V sensor supply remains on the sensors.
ESP32 GPIO25 is the PWM signal. The pump's DB25 pin 25 is auxiliary 24 V and is
unused in this plan.

Keep the pump disconnected while measuring AO+ against AO- at 1 kHz and
0/25/50/75/100% duty. Targets are 0/2.5/5/7.5/10 V. Use the trimmer with the
meter connected and verify both endpoints, including a maximum of 10 V. Record
settling, ripple and whether output returns to zero after a nonzero command,
loss of PWM, reset and power cycling. The
[unloaded bench example](../firmware/examples/pwm-converter-bench/README.md)
produces test PWM without a production profile.

### Grounding and the optional voltage output

The pump specifies pin 3 for the input return. It separately lists 5, 13, 17
and 18 at earth ground. Keep the converter's PWM input pair, supply pair and
analog output pair on their designated terminals. Use the actual converter and
supply wiring to determine continuity among their reference nodes, including
any USB or shared-supply ground paths. The board's terminal labels alone do not
establish isolation between the PWM and analog sides.

The passive HiLetgo divider connects its screw GND to the ADC reference through
header **-**. If the converter, supply or USB already connects ESP32 GND to
pin 3, attaching the feedback divider also joins pin 3 to pump earth at pin 5.
Keep pins 14/5 disconnected until that complete reference arrangement is
verified or an isolated feedback input is fitted. After verification, divider
3 **S** goes to **GPIO39 / SVN** and its **-** to ESP32 GND. Leave **+** open on
the verified passive revision. A measured 10 V at the input should give about
2 V at S. The output on 14/5 represents running command speed. Motor-running
status and actual flow require their own signals.

## Spare onboard relay for start/stop

Select a physically unused channel on the relay board. Identify its COM and NO
and its exact 74HC595 bit with the [unloaded relay test](../docs/relay-board-test.md).
The bit must be separate from the six valve bits. Keep the pump wires
disconnected during mapping. The chosen contact pair must remain separate from the mains valve COM bus
and supply wiring. Verify the contact at the pump input's typical 1 mA.
When mapped and verified,
put DB25 pin 15 on COM and pin 17 on NO. Closing that dry contact pulls the
active-low pump input to its reference.

On the drive select **Remote Control > Voltage Input**, exit that menu, then
select **Continuous Pump Mode**. Set **START/STOP required ON** and
**AUTO START OFF**. The factory START/STOP setting is OFF, which permits
running from a sufficient analog command with the contact open. Check that
voltage scaling is appropriate and non-inverted. Verify the open contact
inhibits running with a nonzero command, and verify opening it stops the
pump during commissioning.

For the external contact-interface alternative, GPIO26 drives the logic side
of a reviewed 3.3 V-compatible driver. Its dry contact still connects across
15/17. Leave GPIO26 unused for the spare onboard channel.

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
| `pumpContactBit` | Unassigned | Select a tested spare shift-register bit and leave `pumpContactPin` unassigned |
| `pumpContactPin` | GPIO26 only for the external driver alternative | Leave unassigned for the onboard contact path |

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


## Historical Cole-Parmer 75211-30 DB15 interface

The older **75211-30** used DB15 **1(+)/3(-)** for voltage command,
**9(+)/5(-)** for voltage output, and **10/12** for its dry run contact.
Its front panel used **V** for voltage remote control. The reported nameplate
range was 60-3600 RPM, while the operating manual listed 180-3600 RPM. The
actual drive/head needs its own calibration. The older EC Buying
B0CPJGFCGR converter had a 3.3-12 V supply rating and shared power, PWM and
output ground. Those ratings and terminals apply to that converter only.

### Recorded old Arduino wiring and code evidence

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


## References

- [Masterflex 75211-70 operating manual, manufacturer-authored mirror](https://manualmachine.com/masterflex/7521170/15984751-instruction-manual/),
  A-1299-1142 Edition 02, pp. 3-21 to 3-24 and 7-1.
- [Garosa 3.3P-10V seller listing](https://www.amazon.ca/Voltage-Module-Voltage-Converter-Digital-Analog/dp/B07WZNV1V2).
- [Cole-Parmer/Barnant 75211-30 operating manual, manufacturer-authored mirror](https://manualmachine.com/coleparmer/7521130/15945005-instruction-manual/),
  A-1299-0853 Edition 03, pp. 12-13.
- [Historical EC Buying converter specification](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR).
- [Arduino Mega 2560 pinout](https://docs.arduino.cc/hardware/mega-2560/) and
  [Arduino PWM guide](https://support.arduino.cc/hc/en-us/articles/9350537961500-Use-PWM-output-with-Arduino).

# Pump connector: input, output and remote start

The DB15 is a connector. It does not by itself establish a voltage range,
serial protocol or pin assignment. The installed digital gear pump's exact
drive model/nameplate is still needed before final wiring or physical operation.
Do not substitute the later Masterflex DB25 profile for this drive.

## Direction of each signal

```text
ESP32 command -> DAC voltage output -> pump speed INPUT (VIN)
pump speed OUTPUT (VOUT) -> protected/scaled ADC input -> ESP32 reading
```

The photographed cable tags label both speed signals **0-10 V**. That is useful
evidence, but it still needs checking against the installed drive's manual and
selected voltage/current control mode. It does not mean the pump's output needs
a DAC. A DAC generates the command; an ADC reads feedback.

**The installed pump's actual operating range is not confirmed as 0-10 V.**
That number came from the photographed tags, not a measurement or an identified
drive manual. The fact that the old Arduino controlled it is useful evidence
about the old interface, but does not determine the pump's selectable/full-scale
range.

The recorded Arduino was a Mega 2560, whose GPIOs operate at 5 V. Its D3
`analogWrite()` output is PWM, not a generated 10 V analog voltage. Possible
explanations include a 0-5 V/PWM-compatible configuration, intermediate
conditioning, or using only part of a wider command range. These are hypotheses,
not a recovered circuit. A raw 10 V feedback connection to an ordinary Mega
analog input would also be outside its normal input range. Trace the original
wire and identify the drive before selecting a DAC or feedback divider.

See Arduino's [Mega 2560 specifications](https://store.arduino.cc/products/arduino-mega-2560-rev3)
and [PWM documentation](https://support.arduino.cc/hc/en-us/articles/9350537961500-Use-PWM-output-with-Arduino).

| Notebook wire | Recorded old Arduino connection | New interface role |
| --- | --- | --- |
| Orange, pump VIN | Digital 3 | Speed command into pump, using the verified input range and a suitable voltage-output stage |
| White, pump VOUT | Analog A8 or A9; handwriting unclear | Speed feedback from pump, through input scaling/protection to an ADC |
| Blue, pump ground | GND beside AREF/13 | Pump's designated signal reference; verify signal-specific returns against its manual |
| Red, start/stop | Arduino VIN | Unresolved. Arduino VIN is a power terminal, so this old connection must not be copied to an ESP32 GPIO or power pad |

A DFRobot GP8403/DFR0971 is a candidate for a verified 0-10 V command input:
its **VOUT0/VOUT1** terminals are voltage outputs. The module's VOUT0 would go to
the pump's speed **input**, not the pump's VOUT. See the
[manufacturer specification](https://wiki.dfrobot.com/dfr0971).

The pump VOUT must stay within the protected ADC input range after conditioning.
It is speed feedback, not independent measurement of the actual fluid flow.
Likewise, old use of Arduino D3 does not prove that the pump input accepts raw
ESP32 PWM. Existing filtering or amplification must be identified before reuse.

Current relay-board test firmware does not drive a pump or read these signals.
The experiment firmware retains its verified hardware-profile, sensor and
pressure gates. None of these notes authorizes connecting mains valve loads.

## What the old Arduino project establishes

The supplied `C UF mebrane-RR_OB.zip` was inspected again on 26 October 2026.
It contains the generic National Instruments LIFA bridge and supporting
libraries, plus `LabVIEW.docx`. It contains no native `.vi` files. The six
images in that document show front panels for CIP, CWF and Fouling, not the
LabVIEW block diagrams or pin-configuration constants.

The relevant bridge operations in
`10. LabVIEWInterface-C UF membrane codes-OB_RR.txt` are:

| Source line | Command | Meaning |
| --- | --- | --- |
| 140-141 | `pinMode(command[2], command[3])` | LabVIEW supplies the pin number and mode |
| 144-145 | `digitalWrite(command[2], command[3])` | LabVIEW supplies the digital output pin and level |
| 186-187 | `analogRead(command[2])` | LabVIEW supplies the analog input channel |
| 198-199 | `analogWrite(command[2], command[3])` | LabVIEW supplies the PWM output pin and duty value |

The base sketch's custom setup and loop sections are empty. The D3 references
in the bundled AFMotor library describe motor-shield support and do not prove
that the membrane rig used that library to control its pump.

Taken together, the notebook's orange-wire-to-D3 entry and the front panel's
`Duty Cycle (0-255)` indicator suggest a PWM speed-command path. This is an
inference, not a recovered LabVIEW assignment. Neither the bridge code nor the
front-panel photos show a PWM filter, amplifier or 0-10 V converter. They also
do not establish the pump's configured electrical input mode or a safe direct
ESP32 connection.

The recorded sensor connections are pressure white to A10 and flow white to
A12; the pump's white feedback wire is recorded at A8 or A9. Those assignments
come from the notebook, not fixed constants in the generic bridge. The
pressure-transducer specification supplied separately states 0-5 V output.
Analog signal conditioning must therefore be retained or designed for the
ESP32/ADC input range, rather than copying Arduino terminals directly.

To resolve the remaining pump wiring, inspect the exact pump drive model and
trace the old orange D3 wire for interface components. Recovering the native
LabVIEW VIs would establish the host-selected pins and processing. The red
start/stop connection remains unresolved by these source files.

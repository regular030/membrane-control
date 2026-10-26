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

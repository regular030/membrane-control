# Set up the selected PWM converter

For membrane research in **Dr. Onita Basu's lab at Carleton University**.
This is the handoff for Raj and the person preparing the electronics.

Use the [current wiring guide](ordered-parts-wiring.md) for the
**Masterflex 75211-70 DB25** and
[Garosa 3.3P-10V converter](https://www.amazon.ca/Voltage-Module-Voltage-Converter-Digital-Analog/dp/B07WZNV1V2). The installed pump uses the
voltage command on pins 1/3 and a dry start/stop contact on 15/17.

## Connect the Garosa command path

| Garosa terminal | Connect to |
| --- | --- |
| **PWM- / DIN-** | ESP32 **GND** |
| **PWM+ / DIN+** | ESP32 **GPIO25** |
| **Supply+** | Regulated **+24 V DC** |
| **Supply-** | That supply's negative terminal |
| **AO-** | Pump DB25 **pin 3** after bench checks |
| **AO+** | Pump DB25 **pin 1** after bench checks |

Set the **5V PWM input jumper** with power off. The Garosa listing specifies
15-30 V DC supply and the photographed unit says 12-30 V. A separate regulated
24 V supply fits both. Keep the ESP32, sensor and pump voltage references on
their specified terminals. See the [grounding and harness review](../hardware/pump-interface.md)
before adding the pump voltage output and divider.

On the selected spare relay, use **COM to DB25 15** and **NO to DB25 17**.
The lab confirmed **74HC595 bit 15**, LOW for STOP and HIGH for RUN. Verify
that the contact pair is isolated from the mains valve distribution. A separate
3.3 V-compatible contact driver on GPIO26 is an alternative if a spare
onboard relay cannot be used. Both options require a reviewed compiled profile.

## Firmware operation

Version **0.1.13** adds a PWM-converter pump-command option to the full physical
controller. The existing GP8403 backend is retained for older reviewed profiles.
Select the PWM option for the Garosa. An optional ADS1115 uses I2C for acquisition.

The proposed PWM signal is **1 kHz at 12-bit duty resolution**. With the module
configured for 0-10 V, the intended nominal correspondence is:

| Pump command | PWM duty | Intended converter output |
| --- | --- | --- |
| 0% | 0% | 0 V |
| 25% | 25% | 2.5 V |
| 50% | 50% | 5 V |
| 75% | 75% | 7.5 V |
| 100% | 100% | 10 V |

These are targets to measure, not verified voltages or calibrated flow rates.
Duty resolution is not an analog-accuracy claim. Firmware initializes at zero
duty, commands the independent pump contact to STOP during changes and waits
for the reviewed settling interval before permitting RUN. Stop/fault cancels
that pending activation. Software cannot detect a disconnected PWM converter,
guarantee its voltage, or replace an independent hardware shutdown.

Sequence timing does not pause during settling. A step shorter than the
reviewed settling interval may finish without the pump contact ever reaching
RUN. Include settling and any hydraulic delays when reviewing real step times.

## Maintainer: select the PWM profile

Start with `firmware/examples/PwmConverterProfile.example.h`. Copy it to
`firmware/include/BoardProfile.local.h`; keep the example unchanged. The local
profile is excluded from Git and public release payloads.

Set the source to `PumpCommandSource::PwmConverter`, and fill the pin, relay,
protected-input, calibration and safe-state settings from the checked rig.
The example's approval flags are false and its mapping is incomplete on
purpose. The profile must include the measured converter settling interval;
do not turn an unknown interval or an unchecked interface into approval.

The PWM-specific fields are `pumpPwmPin`, `pumpPwmChannel`,
`pumpPwmFrequencyHz`, `pumpPwmResolutionBits`, `pwmSettleMs` and
`pwmConverterInterfaceVerified`. Proposed pin/channel/frequency/resolution are
25 / 0 / 1000 Hz / 12 bits. `pwmSettleMs` starts at the invalid placeholder 0;
the measured reviewed value must be between 10 and 5000 ms. The source selection
and verification flags do not substitute for those physical measurements.

For the onboard contact, keep the template setting `pumpContactBit = 15` in a
`ShiftRegister595` profile, leave `pumpContactPin = -1`, and use
`pumpContactActiveHigh = true`. The selected bit must be separate from all
valve bits and LOW in `shiftUnusedLevels`. The template leaves V6 absent with
`valveBits[5] = -1` and `safeValves[5] = false`. Keep the seven-slot
protocol representation and send false for V6. GPIO26 is only for the external
driver option. See the [contact checks](../hardware/pump-interface.md#spare-onboard-relay-for-startstop).

In `[env:esp32-physical]` in `firmware/platformio.ini`, preserve its existing
flags and add the reviewed profile header:

```ini
build_flags = ${env.build_flags} -DBASU_DRY_RUN=0 -DBASU_VERIFIED_PROFILE_HEADER=\"BoardProfile.local.h\"
```

Build/upload that reviewed source using the setup's **Flash full controller
(setup required)** shortcut, or from the repository root:

```powershell
$env:PLATFORMIO_CORE_DIR = Join-Path (Get-Location) 'work/platformio'
.\.venv\Scripts\python.exe -m platformio run -d firmware -e esp32-physical -t upload --upload-port COM4
```

Use the actual controller port if it is no longer COM4. Close the app connection
before uploading. An external three-wire UART adapter may need IO0/EN download
entry and a manual EN reset afterward with IO0 released. Uploading replaces
the existing board program. Keep pump/valve loads disconnected during the initial
upload. The shortcut builds the installed copy, so profile edits must be in
that copy if using the installed tools.

**The shipped full pump/sensor profile remains locked.** It cannot infer the
relay map, approve the input conditioning, supply calibration or create a pump
stop circuit. GUI checkboxes cannot enable an unverified compiled profile.

## Checks after the converter arrives

Before pressure acquisition is commissioned, use the standalone
[`pwm-converter-bench` example](../firmware/examples/pwm-converter-bench/README.md)
with **the pump DB25 harness and all relay contact loads disconnected**. It
produces only GPIO25 test PWM, uses explicit serial confirmation and a maximum
five-second nonzero test, then commands zero. It does not run the full controller,
touch valve outputs, read pressure or approve a profile. Never bypass the full
controller's pressure checks to make a converter bench measurement.

1. Keep the pump disconnected. Verify the 3.3P-10V marking, 5V input jumper
   position and the converter supply.
2. Measure AO+ relative to AO- at 0/25/50/75/100%, then zero.
   Record error, ripple and settling after both increasing and decreasing steps.
3. Measure power-up with either device powered first, ESP32 reset, absent PWM,
   converter supply loss and restored connections. The seller does not guarantee
   a zero output for all these cases. A voltmeter average alone cannot establish
   pulse amplitude or ripple; use suitable instrumentation when checking those.
4. Check that the separate stop contact stays stopped during the settling delay,
   on Stop, on faults and when the ESP32 loses power. Check the pressure input
   and analog return wiring independently.
5. Complete the approved physical profile and repeat the rig's acceptance checks
   before connecting and operating the pump. Select **Voltage Input**, exit to
   **Continuous Pump Mode**, set **START/STOP required ON**, and turn
   **AUTO START OFF**. Check that an open contact prevents running.

To operate the six installed valves before sensors are ready, use the normal
[Dashboard valve controls](normal-valves.md), which require no sensor or extra
profile form. Those controls keep the pump command at zero. The balance is a
separate USB-B connection; its [serial setup](../hardware/balance-usb-setup.md)
is unchanged.

# Set up the selected PWM converter

For membrane research in **Dr. Onita Basu's lab at Carleton University**.
This is the handoff for Raj and the person preparing the electronics.

## What to order

Order **one [EC Buying PWM-to-voltage converter, B0CPJGFCGR](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR)**.
Choose the item whose product description specifies 3.3-12 V module power,
3.3 V-compatible PWM, and **0-10 V output**. Do not order a GP8403/DFR0971 DAC
as well for this same pump-command path. Check current delivery at your address.

The converter adds only the speed command. The rest of the installation also
needs these items if suitable ones are not already present:

- A **3.3 V logic-compatible isolated dry-contact interface** for pump start/stop.
  The current firmware uses a separate GPIO driver; it does not automatically
  use an eighth onboard valve relay. Verify its supply, default STOP behavior
  and contact suitability before selecting a particular module.
- A **protected analog input stage** for pressure, flow and pump feedback.
  Native ESP32 ADC1 or a supported ADS1115 can acquire the conditioned signals.
  A bare ADS1115 module does not make raw 5 V or 10 V signals safe. The input
  design must establish scaling, clamps/filtering, grounding and calibration.
- A corrected, labelled **DB15 harness**, suitable low-voltage terminal wiring
  and mounting/strain relief. Trace the actual returns instead of duplicating
  the old four-wire common-ground assumption.

Reuse the existing ESP32 board, USB-UART adapter, balance USB-B cable and suitable
regulated supply. Verify that supply against the converter's **3.3-12 V** range:
nominal 12 V is its published upper limit, with no extra tolerance specified.
Do not power this converter from 15/24 V. Its supply does not power the pump motor.

## Connect the command path

With power disconnected, have the actual exposed header labels and references
checked before soldering. The proposed signal assignment is:

| Connection | Destination |
| --- | --- |
| Verified regulated supply, within 3.3-12 V | Converter **VIN** |
| Supply negative and reviewed ESP32 GND | Converter **GND** |
| ESP32 **GPIO25**, candidate | Converter **PWM** |
| Converter **OUT** | Pump DB15 **pin 1 (+)**, after bench checks |
| Converter GND / reviewed analog reference | Pump DB15 **pin 3 (-)** |

The module has a common supply/signal/output ground and **no isolation**.
Resolve the pump/USB grounding before making that reference connection. The
converter has no SDA/SCL wires. Its VIN is its power input; the pump's labelled
VIN is the analog speed command. These are different terminals.

Other pump circuits are separate:

| Circuit | Connection |
| --- | --- |
| Start/stop | Suitable isolated contact across **DB15 10/12**, controlled through its driver by candidate **GPIO26** |
| Speed feedback | **DB15 9 (+)/5 (-)** through the protected/calibrated ADC stage |
| Pressure and flow | Their analog outputs through protected/calibrated ADC inputs, not directly into ESP32 GPIO |

Do not apply a supply voltage to the dry-contact pair, copy the old Arduino VIN
start/stop wire, join pins 3/5/12 blindly, or attach this circuit to the 120 VAC
valve COM distribution. See the [detailed pump/harness explanation](../hardware/pump-interface.md).

## What the new firmware does

Version **0.1.13** adds a PWM-converter pump-command option to the full physical
controller. The existing GP8403 backend is retained for older reviewed profiles.
The selected module uses the PWM option; there is no GP8403/I2C probe for it.
An ADS1115, if chosen for acquisition, still requires I2C.

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

**The shipped factory physical profile remains locked.** It cannot infer the
relay map, approve the input conditioning, supply calibration or create a pump
stop circuit. GUI checkboxes cannot enable an unverified compiled profile.

## Checks after the converter arrives

Before pressure acquisition is commissioned, use the standalone
[`pwm-converter-bench` example](../firmware/examples/pwm-converter-bench/README.md)
with **the pump DB15 harness and all valve contact loads disconnected**. It
produces only GPIO25 test PWM, uses explicit serial confirmation and a maximum
five-second nonzero test, then commands zero. It does not run the full controller,
touch valve outputs, read pressure or approve a profile. Never bypass the full
controller's pressure checks to make a converter bench measurement.

1. Keep the pump disconnected. Check module identity, supply and 0-10 V range
   selection against the received board's instructions.
2. In a reviewed bench procedure, measure OUT-to-GND at 0/25/50/75/100%, then zero.
   Record error, ripple and settling after both increasing and decreasing steps.
3. Measure power-up with either device powered first, ESP32 reset, absent PWM,
   converter supply loss and restored connections. The seller does not guarantee
   a zero output for all these cases. A voltmeter average alone cannot establish
   pulse amplitude or ripple; use suitable instrumentation when checking those.
4. Check that the separate stop contact stays stopped during the settling delay,
   on Stop, on faults and when the ESP32 loses power. Check the pressure input
   and analog return wiring independently.
5. Complete the approved physical profile and repeat the rig's acceptance checks
   before connecting and operating the pump. Select its verified **V** control mode.

To test the seven solenoid valves before sensors are ready, use the separate
[Valve test (no sensors)](valve-test.md) with its own reviewed valve-only profile.
That tool cannot operate the pump or this converter. The balance is a separate
USB-B connection; its [serial setup](../hardware/balance-usb-setup.md) is unchanged.

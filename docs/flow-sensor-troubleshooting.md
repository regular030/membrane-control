# Flow sensor connected, but no reading

The present rig documents a **McMillan 101-3T-CM-A2 analog flow sensor**. Its
white signal wire is an analog voltage output, not I2C. The old Mega A12 input
does not automatically become an ESP32 input when the cable is moved.

## First check the electrical connection

If the white signal wire goes straight into an ESP32 pin, power down and
disconnect that signal until the input circuit is checked. The documented
sensor output is **0-5 V**. ESP32 inputs operate in a 3.3 V domain and are not
5 V tolerant. A pin assignment alone is not a complete input circuit.

The intended arrangement is:

```text
Sensor white analog OUT --> verified scaling/protection/filtering --> configured ADC input
Sensor black reference --> reviewed input/ESP32 reference
Sensor red supply      --> its appropriate external sensor supply, never a GPIO
```

Use **SVP / GPIO36** for flow after its divider. Leave GPIO35 unused. An ADS1115 is an alternative
only with a suitable input stage and a matching firmware profile. Neither a
bare ADC module nor a software setting protects a pin from excessive voltage.
Do not copy the old Arduino A12 label, connect the signal to SDA/SCL, or use the
pump PWM converter as a sensor input circuit.

Have the actual sensor model, supply, return and signal voltage checked with
the ESP32 signal disconnected. A missing displayed reading alone cannot tell
whether an input was damaged. Check wiring and voltages before replacing parts.

## What each firmware program reads

| Board program | Real flow acquisition |
| --- | --- |
| Dry-run controller | None. It generates practice values and ignores the sensor. |
| Bare relay board test | None. Sensors are intentionally unavailable. |
| Valve test (no sensors) | None. Only the reviewed valve circuits are tested. |
| Factory physical controller | Live diagnostic voltages while idle or using manual valves. Calibrated pressure, flow, and pump feedback require a reviewed profile. |
| Reviewed physical controller | Only its configured ADC channel, protected voltage range and calibration. |

Unchecking **Simulation mode** chooses a real serial connection. It does not
configure an ADC, discover sensor wiring, or change the program installed on
the board. Simply attaching the flow cable cannot create a configured reading.

## Test the connected sensors

With app and normal firmware 0.1.19, **Dashboard → Live sensor check** updates
automatically while idle or using manual valves. Scroll below the four metric
cards. In app 0.1.20, the ESP32 sample time advances even when the measured
voltage stays steady. **Connections and settings →
Read sensor inputs** still performs a one-time check while idle. Both show millivolts at
**IO34** for pressure, **SVP / GPIO36** for flow, and **SVN / GPIO39** for optional
pump feedback. Compare it with a meter across the corresponding divider's
**S** and **−**. A verified 5:1 divider gives roughly 1000 mV at the pin for a
5 V signal. An unwired pin can float, and a zero can be a valid signal, so the
voltage alone cannot identify a cable or confirm a good sensor.

The live check also shows nominal estimates for the documented 5:1 wiring.
The Omega PX309-100G5V and McMillan 101 range 3 use 0–5 V spans with 100 psig and
100 mL/min full scale. The app shows a pressure estimate from 100–1000 mV and a
flow estimate from 130–1000 mV. Optional pump feedback displays the estimated
pre-divider voltage from 150–2000 mV. These estimates assume the documented
models and divider ratio and need a meter, known pressure, and timed flow check.
[Omega exact model](https://www.dwyeromega.com/en-gb/general-purpose-stainless-steel-pressure-transducers/PX309/p/PX309-100G5V)
· [McMillan operation manual](https://www.mcmflow.com/wp-content/uploads/2015/02/101-M002.pdf)

In 0.1.18 the three inputs used the ESP32's 11 dB range. Its recommended lower
limit is about 150 mV, and ESP32 ADC1 calibration can return 142 mV for a raw
zero. In 0.1.19, GPIO34 and GPIO36 use the lower 2.5 dB range (100–1250 mV).
GPIO39 keeps the wider range for pump feedback. Treat values near or outside
these ranges as diagnostic and compare with a meter before interpreting them.
[Espressif ADC ranges](https://docs.espressif.com/projects/esp-idf/en/v4.4.8/esp32/api-reference/peripherals/adc.html)
· [ADC1 calibration source](https://github.com/espressif/esp-idf/blob/v4.4.8/components/esp_adc_cal/esp32/esp_adc_cal.c#L69-L76)

The calibrated Dashboard metrics, charts, and pressure interlock still require
a reviewed hardware profile. If the live check is missing, verify that the
controller is connected and running **Flash normal controller** from 0.1.19.

## Set up the pressure and flow readings

With either normal controller build connected, open **Sensor setup** from
Dashboard or **Connections and settings**. You can see the live pin voltages
without starting a run. The pressure input is **IO34**, flow is **SVP/GPIO36**,
and optional pump feedback is **SVN/GPIO39**. Compare each input to your meter
across its divider's **S** and **−** terminals.

For a baseline, stop the pump, verify zero pressure and no flow, then capture
the zero for each channel. This shows how many millivolts the signal moves
from that baseline. To estimate pressure or flow in physical units, capture
two different steady readings for that sensor and enter each measured
reference in psi or mL/min. For flow, measure the volume collected and the
elapsed time. Use **Copy setup readings** before leaving the session to save
the reference points and calculated scale and offset for the rig's profile.
Factory certificates list the sensor voltage before the divider. Use them to
compare expected and actual voltages, and use independent measurements when
capturing the installed circuit's references. The Dashboard uses the measured
fit for live estimates between the two captured points in the current
connection. The run charts and pressure limit use the commissioned firmware
profile.

With the documented divider, the pressure certificate's near-zero output is
around 1 mV at IO34. The factory pressure and flow input range starts at 100 mV.
Use a meter for the zero check, then capture two measured points within the
usable range. If the process needs accurate readings below that range, use a
verified input circuit that can measure the required low voltages before
commissioning the run profile.

## Read the connection status

App and full-controller firmware **0.1.14** provide more specific messages:

| Message | Meaning / next step |
| --- | --- |
| Not configured: real flow channel not set | The firmware flow source is disabled. A maintainer must configure acquisition after the input circuit is ready. |
| Profile locked: inputs not read | An input is declared, but the physical profile is still unreviewed. |
| Input not calibrated | The acquisition calibration/range is incomplete or invalid. |
| Input hardware unavailable | ADC initialization, acquisition or another required hardware dependency failed. |
| Reading invalid/out of range | The acquired signal failed the configured limits or rail rejection. Check voltage and configuration. |
| Reading stale | No sufficiently recent valid acquisition is available. |
| No reading | Older firmware provided no detailed reason. Check its mode/profile and wiring; do not infer a broken sensor. |

Numeric **0 mL/min** is a valid displayed reading. In a reviewed profile, the
maintainer must deliberately decide how a true zero-voltage signal is treated:
the generic input default rejects ADC rails. Do not disable that check merely
to hide a wiring fault. Zero output alone does not prove a sensor is connected.

## Maintainer: enable real acquisition

The compiled physical profile needs `config.flow.source`, a matching native
ADC1 pin or ADS1115 channel, protected pin-voltage limits, scaling/offset,
engineering-unit limits and verified calibration. Configure the full system's
pressure protection, safe relay map and pump stop interface independently.
The factory live check needs no profile editing.

To prepare calibrated charts, collect two reference points per sensor using the
intended production ADC range and the installed divider. For pressure, use a
reference gauge and two known pressures within the rig's approved operating
range. For flow, measure two steady rates from volume collected over time
(`mL/min = 60 × collected mL / seconds`). Use distinct readings within the
sensor's calibrated range. The classic ESP32 ADC has a low-end measurement
limit, so establish an acquisition method that covers the lab's operating
range before accepting the readings.
[Espressif ADC ranges](https://docs.espressif.com/projects/esp-idf/en/v4.4.8/esp32/api-reference/peripherals/adc.html)

Enter the results in a local copy of `PwmConverterProfile.example.h`. For each
channel, let `V1` and `V2` be ADC readings in volts after the divider and `Y1`
and `Y2` the corresponding reference readings in psi or mL/min.

```text
unitsPerVolt = (Y2 - Y1) / (V2 - V1)
offset = Y1 - unitsPerVolt * V1
```

Confirm the fit against an independent reference point. Set the allowed ADC
and engineering ranges from the tested values. Full operation also needs the
lab's approved pressure limit, pump interface, and safe valve state. See the
[local profile and flash steps](pwm-converter-setup.md#maintainer-select-the-pwm-profile).

The PWM converter profile example records the candidate pins and leaves acquisition disabled until calibration is complete. New firmware diagnostics describe
configuration and acquisition status; they do not detect a cable or generate
missing values.

For valves before the input electronics are ready, use
[Valve test (no sensors)](valve-test.md). It remains independent of the sensor
setup and never runs the pump.

Sources: [McMillan Model 101](https://www.mcmflow.com/product/model-101/) and
[Espressif ESP32-WROOM-32E electrical characteristics](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.html).

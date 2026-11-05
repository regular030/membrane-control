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
automatically while idle or using manual valves. **Connections and settings →
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
Do not set production review flags just to test the flow wire.

The PWM converter profile example records the candidate pins and leaves acquisition disabled until calibration is complete. New firmware diagnostics describe
configuration and acquisition status; they do not detect a cable or generate
missing values.

For valves before the input electronics are ready, use
[Valve test (no sensors)](valve-test.md). It remains independent of the sensor
setup and never runs the pump.

Sources: [McMillan Model 101](https://www.mcmflow.com/product/model-101/) and
[Espressif ESP32-WROOM-32E electrical characteristics](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.html).

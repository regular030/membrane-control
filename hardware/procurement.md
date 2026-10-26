# Procurement baseline

Updated 26 October 2026. Reuse the ESP32 relay board, USB-UART adapter, computer,
balance cable and existing supplies already obtained if suitable. The selected
new pump command path uses the **EC Buying PWM converter**, not an extra Arduino
or a second DAC. This list does not constitute a commissioned mains assembly.

## Order for the selected pump interface

| Qty | Item | Link / specification | Check before ordering |
| --- | --- | --- | --- |
| **1** | **EC Buying PWM-to-0-10 V converter, B0CPJGFCGR** | [Exact Amazon Canada listing](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR) | Seller specifies 3.3 V PWM compatibility and 3.3-12 V module supply. Confirm the received variant supports 0-10 V; price, current stock and delivery to the lab are unverified |
| 1, if no suitable interface is present | Isolated pump start/stop contact interface | Verified **3.3 V logic-compatible** control input and suitable isolated dry contact | Pump-side contact across DB15 10/12 only; separate from all 120 VAC valve wiring. Select the exact part after reviewing its signal-contact rating and reset/power-loss behavior |
| Design-dependent | Analog input conditioning and protection | Three channels: pressure 0-5 V, flow 0-5 V, pump feedback 0-10 V | Select scaling, filtering, protection and reference arrangement for the actual ADC. No direct raw 5 V/10 V connection to ESP32 inputs |
| 1 only if the ADC design selects it | ADS1115 module or equivalent ADC | Suitable 3.3 V operation and pull-ups; three usable conditioned inputs | Native ESP32 ADC1 is also supported. Choose one acquisition plan; an ADC alone is not an input-protection circuit |
| As needed after harness tracing | DB15 harness/breakout, terminals and low-voltage wiring | Two-row 15-pin connector with correct gender; labels, ferrules, strain relief | Identify separate pins 1/3, 9/5 and 10/12. Do not substitute a three-row VGA connector |
| Only if existing supply fails checks | Converter power supply/regulation | Regulated output that stays within the selected module's supply limits | Existing nominal 12 V is at the converter's stated maximum. Check tolerance/startup; do not use 15 V or 24 V |

**Do not order a GP8403/DFR0971 or GP8413 DAC in addition to this converter for
the same pump command.** They are alternative interfaces. The PWM path uses one
reviewed GPIO, provisionally **GPIO25**. The separate pump-contact interface is
provisionally controlled by **GPIO26**. Neither assignment is automatically
approved by ordering the parts.

Follow the [pump wiring and bench handoff](pump-interface.md#connecting-the-ec-buying-converter-when-it-arrives)
before attaching the pump. The converter is nonisolated, so resolve its shared
ESP32/USB/pump reference before connection. Test output voltage, zero/stop,
reset, lost PWM and power sequencing with the pump disconnected. Firmware
backend support does not replace the commissioned physical profile or pressure
input.

## Existing setup and optional replacements

| Item | Existing choice / reference | Reuse or replacement check |
| --- | --- | --- |
| Computer | [Lenovo ThinkCentre M720q, Amazon Canada](https://www.amazon.ca/dp/B08G1XKHPB), i5-8500T, 16 GB RAM, 256 GB SSD, Windows 11 Pro listing | Reuse a suitable lab computer first. For a replacement confirm power adapter, monitor cable, SSD condition and return coverage; current price unverified |
| Relay controller | [Srliya 16-channel ESP32-WROOM board](https://www.amazon.ca/dp/B0DKC2L2NH) | Verify the received ESP32_Relay_X16_V1.2 input rating, pin/bit map, startup/OE defaults and suitability for actual inductive valve loads |
| USB-UART | [DAOKAI CP2102 adapter](https://www.amazon.ca/dp/B0BCKBHQ8Y) | Verified 3.3 V TTL TX/RX; adapter power pins disconnected when board externally powered |
| DC supply | Existing believed 12 V supply; [previous SANSUN 12 V 2 A candidate](https://www.amazon.ca/dp/B01AZLA9XQ) | Supply label/current/polarity and both board/converter limits must match. The board's conflicting 5 V vs 5-12 V seller documentation remains unresolved |
| Balance cable | Current USB-A to USB-B data cable; [replacement reference](https://www.amazon.ca/dp/B00NH13DV2) | Reuse the current USB-B I/O path; the green USB-RS232 adapter is not needed for that path |
| DC connector | Matching female jack/pigtail, securely mounted | Confirm actual plug dimensions and polarity; 5.5 x 2.1 mm and 5.5 x 2.5 mm are not interchangeable assumptions |
| Enclosure and wiring | Rated terminals, glands, wire, ferrules, fuses, labels and mounting | Size after electrical/layout review, keeping mains valve conductors and low-voltage pump/sensor circuits separated |

The controller supply does not power the computer, balance, pump motor or
110-120 VAC valve coils. Each retains its appropriate supply. The relay board
has extra channels beyond the seven valves; keep unused bits in reviewed
inactive states. The current production driver uses a separate pump contact
output, not an assumed eighth valve-board relay bit.

## Purchase evidence

The [selected Amazon.ca listing](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR)
was read on 26 October 2026 and contains its own PWM compatibility, supply and
output specifications, plus purchase controls. The returned page did not expose
a current price or delivery estimate to the lab. Verify the offer at checkout;
no Prime or next-day delivery promise has been established.

## Computer offered for comparison

The [HP ProDesk 600 G1 listing](https://www.amazon.ca/dp/B085RY6Z1C) was observed at CAD 199.99 and advertises i5-4570T, 16 GB RAM, 256 GB SSD and Windows 11 Pro. It explicitly warns that it has TPM 1.2. The generic summary table also conflicts with the storage description. Prefer the newer M720q configuration for the Windows application.

See [Microsoft Windows 11 specifications](https://www.microsoft.com/en-us/windows/windows-11-specifications) for TPM 2.0 requirements and [supported Intel processors](https://learn.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-intel-processors).

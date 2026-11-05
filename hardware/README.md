# Hardware baseline

**Current installed valve map, version 0.1.16:** V1, V2, V3, V4, V5 and V7
use bits 0, 1, 2, 3, 5 and 6. There is no V6. Bit 4 has no valve assignment. Use the
[normal valve guide](../docs/normal-valves.md) for sensor-independent ON/OFF
controls. Earlier seven-valve planning below does not override this map.

The installed pump is now the 75211-70 DB25. Its full hardware profile still
requires commissioning.

See the [25 October relay-board pin plan](relay-board-pin-plan.md) for the
seller's shift-register GPIO assignments, proposed UART/PWM/analog connections
and the unresolved board-input voltage discrepancy.

## Existing equipment

| Equipment | Interface or role |
| --- | --- |
| Six installed Granzow H4B19-00Y valves | Photos identify 110-120 VAC, 50/60 Hz, 8 W coils |
| Masterflex 75211-70 digital gear pump | Installed DB25 drive. See its model-specific wiring below |
| Cole-Parmer 75211-30 digital gear-pump drive | Historical DB15 interface |
| Omega PX309-100G5V | 0-100 psi gauge, 0-5 V analog output |
| McMillan 101-3T-CM-A2 | Flow measurement; 12-15 V supply, 0-5 V and pulse options |
| Adam Nimbus NBL 8201e balance | Current: USB-B I/O directly to computer; a second Windows COM port now appears; weight receipt remains to be checked |
| Existing external DC supply | Believed 12 V; label, current rating and condition need checking |

The previously listed Omega USB pressure sensor is not required for the initial application. Do not remove its driver abstraction option if later scope changes.

## Pump signals

The [pump wiring guide](pump-interface.md) covers the **75211-70** and the
[Garosa 3.3P-10V converter](https://www.amazon.ca/Voltage-Module-Voltage-Converter-Digital-Analog/dp/B07WZNV1V2). Garosa AO+/AO- drive DB25 1/3.
Its PWM input uses ESP32 GPIO25 and GND, and its power pair takes regulated
24 V DC. DB25 14/5 provide an optional running command voltage output.
Check its reference paths before connecting the divider.

Start/stop uses the COM/NO terminals of a mapped spare onboard relay across
DB25 15/17. Its bit remains unassigned. GPIO26 is available for a separate
isolated contact driver as an alternative. The factory full profile remains
locked. The earlier DB15 pump and EC Buying converter are documented
separately in the pump guide.

## Analog acquisition

The 0-5 V sensors require input scaling, filtering, protection and calibration.
The identified pump's documented feedback range is 0-10 V; verify actual wiring
and scaling separately.
The old Mega channels were pump feedback A8, pressure A10 and flow A12. These
are analog inputs, not I2C; only a selected external ADC would add an I2C link.
If an ADS1115 is selected, its programmable full-scale range does not permit
input pins above their supply-referenced electrical limits. Read the
[TI datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf) before defining the interface.

## Balance

The user now uses the balance's USB-B **I/O** port directly to the computer
through a USB data cable, using [Adam's Nimbus driver](https://adamequipment.com/support/software-downloads.html)
if required. The previous green USB-to-RS232 adapter is no longer the selected
path. USB-A **Display** is for the remote display. Use one PC connection path
at a time and retain the balance's own power supply.

Select the balance's COM port separately from the ESP32's port. The current app expects **9600 baud, NONE parity / 8N1** by default; the scale and app must match. Enable continuous single-line mass output with units and CRLF line endings. Follow the [Adam manual](https://adamequipment.com.cn/media/docs/manuals/NBLe_i_UM_EN.pdf), including restarting after serial-setting changes. See [balance USB setup](balance-usb-setup.md) for both connection paths. The app can listen for streamed readings and request a weight when polling is enabled. See the [scale connection guide](../docs/scale-connection.md).

The documented single-line mass stream has weight and unit but no per-reading stability flag. Do not manufacture stability status. Stable-only output can withhold samples while collecting liquid and trigger stale-data status; use continuous output without stable-only filtering for the current acquisition setup.

## Items to resolve before energizing

- Masterflex DB25 harness continuity, spare relay bit and signal references.
- Board schematic, relay GPIO/polarity and startup output behavior.
- Valve contact rating for the actual AC inductive load and wiring protection.
- Power-supply voltage/current and total controller/interface demand.
- Sensor calibration, membrane area and liquid-density assumptions.
- Approved valve-state tables, pump commands, process limits and fault states.
- Correct backwash valve routing: the supplied text repeats valve 5 for inlet and outlet.
- Enclosure dimensions, terminal ratings, separation, strain relief and shutdown arrangement.

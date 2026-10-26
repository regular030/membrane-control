# Hardware baseline

Planning baseline dated 24 October 2026. No pin-level wiring is approved yet.

See the [25 October relay-board pin plan](relay-board-pin-plan.md) for the
seller's shift-register GPIO assignments, proposed UART/I2C/analog connections
and the unresolved board-input voltage discrepancy.

## Existing equipment

| Equipment | Interface or role |
| --- | --- |
| Seven Granzow H4B19-00Y valves | Photos identify 110-120 VAC, 50/60 Hz, 8 W coils |
| Cole-Parmer 75211-30 digital gear-pump drive | Current DB15 interface; user reports 60-3600 RPM and 0.1 HP |
| Masterflex L/S pump | Later DB25 profile; exact drive model needed |
| Omega PX309-100G5V | 0-100 psi gauge, 0-5 V analog output |
| McMillan 101-3T-CM-A2 | Flow measurement; 12-15 V supply, 0-5 V and pulse options |
| Adam Nimbus NBL 8201e balance | Current: USB-B I/O directly to computer; a second Windows COM port now appears; weight receipt remains to be checked |
| Existing external DC supply | Believed 12 V; label, current rating and condition need checking |

The previously listed Omega USB pressure sensor is not required for the initial application. Do not remove its driver abstraction option if later scope changes.

## Pump signals

See [pump input/output clarification](pump-interface.md): **pump VOUT goes to
an ADC; a DAC drives the pump VIN/speed input**. DB15 alone does not establish
either signal's range. The user has now identified **75211-30**; the matching
manufacturer manual confirms the model's 0-10 V voltage-control interface.

Cable tags show a 0-10 V speed command, separate 0-10 V speed output and remote
start/stop. Their old DB15 signal numbers agree with the 75211-30 diagram, but
the generic GROUND tag identifies pin 12, the start/stop return. The analog
return pins 3 and 5 still need tracing in the harness. The new DB25 annotations
refer to a future interface, not this drive's connector.

The 75211-30 manual documents command **DB15 1(+)/3(-)**, speed feedback
**9(+)/5(-)** and remote contact **10/12**. This replaces the earlier inference
from labels alone. Check the drive's selected mode, harness continuity and
conditioning before connecting a replacement controller. Pin 12 is not shown
as the common return for both analog signals. The GP8403 is a candidate command
source, subject to verification of its interface and references.

A related [Masterflex family manual](https://documents.thermofisher.com/TFS-Assets/MBD/manuals/Thermo-Scientific-Dry-Bags-Peristaltic-Pump-Complex-Drive-DB3000A-Operating-Manual-GLOBAL-EN-low-res.pdf), printed page 3-23, has separate analog-input return, analog-output reference and digital-control reference pins. This is why a generic ground tag cannot establish all return connections. It is not verification of the installed models.

## Analog acquisition

The 0-5 V sensors require input scaling, filtering, protection and calibration.
The identified pump's documented feedback range is 0-10 V; verify actual wiring
and scaling separately.
If an ADS1115 is selected, its programmable full-scale range does not permit
input pins above their supply-referenced electrical limits. Read the
[TI datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf) before defining the interface.

## Balance

The user now uses the balance's USB-B **I/O** port directly to the computer
through a USB data cable, using [Adam's Nimbus driver](https://adamequipment.com/support/software-downloads.html)
if required. The previous green USB-to-RS232 adapter is no longer the selected
path. USB-A **Display** is for the remote display. Use one PC connection path
at a time and retain the balance's own power supply.

Select the balance's COM port separately from the ESP32's port. The current app expects **9600 baud, NONE parity / 8N1** by default; the scale and app must match. Enable continuous single-line mass output with units and CRLF line endings. Follow the [Adam manual](https://adamequipment.com.cn/media/docs/manuals/NBLe_i_UM_EN.pdf), including restarting after serial-setting changes. See [balance USB setup](balance-usb-setup.md) for both connection paths. The app listens for weights without sending print/poll commands and marks readings stale after more than 3 seconds without a valid reading.

The documented single-line mass stream has weight and unit but no per-reading stability flag. Do not manufacture stability status. Stable-only output can withhold samples while collecting liquid and trigger stale-data status; use continuous output without stable-only filtering for the current acquisition setup.

## Items to resolve before energizing

- Cole-Parmer drive revision, harness continuity and signal-specific returns;
  the later Masterflex pump's exact model is still needed.
- Board schematic, relay GPIO/polarity and startup output behavior.
- Valve contact rating for the actual AC inductive load and wiring protection.
- Power-supply voltage/current and total controller/interface demand.
- Sensor calibration, membrane area and liquid-density assumptions.
- Approved valve-state tables, pump commands, process limits and fault states.
- Correct backwash valve routing: the supplied text repeats valve 5 for inlet and outlet.
- Enclosure dimensions, terminal ratings, separation, strain relief and shutdown arrangement.

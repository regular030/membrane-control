# Hardware baseline

Planning baseline dated 24 October 2026. No pin-level wiring is approved yet.

## Existing equipment

| Equipment | Interface or role |
| --- | --- |
| Seven Granzow H4B19-00Y valves | Photos identify 110-120 VAC, 50/60 Hz, 8 W coils |
| Cole-Parmer digital gear pump | Current DB15 remote-control connection; exact drive model needed |
| Masterflex L/S pump | Later DB25 profile; exact drive model needed |
| Omega PX309-100G5V | 0-100 psi gauge, 0-5 V analog output |
| McMillan 101-3T-CM-A2 | Flow measurement; 12-15 V supply, 0-5 V and pulse options |
| Adam Nimbus balance | USB-B I/O to computer; retains its own power supply |
| Existing external DC supply | Believed 12 V; label, current rating and condition need checking |

The previously listed Omega USB pressure sensor is not required for the initial application. Do not remove its driver abstraction option if later scope changes.

## Pump signals

Cable tags show a 0-10 V speed command into the pump, a separate 0-10 V speed output and remote start/stop. The tagged DB15-to-DB25 mappings are evidence to reconcile with the exact manufacturer manual, not complete instructions for connecting the ESP32.

Use a 3.3 V-compatible DAC with a 0-10 V output stage, an isolated contact/suitable isolated interface for remote start/stop and a protected/scaled analog input for readback. Do not use a raw ESP32 output or raw PWM as a 0-10 V analog command.

A related [Masterflex family manual](https://documents.thermofisher.com/TFS-Assets/MBD/manuals/Thermo-Scientific-Dry-Bags-Peristaltic-Pump-Complex-Drive-DB3000A-Operating-Manual-GLOBAL-EN-low-res.pdf), printed page 3-23, has separate analog-input return, analog-output reference and digital-control reference pins. This is why a generic ground tag cannot establish all return connections. It is not verification of the installed models.

## Analog acquisition

The 0-5 V sensors and 0-10 V pump output require input scaling, filtering, protection and calibration. If an ADS1115 is selected, its programmable full-scale range does not permit input pins above their supply-referenced electrical limits. Read the [TI datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf) before defining the interface.

## Balance

The photographed Nimbus has USB-B I/O for the PC and USB-A Display for a remote display. Use the [Adam manual](https://adamequipment.com.cn/media/docs/manuals/NBLe_i_UM_EN.pdf) and [official driver downloads](https://adamequipment.com/support/software-downloads.html). Verify the actual USB COM port, baud/parity settings, output units and streaming mode.

The documented single-line mass stream has weight and unit but no per-reading stability flag. Do not manufacture stability status. Stable-only output can withhold samples while collecting liquid; explicitly select and validate the intended acquisition mode.

## Items to resolve before energizing

- Pump model identifiers, connector gender and signal-specific returns.
- Board schematic, relay GPIO/polarity and startup output behavior.
- Valve contact rating for the actual AC inductive load and wiring protection.
- Power-supply voltage/current and total controller/interface demand.
- Sensor calibration, membrane area and liquid-density assumptions.
- Approved valve-state tables, pump commands, process limits and fault states.
- Correct backwash valve routing: the supplied text repeats valve 5 for inlet and outlet.
- Enclosure dimensions, terminal ratings, separation, strain relief and shutdown arrangement.

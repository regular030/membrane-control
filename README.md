# Basu Lab Membrane Control

Planned ESP32 firmware and a Windows desktop application for membrane experiment control, sensor acquisition, live graphs and reproducible run records.

**Status:** design and procurement baseline. No operational firmware, desktop executable or verified actuator pin map is included yet. This repository must not be used to energize the rig at this stage.

## Purpose

Bring the existing CIP, CWF and Fouling interfaces into one application while retaining the lab's pressure sensor, flow sensor, balance, pumps and solenoid valves. Replace damaged control boards, document the wiring and make experiments easier to configure and maintain.

The first pump connection is the existing **DB15** interface. The later **DB25** pump uses its own hardware profile and cable harness. The required PC USB connections are the ESP32's UART adapter and the Adam Nimbus balance. The previously discussed Omega USB pressure sensor is outside the required initial build.

## System layout

```text
Windows computer
  |-- USB --> CP2102 adapter <--> ESP32
  |                              |-- Relay outputs --> Seven valve channels
  |                              |-- I2C DAC --> 0-10 V pump speed command
  |                              |-- Isolated contact --> Pump start/stop
  |                              `-- Protected ADC inputs <-- Pressure, flow,
  |                                                          pump speed signal
  `-- USB-B I/O <-- Adam Nimbus balance

External regulated DC supply --> Controller's documented power input
Pump, balance and valve loads --> Their existing, appropriately rated supplies
```

Seven valves plus a separately controlled pump are visible in the legacy UI. An eight-channel relay board is a prototype candidate, not evidence that the pump is simply an eighth on/off motor. The 120 VAC valve switching section requires an appropriate enclosed assembly and electrical review.

## Design decisions and rationale

| Decision | Reason | Limit or tradeoff |
| --- | --- | --- |
| ESP32 owns time-critical sequencing and fault response | A frozen desktop or lost USB link must not leave sequencing dependent on the UI | Exact process-safe states and limits must be agreed with the lab |
| Python, PySide6, pyqtgraph and pyserial on Windows | Supports a normal desktop UI, live plots, device workers and a maintainable codebase | Validate balance drivers and build the executable on Windows |
| USB serial controller link | Simple wired connection for the permanently attached computer | Confirm ESP32 identity with a handshake; a detected adapter alone is insufficient |
| Separate balance connection | Retains the instrument's own measurement interface | Driver, serial settings and units need bench verification |
| External 0-10 V DAC | Pump speed input requires an analog voltage beyond the ESP32's native signal range | Verify grounding, load, startup output and isolation against the exact pump manual |
| Conditioned external analog acquisition | Accommodates 0-5 V sensors and a 0-10 V pump signal | An ADC breakout alone does not provide scaling or protection |
| DB15 and DB25 hardware profiles | Allows a later pump change with explicit connector mappings | A passive connector adapter does not establish electrical compatibility |
| Table-based recipe editor first | Easy to review valve states, durations and repeats | A later visual block editor can use the same validated recipe schema |
| SQLite records plus CSV export | Keeps run metadata and samples together and supports familiar exports | Define retention, backups and bounded chart memory for continuous operation |
| Bundled Windows application | Operators do not need to install Python packages for each run | Vendor USB drivers remain separate dependencies |

These are engineering decisions and their rationale, not claims that hardware compatibility has already been proven.

## Planned application

- Dashboard with device status, last-reading age, pressure, flow, mass, flux and pump command/readback.
- Manual valve and pump controls, labelled as commanded states unless physical position feedback exists.
- CIP, CWF and Fouling profiles, with configurable backwash and CEB phases.
- Sequence table: named step, explicit duration/unit, V1-V7 states, pump command and repetition.
- Live graphs for target/measured flow, pressure, flux and mass.
- Calibration settings, membrane area and liquid-density assumptions.
- Run history, raw-data diagnostics and CSV export.

No legacy sequence is reconstructed from an illuminated valve indicator in a screenshot. Native LabVIEW files or an operator-approved step table are needed to establish process behavior.

## Firmware and communication

Use Arduino C++ with Espressif's ESP32 core, with repeatable command-line builds in addition to IDE bring-up. Separate board wiring from logical valve/pump identifiers. A direct GPIO relay board and a shift-register relay board need different output drivers.

The proposed serial protocol uses newline-delimited JSON, bounded messages, a protocol version, request IDs, acknowledgements, controller identification, heartbeat messages and timestamped telemetry. Final message schemas will be specified under `protocol/` before implementation.

Firmware will use nonblocking acquisition and sequencing. Starting a run requires a verified board profile, valid recipe and required fresh inputs. Reset, communication timeout and local limit violations must produce the process-safe stop behavior agreed with the lab. Reconnection and power restoration must never resume an experiment automatically.

The desktop application is not an emergency stop. Independent electrical shutdown and process protection must be addressed in the hardware design.

## Measurements and records

- Preserve raw sensor values and calibrated values with units and calibration versions.
- Keep pump speed command/readback separate from actual fluid flow.
- Keep flow-meter measurements separate from balance-derived flow.
- Derive balance-based flow from mass change, elapsed time and configured liquid density. Handle tare/container changes explicitly.
- Derive flux from volumetric flow divided by configured membrane area, with explicit conversion to L/m2/h.
- Store UTC timestamps and monotonic elapsed time, recipe snapshots, firmware versions, events and faults.
- Separate sensor acquisition, graph refresh and file-recording intervals.
- The old UI labels cycle duration in seconds and data frequency in minutes. All new interval controls must state units explicitly.

## Hardware and purchase status

See [hardware/README.md](hardware/README.md) for the confirmed equipment and unresolved interfaces, and [hardware/procurement.md](hardware/procurement.md) for shopping links and purchase conditions.

The computer and controller are powered separately. A 12 V DC adapter is a controller supply candidate, not a supply for the balance, computer or 120 VAC valves. Use only the board input specifically documented for that voltage.

## Repository organization

| Folder | Intended contents |
| --- | --- |
| `firmware/` | Controller firmware, board drivers and verified pin profiles |
| `desktop/` | UI, device workers, run control and data storage |
| `protocol/` | Versioned messages and recipe schemas |
| `hardware/` | Wiring evidence, interface specifications and procurement |
| `docs/` | Implementation stages, acceptance criteria and operating procedures |
| `tests/` | Simulator, protocol, sequencing and data-conversion tests |
| `packaging/` | Windows build, installer/ZIP and driver setup instructions |

## Implementation stages

1. Recover the legacy application behavior and confirm wiring, calibration and process limits.
2. Build the application with simulated controller and balance data.
3. Verify real USB/UART identification and balance parsing.
4. Validate sensor acquisition and each low-voltage relay output.
5. Test pump command voltage with the pump disconnected, then supervised pump control.
6. Commission the enclosed valve circuits and approved recipes.
7. Verify disconnects, resets, invalid inputs, stale readings and pressure-limit responses.
8. Package the Windows app and run an extended recording/operation test.

See [docs/implementation-plan.md](docs/implementation-plan.md) for the acceptance checks and open decisions.

## Source material and privacy

The source ZIP supplied for review contains Arduino code exported to text plus LabVIEW front-panel photographs in a Word document. It does not contain the native `.vi` or `.lvproj` files. The Arduino code is primarily a generic NI LIFA bridge, rather than the experiment-specific application.

Original attachments, private correspondence and lab photos remain outside this repository. Add only material needed for the project, with appropriate lab authorization. Runtime data, credentials, local device configurations and build outputs are excluded from version control.

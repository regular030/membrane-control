# How the application fits together

Membrane Control was developed for Dr. Onita Basu's membrane research lab at
Carleton University.

The Windows application configures experiments, shows measurements and records
data. The ESP32 executes timed steps and handles its own heartbeat and pressure
faults. The balance connects to Windows independently of the ESP32.

```text
Windows app
  |-- Controller serial worker --> USB-UART --> ESP32 state machine
  |                                             |-- 74HC595 relay driver --> V1-V7
  |                                             |-- GP8403 DAC --> pump command
  |                                             |-- dry contact --> pump start
  |                                             `-- protected ADC <-- sensors
  |-- Balance serial worker <-- USB-B <-- Adam Nimbus
  |-- SQLite run database --> CSV and metadata export
  `-- Qt dashboard, charts, sequence editor and connection settings
```

## Why these choices

| Choice | Purpose |
| --- | --- |
| Python, PySide6 and pyqtgraph | A conventional desktop program with responsive controls and plots. |
| PlatformIO and Arduino C++ | Repeatable ESP32 builds with a small, readable controller core. |
| Newline JSON with request IDs | Commands and acknowledgements can be inspected during bring-up. |
| Table of timed steps | Operators can review every valve state and duration without learning code. |
| SQLite | Local records without installing a database server. Each run stores its recipe and settings. |
| Bundled portable EXE | Operators can run the app without installing Python or fetching packages. |
| Independent controller watchdog | Loss of host heartbeats causes a local fault; reconnecting never resumes a run. |

## Code map

- `desktop/src/membrane_control/ui.py`: five tabs, first-use help and bounded chart buffers.
- `controller.py`: device identity, command transactions, freshness, run recording and fault gates.
- `transport.py`: background serial workers and the desktop simulator.
- `models.py` and `engine.py`: validated recipes and deterministic simulated sequencing.
- `balance.py`: mass parsing and a rolling mass-change flow estimate.
- `storage.py`: transactional records and export.
- `firmware/include/ControlCore.h`: nonblocking firmware sequence and fault state machine.
- `firmware/include/BoardProfile.h`: the physical wiring and calibration configuration.
- `firmware/include/Hardware.h`: relay, ADC and pump DAC drivers.
- `protocol/v1.md`: the shared command and telemetry contract.

## What a run does

1. The operator selects or edits a recipe and presses Start.
2. The app checks controller identity, fresh telemetry and required balance data.
3. The app loads the recipe and waits for its acknowledgement before requesting Start.
4. The ESP32 validates the recipe and hardware profile, then advances steps using elapsed time.
5. Telemetry updates the plots; recording follows the recipe's separate interval.
6. Stop, completion or a fault ends the run. A later connection starts idle.

The controller's compile-time profile and the recipe's approval are separate.
Checking a box in the editor cannot supply missing physical pin assignments.
The default firmware is a dry run and does not operate the outputs.

## Current scope

Pump control is a percentage of the configured analog command range. It is not a
closed-loop flow controller. Pump voltage feedback, actual flow-meter readings
and balance-derived flow are different measurements. Solenoid valves are on/off;
a percentage opening is not supported by the existing valves.

The supplied source archive did not contain native LabVIEW VIs. CIP, CWF and
Fouling are editable demonstration recipes, not recovered chemical procedures.
Translate Raj's approved step table into recipes before commissioning the rig.

Physical wiring, mains-load switching, input protection, calibration and process
shutdown states need bench verification. Software simulation and compilation do
not establish those results. See the installation guide and firmware README for
the staged setup.

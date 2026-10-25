# Basu Lab Membrane Control

A Windows desktop application and ESP32 firmware for the ceramic membrane
experiment rig. The prototype combines valve and pump sequences, pressure and
flow measurements, balance readings, live graphs and recorded runs.

**Version 0.1.1 is a software prototype.** It opens in Simulation mode and
does not connect hardware automatically. The firmware's default build also
uses simulated measurements and dry-run outputs. The physical rig, board pin
mapping, pump interface and calibrations have not been commissioned.

## Open the Windows app

Download `BasuMembraneControl-0.1.1-windows-x64.exe` from
[Releases](https://github.com/regular030/basu-membrane-control/releases), or
extract the matching portable ZIP. A private repository requires GitHub access.
If an executable release is not listed yet, use the source instructions below.

Double-click the EXE and leave **Simulation mode** checked. Python and LabVIEW
are not required on the operator's computer. The application libraries are
bundled; CP210x and balance USB drivers remain separate vendor components if
needed. See [installation](docs/installation.md) and the
[operator guide](docs/operator-guide.md).

## What is implemented

| Tab | Functions |
| --- | --- |
| Dashboard | Controller and balance status, seven commanded valve states, separate pump command, pressure/flow/flux/mass values, live graphs and Start/Stop |
| Sequence editor | Explicit step durations and valve/pump states, repeats, recording interval, JSON import/export and example CIP/CWF/Fouling templates |
| Connections and settings | Explicit controller/balance port selection, firmware identity, freshness and verification status, membrane area and density settings |
| Run history | Local SQLite records, run metadata and CSV export |

The controller uses a versioned newline-delimited JSON protocol with bounded
messages, identity, acknowledgements, heartbeat, telemetry and fault states.
The desktop separates instrument communication from the UI, marks stale data
unavailable and never resumes a run merely because a device reconnects.
Graphs retain a bounded recent history; persistent records are kept separately.

The Dashboard's device checklist shows ESP32 and scale connections, available
pressure/flow/pump-voltage readings and simulated devices. Valve and pump
movement are labelled **Not monitored** because commands do not prove physical
operation. Status updates use existing data and never open ports automatically.

Demo templates are examples. Missing native LabVIEW `.vi` and `.lvproj` files
mean the original experiment sequences have not been recovered. Valve states
and timings have not been inferred from screenshots. Real recipes need an
operator-approved sequence and hardware approval before use.

## System arrangement

```text
Windows computer
  |-- USB --> CP2102 UART adapter <--> ESP32 relay controller
  |                                      |-- Seven valve channels
  |                                      |-- 0-10 V DAC --> Pump command
  |                                      |-- Isolated pump start/stop contact
  |                                      `-- Conditioned pressure/flow/readback inputs
  `-- USB-B I/O <--> Adam Nimbus balance

External DC supply --> Controller's documented voltage-compatible input
Computer, balance, pumps and AC valve loads --> Their own appropriate supplies
```

The current pump connection is **DB15**. A later **DB25** pump requires its own
verified profile and harness. The previously discussed Omega USB pressure
sensor is outside the initial required build. Seven valves and a separately
controlled pump are not eight interchangeable motor outputs.

The physical firmware profile ships unverified with unassigned pins and closed
actuation gates. A reviewed profile must define board wiring, polarity, safe
states, sensor conditioning/calibration and limits. A desktop setting cannot
bypass that gate. Independent rig shutdown and mains assembly review are still
required; the application Stop control is not an emergency-stop circuit.

## Run from source

Use Python 3.12 x64. From the repository root on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e ".[dev]"
.\.venv\Scripts\python.exe -m membrane_control --demo
```

Run tests with `.\.venv\Scripts\python.exe -m pytest`. See
[development and packaging](docs/development.md) for source smoke tests,
Windows EXE builds and the CI/release workflow. The seven top-level dependency
versions are pinned; transitive dependencies are resolved by pip.

Firmware build instructions and physical commissioning gates are in
[firmware/README.md](firmware/README.md). Build-only commands do not flash a
controller or energize hardware.

## Documentation and validation

- [Architecture and design choices](docs/architecture.md): how the software fits together and why.
- [Version 0.1.1 validation](docs/validation.md): completed software checks and remaining bench work.
- [Hardware baseline](hardware/README.md): confirmed instruments and unresolved interfaces.
- [Procurement](hardware/procurement.md): selected board, adapter and power candidates.
- [Wire protocol](protocol/v1.md): desktop/firmware contract.
- [Implementation and acceptance plan](docs/implementation-plan.md): bench and continuous-operation checks.

Automated tests and Demo smoke tests cover software behavior. Firmware builds
check compilation. Neither proves sensor accuracy, physical valve switching,
actual pump output voltages, chemical process suitability or 24/7 reliability.
Bench verification and an extended physical recording test remain necessary.

Operator data defaults to `%LOCALAPPDATA%\BasuMembraneControl`. Preserve and
back up that folder when updating the EXE. Original attachments, private
correspondence, lab photos, credentials and runtime databases remain outside Git.

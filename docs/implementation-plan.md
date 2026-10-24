# Implementation and acceptance plan

## Stage 1 Evidence and interfaces

Recover native LabVIEW VIs and dependencies or obtain an operator-approved sequence table. Confirm exact hardware profiles, sensor calibration, units, pump return references and process-safe states. The exported Arduino code is a generic bridge and does not specify the process sequences.

Acceptance: a reviewed wiring map and explicit step/state/timing table, with unresolved fields still marked unresolved rather than populated with guessed defaults.

## Stage 2 Simulator and protocol

Define bounded versioned messages, identity, acknowledgements, telemetry, stale-data handling and recipe schemas. Build simulated controller and balance adapters. Start the UI in idle/disconnected mode.

Acceptance: repeated commands, malformed data, partial lines, delayed telemetry, device resets and reconnects are handled; no implicit experiment restart.

## Stage 3 Acquisition

Verify USB balance output and serial settings. Validate analog front ends against known safe test signals. Store raw values, calibrated values, timestamps, units and calibration versions. Distinguish flow-sensor and balance-derived flow.

Acceptance: known values and units match expected tolerances; stale values are marked unavailable; tare and container changes do not generate misleading flow/flux.

## Stage 4 Outputs and pump

Verify every output with low-voltage test loads. Measure DAC zero/full-scale and startup behavior with the pump disconnected. Verify the stop contact defaults. Then validate one pump and one valve under supervision before expanding the wiring.

Acceptance: correct channel/polarity, no unintended startup pulses, process-safe reset/timeout behavior and no raw sensor overvoltage at logic inputs.

## Stage 5 Recipes and interlocks

Implement approved CIP/CWF/Fouling recipes and backwash/CEB phases using a nonblocking controller state machine. Validate permitted valve paths, pump ramps/limits and required sensor freshness. Save an immutable recipe/settings snapshot with each run.

Acceptance: agreed sequences and timing, pre-start validation, controlled transitions, operator stop and local fault responses demonstrated on the rig.

## Stage 6 Packaging and continuous operation

Build a Windows x64 executable bundle with pinned dependencies. Check vendor USB drivers separately. Bound chart memory, rotate diagnostic logs, flush/store records and define backup/retention behavior. Configure the dedicated PC for no sleep and controlled updates between runs.

Acceptance: clean-machine installation test; CSV export verified against stored samples; disconnect, restart and power-loss tests; extended soak test with no unbounded memory/log growth. App autostart may open to idle only.

## Open decisions

- Final eight-channel board revision, schematic, free I2C/GPIO pins and relay polarity.
- Exact DB15 pump model and future DB25 pump model.
- Analogue front-end design, electrical isolation and sensor supply arrangements.
- Lab-approved limits, shutdown behavior and independent emergency shutdown.
- Definition of old unlabeled controls and partially visible table columns.
- Retention, backup destination, exported data layout and operator permissions.

This repository currently contains documentation only. Acceptance checks above describe work to perform, not completed tests.

Membrane Control 0.1.18 improves normal controller recovery after telemetry loss and adds an idle sensor voltage check.

Developed for **Dr. Onita Basu's lab at Carleton University**.

## Install

Download **MembraneControl-Setup-0.1.18-windows-x64.exe** from Assets. The app-only update improves serial recovery. Use **Flash normal controller** from the new setup for the sensor check.

## Serial recovery

An unanswered handshake and an idle stale connection now release the COM port. The app pauses heartbeats while waiting for Stop and keeps an unconfirmed Stop fault visible. After reconnecting to a faulted ESP32, the operator can clear the fault after checking the rig. Old valve commands are never replayed.

See the [serial recovery guide](https://github.com/regular030/membrane-control/blob/v0.1.18/docs/serial-recovery.md).

## Read sensor inputs

Stop the controller, then open **Connections and settings → Read sensor inputs**. Factory normal firmware samples the protected ADC inputs and reports millivolts for pressure (IO34), flow (SVP / GPIO36), and optional pump feedback (SVN / GPIO39). The check does not populate calibrated PSI or mL/min or enable experiments.

See the [sensor test guide](https://github.com/regular030/membrane-control/blob/v0.1.18/docs/flow-sensor-troubleshooting.md#test-the-connected-sensors).

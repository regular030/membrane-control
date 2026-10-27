Membrane Control 0.1.16 corrects the installed valve IDs/mapping and fixes serial-port cleanup and recovery.

Developed for **Dr. Onita Basu's lab at Carleton University**.

## Update

Close the old app completely and install **MembraneControl-Setup-0.1.16-windows-x64.exe**. The COM recovery fix is in the desktop app. For the corrected normal valve mapping, also use **Flash normal controller**, select the ESP32 port (currently COM5), and reconnect in the main controller screen. App-only updates cannot change the ESP32 program.

## Confirmed valve map

The installed labels are **V1, V2, V3, V4, V5 and V7**. There is **no V6**:

| Valve | Bit |
| --- | --- |
| V1 | 0 |
| V2 | 1 |
| V3 | 2 |
| V4 | 3 |
| V5 | 5 |
| V7 | 6 |

Bit4 and bits7-15 remain LOW in manual mode. The normal UI retains the actual V7 label and hides V6 in controls, live data and sequence editing. The demo sequence no longer commands the absent V6. Normal ON/OFF still works without sensors or extra profile forms; pump/experiment behavior is unchanged.

Firmware announces explicit installed IDs as well as the bits. The new app keeps old firmware identifiable but disables the mismatched valve capability with an update message. The seven-slot wire format retains physical numbering: absent V6/index5 is false; V7/index6 is active. See [normal valves](https://github.com/regular030/membrane-control/blob/v0.1.16/docs/normal-valves.md).

## COM5 recovery

Failure-injection tests reproduced two software bugs: a failed close could lose ownership of an open handle, and a blocking driver close could freeze the GUI despite its worker timeout. Pending/failed handles are now retained across deleted test windows. One owned background closer performs driver cleanup, callers wait only their deadline, and a new connection cannot overlap the app's retired owner.

**Recover connection** in **Bare relay board test** retries cleanup, then starts a fresh firmware handshake. It clears old test state and does not replay pulses. Terminal errors take priority over stale packets, receive overflow keeps its exact reason, and hidden Dashboard graph refreshes pause behind equipment dialogs while polling continues. Other instruments' active ports are not seized.

The bare-relay firmware does not need reflashing solely for this app recovery change. A listed COM port still cannot prove firmware response or external driver health. The exact cause of the physical COM5 incident remains unconfirmed because it is on the separate lab PC. See [serial recovery](https://github.com/regular030/membrane-control/blob/v0.1.16/docs/serial-recovery.md).

## Validation

**686 desktop/packaging tests passed**, with four real-symlink cases skipped for unavailable Windows privilege. **100 native firmware tests and all four ESP32 builds passed.** Twelve recovery regressions cover failed/blocked closes, already-closed errors, deleted-window ownership, pending open, concurrent deadlines, no pulse replay, terminal overflow and active-instrument preservation. The corrected mapping and Recover button were visually checked with fake ports. Final packaging results are recorded in [validation](https://github.com/regular030/membrane-control/blob/v0.1.16/docs/validation.md).

The final packaged app passed an isolated Demo launch and clean exit; the Setup EXE passed its payload verification in plan mode. Setup/portable sources and docs match the final files, and firmware manifests plus all release artifact checksums passed. Both GitHub workflows passed actionlint.

This release retains the prior Nimbus scale improvements. No lab serial port was opened, no firmware was uploaded, and no physical valve was operated while preparing this update. Hosted Actions retain the existing account billing lock; binaries are built and checked locally.

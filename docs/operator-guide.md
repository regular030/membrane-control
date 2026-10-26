# Use the app

New user? Start with the [five-minute demo](START-HERE.md).
The app opens with **Simulation mode** checked. Its demo needs no USB equipment
and does not control the physical rig.

## Run a demo and save its results

1. On **Dashboard**, choose a **Preset**: CIP, CWF or Fouling.
2. Click **Start run**. Watch the current step, readings and graphs.
3. Click **Stop run** when you are finished.
4. Click **Export CSV**, then choose a filename and folder.
5. To export an older run, open **Run history**, select its row and click
   **Export selected run**.

Demo results are practice data, not lab measurements. The presets are example
sequences, not approved copies of the old LabVIEW programs.

Readings save automatically during a run. Export, editing and connection
changes are unavailable while an operation is active. Click **Stop run** and
wait for the stopped state before exporting or changing the setup.

## Understand the screen

Resize the whole interface with **Ctrl + -** (smaller) or **Ctrl + +** / **Ctrl + =**
(larger). **Ctrl + 0** resets it to 100%. The percentage appears at the bottom
right. Zoom changes in 10% steps from 60% to 150%; each launch starts at 100%.

The **Device connections** panel on Dashboard shows what the app actually
knows. Hover over a status for more detail.

| Status | Meaning |
| --- | --- |
| Connected | The ESP32 is responding, or current scale data is arriving. |
| Connected (dry run) | A real ESP32 is responding, but its firmware is simulating readings and outputs. |
| Simulated | This device or reading is generated for practice. |
| Reading received | The controller supplied a valid value. Its accuracy still depends on wiring and calibration. |
| Not connected / No reading | A current usable response is missing. |
| Not monitored | The app has no sensor confirming actual valve movement or pump operation. |

A scale may provide real measurements while the ESP32 is in dry run. Read each
status separately. An old point left on a graph is not a new measurement.

If **Start run** is unavailable, read the reason and suggested next action on
Dashboard. A recipe-review checkbox cannot make an unverified controller ready.
Use **Start here** or the **Help** tab if you need the first-use instructions.

## Read the live runtime table

During a sequence, **Live readings** beneath the graphs adds one row whenever a
sample is recorded, using the sequence's **Record every** interval. It includes
the recorded timestamp, runtime, cycle/step, desired and measured flow, flow
estimated from the scale, pressure, flux, mass, pump command/feedback, all seven
commanded valve states, operating mode and device/fault status.

Missing measurements display **Unavailable**. Valve and pump commands do not
confirm actual movement. The table shows the latest 1,000 rows to keep memory
bounded during long operation; complete samples remain in the local run database
and CSV export. Turn off **Follow latest** to inspect earlier rows. A new run
starts a new table; the completed run's rows remain visible until then.

## Review or change a sequence

Open **Sequence editor**. Each row is one step with a duration, valve settings
and a pump setting. Check every row before applying changes. The recording
interval controls how often results are saved, not how quickly the controls
respond. All time fields show their units.

**Apply sequence** uses your edited sequence. **Save as** asks for a name and
file location, then saves and applies that sequence as a custom preset.
**Import JSON** opens and applies a previously saved sequence. Check the
selected preset and the rows before starting it.

For a real experiment, use only the lab's approved sequence and measurement
settings. Membrane area affects flux; liquid density affects flow calculated
from the scale. Do not change these values just to make a graph look right.

## Compare desired and measured flow

Enter **Desired flow (mL/min)** on Dashboard and click **Apply target**. This
changes only the comparison target, not the pump setting or other sequence
edits. You can also set it in **Sequence editor**, then use **Apply sequence**.
The value is saved with custom presets and restored when you import one.

The flow graph shows **Measured flow** and a separate dashed **Desired flow**
line. Recorded samples and exported CSV files include both values; the target
is not substituted for a missing measurement. Older presets start with a target
of 0 mL/min, and older run samples export a blank target column.

This version does not automatically adjust the pump to reach that flow. Pump
output remains the configured percentage in each step or manual command until
the pump interface and flow-control calibration are verified. Stop the current
operation before changing the target.

## Try manual controls

With no sequence running, a valve button sends that valve command immediately.
Typing a **New pump setting** does not send it until you click **Apply pump**.
The **Sent** value shows the last command. Changing a valve keeps that sent pump
setting. Click **Stop run** to leave manual control before starting a sequence.
These are commands; the app cannot confirm physical valve movement.

## Use a commissioned rig

The person setting up the hardware must first verify the wiring, firmware,
calibration and operating limits. Connecting USB or selecting Hardware mode
is not that verification. See [installation](installation.md) for the USB steps
and the online [ESP32 setup guide](https://github.com/regular030/membrane-control/blob/main/firmware/README.md) for firmware work.

Before a physical run, confirm the correct instruments are connected, readings
are current, the approved preset is selected and the rig is ready for its liquid
paths. Valve indicators describe commands unless position feedback exists.

On a fault or disconnect, follow the lab's stop procedure and inspect the
message. Reconnecting USB must not restart the experiment. Restore a known rig
state before starting a new run. If the app is unresponsive, use the rig's
independent shutdown; the screen's Stop button is not an emergency-stop circuit.

## Keep your records

Recorded runs stay in `%LOCALAPPDATA%\BasuMembraneControl`. Back up this folder
and export important runs to CSV. Keep fault notes with the affected run and
record the software and calibration used for real measurements. Stop the run
and close the app before updating it or restarting the PC.

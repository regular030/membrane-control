# Operator guide

This guide describes the prototype workflow. The initial release runs in Demo
mode and has not been commissioned on the physical rig. Example CIP, CWF and
Fouling recipes show how to use the software; their valve sequences are not
recovered LabVIEW procedures or approved chemical-cleaning instructions.

## Explore Demo mode

1. Open the application and leave **Simulation mode** checked (Demo). Check
   that the interface identifies the readings as simulated.
2. Inspect the device status, seven valve channels and the separate pump
   command. A commanded relay state does not confirm physical valve position.
3. Select a sample CIP, CWF or Fouling recipe. Review each step's duration,
   explicit valve states and pump command before starting.
4. Start a simulated run. Watch the current step, elapsed time, graphs and
   event messages. Stop the run and inspect its recorded data.
5. Export a CSV and check its units, timestamps and run identification before
   using it in analysis. Demo data is for exercising the app, not lab results.

## Check device connections

The Dashboard's **Device connections** panel stays visible above the readings.

| Status | Meaning |
| --- | --- |
| Connected | The ESP32 is responding, or fresh scale readings are arriving. |
| Not connected | The required communication or scale data is unavailable. Select the device in Connections and settings. |
| Connected (dry run) | A real ESP32 is responding with firmware that simulates measurements and outputs. |
| Reading received | A valid analog reading is arriving from the controller. This does not establish correct wiring or calibration. |
| No reading | No current valid value is available for that input. |
| Simulated | The displayed device or measurement belongs to desktop Demo mode or ESP32 dry-run firmware. |
| Not monitored | Physical valve position and pump-running status are not measured by the current interfaces. |

The status panel does not open ports automatically. In desktop Simulation mode,
every device is labelled Simulated. With desktop Simulation mode off, a real
scale can be Connected while an ESP32 running dry-run firmware still supplies
simulated pressure, flow and pump feedback. Missing or stale controller data
must not leave an old reading marked available. Hover over a status for details.

## Configure an experiment

Define the complete state of V1 through V7 for every step, plus pump enable
and speed command. Use explicit duration units. Never infer the correct
sequence from a green indicator in a legacy screenshot.

Keep the recording interval separate from acquisition and control timing.
For example, a 30-second recording interval does not mean the controller waits
30 seconds between monitoring or sequencing updates. The legacy screenshots
label recording frequency in minutes and cycle durations in seconds; convert
those values explicitly when transferring settings.

Before deriving flux, record membrane area and units. Distinguish flow-meter
flow from balance-derived flow, and pump speed feedback from liquid flow.
Record liquid density for mass-to-volume conversions. A tare, container
replacement or unstable balance reading must not create an artificial flow
spike.

## Move to hardware after commissioning

The controller profile must match the exact board and DB15 pump harness.
The later DB25 pump needs a separately verified profile and harness. Connector
pin counts do not establish signal compatibility.

| Before starting | What the operator should establish |
| --- | --- |
| Controller | Correct firmware identity; responsive heartbeat; verified hardware profile |
| Balance | Correct instrument; fresh valid readings; expected units and stability status |
| Sensors | Valid calibration; fresh readings; reasonable pressure and flow |
| Recipe | Reviewed valve and pump sequence; explicit durations; appropriate limits |
| Recording | Writable destination; correct run name; recording interval and units checked |
| Rig | Ready for that sequence; correct liquid paths; independent shutdown available |

Begin with manual, supervised tests using the lab's commissioning procedure.
Do not attach live mains loads for a first software test. The desktop Stop
control depends on the computer and communication path; use the independent
rig shutdown if the app or connection fails.

Every launch starts in Demo mode. For a commissioned rig, stop the current run,
uncheck **Simulation mode** and select the controller and balance ports explicitly in
**Connections and settings**. The application does not probe arbitrary ports or reconnect
instruments automatically. Keep each instrument on its intended connection.

## Respond to a fault

Treat missing or stale data as unavailable. Do not interpret the last plotted
value as a fresh measurement. On a disconnect, stop using the affected
measurement for analysis and follow the lab's agreed physical stop procedure.

The firmware's heartbeat timeout and process-specific safe states provide a
local response; their actual wiring and behavior still require bench tests.
Restoring USB or power must not automatically restart an experiment. Inspect
the event log, restore a known rig state and explicitly start a new run.

Keep the original database and CSV with any fault notes. Record the software,
firmware, hardware profile and calibration used for a real experiment. Back
up the data folder regularly and test recovery before an unattended run.

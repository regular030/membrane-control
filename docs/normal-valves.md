# Use the six valves with normal firmware

The lab has **six valves**. Kunshpreet confirmed the individual relay tests and
corrected the count on 26 October 2026:

| Valve | Shift-register bit |
| --- | --- |
| V1 | 0 |
| V2 | 1 |
| V3 | 2 |
| V4 | 3 |
| V5 | 4 |
| V6 | 5 |

The tested polarity is **LOW = off, HIGH = energized**. Manual valve commands
leave relay bits 6-15 LOW. There is no installed V7.

## Install and use

1. Install **MembraneControl-Setup-0.1.15-windows-x64.exe**.
2. Close the app's controller connection. Open the installed **Flash normal
   controller** shortcut, choose the ESP32 port (COM4 if unchanged), and follow
   its upload and IO0/EN instructions. This uploads `esp32-physical`, the normal
   controller program. An app update alone cannot change the board program.
3. Open the app, turn **Simulation mode off**, and connect that ESP32 port.
4. On Dashboard, use **V1-V6 ON/OFF**. These six controls stay visible above the
   measurement cards. Click an energized valve again to turn it off.
5. **Stop valves** turns all six off. The existing connection watchdog also
   stops them if the app stops communicating. Restarting does not resume them.

No pressure sensor, flow sensor, scale, PWM converter, valve profile form or
additional review checkbox is required for these normal-firmware valve toggles.
The commands persist until changed or stopped; they are not the old 500 ms
pulse test. The app displays commanded coil states, not measured valve position.

The pump command remains zero in this valve-only manual state. Pump operation
and automatic experiments retain their separate input/pump configuration.
Stop the current mode before switching between valve-only and pump/recipe
operation. The optional older relay/pulse-test tools remain available under
Connections and settings, but are not needed for this six-valve workflow.

## Compatibility

Existing recipe and telemetry formats retain seven boolean slots so older data
can still be read. The unused seventh slot must be false for the new manual
command. The normal app shows six valve controls and six valve columns. A
legacy sequence that actively commands V7 needs correction before this rig can
use it. The normal firmware advertises `manual_valve_count: 6`, the confirmed
six-bit mapping and a separate `valve_control_ready` capability; the full
`hardware_verified` flag still describes pump/experiment readiness.

For membrane research in **Dr. Onita Basu's lab at Carleton University**.

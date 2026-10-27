# Use the six valves with normal firmware

The lab has **six installed valves: V1, V2, V3, V4, V5 and V7**. Kunshpreet
confirmed this mapping on 26 October 2026. **V6 is not installed.**

| Valve | Shift-register bit |
| --- | --- |
| V1 | 0 |
| V2 | 1 |
| V3 | 2 |
| V4 | 3 |
| V5 | 5 |
| V7 | 6 |

The tested polarity is **LOW = off, HIGH = energized**. Manual valve commands
leave unused relay bit **4** and bits **7-15** LOW. Keep the physical valve
names; V7 must not be relabelled V6.

## Install and use

1. Install **MembraneControl-Setup-0.1.16-windows-x64.exe**.
2. Close the app's controller connection. Open the installed **Flash normal
   controller** shortcut, choose the ESP32 port (currently COM5), and follow
   its upload and IO0/EN instructions. This uploads `esp32-physical`, the normal
   controller program. An app update alone cannot change the board program.
3. Open the app, turn **Simulation mode off**, and connect that ESP32 port.
4. On Dashboard, use **V1, V2, V3, V4, V5 and V7 ON/OFF**. These six controls stay visible above the
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

Recipe and telemetry arrays retain seven boolean slots in physical valve-number
order. **Index 5 is the absent V6 and must be false; index 6 controls V7.** Do not
pack V7 into the V6 slot. The normal app shows six named controls and columns:
V1-V5 and V7. Review old sequences that command the absent V6 before using them.

Normal firmware 0.1.16 advertises `manual_valve_count: 6`,
`manual_valve_ids: [1,2,3,4,5,7]` and `valve_bits: [0,1,2,3,5,6]`, together
with `valve_control_ready`. The desktop requires these explicit IDs and mapping
to enable this capability. Full `hardware_verified` still describes separate
pump/experiment readiness.

For membrane research in **Dr. Onita Basu's lab at Carleton University**.

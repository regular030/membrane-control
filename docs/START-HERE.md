# Start here

1. Open [Releases](https://github.com/regular030/membrane-control/releases)
   and open **Assets**. Download the file ending in
   **windows-x64.exe**. Do not choose **Source code (zip)**.
2. Double-click the EXE. The app tries **COM8** for the ESP32 and **COM6** for
   the scale when detected. Use **Connections and settings** to check the
   connection status, reconnect, or choose other ports.
3. On **Dashboard**, choose a lab-approved **Preset** and click **Start run**
   once the controller reports that the hardware is ready.
4. Watch the graphs, then click **Stop run**.
5. Click **Export CSV** and choose where to save the results. You can
   open the CSV in Excel.

To find that run later, open **Run history**, select it and click
**Export selected run**. The **Start here** button opens the app's **Help** tab.

If the interface does not fit on screen, press **Ctrl + -** to shrink it.
Use **Ctrl + +** (or **Ctrl + =**) to enlarge it and **Ctrl + 0** to reset to 100%.

## Know which mode you are using

| Mode | What happens |
| --- | --- |
| App launched with `--demo` | The app generates practice data without the rig. |
| ESP32 connected (dry run) | A real board is connected, but readings and outputs are simulated. |
| Hardware mode | You selected real connections. The lab must still verify the setup before physical use. |

The demo presets are examples, not approved lab procedures. A USB connection
or a checked recipe-review box does not make the real rig ready.

## Need help?

The confirmed rig has **six valves: V1-V5 and V7**, mapped to bits
**0, 1, 2, 3, 5, 6**. V6 is not installed; bit 4 is unused. With app/normal firmware
**0.1.16** or later, connect the ESP32 and use the six ON/OFF
buttons directly on Dashboard. No sensors, extra profile form or review boxes
are needed for manual valves. [Install the normal firmware once](normal-valves.md)
using **Flash normal controller**. Pump/experiment configuration is separate.

The [scale guide](scale-connection.md) covers COM6/9600, weight requests and the
raw-data test. The old unloaded relay and separate pulse-test tools remain
optional under Connections and settings. For missing flow values, use
[flow sensor troubleshooting](flow-sensor-troubleshooting.md).

For the selected pump PWM converter, give the maintainer the
[order, wiring and first-test guide](pwm-converter-setup.md). Install the latest
**Setup** EXE to receive its firmware sources and tools as well as the app.

- **No EXE:** use the release's **Assets**, not GitHub's green **Code** button.
- **Windows blocks it:** ask the maintainer or IT. Python is not required.
- **Start unavailable:** read the reason and next step shown on Dashboard.
- **No COM device:** check equipment power, the USB data cable or Bluetooth
  pairing, and the port list in Windows Device Manager.

Next: [app installation](installation.md), [operator guide](operator-guide.md),
or [ESP32 setup](https://github.com/regular030/membrane-control/blob/main/firmware/README.md) for the person preparing the hardware.

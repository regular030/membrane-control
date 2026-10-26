# Start here

Try the demo first. You do not need any USB equipment.

1. Open [Releases](https://github.com/regular030/membrane-control/releases)
   and open **Assets**. Download the file ending in
   **windows-x64.exe**. Do not choose **Source code (zip)**.
2. Double-click the EXE. Leave **Simulation mode** checked.
3. On **Dashboard**, choose a **Preset** such as **CWF** and click **Start run**.
4. Watch the graphs, then click **Stop run**.
5. Click **Export CSV** and choose where to save the practice results. You can
   open the CSV in Excel.

To find that run later, open **Run history**, select it and click
**Export selected run**. The **Start here** button opens the app's **Help** tab.

If the interface does not fit on screen, press **Ctrl + -** to shrink it.
Use **Ctrl + +** (or **Ctrl + =**) to enlarge it and **Ctrl + 0** to reset to 100%.

## Know which mode you are using

| Mode | What happens |
| --- | --- |
| Simulation mode checked | The app makes practice data. No USB equipment is needed. |
| ESP32 connected (dry run) | A real board is connected, but readings and outputs are simulated. |
| Hardware mode | You selected real connections. The lab must still verify the setup before physical use. |

The demo presets are examples, not approved lab procedures. A USB connection
or a checked recipe-review box does not make the real rig ready.

## Need help?

To test equipment without sensors, uncheck **Simulation mode** and open
**Connections and settings**. Choose **1. Bare relay board test** for an unloaded
board, or **2. Valve test (no sensors)** after the maintainer has completed the
separate reviewed valve profile. The factory valve-test image stays locked.
See [the valve test guide](valve-test.md). The pump is not operated by either tool.

For the selected pump PWM converter, give the maintainer the
[order, wiring and first-test guide](pwm-converter-setup.md). Install the latest
**Setup** EXE to receive its firmware sources and tools as well as the app.

- **No EXE:** use the release's **Assets**, not GitHub's green **Code** button.
- **Windows blocks it:** ask the maintainer or IT. Python is not required.
- **Start unavailable:** read the reason and next step shown on Dashboard.
- **No USB/COM device:** the demo still works. For real equipment, check its
  power, USB data cable and Windows Device Manager first. A board must appear
  there before it can connect or receive firmware.

Next: [app installation](installation.md), [operator guide](operator-guide.md),
or [ESP32 setup](https://github.com/regular030/membrane-control/blob/main/firmware/README.md) for the person preparing the hardware.

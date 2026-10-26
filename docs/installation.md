# Install and open the app

Use a Windows 11 x64 computer. You do not need Python, Arduino IDE or LabVIEW
for the ready-to-run app.

## Download

For a new Windows x64 PC, download **MembraneControl-Setup-0.1.10-windows-x64.exe**
from the release and double-click it. Internet is required to install its own
Python runtime, PlatformIO and ESP32 compiler/framework. It also installs the
app and creates shortcuts. See the [new-PC setup guide](https://github.com/regular030/membrane-control/blob/main/docs/setup-new-pc.md).
Device drivers remain separate; the setup provides USB driver help.

For the app alone, use the portable download below. It already bundles the
Python runtime and application libraries it needs.

1. Open [Releases](https://github.com/regular030/membrane-control/releases)
   to download the application and setup files.
2. Open the release given to you by the maintainer. Under **Assets**, download
   `MembraneControl-0.1.10-windows-x64.exe` or the matching portable app ZIP.
   **Source code (zip)** is for developers and does not contain the EXE.
3. If you chose the portable ZIP, right-click it and choose **Extract All**.
4. Open the EXE. Leave **Simulation mode** checked and follow
   [Start here](START-HERE.md).

First startup can take a little longer. The app includes its own libraries and
can run the demo without internet or USB equipment. It does not install device
drivers. Ordinary use does not require administrator access. If university
software protection blocks the file, ask the maintainer or IT to review it.

If the interface is too large, use **Ctrl + -** to shrink it. **Ctrl + +**
(or **Ctrl + =**) enlarges it; **Ctrl + 0** restores 100%.

## Connect USB equipment later

Do this after the person setting up the rig has approved its hardware. Installing
this Windows app does not install firmware on the ESP32 or verify the wiring.
The separate [ESP32 setup guide](https://github.com/regular030/membrane-control/blob/main/firmware/README.md) covers that work.

1. Power the equipment and connect its USB **data** cable.
2. Open Windows **Device Manager > Ports (COM & LPT)**. Note the COM number
   belonging to each device, such as `COM4`.
3. In the app, stop any run, uncheck **Simulation mode**, and open
   **Connections and settings**.
4. Click **Refresh serial ports**, select the known ESP32 port and click its
   **Connect** button. Select the scale's own port and connect it separately.
5. Read the status messages. A responding board may still be in **dry run**.

After restarting the PC, the app opens in Simulation mode again. Connect the
instruments explicitly; do not assume their COM numbers stayed the same.
If no port appears, stop at USB detection: try a known data cable, another USB
socket and the correct driver. A firmware upload cannot work before Windows
recognizes the board. Do not choose a port belonging to another lab instrument.
Close Arduino Serial Monitor or any other program already using the same port.

Use the driver for the chip on the actual device:

| Device | Official help |
| --- | --- |
| CP2102 / CP210x USB adapter | [Silicon Labs driver](https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers) |
| Freenove board with CH340 | [Freenove instructions and CH340 folder](https://github.com/Freenove/Freenove_Ultimate_Starter_Kit_for_ESP32) or [WCH driver](https://www.wch-ic.com/downloads/CH341SER_EXE.html) |
| Scale through the existing green USB-to-RS232 adapter | Use the driver for the adapter's actual chipset, if Windows needs one |
| Adam Nimbus through its alternative USB-B I/O connection | [Adam Equipment downloads](https://adamequipment.com/support/software-downloads.html) for the exact model |

Driver installation may need IT or administrator access. The app does not
silently download or run driver installers. The photographed scale connection is
its DB9 **RS-232** port through a USB-to-RS232 adapter. Reuse that path first.
The scale's USB-B **I/O** port is an alternative PC connection; its USB-A display
socket serves a different purpose. Select the balance's own COM port, with serial
settings matching the scale. See the [balance setup guide](https://github.com/regular030/membrane-control/blob/main/hardware/balance-usb-setup.md).

## Updates and saved data

Stop the run and close the app before replacing its EXE. Your recorded runs
stay in `%LOCALAPPDATA%\BasuMembraneControl`. The folder keeps its original name
so existing run history remains available. Paste that address into File
Explorer to find it. Back it up and keep important CSV exports.
Reopening the app or restoring USB does not resume an experiment.

If the app will not open, send the maintainer the version and this file, if it
exists: `%LOCALAPPDATA%\BasuMembraneControl\logs\launcher-error.log`.
For ordinary operation, continue with the [operator guide](operator-guide.md).
Developers should use the online [development guide](https://github.com/regular030/membrane-control/blob/main/docs/development.md) for source installation.

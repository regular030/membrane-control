# Install and open the app

Use a Windows 11 x64 computer. You do not need Python, Arduino IDE or LabVIEW
for the ready-to-run app.

## Download

1. Open [Releases](https://github.com/regular030/membrane-control/releases)
   and sign in if needed. This project is private.
2. Open the release given to you by the maintainer. Under **Assets**, download
   `MembraneControl-0.1.5-windows-x64.exe` or the matching portable app ZIP.
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
| Adam Nimbus scale | [Adam Equipment downloads](https://adamequipment.com/support/software-downloads.html) for the exact model |

Driver installation may need IT or administrator access. The app does not
silently download or run driver installers. Use the scale's USB-B **I/O** port
for the PC connection; its USB-A display socket serves a different purpose.

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

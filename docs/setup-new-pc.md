# Set up a fresh Windows computer

Use Windows 11 x64 and an internet connection for the first setup. Download
`MembraneControl-Setup-0.1.11-windows-x64.exe` from this project's release
assets and run it. Python, Arduino IDE and LabVIEW do not need to be installed
beforehand.

Setup installs the bundled desktop application, a private Python runtime,
PlatformIO, the ESP32 firmware source and its compiler/framework dependencies.
It builds the dry-run, real relay-board-test and full-controller firmware without
connecting to or flashing a board. The full controller's shipped hardware
profile is unverified, so physical operation stays locked.
The application includes PySide6, pyqtgraph, NumPy and pyserial. The firmware
tools live with this installation instead of changing the computer's global
Python or PATH settings. An interrupted download can be retried; read setup's
completion/error messages before continuing.

The default installation folder is `%LOCALAPPDATA%\Programs\MembraneControl`.
Setup and upload logs are in its `logs` folder. Recorded experiments stay in
the separate `%LOCALAPPDATA%\BasuMembraneControl` data folder.

1. Open the **Membrane Control** desktop shortcut and try Simulation mode.
2. Connect the CP2102 controller using a USB data cable. Check **Device Manager
   → Ports (COM & LPT)** for its COM port. No COM port means resolve its USB
   cable/driver first; flashing cannot fix Windows USB detection.
3. If needed, open **USB driver help**. This release does **not** bundle or
   automatically install a USB driver: Silicon Labs' archive returned HTTP 403
   during release preparation, so its bytes/checksum could not be verified.
   The helper explains Windows Update/Device Manager and offers to open the
   [official Silicon Labs page](https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers).
   Driver installation may require administrator approval or university IT.
   The helper does not change PowerShell's global execution policy.
4. Follow the firmware setup guide and use the **Flash ESP32 dry run** shortcut only
   after selecting the correct COM port and deliberately confirming the upload.
   Setup itself never flashes a controller or enables physical outputs.
   For the unloaded relay board, the separate **Flash relay board test** shortcut
   installs real test-pulse firmware. Use the app's **Relay board test** window
   and follow the [relay test guide](relay-board-test.md) with contact loads removed.
   **Flash full controller (setup required)** uploads the complete controller
   program with its default profile locked. The installed `firmware-release`
   folder also contains the versioned source/binary bundle. See
   [full firmware](full-firmware.md) before choosing that target.
5. Connect the scale separately. Its existing green **USB-to-RS232 adapter**
   uses the balance's DB9 port. Its chipset cannot be identified from its color;
   identify its hardware/driver with IT if Windows does not recognize it. Do
   not assume the CP210x driver is appropriate. The alternative scale USB-B
   **I/O** path uses the [Adam driver](https://adamequipment.com/support/software-downloads.html)
   if required. See [balance setup](../hardware/balance-usb-setup.md).
6. In **Connections and settings**, choose the controller and scale's different
   COM ports. Match the scale to **9600 baud, NONE / 8N1** and continuous
   single-line grams output. Those settings must be verified on the scale, not
   inferred from a photo. The app marks weights stale after 3 seconds without
   valid readings; stable-only or manual-print modes can therefore look stale.

Later ordinary use and dry-run flashing can work offline once setup has finished
downloading its tools. Drivers are separate from Python dependencies, and no
installer can infer the unidentified scale adapter's chipset. Reopening the app
or reconnecting USB does not restart an experiment.

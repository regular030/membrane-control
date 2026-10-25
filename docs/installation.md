# Install Basu Membrane Control

Version 0.1.2 is a lab prototype. Demo mode can be used without instruments.
Physical wiring, pump control, calibration and operating recipes have not yet
been commissioned on the rig.

## Download and open

Use Windows 11 x64. The operator does not need Python, pip, Arduino IDE or
LabVIEW to run the packaged desktop application.

1. Sign in to GitHub with an account that can access the private repository.
2. Open the repository's **Releases** page and select the release provided by
   the project maintainer. A draft release is visible only to collaborators
   with sufficient repository access.
3. Download `BasuMembraneControl-0.1.2-windows-x64.exe` directly, or download
   the matching `.zip` and extract it to a local folder. Choose the release
   asset, rather than GitHub's automatically generated source-code ZIP.
4. Double-click the executable. Leave **Simulation mode** checked (Demo).
   Simulated readings
   should appear without USB hardware.

The EXE includes Python, PySide6, plotting and serial libraries. First startup
may take longer while the one-file bundle extracts to a temporary folder.
It does not download packages, run an installer, or change device drivers.
Administrator access is not required for the application itself.

This prototype may be unsigned. Windows or university endpoint protection may
ask an administrator to review it. Check the source and release checksum with
the maintainer; follow the university's software policy rather than disabling
endpoint protection.

To compare a download with `SHA256SUMS.txt`, open PowerShell in the download
folder and run:

```powershell
Get-FileHash .\BasuMembraneControl-0.1.2-windows-x64.exe -Algorithm SHA256
```

A matching hash confirms the file matches that release asset. It is not a
replacement for verifying the repository and publisher.

## First hardware connection

Start with the controller's low-voltage section and disconnected test loads.
The supplied firmware's factory configuration uses dry-run outputs. It does
not establish that the actual relay board is ready to operate valves.

| Device | Connection | First-time check |
| --- | --- | --- |
| ESP32 controller | Laptop USB to CP2102 adapter; adapter's 3.3 V TTL UART to the controller | Confirm a COM port, then a firmware identity and heartbeat response |
| Adam Nimbus balance | USB-A to the balance's USB-B **I/O** port | Verify the instrument's USB mode, driver, serial settings and output format |
| Controller power | Separate external supply to the board's documented voltage-compatible input | Check voltage, polarity and current capacity; the UART adapter is not the relay power supply |

If Windows does not recognize the CP2102, obtain the appropriate driver from
[Silicon Labs](https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers).
Use [Adam Equipment support](https://adamequipment.com/support) for the exact
balance model's manual and USB driver, if one is required. Driver installation
may need university IT or administrator access. The application does not
silently download or execute either vendor's installer.

Open **Device Manager > Ports (COM & LPT)** and note each device's COM number.
A USB adapter detected by Windows is not proof of communication with ESP32
firmware. Close Arduino Serial Monitor and other software holding the same
port before connecting from the app.

The application starts in Demo mode and never opens instrument ports
automatically. In **Connections and settings**, select each known instrument's port before
clicking **Connect**. Refreshing the list enumerates available ports; it does
not send identification commands to unrelated serial devices. Do not select a
port belonging to another lab instrument. A previously used COM number may be
assigned to a different device after reconnection, so check Device Manager.

Before any physical run, complete the commissioning checks in the hardware
documentation. Confirm all required instruments, calibration and a reviewed
hardware profile. The application is not an independent emergency stop.

## Files, updates and troubleshooting

Operator data belongs under `%LOCALAPPDATA%\BasuMembraneControl`, separate
from the executable. Back up this folder and export important runs to CSV.
Do not save experiment data inside a temporary extraction folder.

For an update, stop the run, close the app and replace the executable with a
verified release. Preserve the data folder. Reconnection or app restart is
never an instruction to resume an interrupted experiment.

If the window does not open, look for
`%LOCALAPPDATA%\BasuMembraneControl\logs\launcher-error.log` and send the
error text plus application version to the maintainer. If a device is missing,
check its power, data cable, Device Manager entry and port ownership. A USB-A
to USB-A cable must not be used to connect the laptop to the balance's USB
host/digital-I/O socket.

Packaging background: [PyInstaller's operating model](https://pyinstaller.org/en/stable/operating-mode.html).

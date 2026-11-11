Membrane Control portable app
Windows 11 x64 app

Developed for membrane research in Dr. Onita Basu's lab at Carleton University.

Connect the rig

1. Extract this ZIP, then double-click the file ending in windows-x64.exe.
2. The app tries the lab ESP32's outgoing Bluetooth port and COM6 for the
   scale at startup when detected. Open Connections and settings to check
   the device status.
3. With reviewed hardware and a lab-approved sequence, choose the preset on
   Dashboard and click Start run.
4. Click Stop run, then Export CSV to save the results.
5. Open Run history to find earlier runs and Export selected run.

The Start here button in the app opens Help. Read START-HERE.md for the short
guide, installation.md for download/USB help, and operator-guide.md for use.

The open-bucket pump test uses its own firmware. Use the Windows Setup
shortcut Flash open-bucket pump test with the wired ESP32 USB port. Then
open Connections and settings, choose Open-bucket pump test, and select the
same wired USB port. The lab controller's wired USB port is usually COM5.
After testing, close the test window and restore the normal rig firmware.

Resize the whole interface: Ctrl + - makes it smaller, Ctrl + + (or Ctrl + =)
makes it larger, and Ctrl + 0 restores 100%. The bottom right shows the percentage.

You do not need to install Python or LabVIEW. The app includes its libraries.
Device drivers, when needed, come separately from the device manufacturer.

Launching the EXE with --demo generates practice data. An ESP32 connected in dry run also simulates
its readings and outputs. USB connection or a checked recipe-review box does
not make the physical rig ready. The lab must verify the hardware first.

Recorded runs stay in %LOCALAPPDATA%\BasuMembraneControl. Back up that folder
and keep important CSV files when updating the app. Runs never resume just
because the app or computer restarts.

Membrane Control portable app
Windows 11 x64 app

Developed for membrane research in Dr. Onita Basu's lab at Carleton University.

Try the demo

1. Extract this ZIP, then double-click the file ending in windows-x64.exe.
2. Leave Simulation mode checked. No USB equipment is needed.
3. Choose a Preset on Dashboard and click Start run.
4. Click Stop run, then Export CSV to save the practice results.
5. Open Run history to find earlier runs and Export selected run.

The Start here button in the app opens Help. Read START-HERE.md for the short
guide, installation.md for download/USB help, and operator-guide.md for use.

Resize the whole interface: Ctrl + - makes it smaller, Ctrl + + (or Ctrl + =)
makes it larger, and Ctrl + 0 restores 100%. The bottom right shows the percentage.

You do not need to install Python or LabVIEW. The app includes its libraries.
Device drivers, when needed, come separately from the device manufacturer.

Simulation means practice data. An ESP32 connected in dry run also simulates
its readings and outputs. USB connection or a checked recipe-review box does
not make the physical rig ready. The lab must verify the hardware first.

Recorded runs stay in %LOCALAPPDATA%\BasuMembraneControl. Back up that folder
and keep important CSV files when updating the app. Runs never resume just
because the app or computer restarts.

# Membrane Control

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

A Windows app for viewing membrane experiment readings, running valve/pump
sequences and saving results. **Start with the demo. No USB devices are needed.**

## First time here?

Open the [short Start here guide](docs/START-HERE.md).

1. Open [Releases](https://github.com/regular030/membrane-control/releases)
   and download the Windows `.exe` under **Assets**. For a fresh PC including
   Python and ESP32 firmware tools, choose **MembraneControl-Setup**.
   Sign in if GitHub asks.
   **Source code (zip)** contains the code, not the ready-to-run app.
2. Double-click the EXE. If using Setup, wait for completion and open the new
   **Membrane Control** shortcut. Leave **Simulation mode** checked.
3. Choose a **Preset**, then click **Start run**.
4. Click **Stop run**, then **Export CSV** to save the results.
5. Use **Run history** to find and export earlier runs.

Python and the app's libraries are bundled. LabVIEW is not required.
For download, driver or startup help, see [installation](docs/installation.md).
For setup on a new PC, see [one-file setup](docs/setup-new-pc.md).
The app's **Start here** button opens its **Help** tab.
Use **Ctrl + -** to shrink the whole interface, **Ctrl + +** (or **Ctrl + =**)
to enlarge it, and **Ctrl + 0** to reset to 100%.

## Find your way around

| Tab | What it is for |
| --- | --- |
| Dashboard | Readings, graphs, device status, Start/Stop and manual controls |
| Sequence editor | Review or change the steps in a preset |
| Connections and settings | Select the ESP32 and scale, and check measurement settings |
| Run history | Find recorded runs and export their measurements |
| Help | First-use instructions and an explanation of the operating modes |

## Before using the real rig

This is a prototype. The real wiring, sensor calibration and valve/pump
operation still need bench verification. The CIP, CWF and Fouling demo presets
are examples, not recovered or approved LabVIEW procedures.

Simulation mode uses generated readings. An ESP32 connected with **dry-run
firmware** also generates readings and does not operate the outputs. Seeing a
USB device, connecting the ESP32, or checking a recipe-review box does not make
the rig ready. Follow the lab's setup and approval process before physical use.
See the [operator guide](docs/operator-guide.md).

Runs are kept in `%LOCALAPPDATA%\BasuMembraneControl`. Back up this folder and
keep important CSV exports when updating the app.

## For developers and the person setting up hardware

Everyday users can use the EXE without these tools.

Pushing changes to `main` builds and tests the app on GitHub. After the checks
pass, the new **Main build** appears under **Releases** with a Windows EXE.
See [automatic GitHub builds](docs/development.md#automatic-github-builds).

- [Development](docs/development.md): run the source, tests and Windows build.
- [ESP32 setup](firmware/README.md): USB detection, firmware upload and hardware verification.
- [Architecture](docs/architecture.md) and [protocol](protocol/v1.md): how the code fits together.
- [Hardware](hardware/README.md), [parts](hardware/procurement.md) and [pin plan](hardware/relay-board-pin-plan.md).
- [Validation](docs/validation.md): software checks and physical tests still needed.

Original lab attachments, credentials and recorded experiment data stay outside Git.

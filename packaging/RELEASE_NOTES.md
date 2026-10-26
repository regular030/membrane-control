Membrane Control 0.1.14 makes the sensor-free valve test easier to prepare and use.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download and use

Download **MembraneControl-Setup-0.1.14-windows-x64.exe**. Setup updates the app and installs the valve-profile preparation helper, complete firmware source and guides. The app-only EXE does not include the build tools. Close the old app before updating.

With **Simulation mode off**, choose **Valve test (no sensors)** directly on Dashboard, or **2. Valve test (no sensors)** in Connections and settings. Disconnect in that window and choose **Set up valve mapping and firmware**. The form records the measured V1-V7 raw-bit map, full all-off pattern and installation reviews, then prepares a private valve-only build without editing C++ or the shared PlatformIO configuration.

The separate helper opens a visible console, builds first and requires the exact typed phrase **UPLOAD VALVE TEST** before accessing the selected COM port. Keep pump power/control isolated and relay contact loads disconnected for the initial upload. Reconnect after the installation checks, complete the session checks, arm, and request one **500 ms** valve pulse at a time. No pressure, flow, balance or PWM converter is required for this test. The prepared setup ID must match the board's reply; no pulse is sent automatically.

**All LOW off / All HIGH on confirms polarity, not the individual valve map.** Unknown mappings start blank. Drafts retain recorded values but do not restore review flags. Private build/profile files stay outside the shared factory firmware, whose valve and production profiles remain locked. This tool does not run the pump or an experiment and does not certify mains wiring, valve motion or hydraulic safety. Follow the [valve test guide](https://github.com/regular030/membrane-control/blob/v0.1.14/docs/valve-test.md).

## Missing sensor values

The full controller now reports optional per-input configuration and status. The app distinguishes a disabled channel, locked profile, unavailable hardware, missing calibration, invalid range and stale acquisition instead of showing only **No reading**. Valid zero readings remain valid. Diagnostics do not acquire unconfigured inputs, generate missing measurements or unlock physical outputs. See [flow sensor troubleshooting](https://github.com/regular030/membrane-control/blob/v0.1.14/docs/flow-sensor-troubleshooting.md).

Balance behavior is unchanged. Scale troubleshooting is deferred at the user's request.

## Validation and scope

**550 desktop/packaging tests passed**, with four real-symlink checks skipped for missing Windows privilege. **79 native firmware tests**, all four factory target builds, a separate synthetic generated-profile build, the packaged app and the Setup payload checks passed. The final Dashboard UI changes also passed 57 focused tests. The [validation record](https://github.com/regular030/membrane-control/blob/v0.1.14/docs/validation.md) gives details.

The firmware ZIP still contains the four factory targets plus complete source. No physical rig, serial port or connected valve was operated while preparing this release. Hosted Actions remain blocked by the existing account billing lock; release files were built and checked locally.

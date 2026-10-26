Membrane Control 0.1.13 adds pump-command support for the selected Amazon PWM-to-0-10 V converter.

Developed for membrane research in **Dr. Onita Basu's lab at Carleton University**.

## Download

Close the old app and download **MembraneControl-Setup-0.1.13-windows-x64.exe** to update the app, firmware sources, setup guides and installed tools. **MembraneControl-0.1.13-windows-x64.exe** is an app-only update. Python is bundled with the desktop app. Pump PWM support requires the new full-controller firmware and a reviewed installation profile; updating only the desktop EXE does not change the board program.

## Selected PWM converter and wiring

The selected part is the [EC Buying PWM converter, B0CPJGFCGR](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR). Its listing specifies a 3.3-12 V module supply, 3.3 V-compatible PWM, and selectable 0-5/0-10 V output. Do not order an I2C DAC as well for the same command path. The module is not isolated; its signal and output reference must be checked against the pump and USB ground arrangement. No delivery date or price is promised here.

The new [setup handoff](https://github.com/regular030/membrane-control/blob/v0.1.13/docs/pwm-converter-setup.md) covers the order list, candidate GPIO25/PWM connection, converter OUT to pump DB15 1/3, separate isolated start/stop contact 10/12, and protected feedback 9/5. It also corrects the old notebook interpretation: Mega D3 generated 5 V PWM and A8/A10/A12 were analog inputs. No hidden external DAC is assumed.

The PWM backend uses reviewed pin/timer settings and a measured settling interval. It commands zero duty at initialization, holds the independent pump STOP contact during changes, and only permits RUN after the nonblocking delay and a current controller safety tick. Stop/fault cancels pending activation. Checked LEDC operations report initialization/write errors. PWM cannot detect an unplugged converter or prove its analog voltage. GP8403 operation remains supported for older reviewed profiles; the PWM path does not require or probe that DAC.

## Firmware bundle and existing tools

**MembraneControl-Firmware-0.1.13-esp32.zip** includes complete source and four compiled targets: dry-run, bare relay bench, sensor-free valve test and physical controller, with offsets/checksums. The portable ZIP and Setup include it. The new setup guide and parts list are bundled for the lab maintainer. A PWM profile example is included with all approvals false and missing measured mapping/calibration values. Custom reviewed local profiles are excluded, and the factory-image packager rejects commissioned builds labelled as factory images.

The separate **Valve test (no sensors)** remains available with its own reviewed valve-only profile and isolated pump. Normal production still requires a checked board profile, protected/calibrated pressure and independent stop hardware. Missing readings are not generated. The scale uses USB-B I/O and has a second COM port, but balance-side serial setup and weight receipt remain unresolved. Desired flow remains a comparison target, not automatic flow regulation.

A source-only converter bench project is also included for voltage checks with the pump and all valve contact loads disconnected. It provides explicit serial confirmation, fixed percentage commands and a five-second cap rather than bypassing pressure checks in the production controller. It is built separately; no fifth factory image or automatic hardware test is installed.

## Validation

All **421 desktop/packaging tests**, **67 native firmware tests**, four main ESP32 builds and the separate converter bench build passed. The Windows app launched in isolated demo mode and exited cleanly; Setup verified its bundled payload without installing or opening USB. Both workflows pass actionlint. Results are recorded in the [validation record](https://github.com/regular030/membrane-control/blob/v0.1.13/docs/validation.md).

No physical rig was operated for this release. Converter output, settling, loss of PWM, power sequencing, harness references and complete rig commissioning must still be checked after the hardware arrives. Hosted GitHub Actions remain blocked by the account billing lock; release binaries were built and checked locally.

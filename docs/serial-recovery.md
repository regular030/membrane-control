# ESP32 serial connection recovery

The user reports that COM5 remains visible in Windows Device Manager after the
bare-relay tool disconnects, but the app cannot identify the firmware again
until the PC restarts. A listed port proves that Windows lists the adapter; it
does not prove that a program can open the port or receive firmware data.

## Normal firmware after a telemetry or Stop timeout

**Controller telemetry is stale** means the app stopped receiving usable
controller updates. **No acknowledgement for stop** means the app could not
confirm the Stop command. Check the equipment locally and switch off the
valve and pump load supplies before retrying.

1. Close Membrane Control and any serial monitor. Unplug the ESP32's USB-to-UART
   adapter from the PC, wait for that COM entry to disappear, and reconnect it.
2. With only the controller supply on, tap **EN** with **IO0** released.
3. Reopen the app, refresh ports, and connect the ESP32 in **Connections and
   settings**. If a fault remains after reconnecting, clear it only after
   checking the rig. The app does not resume an old valve command.
4. If the app still says the adapter opened without an ESP32 response, capture
   the boot log at **115200 baud** with the app closed. A working USB COM port
   can coexist with a reset, power, or UART problem on the controller.
   [ESP32 boot log](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html#boot-log)

App 0.1.18 releases a connection if firmware never responds, stops heartbeats
while Stop is pending, and lets the operator clear a latched fault after a
fresh handshake. If the valve-switching failure only happens with a load
connected, have the load switching and board supply checked before repeating
it under load. A brownout or electrical transient is possible and needs an
on-site check.

## Capture a dropout in 0.1.19

After the next dropout, use **Connections and settings → Copy ESP32 log** before
pressing EN. Paste the recent events into the troubleshooting message. The log
records the COM port, valve commands, matching acknowledgements, last telemetry
age and uptime, Stop and connection errors. It keeps recent events across app
restarts in the app data folder under `logs/esp32-link.jsonl`.

A fresh handshake records the ESP32's last boot reason when the new firmware
reports it. An EN reset or power cycle can replace an earlier reset reason.
The app and firmware have no three-command cutoff. Record which valves were
commanded and whether their relay LEDs, contact outputs, and actual valves
responded. A relay click alone establishes relay movement. If the controller
remains responsive in an unloaded check, have the affected valve circuit and
power checked before repeating with the load attached.

## A valve reply is missing but telemetry continues

In the supplied 0.1.19 log, the V1 command was followed by a malformed serial
line. Valve-mode telemetry continued, then the ESP32 acknowledged Stop. Valid
telemetry stopped after that acknowledgement. Windows reopened COM5, and the
ESP32 never answered the logged reconnect requests. This sequence does not
identify what interrupted communication after Stop.

App and normal firmware 0.1.20 can use a fresh telemetry receipt containing the
exact valve request ID and requested states to recover a lost valve reply. If
there is no matching receipt, the original Stop fallback applies. After a full
dropout, separate the rig's load wiring from the test and check boot and idle
serial output at 115200 baud. If the relay board stays connected unloaded,
have the lab check the valve circuit and its supply before retrying under load.

## Bare relay board recovery

In **Bare relay board test**, select the ESP32 port and click **Recover
connection**. The app ends the old session, retries its outstanding port cleanup,
and starts a fresh firmware handshake only after the previous owner releases
the port. It does not restore an old pulse, baseline confirmation or queued
command. A pending cleanup is reported rather than opening a competing worker.

If the app reports that a close is still pending, let it finish and try Recover
again. If another program owns COM5, close that program's serial connection.
Keep the exact error if it persists. A Windows driver or device that never
finishes its I/O cannot be guaranteed to recover solely through this button.

## What changed

Failure-injection tests reproduced an app bug: the connection object could be
discarded before its handle successfully closed, and the relay window could
discard the failed cleanup owner too. Closing and reopening the test window
then provided no route to retry releasing that port. A second reproduced bug
allowed a driver's blocking close call to freeze the GUI despite the nominal
worker timeout.

The new transport retains failed or pending cleanup across deleted dialogs,
serializes physical close attempts, and bounds caller waits. A replacement
connection cannot overlap the app's retired owner. Terminal errors take
precedence over stale queued status, and receive overflow reports its actual
reason. Active ports owned by another instrument are not seized. Dashboard
graphs pause behind equipment dialogs while controller polling continues,
reducing unnecessary work on the GUI thread used for test heartbeats.

The exact cause of the lab failures still needs a boot log or an on-site test.

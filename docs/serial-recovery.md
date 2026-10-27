# COM5 is listed, but the relay tool cannot reconnect

The user reports that COM5 remains visible in Windows Device Manager after the
bare-relay tool disconnects, but the app cannot identify the firmware again
until the PC restarts. A listed port proves that Windows lists the adapter; it
does not prove that a program can open the port or receive firmware data.

## Recovery in app 0.1.16

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

These are demonstrated software failures and recovery fixes. The exact cause
of the reported physical COM5 incident still needs a live error/log; the
adapter is on the separate lab PC. No lab serial port was opened to prepare
this update.

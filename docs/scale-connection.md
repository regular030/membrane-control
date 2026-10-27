# Adam Nimbus scale: USB-B, COM6 and 9600

The current scale is **Adam Nimbus NBL 8201e**. Its display changes normally.
It is connected through its square **USB-B I/O** port and currently appears as
**COM6** on the lab PC. The ESP32 uses its own separate port. The former green
USB-to-RS232 adapter is not the current connection.

## Try app 0.1.15

1. Open **Connections and settings** with Simulation mode off.
2. Under Balance, select **COM6**, **9600**, and the serial format matching the
   balance's menu: **NONE = 8N1**, **EVEN = 7E1**, **ODD = 7O1**.
3. Leave **Request weight every second** checked and click **Connect**.
   The app requests a weight when a fresh weight is not already streaming.
4. Watch **Balance mass** on Dashboard. **Request reading** also sends a manual
   read-only Print request. No tare, zero, reset or settings command is sent.

Automatic/manual requests share a one-second rate limit and wait until the
port actually opens. Sending a request does not count as receiving a weight.
The displayed mass and connection evidence still require actual valid data.

## If no weight arrives

Open **Test scale / raw data** in the Balance section. This closes the main
scale connection first so two windows cannot compete for COM6. Select the same
port, baud and format, then **Connect** and **Request reading**. The window
shows actual received bytes, decoded lines, parsed masses and errors, with both
escaped text and hexadecimal data.

- **No bytes received:** check `SERIAL ENABLE` on the balance, its baud/parity
  and the USB-B data cable. The Nimbus manual requires a power cycle after
  serial setting changes. A COM port by itself does not prove data is arriving.
- **Bytes arrive but no readable lines:** match the parity/format selection to
  the balance. The app now accepts CR, LF and CRLF line endings.
- **Readable lines but no parsed mass:** copy the raw log for troubleshooting.
  Ordinary mass lines and documented `Net:` mass fields, decimal comma and
  SOH/EOT form boundaries are supported. Gross/Tare/ID lines are not silently
  substituted for the net result.

**USB ready signal (DTR)** defaults on for the raw balance connection, following
normal USB serial readiness conventions. It can be changed in the diagnostic
window after disconnecting. ESP32 reset/control-line behavior is unchanged.
This is a compatibility change, not proof that DTR caused this particular
scale's missing data.

For a continuous output setup, the balance menu can use `CONTIN ON`,
`STABLE OFF`, `PERIOD OFF` and `SINGLE`. The app's polling option also supports
requesting readings without relying on continuous output. Close the diagnostic
window before reconnecting the scale in the main app.

These software changes were checked with fake serial data. A live COM6 test is
still needed to confirm that this physical balance responds.

Sources: [official Nimbus manual, sections 11 and 13.3](https://adamequipment.com.cn/media/docs/manuals/NBLe_i_UM_EN.pdf)
and [pySerial control-line documentation](https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.dtr).

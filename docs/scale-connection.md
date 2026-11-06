# Connect the Adam Nimbus scale over USB

On 5 November 2026, the user reported that the **Adam Nimbus NBL 8201e**
was reading in the app with default settings. The scale connects directly to
the lab PC through its square **USB-B I/O** port. Windows previously listed it
as **COM6**, separate from the ESP32's port.

## Connect in the app

1. Open **Connections and settings** to check the balance connection.
2. Under **Balance**, select the scale's current COM port. The app defaults to
   **9600 baud** and **NONE · 8N1**. If the scale uses different settings,
   match its baud and parity in the app. **EVEN** uses **7E1** and **ODD** uses
   **7O1**.
3. Leave **Request weight every second** checked and click **Connect**.
   The app requests a weight when a fresh weight is not already streaming.
4. Watch **Balance mass** on Dashboard. **Request reading** also sends a manual
   read-only Print request. No tare, zero, reset or settings command is sent.

Automatic/manual requests share a one-second rate limit and wait until the
port actually opens. Sending a request does not count as receiving a weight.
The displayed mass and connection evidence still require actual valid data.

## If no weight arrives

Open **Test scale / raw data** in the Balance section. This closes the main
scale connection first so two windows cannot compete for the port. Select the same
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

The main app leaves the USB ready signal (**DTR**) off for the lab scale on
**COM6**. In the lab test, the display stayed steady and a Print request
returned a valid weight with DTR off. If using **Test scale / raw data** on
COM6, uncheck **USB ready signal (DTR)** before connecting.

For a continuous output setup, the balance menu can use `CONTIN ON`,
`STABLE OFF`, `PERIOD OFF` and `SINGLE`. The app's polling option also supports
requesting readings without relying on continuous output. Close the diagnostic
window before reconnecting the scale in the main app.

Sources: [official Nimbus manual, sections 11 and 13.3](https://adamequipment.com.cn/media/docs/manuals/NBLe_i_UM_EN.pdf)
and [pySerial control-line documentation](https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.dtr).

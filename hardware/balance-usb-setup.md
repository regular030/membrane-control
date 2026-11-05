# Connect the Adam Nimbus NBL 8201e balance

On 5 November 2026, the user reported that the **Adam Nimbus NBL 8201e**
was reading in the app with default settings. Its square **USB-B I/O** port
connects directly to the computer with a USB data cable. Windows previously
listed the scale as **COM6**. The scale and the ESP32 each use their own COM port.

The app supports automatic Print requests, 8N1, 7E1 and 7O1 serial formats,
and a diagnostic window that shows received bytes. See the
[connection and diagnostic steps](../docs/scale-connection.md).

## Choose one connection path

| Path | Cable and driver |
| --- | --- |
| Current | Balance USB-B **I/O** → USB data cable → computer USB. Use [Adam's Nimbus driver](https://adamequipment.com/support/software-downloads.html) if required. |
| Previous, alternative only | Balance DB9 RS-232 → green USB-to-RS232 adapter → computer USB. This adapter was not detected on the lab PC. Its chipset/driver remains unidentified; do not select it as the current connection. |

Use one path at a time. The balance's USB-A **Display** socket is for the remote
display, not the computer. The balance retains its own power supply. The
ESP32's 3.3 V TTL UART adapter is not a substitute for an RS-232 interface.

## Set up serial output

1. In Windows **Device Manager → Ports (COM & LPT)**, identify the balance
   connection by unplugging and reconnecting its USB adapter or cable. Do not
   assume a COM number from the photo or select the ESP32's port.
2. Enable serial output on the balance and match its baud rate and parity in
   the app. The app defaults to **9600 baud** and **NONE · 8N1**. It also
   supports **EVEN · 7E1** and **ODD · 7O1**.
3. For continuous readings, select grams and single-line output, with
   stable-only filtering off while collecting liquid. The documented format
   is `123.4 g` followed by carriage return and line feed. Restart the balance
   after changing its serial settings.
   [Nimbus manual, sections 11 and 13.3](https://adamequipment.com.cn/media/docs/manuals/NBLe_i_UM_EN.pdf)
4. Stop any app run, uncheck **Simulation mode**, and open **Connections and
   settings**. Close other programs using the balance's port, then select that
   port in the **Balance** section and click **Connect**. Leave **Request weight
   every second** checked to ask for readings when the scale is not streaming.

## If the balance is absent from the port menu

Opening **Connections and settings** refreshes the port lists. You can also
click **Refresh serial ports** after reconnecting the cable. The scale may be
listed as **USB Serial Port** or by its adapter chipset name rather than Adam
or Nimbus. Refreshing does not connect either device automatically.

If Device Manager shows only the ESP32's COM port, the scale's connection is not
yet available to the app. With the current USB-B path, check the balance is
powered, the data cable is in the square **I/O** socket, and the Nimbus driver
has been installed. Look under **Other devices** for a warning. Open its
**Properties > Details > Hardware Ids** and record the `USB\VID_...&PID_...`
identifier to identify the device/driver. Try another USB data cable or computer
USB port, and compare Device Manager before and after unplugging the scale.

Do not install a guessed CP210x driver merely because that is the ESP32's
adapter. The app cannot create a COM port for hardware Windows has not exposed.

## Confirm readings

Put a known weight on the pan and confirm that **Balance mass** on the
Dashboard matches the scale. Click **Request reading** to send one Print
request. With polling enabled, the app sends at most one request per second
when fresh readings are absent.

The app marks weight data stale after **3 seconds** without a valid reading.
If the mass stays blank or goes stale, use **Test scale / raw data** to check
whether the scale is sending data. [Scale connection and diagnostics](../docs/scale-connection.md#if-no-weight-arrives)

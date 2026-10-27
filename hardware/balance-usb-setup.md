# Connect the Adam Nimbus NBL 8201e balance

Current connection, confirmed by the user on 26 October 2026:
**balance USB-B I/O -> USB data cable -> computer USB**. Use the Nimbus native-USB
driver if required. The user now confirms that Windows exposes a second COM
port on this USB-B connection. The user reports that the port appears but no
weight arrives. The user now reports **COM6 at 9600 baud**, with a changing
physical display but no app weight. The model is **Adam Nimbus NBL 8201e**.
The scale connects independently of the ESP32's USB-to-UART adapter, with a
different COM port for each device.

App 0.1.15 adds automatic Print requests, matching8N1/7E1/7O1 options, raw
CR/LF framing and actual byte diagnostics. Raw balance USB readiness (DTR) is
enabled independently of ESP32 reset lines. See the current
[COM6 connection and diagnostic steps](../docs/scale-connection.md).

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
2. On the balance, enable its serial interface. Use **9600 baud, NONE parity**
   for the current app's **8 data bits, no parity, 1 stop bit (8N1)** connection.
   These are recommended matching settings, not settings confirmed by a photo.
3. Select grams and continuous single-line output, with stable-only filtering
   off while collecting liquid. The documented format is `123.4 g` followed by
   carriage return and line feed. Restart the balance after changing its serial
   settings, as required by the [Nimbus manual, sections 11 and 13.3](https://adamequipment.com.cn/media/docs/manuals/NBLe_i_UM_EN.pdf).
4. Stop any app run, uncheck **Simulation mode**, and open **Connections and
   settings**. Refresh the ports, select the balance's COM port and **9600** in
   the **Balance** section, then click **Connect**. Close other programs using
   that port first.

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

The app waits for incoming weights; it does not configure the balance or send
print/poll commands. A detected USB adapter alone does not confirm balance data.
Confirm that a known change on the pan changes the displayed mass.

Without a valid weight for more than **3 seconds**, the app marks weight data
stale. Stable-only output, manual-print mode or a long periodic-output interval
can cause this even when the cable is connected. Use continuous output for the
current app. Its baud selection must match the balance; the app's serial format
is fixed at 8N1. The documented simple mass stream has no per-reading stability flag.
